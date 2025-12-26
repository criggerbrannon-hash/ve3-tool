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

        # Auto connect to port 9222
        print("\n[1] Kết nối Chrome port 9222...")
        options = ChromiumOptions()
        try:
            options.set_local_port(9222)
            self.driver = ChromiumPage(addr_or_opts=options)
            print("    ✓ OK")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            print("    Hãy mở Chrome với: chrome --remote-debugging-port=9222")
            return False

        # Check URL
        print(f"[2] URL: {self.driver.url}")
        if "/project/" not in self.driver.url:
            print("    ⚠️ Hãy mở project Flow trong Chrome trước!")
            return False

        # Inject
        print("[3] Inject interceptor...")
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
    import sys

    gen = BatchGenerator()

    if not gen.setup():
        return

    # Check command line args for prompts file
    prompts = DEFAULT_PROMPTS

    if len(sys.argv) > 1:
        # First arg could be number or file path
        arg = sys.argv[1]
        if arg.isdigit():
            n = int(arg)
            prompts = (DEFAULT_PROMPTS * 10)[:n]
            print(f"\n→ {n} prompts (từ command line)")
        else:
            try:
                prompts = [l.strip() for l in open(arg, encoding='utf-8') if l.strip()]
                print(f"\n→ {len(prompts)} prompts từ {arg}")
            except:
                print(f"    ⚠️ Không đọc được file {arg}, dùng mặc định")
    else:
        print(f"\n→ {len(prompts)} prompts mặc định")
        print("   (Dùng: python batch_generator.py 20  hoặc  python batch_generator.py prompts.txt)")

    try:
        gen.run_batch(prompts)
    except KeyboardInterrupt:
        print("\n\nDừng!")

    print("\nXong!")


if __name__ == "__main__":
    main()
