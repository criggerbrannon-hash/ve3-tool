"""
Simple Test: Image-to-Video via Proxy API
==========================================
Test tạo video từ ảnh (Image-to-Video) qua nanoai.pics proxy.

Flow:
1. Tạo ảnh trước để lấy media_name (hoặc dùng media_name có sẵn)
2. Dùng media_name để tạo video từ ảnh
"""
import json
import time
import requests
from pathlib import Path

# =============================================================================
# CONFIG - THAY ĐỔI CÁC GIÁ TRỊ NÀY
# =============================================================================
BEARER_TOKEN = "ya29.YOUR_GOOGLE_TOKEN_HERE"  # Token Google từ Chrome DevTools
PROJECT_ID = "a82d45ed-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # Project ID
PROXY_TOKEN = "YOUR_NANOAI_PROXY_TOKEN"  # Token từ nanoai.pics

# Nếu đã có media_name từ ảnh trước đó, điền vào đây để skip bước tạo ảnh
EXISTING_MEDIA_NAME = ""  # Ví dụ: "projects/xxx/locations/xxx/flowMedia/xxx"

# Video prompt
VIDEO_PROMPT = "The cat slowly walks forward, gentle breeze moving its fur, cinematic"

# Image prompt (chỉ dùng nếu chưa có media_name)
IMAGE_PROMPT = "A beautiful orange cat sitting peacefully, studio lighting, 8K photo"

OUTPUT_DIR = Path("./output")
# =============================================================================

# API URLs
PROXY_BASE = "https://flow-api.nanoai.pics/api/fix"
GOOGLE_BASE = "https://aisandbox-pa.googleapis.com"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def create_proxy_headers():
    """Create headers for proxy API."""
    return {
        "Authorization": f"Bearer {PROXY_TOKEN}",
        "Content-Type": "application/json"
    }


def poll_task(task_id, headers, max_attempts=120, interval=3):
    """Poll task status until complete."""
    url = f"{PROXY_BASE}/task-status?taskId={task_id}"

    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            result = resp.json()

            log(f"Poll {attempt+1}: {json.dumps(result)[:200]}")

            if result.get("success"):
                task_result = result.get("result", {})

                # Check for error
                if "error" in task_result:
                    error = task_result["error"]
                    if isinstance(error, dict):
                        error = error.get("message", str(error))
                    return False, None, str(error)

                # Check for success flag
                if task_result.get("success") == True:
                    return True, task_result, None

                # Check for media/videos directly
                if "media" in task_result or "videos" in task_result or "operations" in task_result:
                    return True, task_result, None

            time.sleep(interval)

        except Exception as e:
            log(f"Poll error: {e}")
            time.sleep(interval)

    return False, None, "Timeout"


def step1_generate_image():
    """Step 1: Generate image to get media_name."""
    log("=" * 60)
    log("STEP 1: GENERATE IMAGE")
    log("=" * 60)

    headers = create_proxy_headers()

    # Build image request
    body_json = {
        "clientContext": {
            "sessionId": f";{int(time.time() * 1000)}",
            "projectId": PROJECT_ID,
            "tool": "PINHOLE"
        },
        "requests": [{
            "clientContext": {
                "sessionId": f";{int(time.time() * 1000)}",
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

    log(f"Creating image task...")
    log(f"Prompt: {IMAGE_PROMPT[:50]}...")

    try:
        resp = requests.post(
            f"{PROXY_BASE}/create-image-veo3",
            headers=headers,
            json=payload,
            timeout=30
        )

        result = resp.json()
        log(f"Create response: {json.dumps(result)[:300]}")

        if not result.get("success"):
            log(f"❌ Failed to create image task: {result.get('error')}")
            return None

        task_id = result.get("taskId")
        if not task_id:
            log("❌ No taskId in response")
            return None

        log(f"Task created: {task_id}")
        log("Polling for result...")

        success, task_result, error = poll_task(task_id, headers)

        if not success:
            log(f"❌ Image generation failed: {error}")
            return None

        # Extract media_name from response
        media_name = None

        # Try different response formats
        if "media" in task_result:
            media_list = task_result["media"]
            if media_list:
                first_media = media_list[0]
                media_name = first_media.get("name")

                # Debug: show all keys
                log(f"Media item keys: {list(first_media.keys())}")

                if "image" in first_media:
                    img_wrapper = first_media["image"]
                    log(f"  image keys: {list(img_wrapper.keys())}")

                    if "generatedImage" in img_wrapper:
                        gen_img = img_wrapper["generatedImage"]
                        log(f"  generatedImage keys: {list(gen_img.keys())}")

                        # Try to get media name from different locations
                        if not media_name:
                            media_name = gen_img.get("name") or gen_img.get("mediaName")

        if media_name:
            log(f"✅ Got media_name: {media_name}")
            return media_name
        else:
            log("❌ No media_name found in response")
            log(f"Full response: {json.dumps(task_result)[:500]}")
            return None

    except Exception as e:
        log(f"❌ Error: {e}")
        return None


def step2_generate_video(media_name):
    """Step 2: Generate video from image using media_name."""
    log("")
    log("=" * 60)
    log("STEP 2: GENERATE VIDEO FROM IMAGE")
    log("=" * 60)

    headers = create_proxy_headers()

    # Build video request for Image-to-Video
    # Key: use referenceImages with mediaId
    body_json = {
        "clientContext": {
            "sessionId": f";{int(time.time() * 1000)}",
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
            # KEY: Image-to-Video model
            "videoModelKey": "veo_3_0_r2v_fast_ultra",
            # KEY: Reference image
            "referenceImages": [{
                "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                "mediaId": media_name
            }],
            "metadata": {
                "sceneId": f"test-{int(time.time())}"
            }
        }]
    }

    # KEY: Use batchAsyncGenerateVideoReferenceImages endpoint for I2V
    flow_url = f"{GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"

    payload = {
        "body_json": body_json,
        "flow_auth_token": BEARER_TOKEN,
        "flow_url": flow_url
    }

    log(f"Creating video task (Image-to-Video)...")
    log(f"Reference image: {media_name[:60]}...")
    log(f"Video prompt: {VIDEO_PROMPT[:50]}...")
    log(f"Endpoint: {flow_url}")

    try:
        resp = requests.post(
            f"{PROXY_BASE}/create-video-veo3",
            headers=headers,
            json=payload,
            timeout=30
        )

        result = resp.json()
        log(f"Create response: {json.dumps(result)[:300]}")

        if not result.get("success"):
            log(f"❌ Failed to create video task: {result.get('error')}")
            return None

        task_id = result.get("taskId")
        if not task_id:
            log("❌ No taskId in response")
            return None

        log(f"Task created: {task_id}")
        log("Polling for result (video takes 2-5 minutes)...")

        success, task_result, error = poll_task(task_id, headers, max_attempts=120, interval=5)

        if not success:
            log(f"❌ Video generation failed: {error}")
            return None

        # Extract video URL
        video_url = None

        log(f"Task result keys: {list(task_result.keys())}")

        # Try operations format (from Google API)
        if "operations" in task_result:
            ops = task_result["operations"]
            if ops:
                op = ops[0]
                status = op.get("status", "")
                log(f"Operation status: {status}")

                if "SUCCEEDED" in status or "COMPLETE" in status:
                    media_list = op.get("media", [])
                    if media_list:
                        video_info = media_list[0].get("video", {})
                        video_url = video_info.get("url") or video_info.get("videoUrl")

        # Try direct video/media format
        if not video_url:
            if "videos" in task_result and task_result["videos"]:
                video_url = task_result["videos"][0].get("url")
            elif "media" in task_result and task_result["media"]:
                video_info = task_result["media"][0].get("video", {})
                video_url = video_info.get("url")
            elif "videoUrl" in task_result:
                video_url = task_result["videoUrl"]

        if video_url:
            log(f"✅ Got video URL: {video_url[:80]}...")
            return video_url
        else:
            log("❌ No video URL found")
            log(f"Full result: {json.dumps(task_result)[:1000]}")
            return None

    except Exception as e:
        log(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def download_video(url, output_dir):
    """Download video to local file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"i2v_test_{int(time.time())}.mp4"
    output_path = output_dir / filename

    log(f"Downloading video...")

    try:
        resp = requests.get(url, timeout=120, stream=True)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            log(f"✅ Saved to: {output_path}")
            return output_path
        else:
            log(f"❌ Download failed: {resp.status_code}")
            return None
    except Exception as e:
        log(f"❌ Download error: {e}")
        return None


def main():
    print("=" * 60)
    print("IMAGE-TO-VIDEO TEST")
    print("=" * 60)
    print()

    # Check config
    if "YOUR" in BEARER_TOKEN:
        print("❌ Please set BEARER_TOKEN in the script!")
        print("   Get it from Chrome DevTools when generating image on labs.google/fx")
        return

    if "YOUR" in PROXY_TOKEN:
        print("❌ Please set PROXY_TOKEN in the script!")
        print("   Get it from nanoai.pics")
        return

    media_name = EXISTING_MEDIA_NAME

    # Step 1: Generate image (if no existing media_name)
    if not media_name:
        media_name = step1_generate_image()
        if not media_name:
            log("Failed to get media_name. Exiting.")
            return
    else:
        log(f"Using existing media_name: {media_name[:60]}...")

    # Step 2: Generate video from image
    video_url = step2_generate_video(media_name)
    if not video_url:
        log("Failed to generate video. Exiting.")
        return

    # Step 3: Download video
    download_video(video_url, OUTPUT_DIR)

    print()
    print("=" * 60)
    print("DONE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
