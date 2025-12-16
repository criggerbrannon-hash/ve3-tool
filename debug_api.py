#!/usr/bin/env python3
"""
Debug script để kiểm tra Google Flow API
=========================================
Chạy: python debug_api.py <token>

Script này sẽ:
1. Test token với API endpoint cũ
2. Thử các model khác nhau
3. In chi tiết response để debug
"""

import sys
import json
import requests
import uuid
import time
import random


def test_api(token: str, verbose: bool = True):
    """Test Google Flow API với các cấu hình khác nhau."""

    # Các endpoints có thể
    endpoints = {
        "current": "https://aisandbox-pa.googleapis.com",
        "alt1": "https://labs.google.com/api",
        "alt2": "https://generativelanguage.googleapis.com"
    }

    # Các model có thể
    models = [
        "GEM_PIX",           # Model cũ
        "IMAGEN_4",          # Imagen 4
        "NANO_BANANA_PRO",   # Model mới nhất
        "NANO_BANANA",       # Nano Banana
    ]

    project_id = str(uuid.uuid4())
    session_id = f";{int(time.time() * 1000)}"

    print("="*60)
    print("🔍 GOOGLE FLOW API DEBUG")
    print("="*60)
    print(f"Token: {token[:50]}...")
    print(f"Project ID: {project_id}")
    print()

    # Headers chuẩn
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Test 1: Token validation - simple request
    print("📋 TEST 1: Token validation")
    print("-"*40)

    base_url = endpoints["current"]
    url = f"{base_url}/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    for model in models:
        print(f"\n🎨 Testing model: {model}")

        payload = {
            "requests": [{
                "clientContext": {
                    "sessionId": session_id,
                    "projectId": project_id,
                    "tool": "PINHOLE"
                },
                "seed": random.randint(1, 999999),
                "imageModelName": model,
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": "a simple red circle on white background",
                "imageInputs": []
            }]
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=60
            )

            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                print("   ✅ SUCCESS!")
                data = response.json()
                if verbose:
                    print(f"   Response keys: {list(data.keys())}")
                    if "media" in data:
                        print(f"   Media count: {len(data.get('media', []))}")
                return model, True, data

            elif response.status_code == 401:
                print("   ❌ 401 Unauthorized - Token expired or invalid")

            elif response.status_code == 403:
                print("   ❌ 403 Forbidden")
                try:
                    error_data = response.json()
                    print(f"   Error: {json.dumps(error_data, indent=2)[:500]}")
                except:
                    print(f"   Response: {response.text[:300]}")

            elif response.status_code == 400:
                print("   ❌ 400 Bad Request")
                try:
                    error_data = response.json()
                    print(f"   Error: {json.dumps(error_data, indent=2)[:500]}")
                except:
                    print(f"   Response: {response.text[:300]}")
            else:
                print(f"   Response: {response.text[:300]}")

        except Exception as e:
            print(f"   ❌ Exception: {e}")

        time.sleep(1)

    # Test 2: Try different endpoint format
    print("\n" + "="*60)
    print("📋 TEST 2: Alternative endpoint formats")
    print("-"*40)

    alt_urls = [
        f"{base_url}/v1/projects/-/flowMedia:batchGenerateImages",
        f"{base_url}/v1beta/projects/{project_id}/flowMedia:batchGenerateImages",
        f"{base_url}/$rpc/google.cloud.aisandbox.v1.FlowService/BatchGenerateImages",
    ]

    for url in alt_urls:
        print(f"\n🔗 Testing: {url[:60]}...")

        payload = {
            "requests": [{
                "clientContext": {
                    "sessionId": session_id,
                    "projectId": project_id,
                    "tool": "PINHOLE"
                },
                "seed": random.randint(1, 999999),
                "imageModelName": "GEM_PIX",
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": "test",
                "imageInputs": []
            }]
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=30
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print("   ✅ Found working endpoint!")
                return "GEM_PIX", True, response.json()
        except Exception as e:
            print(f"   Error: {e}")

    print("\n" + "="*60)
    print("❌ Không tìm được cấu hình hoạt động")
    print()
    print("GỢI Ý:")
    print("1. Token có thể đã hết hạn - thử lấy token mới")
    print("2. Google có thể đã thay đổi API - cần cập nhật code")
    print("3. Account có thể bị rate limit - đợi vài phút rồi thử lại")
    print("="*60)

    return None, False, None


def get_token_from_clipboard():
    """Lấy token từ clipboard."""
    try:
        import pyperclip
        text = pyperclip.paste()
        if text and text.startswith("ya29."):
            return text.strip()
    except:
        pass
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        # Try clipboard
        token = get_token_from_clipboard()
        if not token:
            print("Cách sử dụng:")
            print("  python debug_api.py <token>")
            print()
            print("Hoặc copy token vào clipboard và chạy:")
            print("  python debug_api.py")
            print()
            print("Để lấy token:")
            print("1. Mở https://labs.google/fx/vi/tools/flow")
            print("2. Mở DevTools (F12) -> Network tab")
            print("3. Tạo 1 ảnh bất kỳ")
            print("4. Tìm request 'flowMedia:batchGenerateImages'")
            print("5. Copy giá trị 'authorization' header (bắt đầu ya29.)")
            sys.exit(1)

    model, success, data = test_api(token)

    if success:
        print(f"\n✅ Thành công với model: {model}")
    else:
        print("\n❌ Tất cả tests đều thất bại")
        sys.exit(1)
