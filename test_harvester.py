#!/usr/bin/env python3
"""
VE3 Tool - Token Harvester
===========================
Harvest reCAPTCHA Enterprise tokens từ browser.

Ý tưởng:
- Mở labs.google trong Chrome
- Gọi grecaptcha.enterprise.execute() để lấy token
- Dùng token đó cho API call

Cài đặt:
  pip install DrissionPage requests
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
from collections import deque

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("Cần cài đặt: pip install DrissionPage requests")
    exit(1)

OUTPUT_DIR = Path("./test_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Site key của labs.google (từ anchor URL trước đó)
SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"

# JS để lấy token
JS_GET_TOKEN = """
(async function() {
    if (typeof grecaptcha === 'undefined' || !grecaptcha.enterprise) {
        return {error: 'grecaptcha not found'};
    }

    try {
        const token = await grecaptcha.enterprise.execute('%s', {action: 'submit'});
        return {token: token, time: Date.now()};
    } catch(e) {
        return {error: e.toString()};
    }
})();
""" % SITE_KEY


class TokenHarvester:
    def __init__(self):
        self.driver = None
        self.tokens = deque(maxlen=10)  # Giữ 10 tokens gần nhất
        self.bearer = None
        self.x_browser = None

    def start(self):
        print("=" * 60)
        print("  VE3 - TOKEN HARVESTER")
        print("=" * 60)

        # Get Bearer
        print("\n[1] BEARER TOKEN")
        self.bearer = input("    Paste: ").strip().replace("Bearer ", "")

        print("\n[2] X-BROWSER-VALIDATION (optional)")
        self.x_browser = input("    Paste (Enter to skip): ").strip()

        # Open Chrome
        print("\n[3] Mở Chrome...")
        options = ChromiumOptions()
        options.set_argument("--start-maximized")

        try:
            self.driver = ChromiumPage(options)
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            return

        # Go to labs.google
        print("\n[4] Đi tới labs.google...")
        self.driver.get("https://labs.google/fx/tools/image-fx")
        time.sleep(3)

        # Check login
        if "accounts.google" in self.driver.url:
            print("    ⚠️ Cần đăng nhập Google!")
            input("    Đăng nhập xong nhấn Enter...")
            time.sleep(2)

        # Wait for grecaptcha
        print("\n[5] Chờ reCAPTCHA load...")
        time.sleep(3)

        # Test get token
        print("\n[6] Test lấy token...")
        token_result = self.get_token()

        if token_result:
            print(f"    ✅ Token: {token_result[:50]}...")
            print(f"    Length: {len(token_result)}")
        else:
            print("    ❌ Không lấy được token!")
            print("    Có thể grecaptcha chưa load hoặc site key sai")
            return

        # Menu
        self.menu()

    def get_token(self):
        """Lấy token mới từ grecaptcha"""
        try:
            result = self.driver.run_js(JS_GET_TOKEN)

            if isinstance(result, dict):
                if 'token' in result:
                    token = result['token']
                    self.tokens.append({
                        'token': token,
                        'time': time.time()
                    })
                    return token
                elif 'error' in result:
                    print(f"    JS Error: {result['error']}")
            return None
        except Exception as e:
            print(f"    Exception: {e}")
            return None

    def call_api(self, prompt, token=None):
        """Gọi API với token"""
        if not token:
            print("    Lấy token mới...")
            token = self.get_token()

        if not token:
            print("    ❌ Không có token!")
            return False

        # Lấy project ID từ page (hoặc dùng default)
        project_id = "image-fx-experiment"

        # Try to get from page
        try:
            # Tìm trong URL hoặc page content
            page_content = self.driver.html
            import re
            match = re.search(r'"projectId":\s*"([^"]+)"', page_content)
            if match:
                project_id = match.group(1)
        except:
            pass

        url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

        payload = {
            "clientContext": {
                "recaptchaToken": token,
                "sessionId": f";{int(time.time() * 1000)}"
            },
            "requests": [
                {
                    "clientContext": {
                        "recaptchaToken": token,
                        "sessionId": f";{int(time.time() * 1000)}",
                        "projectId": project_id,
                        "tool": "PINHOLE"
                    },
                    "seed": 123456,
                    "imageModelName": "GEM_PIX_2",
                    "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                    "prompt": prompt,
                    "imageInputs": []
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {self.bearer}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }

        if self.x_browser:
            headers["x-browser-validation"] = self.x_browser
            headers["x-browser-channel"] = "stable"
            headers["x-browser-year"] = "2025"

        print(f"    ⏳ Calling API...")

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
            print(f"    Status: {resp.status_code}")

            if resp.status_code == 200:
                result = resp.json()
                if "media" in result and result["media"]:
                    print(f"    ✅ SUCCESS! {len(result['media'])} images")

                    for i, m in enumerate(result["media"]):
                        img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                        if img_url:
                            try:
                                img_resp = requests.get(img_url, timeout=30)
                                if img_resp.status_code == 200:
                                    fname = f"harvest_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                                    (OUTPUT_DIR / fname).write_bytes(img_resp.content)
                                    print(f"       ✓ {fname}")
                            except:
                                pass
                    return True
                else:
                    print(f"    ⚠️ No images")
            else:
                print(f"    ❌ {resp.text[:200]}")

        except Exception as e:
            print(f"    ❌ {e}")

        return False

    def menu(self):
        print("\n" + "=" * 60)
        print("  COMMANDS:")
        print("    g <prompt>  - Generate image với prompt")
        print("    t           - Test lấy token")
        print("    q           - Quit")
        print("=" * 60)

        while True:
            cmd = input("\n> ").strip()

            if not cmd:
                continue

            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 't':
                token = self.get_token()
                if token:
                    print(f"Token: {token[:60]}...")
                    print(f"Length: {len(token)}")
            elif cmd.lower().startswith('g '):
                prompt = cmd[2:].strip()
                if prompt:
                    self.call_api(prompt)
                else:
                    print("Cần nhập prompt!")
            else:
                print("Lệnh không hợp lệ. Dùng: g <prompt>, t, q")

        if self.driver:
            self.driver.quit()


if __name__ == "__main__":
    harvester = TokenHarvester()
    harvester.start()
