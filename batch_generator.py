#!/usr/bin/env python3
"""
Google Flow API - Direct API Batch Generator
=============================================
Chặn request Chrome để lấy Bearer + recaptchaToken, rồi gọi API trực tiếp.
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime

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

# JS để chặn REQUEST và lấy tokens
JS_CAPTURE_REQUEST = '''
(function() {
    if (window.__captureReady) return 'ALREADY_READY';
    window.__captureReady = true;

    window.__captured = {
        bearer: null,
        recaptchaToken: null,
        projectId: null,
        xBrowserValidation: null,
        timestamp: 0
    };

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('batchGenerateImages')) {
            // Lấy headers
            if (opts?.headers) {
                if (opts.headers.Authorization) {
                    window.__captured.bearer = opts.headers.Authorization;
                }
                if (opts.headers['x-browser-validation']) {
                    window.__captured.xBrowserValidation = opts.headers['x-browser-validation'];
                }
            }

            // Lấy body (chứa recaptchaToken)
            if (opts?.body) {
                try {
                    const body = JSON.parse(opts.body);
                    if (body.recaptchaToken) {
                        window.__captured.recaptchaToken = body.recaptchaToken;
                    }
                    if (body.requests?.[0]?.clientContext?.projectId) {
                        window.__captured.projectId = body.requests[0].clientContext.projectId;
                    }
                    window.__captured.timestamp = Date.now();
                    console.log('[CAPTURED] Got tokens!');
                } catch(e) {}
            }
        }

        return origFetch.apply(this, arguments);
    };

    console.log('[INTERCEPTOR] Ready');
    return 'READY';
})();
'''


class DirectAPIGenerator:
    """Gọi API trực tiếp với tokens từ Chrome"""

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(self, bearer: str, recaptcha_token: str, project_id: str, x_browser: str = None):
        self.bearer = bearer
        self.recaptcha_token = recaptcha_token
        self.project_id = project_id
        self.x_browser = x_browser
        self.session_id = f"session_{int(time.time())}"
        self.stats = {"total": 0, "success": 0, "failed": 0}

    def generate_images(self, prompt: str, count: int = 4):
        """Gọi API trực tiếp"""
        url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"

        headers = {
            "Authorization": self.bearer,
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Origin": "https://aisandbox.google.com",
            "Referer": "https://aisandbox.google.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
        }

        if self.x_browser:
            headers["x-browser-validation"] = self.x_browser

        # Build payload giống Chrome
        requests_data = []
        for i in range(count):
            requests_data.append({
                "clientContext": {
                    "sessionId": self.session_id,
                    "projectId": self.project_id,
                    "tool": "IMAGE_FX"
                },
                "seed": int(time.time() * 1000) + i,
                "imageModelName": "GEM_PIX_2",
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": prompt,
                "imageInputs": []
            })

        payload = {
            "requests": requests_data,
            "recaptchaToken": self.recaptcha_token
        }

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                images = []
                if data.get("media"):
                    for m in data["media"]:
                        img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                        if img_url:
                            images.append(img_url)
                return images, None

            elif resp.status_code == 401:
                return [], "401 - Bearer token hết hạn"

            elif resp.status_code == 403:
                if "recaptcha" in resp.text.lower():
                    return [], "403 - recaptchaToken hết hạn"
                return [], f"403 - {resp.text[:100]}"

            else:
                return [], f"{resp.status_code} - {resp.text[:100]}"

        except Exception as e:
            return [], str(e)

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
        print(f"  DIRECT API - {len(prompts)} PROMPTS")
        print(f"{'=' * 60}")

        for idx, prompt in enumerate(prompts, 1):
            self.stats["total"] += 1
            print(f"\n[{idx}/{len(prompts)}] {prompt[:50]}...")

            images, error = self.generate_images(prompt)

            if error:
                print(f"    ✗ {error}")
                self.stats["failed"] += 1

                if "recaptcha" in error.lower() or "401" in error:
                    print("\n[STOP] Token hết hạn. Cần lấy token mới.")
                    break
                continue

            if images:
                saved = self.download_images(images, idx)
                print(f"    ✓ Saved {len(saved)} images")
                self.stats["success"] += 1
            else:
                print("    ✗ No images")
                self.stats["failed"] += 1

            time.sleep(1)

        print(f"\n{'=' * 60}")
        print(f"  Done: {self.stats['success']}/{self.stats['total']} success")
        print(f"  Output: {OUTPUT_DIR.absolute()}")


def main():
    print("=" * 60)
    print("  BATCH GENERATOR - DIRECT API")
    print("  Chặn Chrome request → Lấy tokens → Gọi API")
    print("=" * 60)

    # Connect Chrome
    print("\n[1] Kết nối Chrome port 9222...")
    options = ChromiumOptions()
    options.set_local_port(9222)

    try:
        driver = ChromiumPage(addr_or_opts=options)
        print(f"    ✓ URL: {driver.url}")
    except Exception as e:
        print(f"    ✗ {e}")
        print("\n    Mở Chrome với proxy trước:")
        print('    chrome.exe --proxy-server="socks5://127.0.0.1:1080" --remote-debugging-port=9222')
        return

    if "/project/" not in driver.url:
        print("\n    ⚠ Hãy mở project Flow trước!")
        input("    Nhấn ENTER khi đã sẵn sàng...")

    # Inject interceptor
    print("\n[2] Inject interceptor...")
    driver.run_js(JS_CAPTURE_REQUEST)
    print("    ✓ OK")

    # Wait for user to generate once
    print("\n[3] Click 'Generate' trong Chrome để lấy tokens...")
    print("    (Script sẽ chặn request và lấy Bearer + recaptchaToken)")

    captured = None
    for i in range(120):
        time.sleep(1)
        data = driver.run_js("return window.__captured;")
        if data and data.get("recaptchaToken") and data.get("bearer"):
            captured = data
            print(f"\n    ✓ Captured!")
            print(f"      Bearer: {data['bearer'][:50]}...")
            print(f"      recaptchaToken: {data['recaptchaToken'][:40]}...")
            break
        print(f"    Waiting... {i+1}s", end="\r")

    if not captured:
        print("\n    ✗ Timeout! Không lấy được tokens.")
        return

    # Run batch with API
    print("\n[4] Gọi API trực tiếp...")
    generator = DirectAPIGenerator(
        captured["bearer"],
        captured["recaptchaToken"],
        captured.get("projectId", driver.url.split("/project/")[1].split("/")[0]),
        captured.get("xBrowserValidation")
    )

    generator.run_batch(DEFAULT_PROMPTS)


if __name__ == "__main__":
    main()
