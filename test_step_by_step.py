"""
Step-by-Step Test for Image-to-Video
=====================================
Test từng bước riêng biệt để debug dễ hơn.

Chạy:
  python test_step_by_step.py image    # Test tạo ảnh để lấy media_name
  python test_step_by_step.py video    # Test tạo video từ media_name
  python test_step_by_step.py full     # Test full flow
"""
import json
import time
import sys
import requests
from pathlib import Path

# =============================================================================
# CONFIG
# =============================================================================
BEARER_TOKEN = "ya29.YOUR_TOKEN"  # Google token từ Chrome
PROJECT_ID = "a82d45ed-xxxx"       # Project ID
PROXY_TOKEN = "YOUR_PROXY_TOKEN"   # Token nanoai.pics

# Điền media_name vào đây sau khi chạy test image
MEDIA_NAME = ""

# Prompts
IMAGE_PROMPT = "A cute orange cat sitting in a garden, 8K photo, studio lighting"
VIDEO_PROMPT = "The cat slowly walks forward, gentle wind, cinematic lighting"

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


def poll(task_id, max_attempts=120, interval=3):
    """Poll task until complete."""
    url = f"{PROXY_BASE}/task-status?taskId={task_id}"

    for i in range(max_attempts):
        try:
            r = requests.get(url, headers=headers(), timeout=30)
            data = r.json()

            if i % 5 == 0:  # Log every 5 attempts
                log(f"Poll #{i+1}: {json.dumps(data)[:150]}...")

            if data.get("success"):
                result = data.get("result", {})

                if "error" in result:
                    return False, None, str(result["error"])

                # Check success conditions
                if result.get("success") == True:
                    return True, result, None
                if "media" in result or "videos" in result or "operations" in result:
                    return True, result, None

            time.sleep(interval)

        except Exception as e:
            log(f"Poll error: {e}")
            time.sleep(interval)

    return False, None, "Timeout"


def test_create_image():
    """Test: Tạo ảnh để lấy media_name."""
    print("\n" + "=" * 60)
    print("TEST: CREATE IMAGE")
    print("=" * 60)

    body = {
        "clientContext": {
            "sessionId": f";{int(time.time()*1000)}",
            "projectId": PROJECT_ID,
            "tool": "PINHOLE"
        },
        "requests": [{
            "clientContext": {
                "sessionId": f";{int(time.time()*1000)}",
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
        "body_json": body,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": f"{GOOGLE_BASE}/v1/projects/{PROJECT_ID}/flowMedia:batchGenerateImages"
    }

    log(f"Image prompt: {IMAGE_PROMPT}")
    log("Sending request...")

    r = requests.post(f"{PROXY_BASE}/create-image-veo3", headers=headers(), json=payload, timeout=30)
    data = r.json()
    log(f"Response: {json.dumps(data)}")

    if not data.get("success"):
        log(f"❌ Failed: {data.get('error')}")
        return

    task_id = data.get("taskId")
    log(f"Task ID: {task_id}")
    log("Polling...")

    ok, result, err = poll(task_id, max_attempts=60, interval=2)

    if not ok:
        log(f"❌ Failed: {err}")
        return

    # Extract media_name
    log("\n--- RESULT ---")
    log(f"Keys: {list(result.keys())}")

    media_name = None
    if "media" in result and result["media"]:
        media = result["media"][0]
        log(f"Media keys: {list(media.keys())}")
        media_name = media.get("name")

        if "image" in media:
            img = media["image"]
            log(f"Image keys: {list(img.keys())}")
            if "generatedImage" in img:
                gen = img["generatedImage"]
                log(f"GeneratedImage keys: {list(gen.keys())}")
                if not media_name:
                    media_name = gen.get("name")

    if media_name:
        log(f"\n✅ SUCCESS!")
        log(f"media_name = \"{media_name}\"")
        log("\n>>> Copy dòng trên vào MEDIA_NAME trong script rồi chạy 'python test_step_by_step.py video'")
    else:
        log("\n❌ No media_name found")
        log(f"Full result: {json.dumps(result, indent=2)}")


def test_create_video():
    """Test: Tạo video từ media_name."""
    print("\n" + "=" * 60)
    print("TEST: CREATE VIDEO FROM IMAGE")
    print("=" * 60)

    if not MEDIA_NAME:
        print("❌ MEDIA_NAME is empty!")
        print("   Run 'python test_step_by_step.py image' first to get media_name")
        return

    log(f"Media name: {MEDIA_NAME[:60]}...")
    log(f"Video prompt: {VIDEO_PROMPT}")

    # Body cho Image-to-Video
    body = {
        "clientContext": {
            "sessionId": f";{int(time.time()*1000)}",
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
                "mediaId": MEDIA_NAME
            }],
            "metadata": {
                "sceneId": f"test-{int(time.time())}"
            }
        }]
    }

    # I2V endpoint
    flow_url = f"{GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"

    payload = {
        "body_json": body,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": flow_url
    }

    log(f"Endpoint: {flow_url}")
    log("Sending request...")

    r = requests.post(f"{PROXY_BASE}/create-video-veo3", headers=headers(), json=payload, timeout=30)
    data = r.json()
    log(f"Response: {json.dumps(data)}")

    if not data.get("success"):
        log(f"❌ Failed: {data.get('error')}")
        return

    task_id = data.get("taskId")
    log(f"Task ID: {task_id}")
    log("Polling (video takes 2-5 minutes)...")

    ok, result, err = poll(task_id, max_attempts=120, interval=5)

    if not ok:
        log(f"❌ Failed: {err}")
        return

    # Extract video URL
    log("\n--- RESULT ---")
    log(f"Keys: {list(result.keys())}")

    video_url = None

    if "operations" in result:
        ops = result["operations"]
        if ops:
            op = ops[0]
            log(f"Operation status: {op.get('status')}")
            log(f"Operation keys: {list(op.keys())}")

            if op.get("media"):
                video_info = op["media"][0].get("video", {})
                video_url = video_info.get("url")

    if not video_url:
        if "videos" in result and result["videos"]:
            video_url = result["videos"][0].get("url")
        elif "videoUrl" in result:
            video_url = result["videoUrl"]

    if video_url:
        log(f"\n✅ SUCCESS!")
        log(f"Video URL: {video_url}")

        # Download
        OUTPUT_DIR.mkdir(exist_ok=True)
        path = OUTPUT_DIR / f"i2v_{int(time.time())}.mp4"
        log(f"Downloading to {path}...")
        r = requests.get(video_url, timeout=120)
        if r.status_code == 200:
            path.write_bytes(r.content)
            log(f"✅ Saved: {path}")
        else:
            log(f"❌ Download failed: {r.status_code}")
    else:
        log("\n❌ No video URL found")
        log(f"Full result: {json.dumps(result, indent=2)[:2000]}")


def test_text_to_video():
    """Test: Text-to-Video (không cần ảnh)."""
    print("\n" + "=" * 60)
    print("TEST: TEXT TO VIDEO (T2V)")
    print("=" * 60)

    log(f"Video prompt: {VIDEO_PROMPT}")

    body = {
        "clientContext": {
            "sessionId": f";{int(time.time()*1000)}",
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
            "videoModelKey": "veo_3_1_t2v_fast_ultra",  # T2V model
            "metadata": {
                "sceneId": f"test-{int(time.time())}"
            }
        }]
    }

    # T2V endpoint
    flow_url = f"{GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoText"

    payload = {
        "body_json": body,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": flow_url
    }

    log(f"Endpoint: {flow_url}")
    log("Sending request...")

    r = requests.post(f"{PROXY_BASE}/create-video-veo3", headers=headers(), json=payload, timeout=30)
    data = r.json()
    log(f"Response: {json.dumps(data)}")

    if not data.get("success"):
        log(f"❌ Failed: {data.get('error')}")
        return

    task_id = data.get("taskId")
    log(f"Task ID: {task_id}")
    log("Polling (video takes 2-5 minutes)...")

    ok, result, err = poll(task_id, max_attempts=120, interval=5)

    if not ok:
        log(f"❌ Failed: {err}")
        log(f"Result: {result}")
        return

    # Extract video URL
    log("\n--- RESULT ---")
    video_url = None

    if "operations" in result:
        ops = result["operations"]
        if ops:
            op = ops[0]
            log(f"Status: {op.get('status')}")
            if op.get("media"):
                video_url = op["media"][0].get("video", {}).get("url")

    if video_url:
        log(f"\n✅ Video URL: {video_url}")
        OUTPUT_DIR.mkdir(exist_ok=True)
        path = OUTPUT_DIR / f"t2v_{int(time.time())}.mp4"
        r = requests.get(video_url, timeout=120)
        if r.status_code == 200:
            path.write_bytes(r.content)
            log(f"✅ Saved: {path}")
    else:
        log("\n❌ No video URL")
        log(f"Result: {json.dumps(result, indent=2)[:1500]}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_step_by_step.py image   - Test tạo ảnh lấy media_name")
        print("  python test_step_by_step.py video   - Test tạo video từ media_name")
        print("  python test_step_by_step.py t2v     - Test text-to-video (không cần ảnh)")
        print("  python test_step_by_step.py full    - Test full flow (ảnh -> video)")
        return

    # Check config
    if "YOUR" in BEARER_TOKEN or "YOUR" in PROXY_TOKEN:
        print("❌ Please configure BEARER_TOKEN and PROXY_TOKEN first!")
        return

    cmd = sys.argv[1].lower()

    if cmd == "image":
        test_create_image()
    elif cmd == "video":
        test_create_video()
    elif cmd == "t2v":
        test_text_to_video()
    elif cmd == "full":
        test_create_image()
        print("\n" + "=" * 60)
        print("Waiting 5 seconds before video step...")
        time.sleep(5)
        # Note: You need to manually copy media_name to MEDIA_NAME variable
        print("❌ For full test, please copy media_name from image step to MEDIA_NAME variable")
        print("   Then run: python test_step_by_step.py video")
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
