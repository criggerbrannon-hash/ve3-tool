#!/usr/bin/env python3
"""
VE3 Tool - Dùng DrissionPage điều khiển Chrome thật
===================================================
Cách này giữ nguyên session/cookies/fingerprint của browser.

Cài đặt:
  pip install DrissionPage

Cách dùng:
  1. Chạy script
  2. Đăng nhập Google trong Chrome (nếu chưa)
  3. Script sẽ tự tạo ảnh và lấy kết quả
"""

import json
import time
from pathlib import Path
from datetime import datetime

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("Cần cài đặt DrissionPage:")
    print("  pip install DrissionPage")
    exit(1)

OUTPUT_DIR = Path("./test_output")
OUTPUT_DIR.mkdir(exist_ok=True)


def main():
    print("=" * 60)
    print("  VE3 - DRISSIONPAGE TEST")
    print("=" * 60)

    # Config Chrome
    options = ChromiumOptions()
    options.set_argument("--start-maximized")
    # Dùng profile mặc định để giữ login
    # options.set_user_data_path(r"C:\Users\admin\AppData\Local\Google\Chrome\User Data")

    print("\n[1] Mở Chrome...")
    driver = ChromiumPage(options)

    print("[2] Đi tới labs.google...")
    driver.get("https://labs.google/fx/tools/image-fx")

    print("[3] Chờ trang load...")
    time.sleep(3)

    # Kiểm tra đã login chưa
    if "accounts.google.com" in driver.url:
        print("\n⚠️  Cần đăng nhập Google!")
        print("    Đăng nhập xong nhấn Enter...")
        input()

    print("[4] Chờ editor load...")
    time.sleep(2)

    # Tìm input prompt
    print("[5] Tìm input prompt...")

    # Thử nhiều selector
    selectors = [
        "textarea",
        "[contenteditable='true']",
        "input[type='text']",
        ".prompt-input",
    ]

    prompt_input = None
    for sel in selectors:
        try:
            prompt_input = driver.ele(sel, timeout=2)
            if prompt_input:
                print(f"    ✓ Tìm thấy: {sel}")
                break
        except:
            continue

    if not prompt_input:
        print("    ❌ Không tìm thấy input!")
        print("    Các elements hiện có:")
        for tag in ["textarea", "input", "div[contenteditable]"]:
            try:
                els = driver.eles(tag)
                print(f"      {tag}: {len(els)} elements")
            except:
                pass
        driver.quit()
        return

    # Nhập prompt
    test_prompt = "a cute cat wearing sunglasses"
    print(f"[6] Nhập prompt: {test_prompt}")
    prompt_input.clear()
    prompt_input.input(test_prompt)
    time.sleep(1)

    # Tìm nút Generate
    print("[7] Tìm nút Generate...")

    btn_selectors = [
        "button:contains('Generate')",
        "button:contains('Create')",
        "[aria-label*='Generate']",
        "[aria-label*='Create']",
        "button[type='submit']",
    ]

    gen_btn = None
    for sel in btn_selectors:
        try:
            gen_btn = driver.ele(sel, timeout=2)
            if gen_btn:
                print(f"    ✓ Tìm thấy: {sel}")
                break
        except:
            continue

    if not gen_btn:
        print("    ❌ Không tìm thấy nút Generate!")
        print("    Nhấn Enter để tiếp tục thủ công...")
        input()
    else:
        print("[8] Click Generate...")
        gen_btn.click()

    # Chờ kết quả
    print("[9] Chờ ảnh được tạo (có thể mất 30-60 giây)...")

    # Intercept network để lấy response
    # DrissionPage có thể listen network events

    max_wait = 120
    start_time = time.time()

    while time.time() - start_time < max_wait:
        # Tìm ảnh kết quả
        try:
            images = driver.eles("img[src*='lh3.googleusercontent.com']")
            if images and len(images) > 0:
                print(f"\n✅ Tìm thấy {len(images)} ảnh!")

                for i, img in enumerate(images):
                    src = img.attrs.get("src", "")
                    if src and "lh3.googleusercontent.com" in src:
                        print(f"    Image {i+1}: {src[:60]}...")

                        # Download ảnh
                        try:
                            import requests
                            resp = requests.get(src, timeout=30)
                            if resp.status_code == 200:
                                fname = f"drission_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                                (OUTPUT_DIR / fname).write_bytes(resp.content)
                                print(f"    ✓ Saved: {fname}")
                        except Exception as e:
                            print(f"    ❌ Download error: {e}")

                break
        except:
            pass

        print(".", end="", flush=True)
        time.sleep(2)

    print("\n[10] Done!")
    print("    Nhấn Enter để đóng browser...")
    input()

    driver.quit()


if __name__ == "__main__":
    main()
