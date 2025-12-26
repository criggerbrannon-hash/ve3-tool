#!/usr/bin/env python3
"""
VE3 Tool - Test API với cURL
============================
Paste cURL command từ Chrome DevTools, script tự parse tất cả.

Cách dùng:
1. Chrome → F12 → Network → Tạo ảnh
2. Right-click request 'batchGenerateImages' → Copy → Copy as cURL (bash)
3. Chạy script này và paste cURL command
"""

import sys
import re
import json
import requests
from pathlib import Path
from datetime import datetime


OUTPUT_DIR = Path("./test_output")


def parse_curl(curl_command):
    """Parse cURL command để lấy headers và payload."""

    result = {
        "url": "",
        "headers": {},
        "data": "",
        "bearer_token": "",
        "x_browser_validation": "",
        "recaptcha_token": "",
        "project_id": "",
    }

    # Lấy URL
    url_match = re.search(r"curl\s+'([^']+)'", curl_command)
    if not url_match:
        url_match = re.search(r'curl\s+"([^"]+)"', curl_command)
    if url_match:
        result["url"] = url_match.group(1)
        # Extract project ID từ URL
        proj_match = re.search(r'/projects/([^/]+)/', result["url"])
        if proj_match:
            result["project_id"] = proj_match.group(1)

    # Lấy headers
    header_matches = re.findall(r"-H\s+'([^']+)'", curl_command)
    if not header_matches:
        header_matches = re.findall(r'-H\s+"([^"]+)"', curl_command)

    for header in header_matches:
        if ': ' in header:
            key, value = header.split(': ', 1)
            result["headers"][key.lower()] = value

            # Extract specific values
            if key.lower() == 'authorization' and value.startswith('Bearer '):
                result["bearer_token"] = value[7:]  # Remove "Bearer "
            elif key.lower() == 'x-browser-validation':
                result["x_browser_validation"] = value

    # Lấy data/payload
    data_match = re.search(r"--data-raw\s+'(.+?)'(?:\s|$)", curl_command, re.DOTALL)
    if not data_match:
        data_match = re.search(r'--data-raw\s+"(.+?)"(?:\s|$)', curl_command, re.DOTALL)
    if not data_match:
        data_match = re.search(r"--data\s+'(.+?)'(?:\s|$)", curl_command, re.DOTALL)

    if data_match:
        result["data"] = data_match.group(1)
        try:
            payload = json.loads(result["data"])
            # Tìm recaptchaToken
            if "requests" in payload and payload["requests"]:
                client_ctx = payload["requests"][0].get("clientContext", {})
                result["recaptcha_token"] = client_ctx.get("recaptchaToken", "")
                if not result["project_id"]:
                    result["project_id"] = client_ctx.get("projectId", "")
        except json.JSONDecodeError:
            pass

    return result


def test_with_curl():
    """Test API bằng cách paste cURL command."""

    print("=" * 60)
    print("  VE3 TOOL - TEST API WITH CURL")
    print("=" * 60)
    print(f"Time: {datetime.now()}\n")

    print("📋 Paste cURL command từ Chrome DevTools:")
    print("   (Right-click request → Copy → Copy as cURL bash)")
    print("   Paste xong nhấn Enter 2 lần\n")

    # Đọc multiline input
    lines = []
    empty_count = 0
    while True:
        try:
            line = input()
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 1 and lines:  # 1 dòng trống là đủ
                    break
            else:
                empty_count = 0
                lines.append(line)
        except EOFError:
            break

    curl_command = " ".join(lines)

    if not curl_command.strip():
        print("\n❌ Không có input!")
        return False

    print("\n" + "=" * 60)
    print("📝 Đang parse cURL command...")

    # Parse
    parsed = parse_curl(curl_command)

    # Validate
    if not parsed["bearer_token"]:
        print("❌ Không tìm thấy Authorization header!")
        return False

    if not parsed["recaptcha_token"]:
        print("❌ Không tìm thấy recaptchaToken trong payload!")
        return False

    print(f"\n✅ Bearer token: {parsed['bearer_token'][:30]}...{parsed['bearer_token'][-10:]}")
    print(f"✅ recaptchaToken: {parsed['recaptcha_token'][:30]}...{parsed['recaptcha_token'][-10:]}")

    if parsed["x_browser_validation"]:
        print(f"✅ x-browser-validation: {parsed['x_browser_validation']}")
    else:
        print("⚠️  Không có x-browser-validation")

    print(f"📁 Project ID: {parsed['project_id']}")
    print(f"🌐 URL: {parsed['url'][:60]}...")

    # Build headers
    headers = {
        "Authorization": f"Bearer {parsed['bearer_token']}",
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

    if parsed["x_browser_validation"]:
        headers["x-browser-validation"] = parsed["x_browser_validation"]
        headers["x-browser-channel"] = "stable"
        headers["x-browser-copyright"] = "Copyright 2025 Google LLC. All Rights reserved."
        headers["x-browser-year"] = "2025"
        headers["x-client-data"] = "CIDsygE="

    # Sử dụng payload gốc từ cURL
    print("\n⏳ Đang gọi API...")

    try:
        response = requests.post(
            parsed["url"],
            headers=headers,
            data=parsed["data"],
            timeout=120
        )

        print(f"📊 Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()

            if "media" in result and result["media"]:
                print(f"\n✅ THÀNH CÔNG! Nhận được {len(result['media'])} ảnh")

                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                for i, media in enumerate(result["media"]):
                    img = media.get("image", {}).get("generatedImage", {})
                    url = img.get("fifeUrl")
                    seed = media.get("seed", "unknown")
                    prompt = media.get("prompt", "")

                    if url:
                        print(f"\n   📷 Image {i+1}:")
                        print(f"      Prompt: {prompt[:50]}...")
                        print(f"      Seed: {seed}")

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
            print("\n❌ Token hết hạn! Tạo ảnh mới trong Chrome và copy cURL lại.")
            return False

        elif response.status_code == 403:
            print("\n❌ Bị chặn (403)!")
            print(f"   Response: {response.text[:300]}")

            if "recaptcha" in response.text.lower():
                print("\n💡 recaptchaToken đã hết hạn!")
                print("   Tạo ảnh mới trong Chrome và copy cURL lại.")
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
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_with_curl()
    sys.exit(0 if success else 1)
