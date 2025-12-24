"""
Test Image-to-Video với tokens
==============================
Cách dùng:
  1. Tạo file config.json với nội dung:
     {
       "project_id": "...",
       "bearer_token": "ya29...",
       "proxy_token": "eyJhbG..."
     }

  2. Chạy: python test_i2v_now.py
"""
import json
import time
import requests
from pathlib import Path

# =============================================================================
# LOAD CONFIG
# =============================================================================
CONFIG_FILE = Path("config.json")

if not CONFIG_FILE.exists():
    print("❌ Cần tạo file config.json với nội dung:")
    print('''
{
  "project_id": "YOUR_PROJECT_ID",
  "bearer_token": "ya29.xxx",
  "proxy_token": "eyJhbG..."
}
''')
    exit(1)

config = json.loads(CONFIG_FILE.read_text())
PROJECT_ID = config.get("project_id", "")
BEARER_TOKEN = config.get("bearer_token", "")
PROXY_TOKEN = config.get("proxy_token", "")

# Prompts
IMAGE_PROMPT = "A cute orange cat sitting in a garden with flowers, 8K photo, studio lighting"
VIDEO_PROMPT = "The cat slowly walks forward, gentle wind blowing its fur, cinematic"

OUTPUT_DIR = Path("./output")
# =============================================================================

PROXY_BASE = "https://flow-api.nanoai.pics/api/fix"
GOOGLE_BASE = "https://aisandbox-pa.googleapis.com"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def headers():
    return {
        "Authorization": f"Bearer {PROXY_TOKEN}",
        "Content-Type": "application/json"
    }


def poll_task(task_id, max_attempts=120, interval=3):
    """Poll task status."""
    url = f"{PROXY_BASE}/task-status?taskId={task_id}"

    for i in range(max_attempts):
        try:
            r = requests.get(url, headers=headers(), timeout=30)
            data = r.json()

            # Log every few attempts
            if i % 3 == 0:
                status_info = json.dumps(data)[:200]
                log(f"Poll #{i+1}: {status_info}...")

            if data.get("success"):
                result = data.get("result", {})

                # Check for Google API error
                if "error" in result:
                    err = result["error"]
                    if isinstance(err, dict):
                        err = err.get("message", str(err))
                    return False, None, str(err)

                # Success conditions
                if result.get("success") == True:
                    return True, result, None
                if "media" in result or "videos" in result or "operations" in result:
                    return True, result, None

            # Check if failed
            if data.get("code") == "failed":
                return False, None, data.get("message", "Task failed")

            time.sleep(interval)

        except Exception as e:
            log(f"Poll error: {e}")
            time.sleep(interval)

    return False, None, "Timeout after polling"


def step1_create_image():
    """Step 1: Tạo ảnh để lấy media_name."""
    log("=" * 60)
    log("STEP 1: TẠO ẢNH")
    log("=" * 60)
    log(f"Prompt: {IMAGE_PROMPT}")

    session_id = f";{int(time.time() * 1000)}"

    body_json = {
        "clientContext": {
            "sessionId": session_id,
            "projectId": PROJECT_ID,
            "tool": "PINHOLE"
        },
        "requests": [{
            "clientContext": {
                "sessionId": session_id,
                "projectId": PROJECT_ID,
                "tool": "PINHOLE"
            },
            "seed": 123456,
            "imageModelName": "GEM_PIX_2",
            "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "prompt": IMAGE_PROMPT,
            "imageInputs": []
        }]
    }

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": f"{GOOGLE_BASE}/v1/projects/{PROJECT_ID}/flowMedia:batchGenerateImages"
    }

    log(f"Gọi proxy API...")

    try:
        r = requests.post(
            f"{PROXY_BASE}/create-image-veo3",
            headers=headers(),
            json=payload,
            timeout=30
        )
        data = r.json()
        log(f"Response: {json.dumps(data)}")

        if not data.get("success"):
            log(f"❌ Lỗi: {data.get('error')}")
            return None

        task_id = data.get("taskId")
        log(f"Task ID: {task_id}")
        log("Đang chờ kết quả...")

        ok, result, err = poll_task(task_id, max_attempts=60, interval=2)

        if not ok:
            log(f"❌ Lỗi: {err}")
            return None

        # Extract media_name
        log("\n--- KẾT QUẢ ---")
        media_name = None

        if "media" in result and result["media"]:
            media = result["media"][0]
            media_name = media.get("name")
            log(f"Media keys: {list(media.keys())}")

            # Try nested structure
            if not media_name and "image" in media:
                img = media["image"]
                if "generatedImage" in img:
                    gen = img["generatedImage"]
                    media_name = gen.get("name")
                    log(f"GeneratedImage keys: {list(gen.keys())}")

            # Download image
            if "image" in media:
                img_data = media["image"].get("generatedImage", {})
                img_url = img_data.get("fifeUrl")
                if img_url:
                    OUTPUT_DIR.mkdir(exist_ok=True)
                    img_path = OUTPUT_DIR / f"source_img_{int(time.time())}.png"
                    log(f"Downloading image to {img_path}...")
                    img_r = requests.get(img_url, timeout=60)
                    if img_r.status_code == 200:
                        img_path.write_bytes(img_r.content)
                        log(f"✅ Image saved: {img_path}")

        if media_name:
            log(f"\n✅ THÀNH CÔNG!")
            log(f"media_name = {media_name}")
            return media_name
        else:
            log(f"\n❌ Không tìm thấy media_name")
            log(f"Full result: {json.dumps(result, indent=2)[:1000]}")
            return None

    except Exception as e:
        log(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def step2_create_video(media_name):
    """Step 2: Tạo video từ ảnh."""
    log("")
    log("=" * 60)
    log("STEP 2: TẠO VIDEO TỪ ẢNH (I2V)")
    log("=" * 60)
    log(f"Media name: {media_name[:80]}...")
    log(f"Video prompt: {VIDEO_PROMPT}")

    session_id = f";{int(time.time() * 1000)}"

    # Body cho Image-to-Video
    body_json = {
        "clientContext": {
            "sessionId": session_id,
            "projectId": PROJECT_ID,
            "tool": "PINHOLE",
            "userPaygateTier": "PAYGATE_TIER_TWO"
        },
        "requests": [{
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "seed": 123456,
            "textInput": {
                "prompt": VIDEO_PROMPT
            },
            "videoModelKey": "veo_3_0_r2v_fast_ultra",  # I2V model
            "referenceImages": [{
                "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                "mediaId": media_name
            }],
            "metadata": {
                "sceneId": f"test-i2v-{int(time.time())}"
            }
        }]
    }

    # I2V endpoint
    flow_url = f"{GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": flow_url
    }

    log(f"Endpoint: {flow_url}")
    log("Gọi proxy API...")

    try:
        r = requests.post(
            f"{PROXY_BASE}/create-video-veo3",
            headers=headers(),
            json=payload,
            timeout=30
        )
        data = r.json()
        log(f"Response: {json.dumps(data)}")

        if not data.get("success"):
            log(f"❌ Lỗi: {data.get('error')}")
            return None

        task_id = data.get("taskId")
        log(f"Task ID: {task_id}")
        log("Đang chờ video (2-5 phút)...")

        ok, result, err = poll_task(task_id, max_attempts=120, interval=5)

        if not ok:
            log(f"❌ Lỗi: {err}")
            return None

        # Extract video URL
        log("\n--- KẾT QUẢ VIDEO ---")
        video_url = None

        if "operations" in result:
            ops = result["operations"]
            if ops:
                op = ops[0]
                status = op.get("status", "")
                log(f"Status: {status}")

                if "SUCCEEDED" in status or "COMPLETE" in status:
                    if op.get("media"):
                        video_info = op["media"][0].get("video", {})
                        video_url = video_info.get("url")

        # Fallback formats
        if not video_url:
            if "videos" in result and result["videos"]:
                video_url = result["videos"][0].get("url")
            elif "videoUrl" in result:
                video_url = result["videoUrl"]

        if video_url:
            log(f"\n✅ Video URL: {video_url[:100]}...")

            # Download
            OUTPUT_DIR.mkdir(exist_ok=True)
            video_path = OUTPUT_DIR / f"i2v_video_{int(time.time())}.mp4"
            log(f"Downloading to {video_path}...")

            vid_r = requests.get(video_url, timeout=120, stream=True)
            if vid_r.status_code == 200:
                with open(video_path, "wb") as f:
                    for chunk in vid_r.iter_content(8192):
                        f.write(chunk)
                log(f"✅ Video saved: {video_path}")
                return str(video_path)
            else:
                log(f"❌ Download failed: {vid_r.status_code}")
                return None
        else:
            log(f"\n❌ Không tìm thấy video URL")
            log(f"Full result: {json.dumps(result, indent=2)[:1500]}")
            return None

    except Exception as e:
        log(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("=" * 60)
    print("TEST IMAGE-TO-VIDEO")
    print("=" * 60)
    print(f"Project ID: {PROJECT_ID}")
    print(f"Bearer Token: {BEARER_TOKEN[:50]}...")
    print(f"Proxy Token: {PROXY_TOKEN[:50]}...")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Step 1: Tạo ảnh
    media_name = step1_create_image()

    if not media_name:
        log("\n❌ FAILED: Không lấy được media_name từ ảnh")
        return

    # Step 2: Tạo video từ ảnh
    video_path = step2_create_video(media_name)

    if video_path:
        print("\n" + "=" * 60)
        print("✅ HOÀN THÀNH!")
        print(f"Video: {video_path}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ THẤT BẠI")
        print("=" * 60)


if __name__ == "__main__":
    main()
