#!/usr/bin/env python3
"""
VE3 Tool - Video API Test Script
================================
Script test đơn giản để kiểm tra tạo video từ ảnh.

Cách dùng:
1. Lấy token thủ công từ Network tab (ya29.xxx)
2. Chạy script này với token và path ảnh

python test_video.py
"""

import os
import sys
from pathlib import Path

# Add modules to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.google_video_api import GoogleVideoAPI, VideoAspectRatio, VideoDuration


def test_video_api():
    """Test Video API."""

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    VE3 TOOL - VIDEO API TEST                                 ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Test tạo video từ ảnh + prompt                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    # === 1. Nhập Token ===
    print("📋 BƯỚC 1: Nhập Bearer Token")
    print("   (Lấy từ Network tab khi tạo video trên labs.google)")
    print("   Token bắt đầu bằng 'ya29.'")
    print()

    token = input("   Nhập token: ").strip()

    if not token:
        print("❌ Token không được để trống!")
        return

    if not token.startswith("ya29."):
        print("⚠️  Warning: Token thường bắt đầu bằng 'ya29.'")

    # === 2. Chọn ảnh ===
    print()
    print("🖼️  BƯỚC 2: Chọn ảnh nguồn")

    # Tìm ảnh trong thư mục nv hoặc img
    default_images = []
    for pattern in ["PROJECTS/*/nv/*.png", "PROJECTS/*/img/*.png", "nv/*.png", "img/*.png"]:
        default_images.extend(Path(".").glob(pattern))

    if default_images:
        print("   Tìm thấy các ảnh:")
        for i, img in enumerate(default_images[:10], 1):
            print(f"   {i}. {img}")
        print()

        choice = input("   Chọn số hoặc nhập path khác: ").strip()

        if choice.isdigit() and 1 <= int(choice) <= len(default_images):
            image_path = default_images[int(choice) - 1]
        else:
            image_path = Path(choice)
    else:
        image_path = Path(input("   Nhập path đến ảnh: ").strip())

    if not image_path.exists():
        print(f"❌ Không tìm thấy ảnh: {image_path}")
        return

    print(f"   ✓ Đã chọn: {image_path}")

    # === 3. Nhập Prompt ===
    print()
    print("📝 BƯỚC 3: Nhập video prompt")
    print("   (Mô tả chuyển động, hiệu ứng...)")
    print()

    default_prompt = "gentle camera movement, soft wind blowing hair, cinematic lighting"
    prompt = input(f"   Prompt [{default_prompt}]: ").strip()

    if not prompt:
        prompt = default_prompt

    # === 4. Test Connection ===
    print()
    print("🔗 Đang test kết nối...")

    api = GoogleVideoAPI(bearer_token=token, verbose=True)

    success, msg = api.test_connection()
    print(f"   {msg}")

    if not success:
        print("❌ Kết nối thất bại. Kiểm tra lại token.")
        return

    # === 5. Tạo Video ===
    print()
    print("🎬 Bắt đầu tạo video...")
    print(f"   Ảnh: {image_path}")
    print(f"   Prompt: {prompt}")
    print()

    # Tạo output dir
    output_dir = Path("./output/videos")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate video
    success, operation_id, error = api.generate_video(
        prompt=prompt,
        image_path=image_path,
        aspect_ratio=VideoAspectRatio.LANDSCAPE,
        duration=VideoDuration.SHORT
    )

    if not success:
        print(f"❌ Lỗi tạo video: {error}")
        return

    print(f"   ✓ Operation ID: {operation_id}")

    # === 6. Chờ hoàn thành ===
    print()
    print("⏳ Đang chờ video hoàn thành (có thể mất 1-5 phút)...")

    success, video, error = api.wait_for_video(
        operation_id=operation_id,
        max_wait=300,  # 5 phút
        poll_interval=5
    )

    if not success:
        print(f"❌ Lỗi: {error}")
        return

    # === 7. Download ===
    print()
    print("📥 Đang download video...")

    video_path = api.download_video(
        video=video,
        output_dir=output_dir,
        filename=f"test_{image_path.stem}"
    )

    if video_path:
        print()
        print("=" * 60)
        print(f"✅ THÀNH CÔNG!")
        print(f"   Video saved: {video_path}")
        print("=" * 60)
    else:
        print("❌ Download thất bại")


def test_with_args():
    """Test với arguments từ command line."""
    if len(sys.argv) >= 4:
        token = sys.argv[1]
        image_path = sys.argv[2]
        prompt = sys.argv[3]

        print(f"Token: {token[:30]}...")
        print(f"Image: {image_path}")
        print(f"Prompt: {prompt}")

        api = GoogleVideoAPI(bearer_token=token, verbose=True)

        output_dir = Path("./output/videos")
        output_dir.mkdir(parents=True, exist_ok=True)

        success, video_path, error = api.generate_and_download(
            prompt=prompt,
            image_path=Path(image_path),
            output_dir=output_dir
        )

        if success:
            print(f"\n✅ Video saved: {video_path}")
        else:
            print(f"\n❌ Error: {error}")
    else:
        test_video_api()


if __name__ == "__main__":
    test_with_args()
