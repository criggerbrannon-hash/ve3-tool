#!/usr/bin/env python3
"""
Test Direct Flow API - Tự động hóa flow lấy token và tạo ảnh

Flow:
1. Mở Chrome với profile đã login
2. Inject JS capture script
3. Trigger tạo ảnh để capture fresh recaptchaToken
4. Dùng token để gọi API trực tiếp

Yêu cầu:
- pip install pyautogui pyperclip requests
- Chrome đã login Google
"""

import sys
import json
import time
import random
from pathlib import Path

try:
    import requests
    import pyautogui as pag
    import pyperclip
except ImportError as e:
    print(f"Thiếu thư viện: {e}")
    print("Chạy: pip install pyautogui pyperclip requests")
    sys.exit(1)

pag.FAILSAFE = True
pag.PAUSE = 0.1


class DirectFlowTest:
    """Test Direct Flow API."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"
    API_URL = "https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    def __init__(self, chrome_path: str = None, profile_path: str = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path

    def log(self, msg: str):
        print(f"[DirectFlow] {msg}")

    def open_chrome(self, url: str):
        """Mở Chrome."""
        import subprocess
        cmd = [self.chrome_path]

        if self.profile_path:
            profile = Path(self.profile_path)
            if (profile / "Default").exists():
                cmd.append(f"--user-data-dir={profile}")
            else:
                cmd.extend([
                    f"--user-data-dir={profile.parent}",
                    f"--profile-directory={profile.name}"
                ])

        cmd.append(url)
        subprocess.Popen(cmd, shell=False)
        self.log(f"Mở Chrome: {url}")

    def inject_capture(self):
        """Inject JS để capture tokens."""
        js = '''
(function(){
    window._tokens = {bearer: null, recaptcha: null, projectId: null, payload: null};
    const orig = window.fetch;
    window.fetch = async function(url, opts) {
        if (url.toString().includes('batchGenerateImages')) {
            const auth = opts?.headers?.Authorization || opts?.headers?.authorization;
            if (auth) window._tokens.bearer = auth.replace('Bearer ', '');
            if (opts?.body) {
                try {
                    const body = JSON.parse(opts.body);
                    window._tokens.recaptcha = body.clientContext?.recaptchaToken;
                    window._tokens.projectId = body.requests?.[0]?.clientContext?.projectId;
                    window._tokens.payload = body;
                } catch(e) {}
            }
            console.log('[CAPTURED]', window._tokens);
        }
        return orig.apply(this, arguments);
    };
    console.log('[OK] Capture ready!');
})();
'''
        pag.hotkey("ctrl", "shift", "j")
        time.sleep(1.5)
        pyperclip.copy(js)
        pag.hotkey("ctrl", "v")
        time.sleep(0.2)
        pag.press("enter")
        time.sleep(0.5)
        pag.hotkey("ctrl", "shift", "j")
        time.sleep(0.5)
        self.log("Đã inject capture script")

    def get_tokens(self) -> dict:
        """Lấy tokens đã capture."""
        pag.hotkey("ctrl", "shift", "j")
        time.sleep(1)
        pyperclip.copy('copy(JSON.stringify(window._tokens || {}))')
        pag.hotkey("ctrl", "v")
        time.sleep(0.2)
        pag.press("enter")
        time.sleep(0.5)
        pag.hotkey("ctrl", "shift", "j")
        time.sleep(0.3)

        result = pyperclip.paste()
        try:
            return json.loads(result) if result.startswith('{') else {}
        except:
            return {}

    def trigger_generation(self, prompt: str = "test"):
        """Trigger tạo ảnh để capture token."""
        js = f'''
(async function(){{
    const ta = document.querySelector('textarea');
    if (!ta) return;
    ta.value = "{prompt}";
    ta.dispatchEvent(new Event('input', {{bubbles: true}}));
    await new Promise(r => setTimeout(r, 300));
    ta.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', keyCode: 13, bubbles: true}}));
    console.log('[TRIGGER] Sent!');
}})();
'''
        pag.hotkey("ctrl", "shift", "j")
        time.sleep(1)
        pyperclip.copy(js)
        pag.hotkey("ctrl", "v")
        time.sleep(0.2)
        pag.press("enter")
        time.sleep(0.5)
        pag.hotkey("ctrl", "shift", "j")
        time.sleep(0.3)
        self.log("Đã trigger generation")

    def call_api(self, prompt: str, tokens: dict, count: int = 2) -> dict:
        """Gọi API tạo ảnh."""
        bearer = tokens.get('bearer')
        recaptcha = tokens.get('recaptcha')
        project_id = tokens.get('projectId') or str(__import__('uuid').uuid4())
        session_id = f";{int(time.time() * 1000)}"

        if not bearer:
            return {"error": "Thiếu bearer token"}
        if not recaptcha:
            return {"error": "Thiếu recaptcha token"}

        payload = {
            "clientContext": {
                "recaptchaToken": recaptcha,
                "sessionId": session_id
            },
            "requests": [
                {
                    "clientContext": {
                        "recaptchaToken": recaptcha,
                        "sessionId": session_id,
                        "projectId": project_id,
                        "tool": "PINHOLE"
                    },
                    "seed": random.randint(1, 999999),
                    "imageModelName": "GEM_PIX_2",
                    "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                    "prompt": prompt,
                    "imageInputs": []
                }
                for _ in range(count)
            ]
        }

        url = self.API_URL.format(project_id=project_id)
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }

        self.log(f"Calling API: {prompt[:40]}...")
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)

        self.log(f"Status: {resp.status_code}")

        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"{resp.status_code}: {resp.text[:200]}"}

    def download_images(self, result: dict, output_dir: str = "./output"):
        """Download ảnh."""
        Path(output_dir).mkdir(exist_ok=True)

        for i, media in enumerate(result.get("media", [])):
            url = media.get("image", {}).get("generatedImage", {}).get("fifeUrl")
            if url:
                path = Path(output_dir) / f"image_{i+1}.png"
                path.write_bytes(requests.get(url).content)
                self.log(f"Saved: {path}")

    def run_full_test(self, prompt: str = "A beautiful sunset over mountains"):
        """Chạy full test."""
        print("=" * 60)
        print("  DIRECT FLOW API TEST")
        print("=" * 60)

        # 1. Mở Chrome
        print("\n[1] Mở Chrome...")
        self.open_chrome(self.FLOW_URL)

        print("\n[2] Đợi trang load (15s)...")
        time.sleep(15)

        # 2. Inject capture
        print("\n[3] Inject capture script...")
        self.inject_capture()
        time.sleep(1)

        # 3. Trigger để lấy token
        print("\n[4] Trigger tạo ảnh để capture token...")
        self.trigger_generation("test capture token")

        print("\n[5] Đợi request được gửi (8s)...")
        time.sleep(8)

        # 4. Lấy tokens
        print("\n[6] Lấy captured tokens...")
        tokens = self.get_tokens()

        print(f"    Bearer: {'✓' if tokens.get('bearer') else '✗'}")
        print(f"    reCAPTCHA: {'✓' if tokens.get('recaptcha') else '✗'}")
        print(f"    ProjectID: {'✓' if tokens.get('projectId') else '✗'}")

        if not tokens.get('recaptcha'):
            print("\n❌ Không capture được token!")
            print("   → Hãy thử tạo ảnh THỦ CÔNG trong browser")
            return

        # 5. Gọi API
        print(f"\n[7] Gọi API với prompt: {prompt[:40]}...")
        result = self.call_api(prompt, tokens, count=2)

        if "error" in result:
            print(f"\n❌ Lỗi: {result['error']}")
            return

        # 6. Download
        images = result.get("media", [])
        print(f"\n[8] Tạo thành công {len(images)} ảnh!")

        self.download_images(result, "./test_direct_output")
        print("\n✅ DONE! Ảnh lưu tại ./test_direct_output/")


def main():
    # Lấy Chrome profile từ argument hoặc dùng default
    profile = None
    if len(sys.argv) > 1:
        profile = sys.argv[1]

    test = DirectFlowTest(profile_path=profile)

    # Chạy test
    test.run_full_test("A majestic dragon flying over snowy mountains, 4k detailed")


if __name__ == "__main__":
    main()
