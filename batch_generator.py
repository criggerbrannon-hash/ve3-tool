#!/usr/bin/env python3
"""
Google Flow API - Batch Generator (Full Auto)
==============================================
Capture Bearer token từ Chrome, gọi API generateContent.
"""

import json
import time
import random
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

# JS capture tokens - based on chrome_token_extractor.py
# CANCEL request để script tự gọi API
JS_INTERCEPTOR = '''
window._tk=null;window._pj=null;window._xbv=null;window._rct=null;window._payload=null;window._sid=null;
(function(){
    if(window.__interceptReady) return 'ALREADY_READY';
    window.__interceptReady = true;

    var orig = window.fetch;
    window.fetch = function(url, opts) {
        var urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('aisandbox-pa.googleapis.com') && urlStr.includes('batchGenerateImages')) {
            console.log('[INTERCEPT] Capturing request...');

            // Extract projectId from URL: /v1/projects/{projectId}/flowMedia:batchGenerateImages
            var match = urlStr.match(/\/projects\/([^\/]+)\//);
            if (match && match[1]) {
                window._pj = match[1];
                console.log('[TOKEN] projectId from URL:', window._pj);
            }

            // Capture từ headers
            if (opts && opts.headers) {
                var h = opts.headers;
                if (h['Authorization']) {
                    window._tk = h['Authorization'].replace('Bearer ', '');
                    console.log('[TOKEN] Bearer captured!');
                }
                if (h['x-browser-validation']) {
                    window._xbv = h['x-browser-validation'];
                    console.log('[TOKEN] x-browser-validation captured!');
                }
            }

            // Capture payload và recaptchaToken
            if (opts && opts.body) {
                window._payload = opts.body;
                try {
                    var body = JSON.parse(opts.body);
                    // sessionId from clientContext
                    if (body.clientContext) {
                        window._sid = body.clientContext.sessionId;
                        // Fallback projectId from body if not in URL
                        if (!window._pj && body.clientContext.projectId) {
                            window._pj = body.clientContext.projectId;
                        }
                    }
                    // recaptchaToken có thể ở root hoặc trong requests[0]
                    if (body.recaptchaToken) {
                        window._rct = body.recaptchaToken;
                        console.log('[TOKEN] recaptchaToken captured (root)!');
                    } else if (body.requests && body.requests[0] && body.requests[0].clientContext && body.requests[0].clientContext.recaptchaToken) {
                        window._rct = body.requests[0].clientContext.recaptchaToken;
                        console.log('[TOKEN] recaptchaToken captured (requests[0])!');
                    }
                } catch(e) {
                    console.log('[ERROR] Parse body failed:', e);
                }
            }

            // CANCEL request - return fake response
            console.log('[INTERCEPT] Request cancelled, tokens captured!');
            return Promise.resolve(new Response(JSON.stringify({cancelled:true})));
        }

        return orig.apply(this, arguments);
    };
    console.log('[INTERCEPTOR] Ready - will capture batchGenerateImages requests');
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
        self.xbv = None  # x-browser-validation header
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
        # Reset completely
        self.driver.run_js("""
            window.__interceptReady = false;
            window._tk = null;
            window._pj = null;
            window._xbv = null;
            window._rct = null;
            window._payload = null;
            window._sid = null;
        """)
        time.sleep(0.3)
        result = self.driver.run_js(JS_INTERCEPTOR)
        print(f"    ✓ Interceptor: {result}")

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
        print(f"    Prompt: {prompt[:50]}...")

        textarea = self.find_textarea()
        if textarea:
            textarea.clear()
            time.sleep(0.2)
            textarea.input(prompt)
            time.sleep(0.3)
            textarea.input('\n')
            print("    ✓ Đã gửi, đợi capture...")

        # Đợi 3 giây theo hướng dẫn
        time.sleep(3)

        # Đọc tokens từ window variables
        for i in range(10):
            tokens = self.driver.run_js("""
                return {
                    tk: window._tk,
                    pj: window._pj,
                    xbv: window._xbv,
                    rct: window._rct,
                    sid: window._sid
                };
            """)

            # Debug output
            if i == 0 or i == 5:
                print(f"    [DEBUG] Bearer: {'YES' if tokens.get('tk') else 'NO'}")
                print(f"    [DEBUG] recaptcha: {'YES' if tokens.get('rct') else 'NO'}")
                print(f"    [DEBUG] projectId: {'YES' if tokens.get('pj') else 'NO'}")

            if tokens.get("tk") and tokens.get("rct"):
                self.bearer = f"Bearer {tokens['tk']}"
                self.project_id = tokens.get("pj")
                self.session_id = tokens.get("sid")
                self.recaptcha_token = tokens.get("rct")
                self.xbv = tokens.get("xbv")
                print(f"    ✓ Got Bearer token!")
                print(f"    ✓ Got recaptchaToken!")
                if self.project_id:
                    print(f"    ✓ Project ID: {self.project_id[:20]}...")
                return True

            time.sleep(1)

        print("    ✗ Không lấy được đủ tokens")
        return False

    def refresh_recaptcha(self, prompt):
        """Gửi prompt mới để lấy fresh recaptchaToken"""
        # Reset captured data
        self.driver.run_js("window._rct = null;")

        textarea = self.find_textarea()
        if textarea:
            textarea.clear()
            time.sleep(0.2)
            textarea.input(prompt)
            time.sleep(0.3)
            textarea.input('\n')

        # Đợi 3 giây
        time.sleep(3)

        # Wait for new token
        for i in range(10):
            rct = self.driver.run_js("return window._rct;")
            if rct:
                self.recaptcha_token = rct
                print(f"    ✓ Got new recaptchaToken!")
                return True
            time.sleep(1)
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
        # Add x-browser-validation if captured
        if self.xbv:
            headers["x-browser-validation"] = self.xbv

        # Build requests array như format chuẩn của Flow API
        requests_data = []
        for i in range(count):
            requests_data.append({
                "clientContext": {
                    "sessionId": self.session_id or f";{int(time.time() * 1000)}",
                    "projectId": self.project_id,
                    "tool": "IMAGE_FX"
                },
                "seed": random.randint(100000, 999999),
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
            print("    → Gọi API tạo 1 ảnh...")
            images, error = self.call_api(prompt, count=1)

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
