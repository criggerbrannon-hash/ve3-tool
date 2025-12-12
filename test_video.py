#!/usr/bin/env python3
"""
VE3 Tool - Video API Test Script v2
===================================
Test tạo video với mediaId + token + projectId

Cách dùng:
1. Lấy token từ Network tab (ya29.xxx)
2. Lấy projectId từ URL (d7e14483-3057-4b21-b5af-7d1ee2386bd0)
3. Lấy mediaId của ảnh từ Network tab
4. Chạy script này

python test_video.py
"""

import os
import sys
import json
from pathlib import Path

# Add modules to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.google_video_api import GoogleVideoAPI, VideoAspectRatio, VideoModel


def test_video_api():
    """Test Video API với input đầy đủ."""

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    VE3 TOOL - VIDEO API TEST v2                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Test tạo video từ ảnh đã có trong project                                   ║
║                                                                              ║
║  Cần 3 thứ từ Network tab:                                                   ║
║  1. Bearer Token (ya29.xxx)                                                  ║
║  2. Project ID (từ URL)                                                      ║
║  3. Media ID của ảnh                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    # === 1. Nhập Token ===
    print("📋 BƯỚC 1: Nhập Bearer Token")
    print("   (Copy từ Network tab -> authorization header)")
    print()
    token = input("   Token (ya29.xxx): ").strip()

    if not token:
        print("❌ Token không được để trống!")
        return

    # === 2. Nhập Project ID ===
    print()
    print("📋 BƯỚC 2: Nhập Project ID")
    print("   (Từ URL: https://labs.google/fx/vi/tools/flow/project/[PROJECT_ID])")
    print()
    project_id = input("   Project ID: ").strip()

    if not project_id:
        print("❌ Project ID không được để trống!")
        return

    # === 3. Nhập Media ID ===
    print()
    print("📋 BƯỚC 3: Nhập Media ID của ảnh")
    print("   (Lấy từ payload khi tạo video -> referenceImages -> mediaId)")
    print()
    media_id = input("   Media ID: ").strip()

    if not media_id:
        print("❌ Media ID không được để trống!")
        return

    # === 4. Nhập Prompt ===
    print()
    print("📝 BƯỚC 4: Nhập video prompt")
    default_prompt = "gentle camera movement, soft lighting, cinematic"
    prompt = input(f"   Prompt [{default_prompt}]: ").strip()
    if not prompt:
        prompt = default_prompt

    # === 5. Tạo API client ===
    print()
    print("🔗 Khởi tạo API client...")

    api = GoogleVideoAPI(
        bearer_token=token,
        project_id=project_id,
        verbose=True
    )

    # === 6. Test connection ===
    print()
    print("🔗 Test kết nối...")
    success, msg = api.test_connection()
    print(f"   {msg}")

    if not success:
        print("❌ Kết nối thất bại!")
        return

    # === 7. Tạo video ===
    print()
    print("🎬 Bắt đầu tạo video...")
    print(f"   Project: {project_id}")
    print(f"   Media ID: {media_id[:30]}...")
    print(f"   Prompt: {prompt}")
    print()

    success, scene_id, error = api.generate_video(
        prompt=prompt,
        media_id=media_id,
        aspect_ratio=VideoAspectRatio.LANDSCAPE,
        model=VideoModel.VEO_3_FAST
    )

    if not success:
        print(f"❌ Lỗi tạo video: {error}")
        return

    print(f"   ✓ Scene ID: {scene_id}")

    # === 8. Poll status ===
    print()
    print("⏳ Đang chờ video hoàn thành...")
    print("   (Có thể mất 1-5 phút)")

    success, video, error = api.wait_for_video(
        operation_id=scene_id,
        max_wait=300,
        poll_interval=5
    )

    if not success:
        print(f"❌ Lỗi: {error}")
        return

    # === 9. Download ===
    print()
    print("📥 Đang download video...")

    output_dir = Path("./output/videos")
    output_dir.mkdir(parents=True, exist_ok=True)

    video_path = api.download_video(
        video=video,
        output_dir=output_dir,
        filename=f"video_{scene_id[:8]}"
    )

    if video_path:
        print()
        print("=" * 60)
        print("✅ THÀNH CÔNG!")
        print(f"   Video: {video_path}")
        print("=" * 60)
    else:
        print("❌ Download thất bại")
        if video and video.url:
            print(f"   Video URL: {video.url}")


def quick_test():
    """Quick test với command line args."""
    if len(sys.argv) >= 5:
        token = sys.argv[1]
        project_id = sys.argv[2]
        media_id = sys.argv[3]
        prompt = sys.argv[4]

        print(f"Token: {token[:30]}...")
        print(f"Project: {project_id}")
        print(f"Media ID: {media_id[:30]}...")
        print(f"Prompt: {prompt}")

        api = GoogleVideoAPI(
            bearer_token=token,
            project_id=project_id,
            verbose=True
        )

        # Generate
        success, scene_id, error = api.generate_video(
            prompt=prompt,
            media_id=media_id
        )

        if not success:
            print(f"❌ Error: {error}")
            return

        # Wait
        success, video, error = api.wait_for_video(scene_id, max_wait=300)

        if success and video:
            output_dir = Path("./output/videos")
            output_dir.mkdir(parents=True, exist_ok=True)
            video_path = api.download_video(video, output_dir)
            print(f"✅ Video: {video_path}")
        else:
            print(f"❌ Error: {error}")
    else:
        test_video_api()


if __name__ == "__main__":
    quick_test()
