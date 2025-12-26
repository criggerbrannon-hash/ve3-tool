#!/usr/bin/env python3
"""
VE3 Tool - DrissionPage Auto Intercept
=======================================
Tự động hóa hoàn toàn: mở Chrome, inject JS, chờ payload, gửi API.

Cài đặt:
  pip install DrissionPage requests

Cách dùng:
  1. Chạy script
  2. Đăng nhập Google (nếu chưa)
  3. Nhập prompt và nhấn Generate trong Chrome
  4. Script tự động bắt request và gửi API
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
import os

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("Cần cài đặt:")
    print("  pip install DrissionPage requests")
    exit(1)

# Config
OUTPUT_DIR = Path("./test_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Thư mục Downloads của user
if os.name == 'nt':
    DOWNLOADS = Path.home() / "Downloads"
else:
    DOWNLOADS = Path.home() / "Downloads"

JS_INTERCEPTOR = """
(function(){
    if(window.__interceptorInstalled) return 'ALREADY_INSTALLED';
    window.__interceptorInstalled = true;

    if(!window.__origFetch) window.__origFetch = window.fetch;

    window.__lastPayload = null;
    window.__lastHeaders = null;

    window.fetch = async (url, opts) => {
        if (url.includes('batchGenerateImages')) {
            // Lưu payload và headers
            window.__lastPayload = opts.body;
            window.__lastHeaders = {};
            if (opts.headers) {
                for (let [k, v] of opts.headers.entries ? opts.headers.entries() : Object.entries(opts.headers)) {
                    window.__lastHeaders[k] = v;
                }
            }

            // Download file
            const blob = new Blob([opts.body], {type:'application/json'});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'payload_' + Date.now() + '.json';
            a.click();

            console.log('[VE3] Payload captured!');

            // Block request gốc
            return new Response('{"blocked":"ve3"}');
        }
        return window.__origFetch(url, opts);
    };

    return 'INSTALLED';
})();
"""


def get_latest_payload():
    """Tìm file payload mới nhất trong Downloads"""
    files = list(DOWNLOADS.glob("payload_*.json"))
    if not files:
        # Thử tìm payload.json thường
        simple = DOWNLOADS / "payload.json"
        if simple.exists():
            return simple
        return None

    # Lấy file mới nhất
    return max(files, key=lambda f: f.stat().st_mtime)


def wait_for_new_payload(last_file=None, timeout=120):
    """Chờ file payload mới"""
    start = time.time()

    while time.time() - start < timeout:
        latest = get_latest_payload()

        if latest:
            # Nếu có file mới hoặc file cũ được update
            if last_file is None:
                # Kiểm tra file có mới không (trong 5 giây gần đây)
                age = time.time() - latest.stat().st_mtime
                if age < 5:
                    return latest
            elif latest != last_file or latest.stat().st_mtime > last_file.stat().st_mtime:
                return latest

        time.sleep(0.3)

    return None


def call_api(payload_path, bearer, x_browser=None):
    """Gọi API với payload"""
    try:
        payload = json.loads(payload_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"    ❌ Lỗi đọc payload: {e}")
        return False

    # Parse info
    project_id = payload.get("requests", [{}])[0].get("clientContext", {}).get("projectId", "")
    prompt = payload.get("requests", [{}])[0].get("prompt", "")[:50]

    print(f"    Project: {project_id}")
    print(f"    Prompt: {prompt}...")

    url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    if x_browser:
        headers["x-browser-validation"] = x_browser
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
                                fname = f"auto_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                                (OUTPUT_DIR / fname).write_bytes(img_resp.content)
                                print(f"       ✓ {fname}")
                        except:
                            pass
                return True
            else:
                print(f"    ⚠️ No images")
                return False
        else:
            print(f"    ❌ Error: {resp.text[:200]}")
            return False

    except Exception as e:
        print(f"    ❌ Exception: {e}")
        return False


def main():
    print("=" * 60)
    print("  VE3 - AUTO INTERCEPT")
    print("=" * 60)

    # Step 1: Lấy Bearer token trước
    print("\n[1] BEARER TOKEN")
    print("    Từ Chrome → F12 → Network → bất kỳ request nào")
    print("    Copy header 'authorization'")
    bearer = input("    Paste: ").strip().replace("Bearer ", "").replace("bearer ", "")

    if not bearer or len(bearer) < 100:
        print("    ❌ Bearer token không hợp lệ!")
        return

    print(f"    ✓ OK ({len(bearer)} chars)")

    # Step 2: x-browser-validation (optional)
    print("\n[2] X-BROWSER-VALIDATION (optional)")
    x_browser = input("    Paste (Enter to skip): ").strip()

    # Step 3: Mở Chrome
    print("\n[3] Mở Chrome...")

    options = ChromiumOptions()
    options.set_argument("--start-maximized")

    # Thử kết nối Chrome đang chạy hoặc mở mới
    try:
        driver = ChromiumPage(options)
    except Exception as e:
        print(f"    ❌ Không thể mở Chrome: {e}")
        print("    Thử chạy Chrome với: chrome.exe --remote-debugging-port=9222")
        return

    print("    ✓ Chrome đã mở")

    # Step 4: Đi tới labs.google
    print("\n[4] Đi tới labs.google...")
    driver.get("https://labs.google/fx/tools/image-fx")
    time.sleep(3)

    # Kiểm tra login
    if "accounts.google" in driver.url:
        print("    ⚠️ Cần đăng nhập Google!")
        input("    Đăng nhập xong nhấn Enter...")
        time.sleep(2)

    # Step 5: Inject JS
    print("\n[5] Inject interceptor...")
    result = driver.run_js(JS_INTERCEPTOR)
    print(f"    ✓ {result}")

    # Step 6: Chờ và xử lý
    print("\n[6] READY!")
    print("    → Nhập prompt trong Chrome")
    print("    → Nhấn Generate")
    print("    → Script sẽ tự động bắt và xử lý")
    print("    → Nhấn Ctrl+C để thoát")
    print()

    last_payload = get_latest_payload()
    count = 0

    try:
        while True:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Đang chờ...", end="\r")

            new_payload = wait_for_new_payload(last_payload, timeout=5)

            if new_payload and new_payload != last_payload:
                count += 1
                print(f"\n\n{'='*40}")
                print(f"[REQUEST #{count}] Detected: {new_payload.name}")

                # Gọi API ngay lập tức
                success = call_api(new_payload, bearer, x_browser)

                if success:
                    print(f"{'='*40}\n")
                else:
                    print(f"    Thử lại với payload mới\n")

                last_payload = new_payload

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\nĐã dừng.")

    driver.quit()


if __name__ == "__main__":
    main()
