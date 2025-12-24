"""
Test I2V với format chính xác từ Chrome DevTools
"""
import json
import time
import requests
from pathlib import Path

# Load config
config = json.loads(Path("config.json").read_text())
PROJECT_ID = config["project_id"]
BEARER_TOKEN = config["bearer_token"]
PROXY_TOKEN = config["proxy_token"]

PROXY_BASE = "https://flow-api.nanoai.pics/api/fix"
GOOGLE_BASE = "https://aisandbox-pa.googleapis.com"
OUTPUT_DIR = Path("./output")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def headers():
    return {
        "Authorization": f"Bearer {PROXY_TOKEN}",
        "Content-Type": "application/json"
    }


def poll_task(task_id, max_attempts=120, interval=5):
    """Poll task status."""
    url = f"{PROXY_BASE}/task-status?taskId={task_id}"

    for i in range(max_attempts):
        try:
            r = requests.get(url, headers=headers(), timeout=30)
            data = r.json()

            if i % 3 == 0:
                log(f"Poll #{i+1}: {json.dumps(data)[:200]}...")

            if data.get("success"):
                result = data.get("result", {})

                if "error" in result:
                    return False, None, str(result["error"])

                # Check operations
                ops = result.get("operations", [])
                if ops:
                    op = ops[0]
                    status = op.get("status", "")
                    log(f"Status: {status}")

                    if "SUCCEEDED" in status or "SUCCESSFUL" in status:
                        # Extract video URL
                        video_url = None
                        media = op.get("media", [])
                        if media:
                            video_url = media[0].get("video", {}).get("fifeUrl")
                        if not video_url:
                            video_url = op.get("metadata", {}).get("video", {}).get("fifeUrl")
                        if video_url:
                            result["_video_url"] = video_url
                        return True, result, None

                    if "FAILED" in status:
                        return False, result, f"Failed: {status}"

                if "media" in result:
                    return True, result, None

            time.sleep(interval)

        except Exception as e:
            log(f"Poll error: {e}")
            time.sleep(interval)

    return False, None, "Timeout"


def create_image():
    """Tạo ảnh để lấy mediaId."""
    log("=" * 60)
    log("STEP 1: TẠO ẢNH")
    log("=" * 60)

    session_id = f";{int(time.time() * 1000)}"

    # Format chính xác từ Chrome
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
            "prompt": "A cute orange cat in a garden, studio lighting, 8K",
            "imageInputs": []
        }]
    }

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": f"{GOOGLE_BASE}/v1/projects/{PROJECT_ID}/flowMedia:batchGenerateImages"
    }

    log("Calling proxy...")
    r = requests.post(f"{PROXY_BASE}/create-image-veo3", headers=headers(), json=payload, timeout=30)
    data = r.json()
    log(f"Response: {json.dumps(data)}")

    if not data.get("success"):
        log(f"❌ Error: {data.get('error')}")
        return None

    task_id = data.get("taskId")
    log(f"Task ID: {task_id}")

    ok, result, err = poll_task(task_id, max_attempts=60, interval=2)
    if not ok:
        log(f"❌ Error: {err}")
        return None

    # Extract mediaId (name field)
    media_id = None
    if "media" in result and result["media"]:
        media = result["media"][0]
        media_id = media.get("name")

        # Download image
        if "image" in media:
            img_url = media["image"].get("generatedImage", {}).get("fifeUrl")
            if img_url:
                OUTPUT_DIR.mkdir(exist_ok=True)
                img_path = OUTPUT_DIR / f"source_{int(time.time())}.png"
                img_r = requests.get(img_url, timeout=60)
                if img_r.status_code == 200:
                    img_path.write_bytes(img_r.content)
                    log(f"✅ Image saved: {img_path}")

    if media_id:
        log(f"✅ mediaId = {media_id}")
        return media_id
    else:
        log("❌ No mediaId found")
        log(f"Result: {json.dumps(result, indent=2)[:1000]}")
        return None


def create_video(media_id):
    """Tạo video từ ảnh - format chính xác từ Chrome."""
    log("")
    log("=" * 60)
    log("STEP 2: TẠO VIDEO (I2V)")
    log("=" * 60)
    log(f"mediaId: {media_id}")

    session_id = f";{int(time.time() * 1000)}"
    scene_id = f"scene-{int(time.time())}"

    # FORMAT CHÍNH XÁC TỪ CHROME DEVTOOLS
    body_json = {
        "clientContext": {
            "projectId": PROJECT_ID,
            "recaptchaToken": "",  # Proxy sẽ xử lý
            "sessionId": session_id,
            "tool": "PINHOLE",
            "userPaygateTier": "PAYGATE_TIER_TWO"
        },
        "requests": [{
            "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "metadata": {
                "sceneId": scene_id
            },
            "referenceImages": [{
                "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                "mediaId": media_id
            }],
            "seed": 8465,
            "textInput": {
                "prompt": "The cat walks forward slowly, gentle wind, cinematic"
            },
            "videoModelKey": "veo_3_0_r2v_fast_ultra"
        }]
    }

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": f"{GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"
    }

    log(f"Scene ID: {scene_id}")
    log("Calling proxy...")
    log(f"Payload: {json.dumps(body_json, indent=2)}")

    r = requests.post(f"{PROXY_BASE}/create-video-veo3", headers=headers(), json=payload, timeout=30)
    data = r.json()
    log(f"Response: {json.dumps(data)}")

    if not data.get("success"):
        log(f"❌ Error: {data.get('error')}")
        return None

    task_id = data.get("taskId")
    log(f"Task ID: {task_id}")
    log("Waiting for video (2-5 min)...")

    ok, result, err = poll_task(task_id, max_attempts=120, interval=5)
    if not ok:
        log(f"❌ Error: {err}")
        return None

    # Extract video URL
    video_url = result.get("_video_url")

    if not video_url:
        ops = result.get("operations", [])
        if ops:
            op = ops[0]
            media = op.get("media", [])
            if media:
                video_url = media[0].get("video", {}).get("fifeUrl")
            if not video_url:
                video_url = op.get("metadata", {}).get("video", {}).get("fifeUrl")

    if video_url:
        log(f"✅ Video URL: {video_url[:80]}...")
        OUTPUT_DIR.mkdir(exist_ok=True)
        video_path = OUTPUT_DIR / f"i2v_{int(time.time())}.mp4"
        log(f"Downloading...")
        vid_r = requests.get(video_url, timeout=120, stream=True)
        if vid_r.status_code == 200:
            with open(video_path, "wb") as f:
                for chunk in vid_r.iter_content(8192):
                    f.write(chunk)
            log(f"✅ Video saved: {video_path}")
            return str(video_path)
    else:
        log("❌ No video URL")
        log(f"Result: {json.dumps(result, indent=2)[:1500]}")

    return None


def main():
    print("=" * 60)
    print("TEST I2V - Chrome Format")
    print("=" * 60)
    print(f"Project: {PROJECT_ID}")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)

    # Step 1
    media_id = create_image()
    if not media_id:
        return

    # Step 2
    video_path = create_video(media_id)

    if video_path:
        print("\n" + "=" * 60)
        print(f"✅ DONE! Video: {video_path}")
        print("=" * 60)
    else:
        print("\n❌ FAILED")


if __name__ == "__main__":
    main()
