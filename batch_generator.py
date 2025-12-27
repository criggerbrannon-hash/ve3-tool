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

# JS capture Authorization header + projectId + sessionId + recaptchaToken
JS_INTERCEPTOR = '''
(function(){
    if(window.__interceptReady) return 'ALREADY_READY';
    window.__interceptReady = true;
    window.__captured = {
        token: null,
        projectId: null,
        sessionId: null,
        recaptchaToken: null
    };

    const origFetch = window.fetch;
    window.fetch = function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('aisandbox-pa.googleapis.com') && urlStr.includes('batchGenerateImages')) {
            // Capture Bearer token from headers
            if (opts?.headers) {
                let auth = opts.headers.Authorization || opts.headers.authorization;
                if (!auth && typeof opts.headers === 'object') {
                    for (let key in opts.headers) {
                        if (key.toLowerCase() === 'authorization') {
                            auth = opts.headers[key];
                            break;
                        }
                    }
                }
                if (auth && auth.startsWith('Bearer ')) {
                    window.__captured.token = auth;
                    console.log('[CAPTURED] Bearer token!');
                }
            }

            // Capture projectId, sessionId and recaptchaToken from body
            if (opts?.body) {
                try {
                    const body = JSON.parse(opts.body);
                    if (body.clientContext) {
                        if (body.clientContext.projectId) {
                            window.__captured.projectId = body.clientContext.projectId;
                            console.log('[CAPTURED] projectId:', body.clientContext.projectId);
                        }
                        if (body.clientContext.sessionId) {
                            window.__captured.sessionId = body.clientContext.sessionId;
                        }
                    }
                    // recaptchaToken nằm ở root level
                    if (body.recaptchaToken) {
                        window.__captured.recaptchaToken = body.recaptchaToken;
                        console.log('[CAPTURED] recaptchaToken!');
                    }
                } catch(e) {}
            }
        }
        return origFetch.apply(this, arguments);
    };
    console.log('[INTERCEPTOR] Ready');
    return 'READY';
})();
'''


class BatchGenerator:
    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(self):
        self.driver = None
        self.bearer = None
        self.project_id = None
        self.session_id = None
        self.recaptcha_token = None
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

    def get_tokens(self, prompt):
        """Gửi prompt để capture tất cả tokens cần thiết"""
        print(f"\n[3] Gửi prompt để lấy tokens...")
        print(f"    Prompt: {prompt[:50]}...")

        textarea = self.find_textarea()
        if textarea:
            textarea.clear()
            time.sleep(0.2)
            textarea.input(prompt)
            time.sleep(0.3)
            textarea.input('\n')
            print("    ✓ Đã gửi")

        print("    Đợi capture tokens...")
        for i in range(30):
            time.sleep(1)
            captured = self.driver.run_js("return window.__captured || {};")
            if captured and captured.get("token") and captured.get("recaptchaToken"):
                self.bearer = captured.get("token")
                self.project_id = captured.get("projectId")
                self.session_id = captured.get("sessionId")
                self.recaptcha_token = captured.get("recaptchaToken")
                print(f"    ✓ Got Bearer token!")
                print(f"    ✓ Got recaptchaToken!")
                if self.project_id:
                    print(f"    ✓ Project ID: {self.project_id[:20]}...")
                return True
            print(f"    {i+1}s...", end="\r")

        print("    ✗ Không lấy được đủ tokens")
        return False

    def refresh_recaptcha(self, prompt):
        """Gửi prompt mới để lấy fresh recaptchaToken"""
        # Reset captured data
        self.driver.run_js("window.__captured.recaptchaToken = null;")

        textarea = self.find_textarea()
        if textarea:
            textarea.clear()
            time.sleep(0.2)
            textarea.input(prompt)
            time.sleep(0.3)
            textarea.input('\n')

        # Wait for new token
        for i in range(15):
            time.sleep(1)
            captured = self.driver.run_js("return window.__captured || {};")
            if captured and captured.get("recaptchaToken"):
                self.recaptcha_token = captured.get("recaptchaToken")
                return True
        return False

    def call_api(self, prompt, count=4):
        """Gọi API batchGenerateImages"""
        if not self.project_id:
            return [], "No project_id captured"

        url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"

        headers = {
            "Authorization": self.bearer,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://aisandbox.google.com",
            "Referer": "https://aisandbox.google.com/",
        }

        # Build requests array như format chuẩn của Flow API
        requests_data = []
        for i in range(count):
            requests_data.append({
                "clientContext": {
                    "sessionId": self.session_id or f";{int(time.time() * 1000)}",
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
                "sessionId": self.session_id or f";{int(time.time() * 1000)}",
                "projectId": self.project_id,
                "tool": "IMAGE_FX"
            },
            "requests": requests_data,
            "recaptchaToken": self.recaptcha_token  # Cần recaptchaToken từ Chrome
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                images = []

                # Parse response - images in media[].image.generatedImage.encodedImage
                for media_item in data.get("media", []):
                    gen_image = media_item.get("image", {}).get("generatedImage", {})
                    if gen_image.get("encodedImage"):
                        images.append(gen_image["encodedImage"])  # base64 image
                    elif gen_image.get("fifeUrl"):
                        # Download from URL
                        try:
                            img_resp = requests.get(gen_image["fifeUrl"], timeout=60)
                            if img_resp.status_code == 200:
                                images.append(base64.b64encode(img_resp.content).decode())
                        except:
                            pass

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
        """
        Chạy batch generation:
        - Mỗi prompt: gửi qua Chrome để lấy recaptchaToken mới
        - Sau đó gọi API với token đó để tạo 4 ảnh
        """
        print(f"\n[3] Bắt đầu batch {len(prompts)} prompts...")

        for idx, prompt in enumerate(prompts, 1):
            self.stats["total"] += 1
            print(f"\n[{idx}/{len(prompts)}] {prompt[:50]}...")

            # Bước 1: Gửi prompt qua Chrome để lấy recaptchaToken
            print("    → Gửi Chrome để lấy recaptchaToken...")
            if idx == 1:
                # Lần đầu: lấy tất cả tokens
                if not self.get_tokens(prompt):
                    print("    ✗ Không lấy được tokens")
                    self.stats["failed"] += 1
                    continue
            else:
                # Các lần sau: chỉ cần refresh recaptchaToken
                if not self.refresh_recaptcha(prompt):
                    print("    ✗ Không lấy được recaptchaToken mới")
                    self.stats["failed"] += 1
                    continue

            # Bước 2: Gọi API với recaptchaToken vừa lấy
            print("    → Gọi API tạo 4 ảnh...")
            images, error = self.call_api(prompt, count=4)

            if error:
                print(f"    ✗ API Error: {error}")
                self.stats["failed"] += 1
                if "401" in error:
                    print("\n[STOP] Bearer token hết hạn!")
                    break
                continue

            if images:
                saved = self.save_images(images, idx)
                print(f"    ✓ Saved {len(saved)} images")
                self.stats["success"] += 1
            else:
                print("    ✗ No images in response")
                self.stats["failed"] += 1

            time.sleep(1)

        print(f"\n{'=' * 60}")
        print(f"  DONE: {self.stats['success']}/{self.stats['total']}")
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
