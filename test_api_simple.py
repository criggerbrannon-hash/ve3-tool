#!/usr/bin/env python3
"""
VE3 Tool - Test API đơn giản
============================
Bạn tự lấy token từ Chrome DevTools và điền vào đây.

Cách lấy token:
1. Mở Chrome → vào https://labs.google/fx/tools/flow
2. F12 → Network tab
3. Tạo 1 ảnh bất kỳ
4. Tìm request "batchGenerateImages"
5. Copy các giá trị từ Request Headers
"""

import sys
import json
import requests
from pathlib import Path
from datetime import datetime

# =============================================================================
# ĐIỀN TOKEN VÀO ĐÂY
# =============================================================================

# Bearer token (bắt đầu bằng "ya29.")
# Lấy từ header "Authorization: Bearer ya29.xxxxx"
BEARER_TOKEN = ""  # <-- ĐIỀN TOKEN CỦA BẠN VÀO ĐÂY

# x-browser-validation (optional - thử không có trước)
# Lấy từ header "x-browser-validation: eyJxxxxx"
X_BROWSER_VALIDATION = ""  # <-- ĐIỀN VÀO ĐÂY

# Project ID (optional - tự tạo nếu không có)
# Lấy từ URL: https://labs.google/fx/tools/flow/project/{PROJECT_ID}
PROJECT_ID = ""  # <-- ĐIỀN VÀO ĐÂY

# =============================================================================
# CONFIG
# =============================================================================
TEST_PROMPT = "A cute orange cat sitting on a wooden table, 4k photography"
OUTPUT_DIR = Path("./test_output")
API_BASE = "https://aisandbox-pa.googleapis.com"


def test_api():
    """Test gọi API trực tiếp."""

    print("=" * 60)
    print("  VE3 TOOL - TEST API SIMPLE")
    print("=" * 60)
    print(f"Time: {datetime.now()}")

    # Check token
    if not BEARER_TOKEN:
        print("\n❌ Chưa điền BEARER_TOKEN!")
        print("\nCách lấy:")
        print("1. Mở Chrome → https://labs.google/fx/tools/flow")
        print("2. F12 → Network tab")
        print("3. Tạo 1 ảnh")
        print("4. Tìm request 'batchGenerateImages'")
        print("5. Copy 'Authorization' header (phần sau 'Bearer ')")
        return False

    print(f"\n✅ Bearer token: {BEARER_TOKEN[:30]}...{BEARER_TOKEN[-10:]}")

    if X_BROWSER_VALIDATION:
        print(f"✅ x-browser-validation: {X_BROWSER_VALIDATION[:30]}...")
    else:
        print("⚠️  Không có x-browser-validation (thử không có)")

    # Project ID
    project_id = PROJECT_ID or "test-" + datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"📁 Project ID: {project_id}")

    # Build headers - copy đầy đủ từ Chrome
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }

    if X_BROWSER_VALIDATION:
        headers["x-browser-validation"] = X_BROWSER_VALIDATION
        headers["x-browser-channel"] = "stable"
        headers["x-browser-copyright"] = "Copyright 2025 Google LLC. All Rights reserved."
        headers["x-browser-year"] = "2025"
        headers["x-client-data"] = "CIDsygE="

    # Build payload
    import random
    payload = {
        "requests": [{
            "clientContext": {
                "sessionId": str(random.randint(100000, 999999)),
                "projectId": project_id,
                "tool": "PINHOLE"
            },
            "seed": random.randint(1, 999999),
            "imageModelName": "GEM_PIX_2",
            "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "prompt": TEST_PROMPT,
            "imageInputs": []
        }]
    }

    # Call API
    url = f"{API_BASE}/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    print(f"\n🎨 Prompt: {TEST_PROMPT}")
    print(f"🌐 URL: {url[:60]}...")
    print("\n⏳ Đang gọi API...")

    try:
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=120
        )

        print(f"📊 Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()

            # Check for images
            if "media" in result and result["media"]:
                print(f"\n✅ THÀNH CÔNG! Nhận được {len(result['media'])} ảnh")

                # Download
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                for i, media in enumerate(result["media"]):
                    img = media.get("image", {}).get("generatedImage", {})
                    url = img.get("fifeUrl")
                    seed = img.get("seed")

                    if url:
                        print(f"\n   📷 Image {i+1}:")
                        print(f"      URL: {url[:60]}...")
                        print(f"      Seed: {seed}")

                        # Download
                        try:
                            img_response = requests.get(url, timeout=60)
                            if img_response.status_code == 200:
                                filename = f"test_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                                filepath = OUTPUT_DIR / filename
                                with open(filepath, "wb") as f:
                                    f.write(img_response.content)
                                print(f"      ✅ Saved: {filepath}")
                        except Exception as e:
                            print(f"      ❌ Download error: {e}")

                return True
            else:
                print(f"\n⚠️  Response không có ảnh:")
                print(json.dumps(result, indent=2)[:500])
                return False

        elif response.status_code == 401:
            print("\n❌ Token hết hạn! Lấy token mới.")
            return False

        elif response.status_code == 403:
            print("\n❌ Bị chặn (403)!")
            print(f"   Response: {response.text[:200]}")

            if "captcha" in response.text.lower():
                print("\n💡 Cần x-browser-validation header!")
                print("   Lấy từ Chrome DevTools → Network → Request Headers")
            return False

        else:
            print(f"\n❌ Lỗi: {response.status_code}")
            print(f"   Response: {response.text[:300]}")
            return False

    except requests.exceptions.Timeout:
        print("\n❌ Timeout!")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_api()
    sys.exit(0 if success else 1)
