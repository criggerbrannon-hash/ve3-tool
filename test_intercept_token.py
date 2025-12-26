#!/usr/bin/env python3
"""
VE3 Tool - Intercept Token Test
================================
Inject JS để chặn fetch request và lấy token TRƯỚC khi gửi.

Cách dùng:
1. Đóng hết Chrome đang chạy
2. Chạy script này
3. Script mở Chrome, inject JS
4. Bạn tạo ảnh trong Flow
5. Script bắt token và tự gọi API
"""

import sys
import os
import json
import time
import subprocess
import requests
from pathlib import Path
from datetime import datetime

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    print("❌ Cần cài selenium: pip install selenium")
    sys.exit(1)

# =============================================================================
# CONFIG
# =============================================================================

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_USER_DATA = r"C:\Users\admin\AppData\Local\Google\Chrome\User Data"
CHROME_PROFILE = "Profile 2"

OUTPUT_DIR = Path("./test_output")

# JavaScript để inject - CHẶN fetch và lưu request (không gửi)
INJECT_JS = """
(function() {
    if (window.__fetchIntercepted) return;
    window.__fetchIntercepted = true;
    window.__capturedRequests = [];
    window.__blockRequests = true;  // Bật chế độ chặn

    const originalFetch = window.fetch;

    window.fetch = async function(...args) {
        const [url, options] = args;

        // Chỉ quan tâm đến batchGenerateImages
        if (url && url.includes('batchGenerateImages') && window.__blockRequests) {
            console.log('🎯 BLOCKED batchGenerateImages request!');

            // Lưu request data
            const requestData = {
                url: url,
                method: options?.method || 'GET',
                headers: options?.headers || {},
                body: options?.body || null,
                timestamp: Date.now()
            };

            window.__capturedRequests.push(requestData);

            // Hiển thị thông báo
            const notification = document.createElement('div');
            notification.id = 'interceptor-notification';
            notification.innerHTML = `
                <div style="position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#FF9800;color:white;padding:20px 40px;border-radius:10px;z-index:999999;font-family:sans-serif;box-shadow:0 4px 20px rgba(0,0,0,0.3);">
                    <b>🔒 Request đã bị chặn!</b><br>
                    Token đã được capture. Quay lại terminal.<br>
                    <small>Script sẽ dùng token để tạo ảnh.</small>
                </div>
            `;
            document.body.appendChild(notification);

            // QUAN TRỌNG: KHÔNG gọi originalFetch - chặn hoàn toàn
            // Trả về fake response để Chrome không bị lỗi
            return new Response(JSON.stringify({
                "blocked": true,
                "message": "Request intercepted by VE3 Tool"
            }), {
                status: 200,
                headers: {'Content-Type': 'application/json'}
            });
        }

        return originalFetch.apply(this, args);
    };

    console.log('✅ Fetch BLOCKER installed - requests will be captured and blocked');
})();
"""


def kill_chrome():
    """Kill all Chrome processes on Windows."""
    print("🔄 Đang đóng Chrome cũ...")
    if sys.platform == "win32":
        os.system("taskkill /F /IM chrome.exe /T 2>nul")
    else:
        os.system("pkill -f chrome 2>/dev/null")
    time.sleep(2)


def start_chrome_debug():
    """Start Chrome với remote debugging."""
    print("🚀 Đang khởi động Chrome...")

    # Build command
    cmd = [
        CHROME_PATH,
        f"--user-data-dir={CHROME_USER_DATA}",
        f"--profile-directory={CHROME_PROFILE}",
        "--remote-debugging-port=9222",
        "https://labs.google/fx/tools/flow"
    ]

    # Start Chrome
    subprocess.Popen(cmd, shell=False)
    print("✅ Chrome đã mở với debug port 9222")
    print("⏳ Đợi Chrome khởi động...")
    time.sleep(10)  # Đợi lâu hơn


def connect_to_chrome():
    """Connect Selenium to running Chrome với retry."""
    print("🔗 Đang kết nối đến Chrome...")

    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    # Retry nhiều lần
    for attempt in range(5):
        try:
            driver = webdriver.Chrome(options=options)
            print(f"✅ Đã kết nối! Title: {driver.title}")
            return driver
        except Exception as e:
            print(f"   Lần {attempt + 1}/5: Chưa kết nối được, đợi thêm...")
            time.sleep(3)

    print("❌ Không thể kết nối sau 5 lần thử")
    return None


def inject_interceptor(driver):
    """Inject JavaScript interceptor."""
    print("💉 Đang inject interceptor...")

    try:
        driver.execute_script(INJECT_JS)
        print("✅ Interceptor đã được inject")
        return True
    except Exception as e:
        print(f"❌ Lỗi inject: {e}")
        return False


def wait_for_captured_request(driver, timeout=300):
    """Đợi cho đến khi có request được capture."""
    print("\n" + "=" * 60)
    print("📋 HƯỚNG DẪN:")
    print("   1. Đăng nhập Google nếu cần")
    print("   2. Nhập prompt và tạo ảnh")
    print("   3. Script sẽ tự động bắt token")
    print("=" * 60)
    print("\n⏳ Đang chờ bạn tạo ảnh...")

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Check captured requests
            captured = driver.execute_script("return window.__capturedRequests || [];")

            if captured:
                print(f"\n🎯 Đã capture {len(captured)} request!")
                return captured

            time.sleep(1)

        except Exception as e:
            # Page might have refreshed, re-inject
            if "no such window" in str(e).lower():
                print("\n⚠️ Window đã đóng")
                return None

            try:
                inject_interceptor(driver)
            except:
                pass

    print("\n⏰ Timeout!")
    return None


def make_own_request(captured_request):
    """Dùng token đã capture để tạo ảnh với prompt khác."""
    print("\n" + "=" * 60)
    print("🚀 TẠO ẢNH VỚI TOKEN ĐÃ CAPTURE")
    print("=" * 60)

    url = captured_request["url"]
    body = captured_request["body"]
    headers_raw = captured_request["headers"]

    # Parse payload
    try:
        payload = json.loads(body) if isinstance(body, str) else body
    except:
        print("❌ Không parse được payload")
        return False

    # Extract tokens
    bearer_token = ""
    x_browser_validation = ""

    for key, value in headers_raw.items():
        if key.lower() == "authorization":
            bearer_token = value.replace("Bearer ", "")
        elif key.lower() == "x-browser-validation":
            x_browser_validation = value

    print(f"🔑 Bearer: {bearer_token[:30]}...{bearer_token[-10:]}")
    print(f"🔐 x-browser-validation: {x_browser_validation}")

    # Thay đổi prompt
    new_prompt = "A majestic dragon flying over mountains at sunset, fantasy art, 4k"

    if "requests" in payload:
        for req in payload["requests"]:
            req["prompt"] = new_prompt
            req["seed"] = int(time.time()) % 1000000
            print(f"🎨 Prompt mới: {new_prompt}")

    # Build headers
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    if x_browser_validation:
        headers["x-browser-validation"] = x_browser_validation
        headers["x-browser-channel"] = "stable"
        headers["x-browser-year"] = "2025"

    print(f"\n⏳ Đang gọi API...")

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

            if "media" in result and result["media"]:
                print(f"\n✅ THÀNH CÔNG! Nhận được {len(result['media'])} ảnh")

                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

                for i, media in enumerate(result["media"]):
                    img = media.get("image", {}).get("generatedImage", {})
                    img_url = img.get("fifeUrl")

                    if img_url:
                        try:
                            img_response = requests.get(img_url, timeout=60)
                            if img_response.status_code == 200:
                                filename = f"dragon_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                                filepath = OUTPUT_DIR / filename
                                with open(filepath, "wb") as f:
                                    f.write(img_response.content)
                                print(f"   ✅ Saved: {filepath}")
                        except Exception as e:
                            print(f"   ❌ Download error: {e}")

                return True
            else:
                print(f"⚠️ Không có ảnh")
                print(json.dumps(result, indent=2)[:500])
                return False

        elif response.status_code == 403:
            print(f"❌ Bị chặn (403)")
            print(f"   {response.text[:300]}")

            if "recaptcha" in response.text.lower():
                print("\n💡 recaptchaToken không hợp lệ!")
                print("   Có thể đã hết hạn hoặc bị dùng rồi.")
            return False

        else:
            print(f"❌ Lỗi: {response.status_code}")
            print(f"   {response.text[:300]}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("=" * 60)
    print("  VE3 TOOL - TOKEN INTERCEPTOR")
    print("=" * 60)
    print(f"Time: {datetime.now()}\n")

    driver = None

    try:
        # Kill existing Chrome
        kill_chrome()

        # Start Chrome with debug port
        start_chrome_debug()

        # Connect Selenium
        driver = connect_to_chrome()
        if not driver:
            return False

        # Inject interceptor
        time.sleep(2)
        inject_interceptor(driver)

        # Wait for captured request
        captured = wait_for_captured_request(driver)

        if captured:
            # Thử dùng token (biết trước là sẽ fail vì token đã bị Chrome dùng)
            make_own_request(captured[0])

    except KeyboardInterrupt:
        print("\n\n⚠️ Đã dừng")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n✅ Done!")
    return True


if __name__ == "__main__":
    main()
