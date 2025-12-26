#!/usr/bin/env python3
"""
Google Flow API - Batch Image Generator (UI Automation)
========================================================
Tự động tạo nhiều ảnh bằng DrissionPage - click Generate trong UI.

Vì API yêu cầu reCAPTCHA token từ user interaction,
script này sẽ tự động click nút Generate và download ảnh.

Workflow:
1. Mở Chrome, đăng nhập Google, vào project Flow
2. Với mỗi prompt: nhập prompt -> click Generate -> chờ ảnh -> download
3. Lưu ảnh và thống kê

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
import random
import re

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("Cần cài đặt: pip install DrissionPage requests")
    exit(1)

# Config
OUTPUT_DIR = Path("./batch_output")
OUTPUT_DIR.mkdir(exist_ok=True)

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

# JS to intercept API REQUEST and capture payload (including recaptchaToken)
JS_REQUEST_INTERCEPTOR = '''
(function(){
    if(window.__requestInterceptorReady) return 'ALREADY_READY';
    window.__requestInterceptorReady = true;
    window.__capturedPayload = null;
    window.__capturedBearer = null;
    window.__capturedTime = 0;

    // Intercept fetch to capture payload BEFORE sending
    if (!window.__origFetch) {
        window.__origFetch = window.fetch;
    }

    window.fetch = async function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        // Capture Bearer from any request
        if (opts && opts.headers) {
            const auth = opts.headers['Authorization'] || opts.headers['authorization'];
            if (auth && auth.startsWith('Bearer ')) {
                window.__capturedBearer = auth;
            }
        }

        if (urlStr.includes('batchGenerateImages')) {
            // Capture the payload
            window.__capturedPayload = opts.body;
            window.__capturedTime = Date.now();
            console.log('[BATCH] Captured payload at', new Date().toISOString());

            // BLOCK the original request - we'll send it via Python
            return new Response(JSON.stringify({blocked: true}), {status: 200});
        }

        return window.__origFetch.apply(this, arguments);
    };

    console.log('[BATCH] Request interceptor ready');
    return 'READY';
})();
'''

# JS to get captured payload
JS_GET_PAYLOAD = '''
(function(){
    const payload = window.__capturedPayload;
    const bearer = window.__capturedBearer;
    const time = window.__capturedTime;
    // Clear after reading
    window.__capturedPayload = null;
    window.__capturedTime = 0;
    return { payload: payload, bearer: bearer, time: time };
})();
'''


class BatchGenerator:
    def __init__(self):
        self.driver = None
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": []
        }

    def setup(self):
        """Setup browser."""
        print("=" * 60)
        print("  BATCH IMAGE GENERATOR (UI Automation)")
        print("=" * 60)

        # Chrome
        print("\n[1] MỞ CHROME...")
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
        print("\n[2] URL")
        print(f"    URL hiện tại: {self.driver.url}")
        print("\n    Nhập URL project Flow (phải có /project/xxx):")
        print("    - Enter = giữ nguyên")
        print("    - Hoặc paste URL project")
        url_input = input("    URL: ").strip()

        if url_input:
            print(f"    → Đi tới: {url_input}")
            self.driver.get(url_input)
            print("    → Đang chờ trang load...")
            time.sleep(5)

        # Debug: show current URL
        print(f"    → URL hiện tại: {self.driver.url}")

        # Check project URL
        if "/project/" not in self.driver.url:
            print("    ⚠️ URL không có /project/xxx!")
            print("    Cần mở project Flow trước")
            return False

        # Check login
        if "accounts.google" in self.driver.url:
            print("    ⚠️ Cần đăng nhập Google!")
            input("    Đăng nhập xong nhấn Enter...")
            time.sleep(2)

        # Wait for user to confirm page is ready
        input("\n    Trang đã load xong? Nhấn Enter để tiếp tục...")

        # Inject request interceptor
        print("\n[3] INJECT REQUEST INTERCEPTOR...")
        try:
            result = self.driver.run_js(JS_REQUEST_INTERCEPTOR)
            print(f"    ✓ Result: {result}")
        except Exception as e:
            print(f"    ⚠️ JS warning: {e}")

        # Find UI elements
        print("\n[4] KIỂM TRA UI ELEMENTS...")
        textarea = self.find_prompt_input()
        gen_btn = self.find_generate_button()

        if textarea:
            print("    ✓ Tìm thấy textarea")
        else:
            print("    ❌ Không tìm thấy textarea!")
            return False

        if gen_btn:
            print("    ✓ Tìm thấy nút Generate")
        else:
            print("    ❌ Không tìm thấy nút Generate!")
            return False

        return True

    def find_prompt_input(self):
        """Find the prompt input element."""
        selectors = [
            "tag:textarea",
            "css:textarea",
            "css:[contenteditable='true']",
        ]

        for sel in selectors:
            try:
                el = self.driver.ele(sel, timeout=3)
                if el:
                    return el
            except:
                continue
        return None

    def find_generate_button(self):
        """Find the Generate button."""
        selectors = [
            "@@text():Tạo",
            "@@text():Generate",
            "tag:button@@text():Tạo",
            "tag:button@@text():Generate",
        ]

        for sel in selectors:
            try:
                el = self.driver.ele(sel, timeout=3)
                if el:
                    return el
            except:
                continue
        return None

    def wait_for_payload(self, timeout=30):
        """Wait for payload to be captured from intercepted request."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            result = self.driver.run_js(JS_GET_PAYLOAD)

            if result and result.get("payload"):
                return result

            time.sleep(0.5)

        return None

    def call_api(self, payload_str, bearer):
        """Call API with captured payload."""
        try:
            payload = json.loads(payload_str)
        except Exception as e:
            print(f"    ❌ JSON parse error: {e}")
            return None

        # Get project ID from payload
        project_id = payload.get("requests", [{}])[0].get("clientContext", {}).get("projectId", "")

        if not project_id:
            print("    ❌ No projectId in payload!")
            return None

        url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

        headers = {
            "Authorization": bearer,
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"    ❌ API {resp.status_code}: {resp.text[:100]}")
                return None
        except Exception as e:
            print(f"    ❌ API error: {e}")
            return None

    def generate_one(self, prompt, idx):
        """Generate one image with given prompt using UI automation + API call."""
        print(f"\n[{idx+1}] {prompt[:50]}...")

        try:
            # Find textarea
            textarea = self.find_prompt_input()
            if not textarea:
                print("    ❌ Không tìm thấy textarea!")
                return False, []

            # Clear and enter prompt
            try:
                textarea.clear()
                time.sleep(0.3)
                textarea.input(prompt)
                time.sleep(0.5)
                print("    → Đã nhập prompt")
            except Exception as e:
                print(f"    ❌ Lỗi nhập prompt: {e}")
                return False, []

            # Try multiple methods to submit
            submitted = False

            # Method 1: Press Enter in textarea
            try:
                # Press Ctrl+Enter to submit
                textarea.input('\n')  # Sometimes Enter submits
                time.sleep(0.5)

                # Check if payload was captured
                check = self.driver.run_js("return window.__capturedPayload !== null;")
                if check:
                    submitted = True
                    print("    → Đã submit bằng Enter")
            except:
                pass

            # Method 2: Find and click Generate button
            if not submitted:
                gen_btn = self.find_generate_button()
                if gen_btn:
                    try:
                        # Try JS click first (more reliable)
                        self.driver.run_js("arguments[0].click();", gen_btn)
                        time.sleep(0.5)

                        check = self.driver.run_js("return window.__capturedPayload !== null;")
                        if check:
                            submitted = True
                            print("    → Đã click Generate (JS)")
                    except:
                        pass

                    if not submitted:
                        try:
                            gen_btn.click()
                            print("    → Đã click Generate")
                            submitted = True
                        except Exception as e:
                            print(f"    ⚠️ Click warning: {e}")

            # Method 3: Click using keyboard shortcut or action
            if not submitted:
                try:
                    # Try clicking any visible button with "Tạo" or "Generate"
                    self.driver.run_js('''
                        const btns = document.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.textContent.includes('Tạo') || btn.textContent.includes('Generate')) {
                                btn.click();
                                break;
                            }
                        }
                    ''')
                    print("    → Đã click button qua JS querySelectorAll")
                    submitted = True
                except:
                    pass

            if not submitted:
                print("    ❌ Không thể submit!")
                return False, []

            # Wait for payload to be captured
            print("    → Đang chờ payload...")
            captured = self.wait_for_payload(timeout=15)

            if not captured or not captured.get("payload"):
                print("    ❌ Timeout - không bắt được payload!")
                return False, []

            payload_str = captured.get("payload")
            bearer = captured.get("bearer")

            if not bearer:
                print("    ❌ Không có Bearer token!")
                return False, []

            print(f"    → Payload captured, calling API...")

            # Call API with captured payload
            result = self.call_api(payload_str, bearer)

            if not result:
                return False, []

            # Extract and download images
            images = []
            if "media" in result:
                for m in result["media"]:
                    img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                    if img_url:
                        images.append({"url": img_url, "seed": m.get("seed", "unknown")})

            if not images:
                print("    ❌ No images in response!")
                return False, []

            print(f"    ✓ Got {len(images)} images")

            # Download images
            saved = []
            for i, img in enumerate(images):
                url = img.get("url")
                if url:
                    try:
                        resp = requests.get(url, timeout=60)
                        if resp.status_code == 200:
                            filename = f"batch_{idx:03d}_{i+1}.png"
                            (OUTPUT_DIR / filename).write_bytes(resp.content)
                            saved.append(filename)
                            print(f"      ✓ Saved: {filename}")
                    except Exception as e:
                        print(f"      ❌ Download error: {e}")

            return len(saved) > 0, saved

        except Exception as e:
            print(f"    ❌ Exception: {e}")
            return False, []

    def run_batch(self, prompts):
        """Run batch generation."""
        print(f"\n{'=' * 60}")
        print(f"  BATCH GENERATION: {len(prompts)} prompts")
        print(f"{'=' * 60}")

        self.stats["total"] = len(prompts)

        for i, prompt in enumerate(prompts):
            try:
                success, saved = self.generate_one(prompt, i)

                if success:
                    self.stats["success"] += 1
                else:
                    self.stats["failed"] += 1
                    self.stats["errors"].append(f"Prompt {i+1}: Failed")

            except Exception as e:
                self.stats["failed"] += 1
                self.stats["errors"].append(f"Prompt {i+1}: {str(e)}")

            # Delay between requests
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
        if self.stats['total'] > 0:
            print(f"  Success rate: {self.stats['success']/self.stats['total']*100:.1f}%")
        print(f"  Output: {OUTPUT_DIR.absolute()}")

        if self.stats["errors"]:
            print(f"\n  Errors:")
            for err in self.stats["errors"][:10]:
                print(f"    - {err}")

    def cleanup(self):
        if self.driver:
            # Don't quit - keep browser open
            pass


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
        input("\nNhấn Enter để kết thúc...")
        gen.cleanup()


if __name__ == "__main__":
    main()
