#!/usr/bin/env python3
"""
Google Flow API - Batch Image Generator (Full Auto)
====================================================
Script nhập prompt, tự click Generate, download ảnh.
"""

import json
import time
import requests
from pathlib import Path

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

# JS interceptor - bắt response
JS_INTERCEPTOR = '''
(function(){
    if(window.__batchReady) return 'ALREADY_READY';
    window.__batchReady = true;
    window.__images = [];
    window.__imageTime = 0;

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const response = await origFetch.apply(this, arguments);
        const urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('batchGenerateImages')) {
            try {
                const clone = response.clone();
                const data = await clone.json();
                if (data.media && data.media.length > 0) {
                    window.__images = [];
                    for (const m of data.media) {
                        const imgUrl = m.image?.generatedImage?.fifeUrl;
                        if (imgUrl) window.__images.push(imgUrl);
                    }
                    window.__imageTime = Date.now();
                    console.log('[BATCH] Got', window.__images.length, 'images');
                }
            } catch(e) {}
        }
        return response;
    };
    console.log('[BATCH] Ready');
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
            print("    ⚠️ Hãy mở project Flow trong Chrome!")
            return False

        print("[3] Inject interceptor...")
        self.driver.run_js(JS_INTERCEPTOR)
        print("    ✓ OK")

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

    def wait_for_images(self, timeout=120):
        start = time.time()
        last_time = self.driver.run_js("return window.__imageTime || 0;")

        while time.time() - start < timeout:
            current = self.driver.run_js("return window.__imageTime || 0;")
            if current > last_time:
                images = self.driver.run_js("return window.__images || [];")
                self.driver.run_js("window.__images = []; window.__imageTime = 0;")
                return images
            time.sleep(0.5)
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

    def run_batch(self, prompts):
        print(f"\n{'=' * 60}")
        print(f"  TẠO {len(prompts)} ẢNH (Full Auto)")
        print(f"{'=' * 60}")

        self.stats["total"] = len(prompts)

        for i, prompt in enumerate(prompts):
            print(f"\n[{i+1}/{len(prompts)}] {prompt[:50]}...")

            # Nhập prompt
            textarea = self.find_textarea()
            if textarea:
                try:
                    textarea.clear()
                    time.sleep(0.3)
                    textarea.input(prompt)
                    print("    ✓ Đã nhập prompt")

                    # Nhấn Enter để gửi
                    time.sleep(0.3)
                    textarea.input('\n')
                    print("    ✓ Đã nhấn Enter")
                except Exception as e:
                    print(f"    ⚠️ Lỗi: {e}")

            # Chờ ảnh
            images = self.wait_for_images(timeout=120)

            if not images:
                print("    ❌ Timeout!")
                self.stats["failed"] += 1
                continue

            # Download
            saved = self.download_images(images, i)
            if saved:
                print(f"    ✓ Saved: {', '.join(saved)}")
                self.stats["success"] += 1
            else:
                print("    ❌ Download thất bại")
                self.stats["failed"] += 1

            time.sleep(2)

        print(f"\n{'=' * 60}")
        print(f"  HOÀN THÀNH: {self.stats['success']}/{self.stats['total']}")
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
            prompts = (DEFAULT_PROMPTS * 10)[:int(arg)]
        else:
            try:
                prompts = [l.strip() for l in open(arg, encoding='utf-8') if l.strip()]
            except:
                pass

    print(f"\n→ {len(prompts)} prompts")

    try:
        gen.run_batch(prompts)
    except KeyboardInterrupt:
        print("\n\nDừng!")

    print("\nXong!")


if __name__ == "__main__":
    main()
