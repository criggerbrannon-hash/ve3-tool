#!/usr/bin/env python3
"""
VE3 Tool - Test PyPasser bypass reCAPTCHA v3
=============================================

Cài đặt:
  pip install PyPasser

Cách tìm Anchor URL:
  1. Chrome → F12 → Network tab
  2. Vào labs.google/fx/tools/image-fx
  3. Filter "anchor" trong Network
  4. Copy URL dạng: https://www.google.com/recaptcha/api2/anchor?ar=1&k=...
"""

import json
import requests
from pathlib import Path
from datetime import datetime

try:
    from pypasser import reCaptchaV3
except ImportError:
    print("Cần cài đặt PyPasser:")
    print("  pip install PyPasser")
    exit(1)

OUTPUT_DIR = Path("./test_output")
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    print("=" * 60)
    print("  VE3 - PYPASSER reCAPTCHA v3 BYPASS TEST")
    print("=" * 60)

    # Step 1: Anchor URL
    print("\n[1] ANCHOR URL")
    print("    Cách tìm:")
    print("    - Chrome → F12 → Network")
    print("    - Vào labs.google → tạo ảnh")
    print("    - Filter 'anchor' trong Network")
    print("    - Copy URL: https://www.google.com/recaptcha/api2/anchor?...")
    print()

    anchor_url = input("    Paste Anchor URL: ").strip()

    if not anchor_url or "recaptcha" not in anchor_url:
        print("    ❌ URL không hợp lệ!")
        return

    # Step 2: Generate reCAPTCHA token
    print("\n[2] Đang bypass reCAPTCHA v3...")

    try:
        recaptcha_token = reCaptchaV3(anchor_url, timeout=20)
        print(f"    ✅ Token: {recaptcha_token[:50]}...")
        print(f"    Length: {len(recaptcha_token)}")
    except Exception as e:
        print(f"    ❌ Lỗi: {e}")
        return

    # Step 3: Bearer token
    print("\n[3] BEARER TOKEN")
    print("    Copy từ Network → Headers → authorization")
    bearer = input("    Paste: ").strip().replace("Bearer ", "").replace("bearer ", "")

    if not bearer:
        print("    ❌ Cần Bearer token!")
        return

    # Step 4: Other info
    print("\n[4] PROJECT ID")
    print("    Copy từ payload hoặc URL")
    project_id = input("    Paste (Enter=default): ").strip()
    if not project_id:
        project_id = "image-fx-experiment"  # Default project

    # Step 5: Prompt
    print("\n[5] PROMPT")
    prompt = input("    Nhập prompt (Enter=test): ").strip()
    if not prompt:
        prompt = "a beautiful sunset over mountains"

    # Step 6: Build request
    print("\n[6] Đang gọi API...")

    url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    # Build payload với token mới
    payload = {
        "clientContext": {
            "recaptchaToken": recaptcha_token,
            "sessionId": f";{int(datetime.now().timestamp() * 1000)}"
        },
        "requests": [
            {
                "clientContext": {
                    "recaptchaToken": recaptcha_token,
                    "sessionId": f";{int(datetime.now().timestamp() * 1000)}",
                    "projectId": project_id,
                    "tool": "PINHOLE"
                },
                "seed": 123456,
                "imageModelName": "GEM_PIX_2",
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": prompt,
                "imageInputs": []
            },
            {
                "clientContext": {
                    "recaptchaToken": recaptcha_token,
                    "sessionId": f";{int(datetime.now().timestamp() * 1000)}",
                    "projectId": project_id,
                    "tool": "PINHOLE"
                },
                "seed": 789012,
                "imageModelName": "GEM_PIX_2",
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": prompt,
                "imageInputs": []
            }
        ]
    }

    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    print(f"    URL: {url[:60]}...")
    print(f"    Prompt: {prompt}")

    try:
        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=120
        )

        print(f"\n[RESULT] Status: {resp.status_code}")

        if resp.status_code == 200:
            result = resp.json()
            if "media" in result and result["media"]:
                print(f"✅ SUCCESS! {len(result['media'])} images")

                for i, m in enumerate(result["media"]):
                    img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                    if img_url:
                        try:
                            img_resp = requests.get(img_url, timeout=30)
                            if img_resp.status_code == 200:
                                fname = f"pypasser_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                                (OUTPUT_DIR / fname).write_bytes(img_resp.content)
                                print(f"   ✓ Saved: {fname}")
                        except Exception as e:
                            print(f"   ❌ Download error: {e}")
            else:
                print(f"⚠️ No images in response")
                print(json.dumps(result, indent=2)[:500])

        elif resp.status_code == 403:
            print("❌ 403 Forbidden")
            print(f"   {resp.text[:300]}")
            print("\n   Có thể PyPasser không tương thích với site này")

        else:
            print(f"❌ Error: {resp.text[:300]}")

    except Exception as e:
        print(f"❌ Exception: {e}")


if __name__ == "__main__":
    main()
