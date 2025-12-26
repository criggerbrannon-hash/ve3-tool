#!/usr/bin/env python3
"""
Google Flow API - Batch Image Generator (Semi-Auto)
====================================================
Script nhập prompt tự động, user click Generate, script download ảnh.

Đây là cách đã test thành công với test_debug.py:
1. Script inject interceptor và nhập prompt
2. User click Generate (trigger reCAPTCHA thật)
3. Script bắt payload và gọi API
4. Script download ảnh

Cài đặt:
    pip install DrissionPage requests
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
import random

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

# JS interceptor - giống test_debug.py
JS_INTERCEPTOR = '''
(function(){
    if(window.__batchReady) return 'ALREADY_READY';
    window.__batchReady = true;
    window.__payload = null;
    window.__bearer = null;
    window.__payloadTime = 0;

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        // Capture Bearer
        if (opts && opts.headers) {
            const auth = opts.headers['Authorization'] || opts.headers['authorization'];
            if (auth && auth.startsWith('Bearer ')) {
                window.__bearer = auth;
            }
        }

        // Capture payload for batchGenerateImages
        if (urlStr.includes('batchGenerateImages')) {
            window.__payload = opts.body;
            window.__payloadTime = Date.now();
            console.log('[BATCH] Payload captured!');
            // Block original - we send via Python
            return new Response('{"blocked":true}', {status: 200});
        }

        return origFetch.apply(this, arguments);
    };

    console.log('[BATCH] Interceptor ready');
    return 'READY';
})();
'''


class BatchGenerator:
    def __init__(self):
        self.driver = None
        self.stats = {"total": 0, "success": 0, "failed": 0}

    def setup(self):
        print("=" * 60)
        print("  BATCH GENERATOR (Semi-Auto)")
        print("  Script nhập prompt, bạn click Generate")
        print("=" * 60)

        # Chrome
        print("\n[1] CHROME")
        print("    1 = Mở Chrome mới")
        print("    2 = Kết nối port 9222")
        choice = input("    Chọn (Enter=2): ").strip() or "2"

        options = ChromiumOptions()
        try:
            if choice == "2":
                options.set_local_port(9222)
                self.driver = ChromiumPage(addr_or_opts=options)
                print("    ✓ Kết nối port 9222")
            else:
                self.driver = ChromiumPage(options)
                print("    ✓ Chrome mới")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            return False

        # URL
        print(f"\n[2] URL hiện tại: {self.driver.url}")
        if "/project/" not in self.driver.url:
            print("    ⚠️ Cần mở project Flow trước!")
            url = input("    Nhập URL (hoặc Enter để tiếp tục): ").strip()
            if url:
                self.driver.get(url)
                time.sleep(3)

        # Inject
        print("\n[3] INJECT INTERCEPTOR...")
        result = self.driver.run_js(JS_INTERCEPTOR)
        print(f"    ✓ {result}")

        return True

    def get_payload(self):
        """Get captured payload."""
        result = self.driver.run_js('''
            return {
                payload: window.__payload,
                bearer: window.__bearer,
                time: window.__payloadTime
            };
        ''')
        # Clear after reading
        self.driver.run_js('window.__payload = null; window.__payloadTime = 0;')
        return result

    def call_api(self, payload_str, bearer):
        """Call API - giống test_debug.py"""
        try:
            payload = json.loads(payload_str)
        except:
            return None

        project_id = payload.get("requests", [{}])[0].get("clientContext", {}).get("projectId", "")
        url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

        headers = {
            "Authorization": bearer,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }

        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"    ❌ API {resp.status_code}")
            return None

    def download_images(self, result, idx):
        """Download images from result."""
        saved = []
        if "media" in result:
            for i, m in enumerate(result["media"]):
                img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                if img_url:
                    try:
                        resp = requests.get(img_url, timeout=60)
                        if resp.status_code == 200:
                            filename = f"batch_{idx:03d}_{i+1}.png"
                            (OUTPUT_DIR / filename).write_bytes(resp.content)
                            saved.append(filename)
                    except:
                        pass
        return saved

    def find_textarea(self):
        """Find textarea."""
        for sel in ["tag:textarea", "css:textarea"]:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    return el
            except:
                pass
        return None

    def run_batch(self, prompts):
        print(f"\n{'=' * 60}")
        print(f"  SẼ TẠO {len(prompts)} ẢNH")
        print(f"  Mỗi prompt: script nhập → bạn click Generate → script download")
        print(f"{'=' * 60}")

        self.stats["total"] = len(prompts)

        for i, prompt in enumerate(prompts):
            print(f"\n[{i+1}/{len(prompts)}] {prompt[:50]}...")

            # Find and fill textarea
            textarea = self.find_textarea()
            if textarea:
                try:
                    textarea.clear()
                    time.sleep(0.2)
                    textarea.input(prompt)
                    print("    ✓ Đã nhập prompt")
                except Exception as e:
                    print(f"    ⚠️ Không nhập được: {e}")
            else:
                print("    ⚠️ Không tìm thấy textarea")

            # Wait for user to click Generate
            print("    → BẠN CLICK 'Generate' TRONG CHROME...")

            # Poll for payload
            start = time.time()
            payload_data = None
            while time.time() - start < 120:  # 2 minutes timeout
                data = self.get_payload()
                if data and data.get("payload"):
                    payload_data = data
                    break
                time.sleep(0.5)

            if not payload_data:
                print("    ❌ Timeout - bạn chưa click Generate?")
                self.stats["failed"] += 1
                continue

            print("    ✓ Payload captured!")

            # Call API
            result = self.call_api(payload_data["payload"], payload_data["bearer"])
            if not result:
                self.stats["failed"] += 1
                continue

            # Download
            saved = self.download_images(result, i)
            if saved:
                print(f"    ✓ Saved: {', '.join(saved)}")
                self.stats["success"] += 1
            else:
                print("    ❌ Không download được ảnh")
                self.stats["failed"] += 1

            # Small delay
            if i < len(prompts) - 1:
                time.sleep(1)

        # Stats
        print(f"\n{'=' * 60}")
        print(f"  HOÀN THÀNH!")
        print(f"  Success: {self.stats['success']}/{self.stats['total']}")
        print(f"  Failed: {self.stats['failed']}")
        print(f"  Output: {OUTPUT_DIR.absolute()}")
        print(f"{'=' * 60}")


def main():
    gen = BatchGenerator()

    if not gen.setup():
        return

    # Prompts
    print(f"\n{'=' * 60}")
    print("  CHỌN PROMPTS:")
    print("    1 = 10 prompts mặc định")
    print("    2 = Nhập số lượng")
    print("    3 = Load từ file")
    print(f"{'=' * 60}")

    choice = input("\nChọn (Enter=1): ").strip() or "1"

    if choice == "1":
        prompts = DEFAULT_PROMPTS
    elif choice == "2":
        n = int(input("Số lượng (1-100): ") or "10")
        prompts = (DEFAULT_PROMPTS * 10)[:n]
    elif choice == "3":
        path = input("Path file: ").strip()
        try:
            prompts = [l.strip() for l in open(path, encoding='utf-8') if l.strip()]
        except:
            prompts = DEFAULT_PROMPTS
    else:
        prompts = DEFAULT_PROMPTS

    print(f"\n→ {len(prompts)} prompts")
    input("Nhấn Enter để bắt đầu...")

    try:
        gen.run_batch(prompts)
    except KeyboardInterrupt:
        print("\n\nDừng!")

    input("\nNhấn Enter để kết thúc...")


if __name__ == "__main__":
    main()
