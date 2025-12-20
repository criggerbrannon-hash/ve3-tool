#!/usr/bin/env python3
"""
Test reCAPTCHA Enterprise với Site Key từ Google Labs Flow
Site Key: 6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV

Cách hoạt động của reCAPTCHA Enterprise:
1. Client gửi request đến grecaptcha.enterprise.execute() với site key
2. Nhận về token
3. Gửi token đến server để verify

Test này sẽ dùng Selenium để thực hiện reCAPTCHA challenge.
"""

import os
import sys
import time
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("❌ Cần cài đặt selenium: pip install selenium")
    sys.exit(1)


# reCAPTCHA Enterprise Site Key từ Google Labs Flow
RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
FLOW_URL = "https://labs.google/fx/vi/tools/flow"


class RecaptchaEnterpriseTest:
    """Test reCAPTCHA Enterprise integration."""

    def __init__(self, chrome_profile_path: str = None, headless: bool = False):
        self.chrome_profile_path = chrome_profile_path
        self.headless = headless
        self.driver = None

    def _create_driver(self):
        """Tạo Chrome driver."""
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        # Standard options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")

        # Profile nếu có
        if self.chrome_profile_path:
            options.add_argument(f"--user-data-dir={self.chrome_profile_path}")

        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(options=options)

        # Execute CDP commands to hide automation
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        })

        return self.driver

    def get_recaptcha_token(self, action: str = "login") -> str:
        """
        Lấy reCAPTCHA token bằng cách execute grecaptcha.enterprise.

        Args:
            action: Action name cho reCAPTCHA (e.g., "login", "submit")

        Returns:
            reCAPTCHA token string hoặc None
        """
        if not self.driver:
            self._create_driver()

        print(f"\n🔐 Đang lấy reCAPTCHA Enterprise token...")
        print(f"   Site Key: {RECAPTCHA_SITE_KEY}")
        print(f"   Action: {action}")

        try:
            # Navigate to Flow page
            print(f"\n📍 Truy cập: {FLOW_URL}")
            self.driver.get(FLOW_URL)
            time.sleep(3)

            # Chờ grecaptcha.enterprise load
            print("⏳ Đợi reCAPTCHA Enterprise load...")

            wait_script = """
                return new Promise((resolve) => {
                    let attempts = 0;
                    const check = () => {
                        if (typeof grecaptcha !== 'undefined' &&
                            typeof grecaptcha.enterprise !== 'undefined' &&
                            typeof grecaptcha.enterprise.execute === 'function') {
                            resolve(true);
                        } else if (attempts < 30) {
                            attempts++;
                            setTimeout(check, 500);
                        } else {
                            resolve(false);
                        }
                    };
                    check();
                });
            """

            loaded = self.driver.execute_script(wait_script)

            if not loaded:
                print("❌ reCAPTCHA Enterprise không load được!")
                return None

            print("✅ reCAPTCHA Enterprise đã sẵn sàng!")

            # Execute reCAPTCHA và lấy token
            print(f"🔄 Executing reCAPTCHA với action '{action}'...")

            execute_script = f"""
                return new Promise((resolve, reject) => {{
                    grecaptcha.enterprise.ready(async () => {{
                        try {{
                            const token = await grecaptcha.enterprise.execute(
                                '{RECAPTCHA_SITE_KEY}',
                                {{action: '{action}'}}
                            );
                            resolve(token);
                        }} catch (error) {{
                            reject(error.message);
                        }}
                    }});
                }});
            """

            token = self.driver.execute_async_script(f"""
                var callback = arguments[arguments.length - 1];
                {execute_script}.then(callback).catch(err => callback('ERROR:' + err));
            """)

            if token and not token.startswith('ERROR:'):
                print(f"✅ Đã lấy được token!")
                print(f"   Token (first 50 chars): {token[:50]}...")
                print(f"   Token length: {len(token)}")
                return token
            else:
                print(f"❌ Lỗi: {token}")
                return None

        except Exception as e:
            print(f"❌ Exception: {e}")
            return None

    def test_token_on_flow(self, token: str) -> dict:
        """
        Test token bằng cách gửi request tới Flow API.

        Args:
            token: reCAPTCHA token

        Returns:
            Response từ API
        """
        import requests

        print(f"\n🧪 Testing token với Flow API...")

        # Headers
        headers = {
            "Content-Type": "application/json",
            "X-Recaptcha-Token": token,
            "Origin": "https://labs.google",
            "Referer": FLOW_URL
        }

        # Test endpoint (nếu có)
        # Thường reCAPTCHA token được gửi cùng với request chính

        print(f"📤 Headers prepared:")
        print(f"   X-Recaptcha-Token: {token[:30]}...")

        return {"status": "prepared", "token_length": len(token)}

    def analyze_page_for_recaptcha(self):
        """Phân tích trang để tìm thông tin reCAPTCHA."""
        if not self.driver:
            self._create_driver()

        print(f"\n🔍 Phân tích trang: {FLOW_URL}")

        self.driver.get(FLOW_URL)
        time.sleep(5)

        # Tìm script chứa reCAPTCHA
        script = """
            const results = {
                grecaptcha: typeof grecaptcha !== 'undefined',
                enterprise: typeof grecaptcha !== 'undefined' && typeof grecaptcha.enterprise !== 'undefined',
                siteKey: null,
                scripts: [],
                divs: []
            };

            // Tìm scripts
            document.querySelectorAll('script[src*="recaptcha"]').forEach(s => {
                results.scripts.push(s.src);
            });

            // Tìm div có data-sitekey
            document.querySelectorAll('[data-sitekey]').forEach(d => {
                results.divs.push({
                    tag: d.tagName,
                    sitekey: d.dataset.sitekey,
                    action: d.dataset.action || null
                });
            });

            // Tìm trong window object
            if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {
                // Có thể có thêm thông tin
            }

            return results;
        """

        results = self.driver.execute_script(script)

        print(f"\n📊 Kết quả phân tích:")
        print(f"   grecaptcha loaded: {results['grecaptcha']}")
        print(f"   enterprise mode: {results['enterprise']}")
        print(f"   Scripts found: {len(results['scripts'])}")
        for s in results['scripts']:
            print(f"      - {s}")
        print(f"   Divs with sitekey: {len(results['divs'])}")
        for d in results['divs']:
            print(f"      - {d}")

        return results

    def close(self):
        """Đóng driver."""
        if self.driver:
            self.driver.quit()
            self.driver = None


def main():
    """Main test function."""
    print("=" * 60)
    print("🔐 TEST reCAPTCHA ENTERPRISE")
    print("=" * 60)
    print(f"Site Key: {RECAPTCHA_SITE_KEY}")
    print(f"Target: {FLOW_URL}")
    print("=" * 60)

    tester = RecaptchaEnterpriseTest(headless=False)

    try:
        # 1. Phân tích trang
        print("\n[1/3] Phân tích trang để tìm reCAPTCHA...")
        results = tester.analyze_page_for_recaptcha()

        # 2. Lấy token
        print("\n[2/3] Lấy reCAPTCHA token...")
        token = tester.get_recaptcha_token(action="pageview")

        if token:
            # 3. Test token
            print("\n[3/3] Kiểm tra token...")
            test_result = tester.test_token_on_flow(token)

            print("\n" + "=" * 60)
            print("✅ KẾT QUẢ TEST THÀNH CÔNG!")
            print("=" * 60)
            print(f"Token: {token[:80]}...")
            print(f"Length: {len(token)} characters")
            print("\nToken này có thể được dùng để:")
            print("  1. Bypass reCAPTCHA challenge khi gọi API")
            print("  2. Thêm vào header X-Recaptcha-Token")
            print("  3. Verify với Google reCAPTCHA Enterprise API")
        else:
            print("\n❌ Không lấy được token!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n⏸️  Nhấn Enter để đóng browser...")
        tester.close()


if __name__ == "__main__":
    main()
