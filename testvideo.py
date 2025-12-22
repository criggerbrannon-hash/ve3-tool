"""
Test Video Generation via Proxy API
Supports both Text-to-Video and Image-to-Video modes
"""
from pathlib import Path
from modules.google_flow_api import GoogleFlowAPI, VideoAspectRatio, VideoModel, ImageAspectRatio

# ============================================================================
# CONFIG - Thay đổi các giá trị này
# ============================================================================
BEARER_TOKEN = "YOUR_BEARER_TOKEN_HERE"  # Lấy từ Chrome DevTools khi tạo ảnh trên Flow
PROJECT_ID = "YOUR_PROJECT_ID_HERE"  # UUID project, ví dụ: a8450355-67a6-4fbd-83f3-d1a04efb2864
PROXY_TOKEN = "YOUR_PROXY_TOKEN_HERE"  # Token từ nanoai.pics

# Test mode: "text2video" hoặc "image2video"
TEST_MODE = "text2video"

# Prompt cho video
VIDEO_PROMPT = "A cute orange cat walking slowly in a beautiful garden with flowers, cinematic lighting, 4K quality"

# Image prompt (cho image2video mode)
IMAGE_PROMPT = "A beautiful orange cat sitting in a garden with colorful flowers, studio lighting, 8K photo"

# Output folder
OUTPUT_DIR = Path("./output")
# ============================================================================


def test_text_to_video(api):
    """Test Text-to-Video generation."""
    print("\n" + "=" * 60)
    print("TEXT-TO-VIDEO TEST")
    print("=" * 60)
    print(f"Prompt: {VIDEO_PROMPT[:50]}...")
    print(f"Aspect: LANDSCAPE (16:9)")
    print(f"Model: VEO3_FAST")
    print()

    success, result, error = api.generate_video(
        prompt=VIDEO_PROMPT,
        aspect_ratio=VideoAspectRatio.LANDSCAPE,
        model=VideoModel.VEO3_FAST
    )

    print()
    print("-" * 40)
    print("RESULT")
    print("-" * 40)
    print(f"Success: {success}")
    print(f"Status: {result.status}")
    print(f"Video URL: {result.video_url}")
    print(f"Operation ID: {result.operation_id}")
    if error:
        print(f"Error: {error}")

    # Download video if successful
    if success and result.video_url:
        print(f"\nDownloading video...")
        video_path = api.download_video(result, OUTPUT_DIR, "test_t2v")
        if video_path:
            print(f"✅ Video saved to: {video_path}")
            print(f"   File size: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("❌ Failed to download video")
    else:
        print(f"\n❌ Video generation failed: {error}")


def test_image_to_video(api):
    """Test Image-to-Video generation."""
    print("\n" + "=" * 60)
    print("IMAGE-TO-VIDEO TEST")
    print("=" * 60)

    # Step 1: Generate image first
    print("\n[Step 1] Generating image first...")
    print(f"Image prompt: {IMAGE_PROMPT[:50]}...")

    success, images, error = api.generate_images(
        prompt=IMAGE_PROMPT,
        aspect_ratio=ImageAspectRatio.LANDSCAPE
    )

    if not success or not images:
        print(f"❌ Image generation failed: {error}")
        return

    image = images[0]
    print(f"\n✅ Image generated!")
    print(f"   Seed: {image.seed}")
    print(f"   URL: {image.url[:80] if image.url else 'N/A'}...")
    print(f"   media_name: {image.media_name[:80] if image.media_name else 'N/A'}...")

    if not image.media_name:
        print("\n❌ No media_name in image response. Cannot proceed with Image-to-Video.")
        print("   The proxy API may not return media_name. Check the full response.")
        return

    # Download image
    print("\n[Step 2] Downloading image...")
    img_path = api.download_image(image, OUTPUT_DIR, "test_i2v_source")
    if img_path:
        print(f"✅ Image saved to: {img_path}")

    # Step 2: Generate video from image
    print("\n[Step 3] Generating video from image...")
    print(f"Video prompt: {VIDEO_PROMPT[:50]}...")
    print(f"Reference image ID: {image.media_name[:50]}...")
    print(f"Model: VEO3_I2V_FAST (Image-to-Video)")
    print()

    success, result, error = api.generate_video(
        prompt=VIDEO_PROMPT,
        aspect_ratio=VideoAspectRatio.LANDSCAPE,
        reference_image_id=image.media_name  # Use media_name as reference
    )

    print()
    print("-" * 40)
    print("RESULT")
    print("-" * 40)
    print(f"Success: {success}")
    print(f"Status: {result.status}")
    print(f"Video URL: {result.video_url}")
    print(f"Operation ID: {result.operation_id}")
    if error:
        print(f"Error: {error}")

    # Download video if successful
    if success and result.video_url:
        print(f"\nDownloading video...")
        video_path = api.download_video(result, OUTPUT_DIR, "test_i2v")
        if video_path:
            print(f"✅ Video saved to: {video_path}")
            print(f"   File size: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("❌ Failed to download video")
    else:
        print(f"\n❌ Video generation failed: {error}")


def main():
    print("=" * 60)
    print("VIDEO GENERATION TEST")
    print(f"Mode: {TEST_MODE.upper()}")
    print("=" * 60)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create API client
    print("\nCreating API client...")
    api = GoogleFlowAPI(
        bearer_token=BEARER_TOKEN,
        project_id=PROJECT_ID,
        proxy_api_token=PROXY_TOKEN,
        use_proxy=True,
        verbose=True,
        timeout=300  # 5 minutes timeout
    )

    if TEST_MODE == "text2video":
        test_text_to_video(api)
    elif TEST_MODE == "image2video":
        test_image_to_video(api)
    else:
        print(f"Unknown test mode: {TEST_MODE}")
        print("Use 'text2video' or 'image2video'")


if __name__ == "__main__":
    main()
