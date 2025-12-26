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

# JS để lấy token - dùng callback thay vì async/await
JS_GET_TOKEN = """
(function() {
    // Check if grecaptcha exists
    if (typeof grecaptcha === 'undefined') {
        return {error: 'grecaptcha undefined'};
    }
    if (!grecaptcha.enterprise) {
        return {error: 'grecaptcha.enterprise not found'};
    }

    // Lưu token vào window để lấy sau
    window.__recaptchaToken = null;
    window.__recaptchaError = null;

    grecaptcha.enterprise.execute('%s', {action: 'submit'})
        .then(function(token) {
            window.__recaptchaToken = token;
        })
        .catch(function(e) {
            window.__recaptchaError = e.toString();
        });

    return {status: 'pending'};
})();
""" % SITE_KEY

# JS để check token đã sẵn sàng chưa
JS_GET_TOKEN_RESULT = """
(function() {
    if (window.__recaptchaToken) {
        var token = window.__recaptchaToken;
        window.__recaptchaToken = null;
        return {token: token};
    }
    if (window.__recaptchaError) {
        var err = window.__recaptchaError;
        window.__recaptchaError = null;
        return {error: err};
    }
    return {status: 'waiting'};
})();
"""

# JS để check grecaptcha status
JS_CHECK_RECAPTCHA = """
(function() {
    return {
        grecaptcha: typeof grecaptcha !== 'undefined',
        enterprise: typeof grecaptcha !== 'undefined' && !!grecaptcha.enterprise,
        ready: typeof grecaptcha !== 'undefined' && typeof grecaptcha.enterprise !== 'undefined' && typeof grecaptcha.enterprise.execute === 'function'
    };
})();
"""


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
        self.bearer = input("    Paste: ").strip().replace("Bearer ", "").replace("bearer ", "")

        print("\n[2] X-BROWSER-VALIDATION (optional)")
        self.x_browser = input("    Paste (Enter to skip): ").strip()

        print("\n[3] URL (Enter = mặc định image-fx)")
        print("    Ví dụ: https://labs.google/fx/vi/tools/flow/project/xxx")
        custom_url = input("    URL: ").strip()
        if not custom_url:
            custom_url = "https://labs.google/fx/tools/image-fx"

        # Open Chrome
        print("\n[4] Mở Chrome...")
        print("    Chọn: 1 = Mở Chrome mới, 2 = Kết nối Chrome đang chạy (port 9222)")
        chrome_choice = input("    Chọn (Enter=1): ").strip()

        options = ChromiumOptions()
        options.set_argument("--start-maximized")

        try:
            if chrome_choice == "2":
                # Kết nối Chrome đang chạy
                options.set_local_port(9222)
                self.driver = ChromiumPage(addr_or_opts=options)
                print("    ✓ Kết nối Chrome port 9222")
            else:
                # Mở Chrome mới
                self.driver = ChromiumPage(options)
                print("    ✓ Chrome mới đã mở")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            print("    Thử chạy Chrome trước với:")
            print('    chrome.exe --remote-debugging-port=9222')
            return

        # Go to URL
        print(f"\n[5] Đi tới {custom_url[:60]}...")
        self.driver.get(custom_url)
        time.sleep(3)

        # Check login
        if "accounts.google" in self.driver.url:
            print("    ⚠️ Cần đăng nhập Google!")
            input("    Đăng nhập xong nhấn Enter...")
            time.sleep(2)

        # Wait for grecaptcha
        print("\n[6] Chờ reCAPTCHA load...")
        for i in range(10):
            time.sleep(1)
            status = self.driver.run_js(JS_CHECK_RECAPTCHA)
            print(f"    Check {i+1}: {status}")
            if status and status.get('ready'):
                print("    ✓ grecaptcha.enterprise ready!")
                break
        else:
            print("    ⚠️ grecaptcha chưa sẵn sàng sau 10s")

        # Test get token
        print("\n[7] Test lấy token...")
        token_result = self.get_token()

        if token_result:
            print(f"    ✅ Token: {token_result[:50]}...")
            print(f"    Length: {len(token_result)}")
        else:
            print("    ❌ Không lấy được token!")
            print("    Tiếp tục vào menu...")

        # Menu
        self.menu()

    def get_token(self):
        """Lấy token mới từ grecaptcha"""
        try:
            # Bước 1: Trigger execute
            result = self.driver.run_js(JS_GET_TOKEN)
            print(f"    Trigger: {result}")

            if isinstance(result, dict) and result.get('error'):
                print(f"    JS Error: {result['error']}")
                return None

            # Bước 2: Chờ và lấy kết quả
            for i in range(20):  # Chờ tối đa 2 giây
                time.sleep(0.1)
                result = self.driver.run_js(JS_GET_TOKEN_RESULT)

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
                    elif result.get('status') == 'waiting':
                        continue

            print("    Timeout waiting for token")
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
        print("    d           - Debug info")
        print("    q           - Quit")
        print("=" * 60)

        while True:
            cmd = input("\n> ").strip()

            if not cmd:
                continue

            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 'd':
                # Debug
                print(f"    URL: {self.driver.url}")
                print(f"    Title: {self.driver.title}")
                # Check grecaptcha
                check1 = self.driver.run_js("return typeof grecaptcha")
                check2 = self.driver.run_js("return typeof grecaptcha !== 'undefined' ? Object.keys(grecaptcha) : 'undefined'")
                print(f"    grecaptcha type: {check1}")
                print(f"    grecaptcha keys: {check2}")
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
                print("Lệnh không hợp lệ. Dùng: g <prompt>, t, d, q")

        if self.driver:
            self.driver.quit()


if __name__ == "__main__":
    harvester = TokenHarvester()
    harvester.start()
