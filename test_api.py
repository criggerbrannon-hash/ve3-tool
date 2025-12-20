#!/usr/bin/env python3
"""
Test Google Flow API với browser validation headers.
"""

import sys
import json
from pathlib import Path

# Thêm modules vào path
sys.path.insert(0, str(Path(__file__).parent))

from modules.google_flow_api import GoogleFlowAPI, AspectRatio

def test_api():
    # ========================================
    # CẤU HÌNH - COPY TỪ BROWSER
    # ========================================

    # 1. Bearer Token (bắt đầu bằng ya29.)
    # PASTE YOUR TOKEN HERE - Copy từ browser Network tab > Request Headers > authorization
    BEARER_TOKEN = "YOUR_BEARER_TOKEN_HERE"

    # 2. x-browser-validation header
    BROWSER_VALIDATION = "UujAs0GAwdnCJ9nvrswZ+O+oco0="

    # 3. x-client-data header (optional)
    X_CLIENT_DATA = "CI+2yQEIorbJAQipncoBCIDsygEIlaHLAQiFoM0BCPedzwEY8KLPAQ=="

    # 4. Project ID từ URL (lấy từ URL sau khi tạo project)
    # VD: https://labs.google/fx/vi/tools/flow/project/ff8334f0-7575-4957-a679-dc0a9e16cb18
    PROJECT_ID = "ff8334f0-7575-4957-a679-dc0a9e16cb18"

    # 5. recaptchaToken (từ payload của browser - nếu cần)
    RECAPTCHA_TOKEN = ""  # Để trống để test xem có cần không

    # ========================================
    # TEST
    # ========================================

    print("=" * 60)
    print("TEST GOOGLE FLOW API")
    print("=" * 60)
    print(f"Token: {BEARER_TOKEN[:50]}...")
    print(f"Browser Validation: {BROWSER_VALIDATION}")
    print(f"Project ID: {PROJECT_ID}")
    print("=" * 60)

    # Tạo client
    client = GoogleFlowAPI(
        bearer_token=BEARER_TOKEN,
        project_id=PROJECT_ID,
        browser_validation=BROWSER_VALIDATION,
        x_client_data=X_CLIENT_DATA,
        verbose=True
    )

    # Test generate
    print("\n>>> Testing generate_images...")

    success, images, error = client.generate_images(
        prompt="a cute cat sitting on a cozy sofa, soft lighting, 4K",
        count=1,
        aspect_ratio=AspectRatio.LANDSCAPE,
        recaptcha_token=RECAPTCHA_TOKEN if RECAPTCHA_TOKEN else None
    )

    print(f"\n>>> Result:")
    print(f"    Success: {success}")
    print(f"    Images: {len(images)}")
    print(f"    Error: {error}")

    if success and images:
        print(f"\n>>> Image details:")
        for i, img in enumerate(images):
            print(f"    [{i}] URL: {img.url[:80] if img.url else 'None'}...")
            print(f"        Seed: {img.seed}")
            print(f"        MediaName: {img.media_name[:50] if img.media_name else 'None'}...")

        # Download test
        output_dir = Path("test_output")
        output_dir.mkdir(exist_ok=True)

        print(f"\n>>> Downloading to {output_dir}...")
        paths = client.download_all_images(images, output_dir, "test")

        for p in paths:
            print(f"    ✓ Saved: {p}")
    else:
        print(f"\n>>> FAILED: {error}")

        # Gợi ý
        if "401" in str(error) or "auth" in str(error).lower():
            print("\n💡 TIP: Token có thể đã hết hạn. Lấy token mới từ browser.")
        elif "403" in str(error):
            print("\n💡 TIP: Có thể cần recaptchaToken. Copy từ Payload của browser request.")
        elif "400" in str(error):
            print("\n💡 TIP: Kiểm tra lại format payload hoặc Project ID.")

if __name__ == "__main__":
    test_api()
