#!/usr/bin/env python3
"""
Google Flow API - Batch Generator (Full Auto)
==============================================
Capture Bearer token từ Chrome, gọi API generateContent.
"""

import json
import time
import requests
import base64
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

# JS capture Authorization header (không cần recaptchaToken)
JS_INTERCEPTOR = '''
(function(){
    if(window.__interceptReady) return 'ALREADY_READY';
    window.__interceptReady = true;
    window.__captured = [];

    const origFetch = window.fetch;
    window.fetch = function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('aisandbox-pa.googleapis.com')) {
            let auth = null;
            if (opts?.headers) {
                if (opts.headers.Authorization) {
                    auth = opts.headers.Authorization;
                } else if (opts.headers.get) {
                    auth = opts.headers.get('Authorization');
                } else if (typeof opts.headers === 'object') {
                    for (let key in opts.headers) {
                        if (key.toLowerCase() === 'authorization') {
                            auth = opts.headers[key];
                            break;
                        }
                    }
                }
            }

            if (auth && auth.startsWith('Bearer ')) {
                window.__captured.push({
                    token: auth,
                    url: urlStr,
                    timestamp: Date.now()
                });
                console.log('[CAPTURED] Bearer token!');
            }
        }
        return origFetch.apply(this, arguments);
    };
    console.log('[INTERCEPTOR] Ready');
    return 'READY';
})();
'''


class BatchGenerator:
    # API endpoint cho generateContent
    API_URL = "https://aisandbox-pa.googleapis.com/v1beta/models/imagen-3.0-capability-001:generateContent"

    def __init__(self):
        self.driver = None
        self.bearer = None
        self.stats = {"total": 0, "success": 0, "failed": 0}

    def setup(self):
        print("=" * 60)
        print("  BATCH GENERATOR (Full Auto + API)")
        print("=" * 60)

        print("\n[1] Kết nối Chrome port 9222...")
        options = ChromiumOptions()
        try:
            options.set_local_port(9222)
            self.driver = ChromiumPage(addr_or_opts=options)
            print(f"    ✓ URL: {self.driver.url}")
        except Exception as e:
            print(f"    ✗ {e}")
            return False

        print("\n[2] Inject interceptor...")
        self.driver.run_js("window.__interceptReady = false; window.__captured = [];")
        time.sleep(0.3)
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

    def get_bearer_token(self, prompt):
        """Gửi prompt để capture Bearer token"""
        print(f"\n[3] Gửi prompt để lấy Bearer token...")
        print(f"    Prompt: {prompt[:50]}...")

        textarea = self.find_textarea()
        if textarea:
            textarea.clear()
            time.sleep(0.2)
            textarea.input(prompt)
            time.sleep(0.3)
            textarea.input('\n')
            print("    ✓ Đã gửi")

        print("    Đợi capture token...")
        for i in range(30):
            time.sleep(1)
            captured = self.driver.run_js("return window.__captured || [];")
            if captured and len(captured) > 0:
                latest = captured[-1]
                self.bearer = latest.get("token")
                if self.bearer:
                    print(f"    ✓ Got Bearer token!")
                    return True
            print(f"    {i+1}s...", end="\r")

        print("    ✗ Không lấy được token")
        return False

    def call_api(self, prompt, count=4):
        """Gọi API generateContent"""
        headers = {
            "Authorization": self.bearer,
            "Content-Type": "application/json",
            "Origin": "https://aisandbox.google.com",
            "Referer": "https://aisandbox.google.com/",
        }

        payload = {
            "imageGenerationConfig": {
                "numberOfImages": count,
                "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE"
            },
            "modelInput": {
                "prompt": prompt
            }
        }

        try:
            resp = requests.post(self.API_URL, headers=headers, json=payload, timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                images = []

                # Parse response - images in candidates[].content.parts[].inlineData.data
                for candidate in data.get("candidates", []):
                    for part in candidate.get("content", {}).get("parts", []):
                        inline = part.get("inlineData", {})
                        if inline.get("data"):
                            images.append(inline["data"])  # base64 image

                return images, None
            else:
                return [], f"{resp.status_code}: {resp.text[:100]}"

        except Exception as e:
            return [], str(e)

    def save_images(self, images_b64, idx):
        """Save base64 images"""
        saved = []
        for i, b64 in enumerate(images_b64):
            try:
                img_data = base64.b64decode(b64)
                filename = f"batch_{idx:03d}_{i+1}.png"
                (OUTPUT_DIR / filename).write_bytes(img_data)
                saved.append(filename)
            except:
                pass
        return saved

    def run_batch(self, prompts):
        # Prompt đầu tiên: gửi qua UI để lấy token
        if not self.get_bearer_token(prompts[0]):
            return

        self.stats["success"] += 1
        print(f"    (Prompt 1 đã xử lý bởi Chrome)")

        # Các prompt còn lại: gọi API
        print(f"\n[4] Gọi API cho {len(prompts)-1} prompts còn lại...")

        for idx, prompt in enumerate(prompts[1:], 2):
            self.stats["total"] += 1
            print(f"\n[{idx}/{len(prompts)}] {prompt[:50]}...")

            images, error = self.call_api(prompt)

            if error:
                print(f"    ✗ {error}")
                self.stats["failed"] += 1
                if "401" in error or "403" in error:
                    print("\n[STOP] Token hết hạn!")
                    break
                continue

            if images:
                saved = self.save_images(images, idx)
                print(f"    ✓ Saved {len(saved)} images")
                self.stats["success"] += 1
            else:
                print("    ✗ No images")
                self.stats["failed"] += 1

            time.sleep(1)

        print(f"\n{'=' * 60}")
        print(f"  DONE: {self.stats['success']}/{len(prompts)}")
        print(f"  Output: {OUTPUT_DIR.absolute()}")
        print("=" * 60)


def main():
    gen = BatchGenerator()
    if not gen.setup():
        return

    gen.stats["total"] = len(DEFAULT_PROMPTS)
    gen.run_batch(DEFAULT_PROMPTS)


if __name__ == "__main__":
    main()
