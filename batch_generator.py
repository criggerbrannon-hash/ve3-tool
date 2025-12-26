#!/usr/bin/env python3
"""
Google Flow API - Batch Image Generator
========================================
Tự động tạo nhiều ảnh bằng DrissionPage + Interceptor.

Workflow:
1. Mở Chrome, đăng nhập Google
2. Inject interceptor để bắt payload
3. Với mỗi prompt: nhập prompt -> click Generate -> bắt payload -> gọi API
4. Lưu ảnh và thống kê

Cài đặt:
    pip install DrissionPage requests

Sử dụng:
    python batch_generator.py
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
from collections import deque
import random

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("Cần cài đặt: pip install DrissionPage requests")
    exit(1)

# Config
OUTPUT_DIR = Path("./batch_output")
OUTPUT_DIR.mkdir(exist_ok=True)

DOWNLOADS_DIR = Path.home() / "Downloads"

# JS Interceptor - lưu payload vào window thay vì download
JS_INTERCEPTOR = '''
(function(){
    if(window.__interceptorInstalled) return 'ALREADY_INSTALLED';
    window.__interceptorInstalled = true;

    window.__capturedPayload = null;
    window.__capturedTime = 0;

    if(!window.__origFetch) window.__origFetch = window.fetch;

    window.fetch = async (url, opts) => {
        if (url.includes('batchGenerateImages')) {
            window.__capturedPayload = opts.body;
            window.__capturedTime = Date.now();
            console.log('[BATCH] Payload captured at', new Date().toISOString());
            // Block original request
            return new Response('{"blocked":"batch"}');
        }
        return window.__origFetch(url, opts);
    };

    console.log('[BATCH] Interceptor ready');
    return 'INSTALLED';
})();
'''

# JS để lấy payload đã capture
JS_GET_PAYLOAD = '''
(function(){
    if (window.__capturedPayload) {
        var payload = window.__capturedPayload;
        var time = window.__capturedTime;
        window.__capturedPayload = null;
        window.__capturedTime = 0;
        return {payload: payload, time: time};
    }
    return null;
})();
'''

# Test prompts
DEFAULT_PROMPTS = [
    "a majestic lion in the savanna at sunset",
    "a cute kitten playing with yarn",
    "a futuristic city with flying cars",
    "a peaceful zen garden with cherry blossoms",
    "an astronaut riding a horse on mars",
    "a dragon breathing fire over a medieval castle",
    "a serene lake reflecting mountains at dawn",
    "a cozy coffee shop on a rainy day",
    "a magical forest with glowing mushrooms",
    "a vintage car on route 66 at sunset",
]


class BatchGenerator:
    def __init__(self):
        self.driver = None
        self.bearer = None
        self.x_browser = None
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": []
        }

    def setup(self):
        """Setup credentials and browser."""
        print("=" * 60)
        print("  BATCH IMAGE GENERATOR")
        print("=" * 60)

        # Get Bearer
        print("\n[1] BEARER TOKEN")
        print("    Copy từ Chrome -> F12 -> Network -> Headers -> authorization")
        self.bearer = input("    Paste: ").strip()
        if self.bearer.lower().startswith("bearer "):
            self.bearer = self.bearer[7:]

        if not self.bearer or len(self.bearer) < 100:
            print("    ❌ Bearer không hợp lệ!")
            return False
        print(f"    ✓ OK ({len(self.bearer)} chars)")

        # x-browser-validation
        print("\n[2] X-BROWSER-VALIDATION (optional)")
        self.x_browser = input("    Paste (Enter to skip): ").strip()

        # Chrome
        print("\n[3] MỞ CHROME...")
        print("    1 = Mở Chrome mới")
        print("    2 = Kết nối Chrome đang chạy (port 9222)")
        choice = input("    Chọn (Enter=1): ").strip()

        options = ChromiumOptions()
        options.set_argument("--start-maximized")

        try:
            if choice == "2":
                options.set_local_port(9222)
                self.driver = ChromiumPage(addr_or_opts=options)
                print("    ✓ Kết nối Chrome port 9222")
            else:
                self.driver = ChromiumPage(options)
                print("    ✓ Chrome mới đã mở")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            return False

        # URL
        print("\n[4] URL")
        print(f"    URL hiện tại: {self.driver.url}")
        print("\n    Nhập URL mới hoặc:")
        print("    - Enter = giữ nguyên trang hiện tại")
        print("    - 1 = https://labs.google/fx/tools/image-fx")
        url_input = input("    URL: ").strip()

        if url_input == "1":
            url_input = "https://labs.google/fx/tools/image-fx"

        if url_input and url_input != "":
            print(f"    → Đi tới: {url_input}")
            self.driver.get(url_input)
            print("    → Đang chờ trang load...")
            time.sleep(5)
        else:
            print("    → Giữ nguyên trang hiện tại")

        # Debug: show current URL
        print(f"    → URL hiện tại: {self.driver.url}")

        # Check login
        if "accounts.google" in self.driver.url:
            print("    ⚠️ Cần đăng nhập Google!")
            input("    Đăng nhập xong nhấn Enter...")
            time.sleep(2)

        # Wait for user to confirm page is ready
        input("\n    Trang đã load xong? Nhấn Enter để tiếp tục...")

        # Inject interceptor
        print("\n[5] INJECT INTERCEPTOR...")
        try:
            result = self.driver.run_js(JS_INTERCEPTOR)
            print(f"    ✓ Result: {result}")
        except Exception as e:
            print(f"    ⚠️ JS error: {e}")

        # Debug: list all visible elements
        print("\n[6] DEBUG - KIỂM TRA ELEMENTS...")
        try:
            # Check textarea
            textareas = self.driver.eles("tag:textarea")
            print(f"    Textareas: {len(textareas)}")

            # Check contenteditable
            editables = self.driver.eles("css:[contenteditable='true']")
            print(f"    Contenteditable: {len(editables)}")

            # Check buttons
            buttons = self.driver.eles("tag:button")
            print(f"    Buttons: {len(buttons)}")

            # Print button texts
            for i, btn in enumerate(buttons[:5]):
                try:
                    txt = btn.text[:30] if btn.text else "(no text)"
                    print(f"      Button {i+1}: {txt}")
                except:
                    pass

        except Exception as e:
            print(f"    Debug error: {e}")

        return True

    def find_prompt_input(self):
        """Find the prompt input element."""
        selectors = [
            # Flow project page
            "tag:textarea",
            "css:textarea",
            # Image-FX page
            "[contenteditable='true']",
            "css:[contenteditable='true']",
            # Fallback
            "tag:input@@type=text",
            "css:input[type='text']",
        ]

        for sel in selectors:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    print(f"    → Found input: {sel}")
                    return el
            except:
                continue
        return None

    def find_generate_button(self):
        """Find the Generate button."""
        selectors = [
            # English
            "@@text():Generate",
            "tag:button@@text():Generate",
            # Vietnamese
            "@@text():Tạo",
            "tag:button@@text():Tạo",
            # By aria-label
            "css:[aria-label*='Generate']",
            "css:[aria-label*='Tạo']",
            # By class containing generate
            "css:button[class*='generate']",
            # Any button with Generate text
            "xpath://button[contains(text(),'Generate')]",
            "xpath://button[contains(text(),'Tạo')]",
        ]

        for sel in selectors:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    print(f"    → Found button: {sel}")
                    return el
            except:
                continue
        return None

    def wait_for_payload(self, timeout=30):
        """Wait for interceptor to capture payload."""
        start = time.time()
        while time.time() - start < timeout:
            result = self.driver.run_js(JS_GET_PAYLOAD)
            if result and result.get("payload"):
                return result["payload"]
            time.sleep(0.3)
        return None

    def call_api(self, payload_str):
        """Call API with captured payload."""
        try:
            payload = json.loads(payload_str)
        except:
            return None

        # Get project ID
        project_id = payload.get("requests", [{}])[0].get("clientContext", {}).get("projectId", "")

        url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

        headers = {
            "Authorization": f"Bearer {self.bearer}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        if self.x_browser:
            headers["x-browser-validation"] = self.x_browser
            headers["x-browser-channel"] = "stable"
            headers["x-browser-year"] = "2025"

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"      API Error: {resp.status_code}")
                return None
        except Exception as e:
            print(f"      API Exception: {e}")
            return None

    def save_images(self, result, prompt_idx):
        """Save images from API result."""
        saved = []
        if "media" in result:
            for i, media in enumerate(result["media"]):
                img_url = media.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                if img_url:
                    try:
                        img_resp = requests.get(img_url, timeout=60)
                        if img_resp.status_code == 200:
                            filename = f"batch_{prompt_idx:03d}_{i+1}.png"
                            (OUTPUT_DIR / filename).write_bytes(img_resp.content)
                            saved.append(filename)
                    except:
                        pass
        return saved

    def generate_one(self, prompt, idx):
        """Generate one image with given prompt."""
        print(f"\n[{idx+1}] {prompt[:50]}...")

        # Find input
        prompt_input = self.find_prompt_input()
        if not prompt_input:
            print("    ❌ Không tìm thấy input!")
            return False

        # Clear and enter prompt
        try:
            prompt_input.clear()
            prompt_input.input(prompt)
            time.sleep(0.5)
        except Exception as e:
            print(f"    ❌ Nhập prompt lỗi: {e}")
            return False

        # Find and click Generate
        gen_btn = self.find_generate_button()
        if not gen_btn:
            print("    ❌ Không tìm thấy nút Generate!")
            return False

        try:
            gen_btn.click()
            print("    → Đã click Generate")
        except Exception as e:
            print(f"    ❌ Click lỗi: {e}")
            return False

        # Wait for payload
        print("    → Đang chờ payload...")
        payload = self.wait_for_payload(timeout=15)

        if not payload:
            print("    ❌ Timeout chờ payload!")
            return False

        print("    → Payload captured, calling API...")

        # Call API
        result = self.call_api(payload)

        if not result:
            print("    ❌ API failed!")
            return False

        # Save images
        saved = self.save_images(result, idx)

        if saved:
            print(f"    ✅ Saved: {', '.join(saved)}")
            return True
        else:
            print("    ⚠️ No images saved")
            return False

    def run_batch(self, prompts):
        """Run batch generation."""
        print(f"\n{'=' * 60}")
        print(f"  BATCH GENERATION: {len(prompts)} prompts")
        print(f"{'=' * 60}")

        self.stats["total"] = len(prompts)

        for i, prompt in enumerate(prompts):
            try:
                success = self.generate_one(prompt, i)

                if success:
                    self.stats["success"] += 1
                else:
                    self.stats["failed"] += 1
                    self.stats["errors"].append(f"Prompt {i+1}: Failed")

            except Exception as e:
                self.stats["failed"] += 1
                self.stats["errors"].append(f"Prompt {i+1}: {str(e)}")

            # Delay giữa các request để tránh rate limit
            if i < len(prompts) - 1:
                delay = random.uniform(2, 4)
                print(f"    ... chờ {delay:.1f}s")
                time.sleep(delay)

        # Print stats
        print(f"\n{'=' * 60}")
        print(f"  BATCH COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Total: {self.stats['total']}")
        print(f"  Success: {self.stats['success']}")
        print(f"  Failed: {self.stats['failed']}")
        print(f"  Success rate: {self.stats['success']/self.stats['total']*100:.1f}%")
        print(f"  Output: {OUTPUT_DIR.absolute()}")

        if self.stats["errors"]:
            print(f"\n  Errors:")
            for err in self.stats["errors"][:10]:
                print(f"    - {err}")

    def cleanup(self):
        if self.driver:
            self.driver.quit()


def main():
    gen = BatchGenerator()

    if not gen.setup():
        return

    # Menu
    print(f"\n{'=' * 60}")
    print("  OPTIONS:")
    print("    1. Test với 10 prompts mặc định")
    print("    2. Test với N prompts tùy chọn")
    print("    3. Load prompts từ file")
    print("    4. Nhập prompts thủ công")
    print(f"{'=' * 60}")

    choice = input("\nChọn (Enter=1): ").strip() or "1"

    prompts = []

    if choice == "1":
        prompts = DEFAULT_PROMPTS

    elif choice == "2":
        n = int(input("Số lượng prompts (1-100): ") or "10")
        n = min(max(1, n), 100)
        # Repeat default prompts
        prompts = (DEFAULT_PROMPTS * (n // len(DEFAULT_PROMPTS) + 1))[:n]

    elif choice == "3":
        file_path = input("Path to prompts file: ").strip()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                prompts = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error reading file: {e}")
            prompts = DEFAULT_PROMPTS

    elif choice == "4":
        print("Nhập prompts (mỗi dòng 1 prompt, dòng trống để kết thúc):")
        while True:
            p = input("> ").strip()
            if not p:
                break
            prompts.append(p)

    if not prompts:
        prompts = DEFAULT_PROMPTS

    print(f"\n→ Sẽ tạo {len(prompts)} ảnh")
    confirm = input("Tiếp tục? (Enter=yes, n=no): ").strip().lower()

    if confirm == 'n':
        print("Cancelled.")
        gen.cleanup()
        return

    try:
        gen.run_batch(prompts)
    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    finally:
        input("\nNhấn Enter để đóng Chrome...")
        gen.cleanup()


if __name__ == "__main__":
    main()
