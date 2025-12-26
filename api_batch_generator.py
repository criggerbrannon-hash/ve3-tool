#!/usr/bin/env python3
"""
Google Flow API - Direct API Batch Generator
=============================================
Gọi API trực tiếp với IPv6 rotating proxy.
Cần lấy token từ Chrome một lần.
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

# API endpoint
API_URL = "https://aisandbox-pa.googleapis.com/v1:batchGenerateImages"

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

# JS để inject vào Chrome lấy token
JS_GET_TOKEN = '''
(function() {
    // Intercept fetch để lấy token
    if (!window.__tokenCapture) {
        window.__tokenCapture = {token: null, recaptcha: null};

        const origFetch = window.fetch;
        window.fetch = async function(url, opts) {
            if (url.includes('batchGenerateImages') && opts?.body) {
                try {
                    const body = JSON.parse(opts.body);
                    if (body.recaptchaToken) {
                        window.__tokenCapture.recaptcha = body.recaptchaToken;
                    }
                } catch(e) {}

                // Get auth header
                if (opts.headers) {
                    const auth = opts.headers.Authorization || opts.headers.authorization;
                    if (auth) {
                        window.__tokenCapture.token = auth;
                    }
                }
            }
            return origFetch.apply(this, arguments);
        };
    }
    return window.__tokenCapture;
})();
'''


class APIBatchGenerator:
    def __init__(self):
        self.bearer_token = None
        self.project_id = None
        self.proxy_url = f"socks5://127.0.0.1:{PROXY_PORT}"
        self.stats = {"total": 0, "success": 0, "failed": 0}

    def setup_from_chrome(self):
        """Lấy token từ Chrome đang mở"""
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions
        except ImportError:
            print("[ERROR] Cần cài: pip install DrissionPage")
            return False

        print("[1] Kết nối Chrome...")
        options = ChromiumOptions()
        options.set_local_port(9222)

        try:
            driver = ChromiumPage(addr_or_opts=options)
        except:
            print("[ERROR] Không kết nối được Chrome port 9222")
            return False

        url = driver.url
        print(f"    URL: {url}")

        # Lấy project ID từ URL
        if "/project/" in url:
            parts = url.split("/project/")
            if len(parts) > 1:
                self.project_id = parts[1].split("/")[0].split("?")[0]
                print(f"    Project ID: {self.project_id}")

        # Inject và đợi user click Generate
        print("\n[2] Inject token capture...")
        driver.run_js(JS_GET_TOKEN)

        print("\n[3] Hãy CLICK 'Generate' một lần trong Chrome để lấy token...")
        print("    (Đợi tối đa 60 giây)")

        for i in range(60):
            time.sleep(1)
            tokens = driver.run_js("return window.__tokenCapture;")
            if tokens and tokens.get('token'):
                self.bearer_token = tokens['token']
                print(f"\n[OK] Đã lấy được Bearer token!")
                print(f"    Token: {self.bearer_token[:50]}...")
                return True
            print(f"    Đợi... {i+1}s", end="\r")

        print("\n[ERROR] Không lấy được token. Hãy click Generate trong Chrome!")
        return False

    def manual_token_input(self):
        """Nhập token thủ công"""
        print("\n[MANUAL] Nhập Bearer token:")
        print("  (Mở Chrome DevTools → Network → tìm request batchGenerateImages)")
        print("  (Copy giá trị Authorization header)")
        token = input("\nBearer token: ").strip()
        if token:
            if not token.startswith("Bearer "):
                token = f"Bearer {token}"
            self.bearer_token = token
            return True
        return False

    def generate_image(self, prompt: str, retry_count: int = 3) -> Tuple[List[str], Optional[str]]:
        """Gọi API generate image"""
        if not self.bearer_token:
            return [], "No token"

        headers = {
            "Authorization": self.bearer_token,
            "Content-Type": "application/json",
            "Origin": "https://aisandbox.google.com",
            "Referer": "https://aisandbox.google.com/",
        }

        # Payload đơn giản (không có recaptchaToken - test xem)
        payload = {
            "requests": [{
                "prompt": prompt,
                "mediaType": "IMAGE"
            }],
            "generationConfig": {
                "imageCount": 4
            }
        }

        proxies = {
            "http": self.proxy_url,
            "https": self.proxy_url,
        }

        for attempt in range(retry_count):
            try:
                print(f"      API call (attempt {attempt+1})...")
                response = requests.post(
                    API_URL,
                    headers=headers,
                    json=payload,
                    proxies=proxies,
                    timeout=60
                )

                if response.status_code == 200:
                    data = response.json()
                    images = []
                    if data.get("media"):
                        for m in data["media"]:
                            url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                            if url:
                                images.append(url)
                    return images, None

                elif response.status_code == 401:
                    return [], "Token expired - cần lấy token mới"

                elif response.status_code == 403:
                    error_msg = response.text[:200]
                    if "recaptcha" in error_msg.lower():
                        return [], "Cần recaptchaToken - API không cho phép gọi trực tiếp"
                    return [], f"403 Forbidden: {error_msg}"

                else:
                    return [], f"HTTP {response.status_code}: {response.text[:100]}"

            except requests.exceptions.ProxyError as e:
                print(f"      Proxy error, retry...")
                time.sleep(2)
            except Exception as e:
                return [], str(e)

        return [], "Max retries exceeded"

    def download_images(self, urls: List[str], idx: int) -> List[str]:
        """Download images"""
        saved = []
        proxies = {
            "http": self.proxy_url,
            "https": self.proxy_url,
        }

        for i, url in enumerate(urls):
            try:
                resp = requests.get(url, proxies=proxies, timeout=60)
                if resp.status_code == 200:
                    filename = f"api_batch_{idx:03d}_{i+1}.png"
                    (OUTPUT_DIR / filename).write_bytes(resp.content)
                    saved.append(filename)
            except:
                pass
        return saved

    def run_batch(self, prompts: List[str]):
        """Chạy batch generate"""
        print("\n" + "=" * 50)
        print("  API BATCH IMAGE GENERATION")
        print("=" * 50)

        for idx, prompt in enumerate(prompts, 1):
            self.stats["total"] += 1
            short = prompt[:40] + "..." if len(prompt) > 40 else prompt
            print(f"\n[{idx}/{len(prompts)}] {short}")

            images, error = self.generate_image(prompt)

            if error:
                print(f"    ✗ {error}")
                self.stats["failed"] += 1

                if "recaptcha" in error.lower():
                    print("\n[STOP] API yêu cầu recaptchaToken.")
                    print("       Không thể gọi API trực tiếp mà không có token từ UI.")
                    break
                continue

            if not images:
                print("    ✗ Không có ảnh")
                self.stats["failed"] += 1
                continue

            saved = self.download_images(images, idx)
            if saved:
                print(f"    ✓ Đã lưu {len(saved)} ảnh")
                self.stats["success"] += 1
            else:
                print("    ✗ Lỗi download")
                self.stats["failed"] += 1

            time.sleep(2)

        # Summary
        print("\n" + "=" * 50)
        print("  KẾT QUẢ")
        print("=" * 50)
        print(f"  Tổng: {self.stats['total']}")
        print(f"  Thành công: {self.stats['success']}")
        print(f"  Thất bại: {self.stats['failed']}")


def main():
    print("=" * 60)
    print("  GOOGLE FLOW - DIRECT API BATCH GENERATOR")
    print("=" * 60)
    print()

    # Start proxy
    print("[PROXY] Starting IPv6 proxy...")
    try:
        rotator = IPv6Rotator(IPV6_LIST)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    proxy = ProxyServer(rotator)
    proxy.start()
    time.sleep(1)
    print()

    # Setup generator
    generator = APIBatchGenerator()

    print("Chọn cách lấy token:")
    print("  1. Tự động từ Chrome (cần Chrome đang mở với --remote-debugging-port=9222)")
    print("  2. Nhập thủ công")
    choice = input("\nChọn (1/2): ").strip()

    if choice == "1":
        if not generator.setup_from_chrome():
            return
    else:
        if not generator.manual_token_input():
            print("[ERROR] Cần token để tiếp tục")
            return

    # Run batch
    generator.run_batch(DEFAULT_PROMPTS)


if __name__ == "__main__":
    main()
