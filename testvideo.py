"""
Test Video Generation via Proxy API
"""
from pathlib import Path
from modules.google_flow_api import GoogleFlowAPI, VideoAspectRatio, VideoModel

# ============================================================================
# CONFIG - Thay đổi các giá trị này
# ============================================================================
BEARER_TOKEN = "YOUR_BEARER_TOKEN_HERE"  # Lấy từ Chrome DevTools khi tạo ảnh trên Flow
PROJECT_ID = "YOUR_PROJECT_ID_HERE"  # UUID project, ví dụ: a8450355-67a6-4fbd-83f3-d1a04efb2864
PROXY_TOKEN = "YOUR_PROXY_TOKEN_HERE"  # Token từ nanoai.pics

# Prompt cho video
VIDEO_PROMPT = "A cute orange cat walking slowly in a beautiful garden with flowers, cinematic lighting, 4K quality"

# Output folder
OUTPUT_DIR = Path("./output")
# ============================================================================

def main():
    print("=" * 60)
    print("TEST VIDEO GENERATION VIA PROXY API")
    print("=" * 60)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create API client
    print("\n[1] Creating API client...")
    api = GoogleFlowAPI(
        bearer_token=BEARER_TOKEN,
        project_id=PROJECT_ID,
        proxy_api_token=PROXY_TOKEN,
        use_proxy=True,
        verbose=True,
        timeout=300  # 5 minutes timeout
    )

    # Generate video
    print(f"\n[2] Generating video...")
    print(f"    Prompt: {VIDEO_PROMPT[:50]}...")
    print(f"    Aspect: LANDSCAPE (16:9)")
    print(f"    Model: VEO3_FAST")
    print()

    success, result, error = api.generate_video(
        prompt=VIDEO_PROMPT,
        aspect_ratio=VideoAspectRatio.LANDSCAPE,
        model=VideoModel.VEO3_FAST
    )

    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Success: {success}")
    print(f"Status: {result.status}")
    print(f"Video URL: {result.video_url}")
    print(f"Operation ID: {result.operation_id}")
    print(f"Error: {error}")

    # Download video if successful
    if success and result.video_url:
        print(f"\n[3] Downloading video...")
        video_path = api.download_video(result, OUTPUT_DIR, "test_video")

        if video_path:
            print(f"\n✅ Video saved to: {video_path}")
            print(f"   File size: {video_path.stat().st_size / 1024 / 1024:.2f} MB")
        else:
            print("\n❌ Failed to download video")
    else:
        print(f"\n❌ Video generation failed: {error}")


if __name__ == "__main__":
    main()
