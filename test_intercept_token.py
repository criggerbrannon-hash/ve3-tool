#!/usr/bin/env python3
"""
VE3 Tool - Token Interceptor (Simple)
======================================
Bước 1: Bạn tự mở Chrome với debug port
Bước 2: Chạy script này để inject và capture token
"""

import sys
import os
import json
import time
import requests
from pathlib import Path
from datetime import datetime

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
except ImportError:
    print("❌ Cần cài selenium: pip install selenium")
    sys.exit(1)

OUTPUT_DIR = Path("./test_output")

# JavaScript chặn fetch
INJECT_JS = """
(function() {
    if (window.__fetchIntercepted) return;
    window.__fetchIntercepted = true;
    window.__capturedRequests = [];

    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const [url, options] = args;

        if (url && url.includes('batchGenerateImages')) {
            console.log('🎯 BLOCKED!');

            window.__capturedRequests.push({
                url: url,
                headers: options?.headers || {},
                body: options?.body || null
            });

            alert('✅ Token captured! Quay lại terminal.');

            return new Response('{"blocked":true}', {status: 200});
        }
        return originalFetch.apply(this, args);
    };
    console.log('✅ Interceptor ready');
})();
"""


def main():
    print("=" * 60)
    print("  VE3 TOOL - TOKEN INTERCEPTOR")
    print("=" * 60)

    print("""
╔══════════════════════════════════════════════════════════╗
║  BƯỚC 1: Mở Chrome với debug port                        ║
╠══════════════════════════════════════════════════════════╣
║  1. Đóng TẤT CẢ Chrome đang mở                           ║
║  2. Mở CMD mới và chạy lệnh sau:                         ║
╚══════════════════════════════════════════════════════════╝
""")

    print('cd /d "C:\\Program Files\\Google\\Chrome\\Application"')
    print('chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\Users\\admin\\AppData\\Local\\Google\\Chrome\\User Data" --profile-directory="Profile 2" https://labs.google/fx/tools/flow')

    print("""
╔══════════════════════════════════════════════════════════╗
║  BƯỚC 2: Nhấn Enter khi Chrome đã mở xong                ║
╚══════════════════════════════════════════════════════════╝
""")

    input(">>> Nhấn Enter khi Chrome đã mở Flow...")

    # Kết nối
    print("\n🔗 Đang kết nối...")

    try:
        options = Options()
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        driver = webdriver.Chrome(options=options)
        print(f"✅ Đã kết nối! Page: {driver.title}")
    except Exception as e:
        print(f"❌ Không kết nối được: {e}")
        print("\n💡 Kiểm tra:")
        print("   - Chrome đã mở với lệnh ở trên chưa?")
        print("   - Có Chrome nào khác đang chạy không?")
        return

    # Inject
    print("💉 Inject interceptor...")
    driver.execute_script(INJECT_JS)
    print("✅ Sẵn sàng!")

    print("""
╔══════════════════════════════════════════════════════════╗
║  BƯỚC 3: Tạo ảnh trong Flow                              ║
║  - Nhập prompt và nhấn Generate                          ║
║  - Sẽ có alert "Token captured!"                         ║
╚══════════════════════════════════════════════════════════╝
""")

    # Đợi capture
    print("⏳ Đang chờ bạn tạo ảnh...")

    while True:
        try:
            captured = driver.execute_script("return window.__capturedRequests || [];")
            if captured:
                print(f"\n🎯 Captured {len(captured)} request!")
                break
            time.sleep(1)
        except:
            print("⚠️ Mất kết nối")
            return

    # Xử lý
    req = captured[0]
    body = json.loads(req["body"]) if isinstance(req["body"], str) else req["body"]
    headers = req["headers"]

    bearer = headers.get("authorization", "").replace("Bearer ", "")
    x_val = headers.get("x-browser-validation", "")

    print(f"\n🔑 Bearer: {bearer[:30]}...{bearer[-10:]}")
    print(f"🔐 x-browser-validation: {x_val}")

    # Gọi API với prompt mới
    print("\n🚀 Gọi API với prompt mới...")

    if "requests" in body:
        for r in body["requests"]:
            r["prompt"] = "A dragon flying over mountains, fantasy art"
            r["seed"] = int(time.time()) % 999999

    api_headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
    }
    if x_val:
        api_headers["x-browser-validation"] = x_val

    resp = requests.post(req["url"], headers=api_headers, data=json.dumps(body), timeout=120)

    print(f"📊 Status: {resp.status_code}")

    if resp.status_code == 200:
        result = resp.json()
        if "media" in result:
            print(f"✅ THÀNH CÔNG! {len(result['media'])} ảnh")

            OUTPUT_DIR.mkdir(exist_ok=True)
            for i, m in enumerate(result["media"]):
                url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                if url:
                    img = requests.get(url).content
                    path = OUTPUT_DIR / f"dragon_{i+1}.png"
                    path.write_bytes(img)
                    print(f"   💾 {path}")
        else:
            print(f"⚠️ Không có ảnh: {str(result)[:200]}")
    else:
        print(f"❌ Lỗi: {resp.text[:300]}")


if __name__ == "__main__":
    main()
