#!/usr/bin/env python3
"""
Google Flow API - Direct API Batch Generator
=============================================
Chrome chạy qua IPv6 proxy để bypass IP block.
Script chặn request để lấy recaptchaToken, sau đó gọi API trực tiếp.
"""

import json
import time
import requests
from pathlib import Path
from typing import Optional, List, Tuple
import threading

# Import proxy
from ipv6_rotate_proxy import IPv6Rotator, ProxyServer, IPV6_LIST, PROXY_PORT

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

# JavaScript để chặn request và lấy tokens
JS_INTERCEPT_REQUEST = '''
(function() {
    if (window.__interceptReady) return 'ALREADY_READY';
    window.__interceptReady = true;

    // Store captured data
    window.__capturedData = {
        bearerToken: null,
        recaptchaToken: null,
        projectId: null,
        lastCapture: 0
    };

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        // Chặn request batchGenerateImages để lấy tokens
        if (urlStr.includes('batchGenerateImages')) {
            // Lấy Bearer token từ headers
            if (opts?.headers) {
                const auth = opts.headers.Authorization || opts.headers.authorization;
                if (auth) {
                    window.__capturedData.bearerToken = auth;
                }
            }

            // Lấy recaptchaToken từ body
            if (opts?.body) {
                try {
                    const body = JSON.parse(opts.body);
                    if (body.recaptchaToken) {
                        window.__capturedData.recaptchaToken = body.recaptchaToken;
                        window.__capturedData.lastCapture = Date.now();
                        console.log('[INTERCEPTED] Got recaptchaToken!');
                    }
                    // Lấy projectId
                    if (body.clientContext?.projectId) {
                        window.__capturedData.projectId = body.clientContext.projectId;
                    }
                } catch(e) {}
            }
        }

        return origFetch.apply(this, arguments);
    };

    console.log('[INTERCEPTOR] Ready to capture tokens');
    return 'READY';
})();
'''


class DirectAPIGenerator:
    """Gọi API trực tiếp sử dụng tokens từ Chrome"""

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(self, bearer_token: str, recaptcha_token: str, project_id: str):
        self.bearer_token = bearer_token
        self.recaptcha_token = recaptcha_token
        self.project_id = project_id
        self.session_id = f"session_{int(time.time())}"

        # Session không cần proxy - gọi API trực tiếp
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": bearer_token,
            "Content-Type": "application/json",
            "Origin": "https://aisandbox.google.com",
            "Referer": "https://aisandbox.google.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0"
        })

        self.stats = {"total": 0, "success": 0, "failed": 0}

    def generate_images(self, prompt: str, count: int = 4) -> Tuple[List[str], Optional[str]]:
        """Gọi API generate images với recaptchaToken"""
        url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"

        # Build requests
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
            "clientContext": {
                "sessionId": self.session_id,
                "projectId": self.project_id,
                "tool": "IMAGE_FX"
            },
            "requests": requests_data,
            "recaptchaToken": self.recaptcha_token  # Token từ Chrome
        }

        try:
            response = self.session.post(url, json=payload, timeout=120)

            if response.status_code == 200:
                data = response.json()
                images = []
                if data.get("media"):
                    for m in data["media"]:
                        img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                        if img_url:
                            images.append(img_url)
                return images, None

            elif response.status_code == 401:
                return [], "Token expired"

            elif response.status_code == 403:
                try:
                    err = response.json()
                    msg = err.get("error", {}).get("message", "")[:100]
                except:
                    msg = response.text[:100]
                return [], f"403: {msg}"

            else:
                return [], f"HTTP {response.status_code}"

        except Exception as e:
            return [], str(e)

    def download_image(self, url: str, filename: str) -> bool:
        try:
            resp = self.session.get(url, timeout=60)
            if resp.status_code == 200:
                (OUTPUT_DIR / filename).write_bytes(resp.content)
                return True
        except:
            pass
        return False

    def run_batch(self, prompts: List[str]):
        print("\n" + "=" * 50)
        print("  DIRECT API BATCH GENERATION")
        print(f"  Project: {self.project_id}")
        print("=" * 50)

        for idx, prompt in enumerate(prompts, 1):
            self.stats["total"] += 1
            short = prompt[:45] + "..." if len(prompt) > 45 else prompt
            print(f"\n[{idx}/{len(prompts)}] {short}")

            images, error = self.generate_images(prompt)

            if error:
                print(f"    ✗ {error}")
                self.stats["failed"] += 1

                if "403" in error and "recaptcha" in error.lower():
                    print("\n[STOP] recaptchaToken hết hạn. Cần lấy token mới.")
                    break
                continue

            if not images:
                print("    ✗ Không có ảnh")
                self.stats["failed"] += 1
                continue

            saved = 0
            for i, img_url in enumerate(images):
                if self.download_image(img_url, f"batch_{idx:03d}_{i+1}.png"):
                    saved += 1

            if saved > 0:
                print(f"    ✓ Saved {saved} images")
                self.stats["success"] += 1
            else:
                print("    ✗ Download failed")
                self.stats["failed"] += 1

            time.sleep(1)

        print("\n" + "=" * 50)
        print(f"  Total: {self.stats['total']} | Success: {self.stats['success']} | Failed: {self.stats['failed']}")
        print(f"  Output: {OUTPUT_DIR.absolute()}")


def main():
    print("=" * 60)
    print("  GOOGLE FLOW - DIRECT API GENERATOR")
    print("  Chrome (IPv6 proxy) → Capture tokens → API calls")
    print("=" * 60)
    print()

    # 1. Start IPv6 proxy for Chrome
    print("[1] Starting IPv6 proxy...")
    try:
        rotator = IPv6Rotator(IPV6_LIST)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    proxy = ProxyServer(rotator)
    proxy.start()
    time.sleep(1)

    # 2. Connect to Chrome
    print("\n[2] Connecting to Chrome...")
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        print("[ERROR] pip install DrissionPage")
        return

    options = ChromiumOptions()
    options.set_local_port(9222)

    try:
        driver = ChromiumPage(addr_or_opts=options)
    except Exception as e:
        print(f"[ERROR] {e}")
        print("\n[TIP] Mở Chrome với proxy:")
        print('  chrome.exe --proxy-server="socks5://127.0.0.1:1080" --remote-debugging-port=9222')
        return

    url = driver.url
    print(f"    URL: {url}")

    if "/project/" not in url:
        print("\n[WARN] Hãy mở project trong Flow trước!")
        input("Nhấn ENTER khi đã sẵn sàng...")

    # 3. Inject interceptor
    print("\n[3] Injecting token interceptor...")
    driver.run_js(JS_INTERCEPT_REQUEST)

    # 4. Wait for user to click Generate
    print("\n[4] Click 'Generate' trong Chrome để lấy tokens...")
    print("    (Script sẽ chặn request và lấy bearerToken + recaptchaToken)")

    captured = None
    for i in range(120):
        time.sleep(1)
        data = driver.run_js("return window.__capturedData;")
        if data and data.get("recaptchaToken") and data.get("bearerToken"):
            captured = data
            print(f"\n[OK] Captured tokens!")
            print(f"    Bearer: {data['bearerToken'][:50]}...")
            print(f"    reCAPTCHA: {data['recaptchaToken'][:50]}...")
            break
        print(f"    Waiting... {i+1}s", end="\r")

    if not captured:
        print("\n[ERROR] Không lấy được tokens")
        return

    # 5. Run batch with captured tokens
    print("\n[5] Starting batch generation...")
    generator = DirectAPIGenerator(
        captured["bearerToken"],
        captured["recaptchaToken"],
        captured.get("projectId", url.split("/project/")[1].split("/")[0])
    )
    generator.run_batch(DEFAULT_PROMPTS)


if __name__ == "__main__":
    main()
