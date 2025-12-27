#!/usr/bin/env python3
"""
Google Flow API - Batch Generator (Full Auto)
==============================================
Nhập prompt → Enter → Chặn request lấy tokens → Gọi API cho batch còn lại
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

# JS chặn REQUEST để lấy tokens
JS_INTERCEPTOR = '''
(function(){
    if(window.__interceptReady) return 'ALREADY_READY';
    window.__interceptReady = true;
    window.__tokens = null;

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('batchGenerateImages') && opts?.body) {
            try {
                const body = JSON.parse(opts.body);

                // Lấy Authorization từ headers
                let bearer = null;
                if (opts.headers) {
                    if (opts.headers.Authorization) {
                        bearer = opts.headers.Authorization;
                    } else if (opts.headers.get) {
                        bearer = opts.headers.get('Authorization');
                    } else if (typeof opts.headers === 'object') {
                        for (let key in opts.headers) {
                            if (key.toLowerCase() === 'authorization') {
                                bearer = opts.headers[key];
                                break;
                            }
                        }
                    }
                }

                // recaptchaToken có thể ở nhiều vị trí
                let recaptchaToken = body.recaptchaToken
                    || body.requests?.[0]?.clientContext?.recaptchaToken
                    || body.requests?.[0]?.recaptchaToken
                    || null;

                let projectId = body.requests?.[0]?.clientContext?.projectId
                    || body.clientContext?.projectId
                    || null;

                window.__tokens = {
                    bearer: bearer,
                    recaptchaToken: recaptchaToken,
                    projectId: projectId,
                    timestamp: Date.now()
                };
                console.log('[CAPTURED] Bearer:', bearer ? 'YES' : 'NO');
                console.log('[CAPTURED] recaptchaToken:', recaptchaToken ? 'YES' : 'NO');
            } catch(e) {
                console.log('[CAPTURE ERROR]', e);
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
        self.recaptcha_token = None
        self.project_id = None
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

        if "/project/" not in self.driver.url:
            print("    ⚠ Mở project Flow trước!")
            return False

        # Get project ID from URL
        self.project_id = self.driver.url.split("/project/")[1].split("/")[0].split("?")[0]
        print(f"    Project: {self.project_id}")

        print("\n[2] Inject interceptor...")
        # Reset interceptor cũ nếu có
        self.driver.run_js("window.__interceptReady = false; window.__tokens = null;")
        time.sleep(0.5)
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

    def get_tokens_from_first_request(self, prompt):
        """Gửi prompt đầu tiên qua UI để lấy tokens"""
        print(f"\n[3] Gửi prompt đầu tiên để lấy tokens...")
        print(f"    Prompt: {prompt[:50]}...")

        textarea = self.find_textarea()
        if textarea:
            textarea.clear()
            time.sleep(0.2)
            textarea.input(prompt)
            time.sleep(0.3)
            textarea.input('\n')  # Enter để gửi
            print("    ✓ Đã gửi")

        # Đợi tokens
        print("    Đợi tokens...")
        for i in range(30):
            time.sleep(1)
            tokens = self.driver.run_js("return window.__tokens;")
            if tokens:
                print(f"    tokens: bearer={bool(tokens.get('bearer'))}, recaptcha={bool(tokens.get('recaptchaToken'))}")
                if tokens.get("bearer") and tokens.get("recaptchaToken"):
                    self.bearer = tokens["bearer"]
                    self.recaptcha_token = tokens["recaptchaToken"]
                    if tokens.get("projectId"):
                        self.project_id = tokens["projectId"]
                    print(f"    ✓ Got tokens!")
                    return True
            print(f"    {i+1}s...", end="\r")

        print("    ✗ Không lấy được tokens")
        print(f"    Debug: {tokens}")
        return False

    def call_api(self, prompt, count=4):
        """Gọi API trực tiếp"""
        url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"

        headers = {
            "Authorization": self.bearer,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://aisandbox.google.com",
            "Referer": "https://aisandbox.google.com/",
        }

        payload = {
            "requests": [{
                "clientContext": {"projectId": self.project_id, "tool": "IMAGE_FX"},
                "seed": int(time.time() * 1000) + i,
                "imageModelName": "GEM_PIX_2",
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": prompt,
                "imageInputs": []
            } for i in range(count)],
            "recaptchaToken": self.recaptcha_token
        }

        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                return [m["image"]["generatedImage"]["fifeUrl"]
                        for m in data.get("media", [])
                        if m.get("image", {}).get("generatedImage", {}).get("fifeUrl")], None
            else:
                return [], f"{resp.status_code}: {resp.text[:100]}"
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
        # Prompt đầu tiên: gửi qua UI để lấy tokens
        if not self.get_tokens_from_first_request(prompts[0]):
            return

        self.stats["success"] += 1  # Prompt đầu đã được xử lý bởi UI
        print(f"    (Prompt 1 đã được xử lý bởi Chrome)")

        # Các prompt còn lại: gọi API trực tiếp
        print(f"\n[4] Gọi API cho {len(prompts)-1} prompts còn lại...")

        for idx, prompt in enumerate(prompts[1:], 2):
            self.stats["total"] += 1
            print(f"\n[{idx}/{len(prompts)}] {prompt[:50]}...")

            images, error = self.call_api(prompt)

            if error:
                print(f"    ✗ {error}")
                self.stats["failed"] += 1
                if "403" in error or "401" in error:
                    print("\n[STOP] Token hết hạn!")
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
