#!/usr/bin/env python3
"""
Google Flow API - Batch Image Generator (Full Auto)
====================================================
Tự động hoàn toàn: nhập prompt, click Generate, download ảnh.

Cách hoạt động:
- Để UI xử lý request bình thường (không block)
- Chỉ intercept RESPONSE để lấy image URLs
- DrissionPage click Generate
- Download ảnh từ response

Sử dụng:
    python batch_generator.py           # 10 prompts mặc định
    python batch_generator.py 20        # 20 prompts
    python batch_generator.py file.txt  # load từ file
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

OUTPUT_DIR = Path("./batch_output")
OUTPUT_DIR.mkdir(exist_ok=True)

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

# JS interceptor - capture RESPONSE (không block request)
JS_INTERCEPTOR = '''
(function(){
    if(window.__autoReady) return 'ALREADY_READY';
    window.__autoReady = true;
    window.__images = [];
    window.__imageTime = 0;

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const response = await origFetch.apply(this, arguments);
        const urlStr = typeof url === 'string' ? url : url.url;

        // Capture response from batchGenerateImages
        if (urlStr.includes('batchGenerateImages')) {
            try {
                const clone = response.clone();
                const data = await clone.json();

                if (data.media && data.media.length > 0) {
                    window.__images = [];
                    for (const m of data.media) {
                        const imgUrl = m.image?.generatedImage?.fifeUrl;
                        if (imgUrl) {
                            window.__images.push(imgUrl);
                        }
                    }
                    window.__imageTime = Date.now();
                    console.log('[AUTO] Got', window.__images.length, 'images');
                }
            } catch(e) {
                console.log('[AUTO] Parse error:', e);
            }
        }

        return response;
    };

    console.log('[AUTO] Interceptor ready');
    return 'READY';
})();
'''


class BatchGenerator:
    def __init__(self):
        self.driver = None
        self.stats = {"total": 0, "success": 0, "failed": 0}

    def setup(self):
        print("=" * 60)
        print("  BATCH GENERATOR (Full Auto)")
        print("=" * 60)

        print("\n[1] Kết nối Chrome port 9222...")
        options = ChromiumOptions()
        try:
            options.set_local_port(9222)
            self.driver = ChromiumPage(addr_or_opts=options)
            print("    ✓ OK")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            return False

        print(f"[2] URL: {self.driver.url}")
        if "/project/" not in self.driver.url:
            print("    ⚠️ Hãy mở project Flow trong Chrome trước!")
            return False

        print("[3] Inject interceptor...")
        result = self.driver.run_js(JS_INTERCEPTOR)
        print(f"    ✓ {result}")

        return True

    def find_textarea(self):
        for sel in ["tag:textarea", "css:textarea"]:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    return el
            except:
                pass
        return None

    def find_generate_button(self):
        selectors = [
            "@@text():Tạo",
            "@@text():Generate",
            "tag:button@@text():Tạo",
            "tag:button@@text():Generate",
        ]
        for sel in selectors:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    return el
            except:
                pass
        return None

    def wait_for_images(self, timeout=90):
        """Wait for images from response."""
        start = time.time()
        last_time = self.driver.run_js("return window.__imageTime || 0;")

        while time.time() - start < timeout:
            current_time = self.driver.run_js("return window.__imageTime || 0;")
            if current_time > last_time:
                images = self.driver.run_js("return window.__images || [];")
                # Clear for next
                self.driver.run_js("window.__images = []; window.__imageTime = 0;")
                return images
            time.sleep(1)

        return []

    def download_images(self, urls, idx):
        saved = []
        for i, url in enumerate(urls):
            try:
                resp = requests.get(url, timeout=60)
                if resp.status_code == 200:
                    filename = f"batch_{idx:03d}_{i+1}.png"
                    (OUTPUT_DIR / filename).write_bytes(resp.content)
                    saved.append(filename)
            except:
                pass
        return saved

    def generate_one(self, prompt, idx, total):
        print(f"\n[{idx+1}/{total}] {prompt[:50]}...")

        # Enter prompt
        textarea = self.find_textarea()
        if textarea:
            try:
                textarea.clear()
                time.sleep(0.2)
                textarea.input(prompt)
                print("    ✓ Nhập prompt")
            except Exception as e:
                print(f"    ❌ Lỗi nhập: {e}")
                return False

        # Click Generate
        gen_btn = self.find_generate_button()
        if not gen_btn:
            print("    ❌ Không tìm thấy nút Generate")
            return False

        try:
            gen_btn.click()
            print("    ✓ Click Generate")
        except Exception as e:
            print(f"    ❌ Lỗi click: {e}")
            return False

        # Wait for response
        print("    → Đang chờ ảnh...")
        images = self.wait_for_images(timeout=90)

        if not images:
            print("    ❌ Timeout!")
            return False

        # Download
        saved = self.download_images(images, idx)
        if saved:
            print(f"    ✓ Saved: {', '.join(saved)}")
            return True
        else:
            print("    ❌ Download thất bại")
            return False

    def run_batch(self, prompts):
        print(f"\n{'=' * 60}")
        print(f"  TẠO {len(prompts)} ẢNH (Full Auto)")
        print(f"{'=' * 60}")

        self.stats["total"] = len(prompts)

        for i, prompt in enumerate(prompts):
            success = self.generate_one(prompt, i, len(prompts))

            if success:
                self.stats["success"] += 1
            else:
                self.stats["failed"] += 1

            # Delay between prompts
            if i < len(prompts) - 1:
                delay = random.uniform(2, 4)
                print(f"    ... chờ {delay:.1f}s")
                time.sleep(delay)

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

    prompts = DEFAULT_PROMPTS

    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg.isdigit():
            n = int(arg)
            prompts = (DEFAULT_PROMPTS * 10)[:n]
            print(f"\n→ {n} prompts")
        else:
            try:
                prompts = [l.strip() for l in open(arg, encoding='utf-8') if l.strip()]
                print(f"\n→ {len(prompts)} prompts từ {arg}")
            except:
                print(f"    ⚠️ Không đọc được {arg}")
    else:
        print(f"\n→ {len(prompts)} prompts mặc định")

    try:
        gen.run_batch(prompts)
    except KeyboardInterrupt:
        print("\n\nDừng!")

    print("\nXong!")


if __name__ == "__main__":
    main()
