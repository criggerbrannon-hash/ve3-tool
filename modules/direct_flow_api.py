#!/usr/bin/env python3
"""
VE3 Tool - Direct Flow API Module
=================================
Gọi Google Flow API trực tiếp, không qua proxy (nanoai.pics).

Flow tự động:
1. Mở Chrome với profile đã login
2. Vào Flow page, inject JS để capture recaptchaToken
3. Trigger tạo ảnh trong browser → capture token
4. Dùng token để gọi API từ Python

Ưu điểm:
- Miễn phí (không cần nanoai.pics)
- Không bị rate limit từ proxy

Nhược điểm:
- Cần Chrome mở liên tục
- Mỗi request cần ~3-5 giây để lấy token mới
"""

import json
import time
import random
import base64
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

try:
    import pyautogui as pag
    pag.FAILSAFE = True
    pag.PAUSE = 0.1
except ImportError:
    pag = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


@dataclass
class GeneratedImage:
    """Kết quả ảnh được tạo."""
    url: str
    base64_data: Optional[str] = None
    seed: Optional[int] = None
    media_name: Optional[str] = None
    local_path: Optional[Path] = None


class DirectFlowAPI:
    """
    Gọi Google Flow API trực tiếp với recaptchaToken tự động.

    Sử dụng browser để lấy recaptchaToken (vì không thể tạo từ Python).
    """

    BASE_URL = "https://aisandbox-pa.googleapis.com"
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        verbose: bool = True,
        timeout: int = 120
    ):
        """
        Khởi tạo DirectFlowAPI.

        Args:
            chrome_path: Đường dẫn Chrome executable
            profile_path: Đường dẫn Chrome profile (đã login Google)
            verbose: In log chi tiết
            timeout: Timeout cho API calls
        """
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.verbose = verbose
        self.timeout = timeout

        # Cached tokens
        self._bearer_token = None
        self._bearer_token_time = 0
        self._project_id = None
        self._session_id = None

        # Browser state
        self._browser_ready = False

    def _log(self, msg: str):
        """Print log."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [DirectFlow] {msg}")

    def _open_chrome(self, url: str) -> bool:
        """Mở Chrome với profile."""
        try:
            cmd = [self.chrome_path]

            if self.profile_path and Path(self.profile_path).exists():
                profile_path = Path(self.profile_path)
                default_folder = profile_path / "Default"

                if default_folder.exists():
                    cmd.append(f"--user-data-dir={profile_path}")
                else:
                    cmd.extend([
                        f"--user-data-dir={profile_path.parent}",
                        f"--profile-directory={profile_path.name}"
                    ])

            cmd.append(url)
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception as e:
            self._log(f"Lỗi mở Chrome: {e}")
            return False

    def _inject_token_capture(self) -> bool:
        """
        Inject JS để capture Bearer token và recaptchaToken.
        Chạy trong DevTools Console.
        """
        if not pag or not pyperclip:
            self._log("Thiếu pyautogui hoặc pyperclip")
            return False

        # JS capture cả Bearer và recaptchaToken
        capture_js = '''
(function(){
    // Capture tokens
    window._flowTokens = {bearer: null, recaptcha: null, projectId: null};

    // Hook fetch để capture
    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const urlStr = url.toString();

        if (urlStr.includes('flowMedia') || urlStr.includes('aisandbox')) {
            // Capture Bearer token
            const auth = opts?.headers?.Authorization || opts?.headers?.authorization;
            if (auth && auth.startsWith('Bearer ')) {
                window._flowTokens.bearer = auth.substring(7);
            }

            // Capture recaptchaToken từ body
            if (opts?.body) {
                try {
                    const body = JSON.parse(opts.body);
                    if (body.clientContext?.recaptchaToken) {
                        window._flowTokens.recaptcha = body.clientContext.recaptchaToken;
                    }
                    if (body.requests?.[0]?.clientContext?.projectId) {
                        window._flowTokens.projectId = body.requests[0].clientContext.projectId;
                    }
                } catch(e) {}
            }

            console.log('[CAPTURE] Tokens captured!', window._flowTokens);
        }

        return origFetch.apply(this, arguments);
    };

    console.log('[DirectFlow] Token capture ready!');
})();
'''

        try:
            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)

            # Paste và chạy
            pyperclip.copy(capture_js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)

            self._log("Đã inject token capture script")
            return True
        except Exception as e:
            self._log(f"Lỗi inject: {e}")
            return False

    def _get_captured_tokens(self) -> Dict[str, str]:
        """Lấy tokens đã capture từ browser."""
        if not pag or not pyperclip:
            return {}

        try:
            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            # Lấy tokens
            js = 'copy(JSON.stringify(window._flowTokens || {}))'
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)

            # Parse result
            result = pyperclip.paste()
            if result and result.startswith('{'):
                return json.loads(result)
        except Exception as e:
            self._log(f"Lỗi lấy tokens: {e}")

        return {}

    def _trigger_image_generation(self, prompt: str = "test image") -> bool:
        """
        Trigger tạo ảnh trong browser để capture fresh recaptchaToken.
        Dùng khi cần token mới (token cũ đã dùng/hết hạn).
        """
        if not pag or not pyperclip:
            return False

        self._log("Triggering image generation để lấy fresh token...")

        try:
            # JS để trigger tạo ảnh
            trigger_js = f'''
(async function(){{
    // Tìm textarea
    const ta = document.querySelector('textarea');
    if (!ta) {{ console.log('No textarea!'); return; }}

    // Set prompt
    ta.value = "{prompt}";
    ta.dispatchEvent(new Event('input', {{bubbles: true}}));

    // Tìm nút gửi và click
    await new Promise(r => setTimeout(r, 500));

    // Trigger Enter
    ta.dispatchEvent(new KeyboardEvent('keydown', {{
        key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
    }}));

    console.log('[DirectFlow] Triggered generation!');
}})();
'''

            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            # Chạy trigger
            pyperclip.copy(trigger_js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)

            # Đợi request được gửi
            self._log("Đợi 5 giây để capture token...")
            time.sleep(5)

            return True
        except Exception as e:
            self._log(f"Lỗi trigger: {e}")
            return False

    def setup_browser(self, project_url: str = None) -> bool:
        """
        Setup browser: mở Chrome, vào Flow, inject capture script.

        Args:
            project_url: URL project cụ thể (nếu có)

        Returns:
            True nếu setup thành công
        """
        url = project_url or self.FLOW_URL

        self._log(f"Mở Chrome: {url}")
        if not self._open_chrome(url):
            return False

        self._log("Đợi trang load (12s)...")
        time.sleep(12)

        # Inject capture script
        if not self._inject_token_capture():
            return False

        self._browser_ready = True
        return True

    def get_fresh_tokens(self, trigger_prompt: str = "beautiful sunset") -> Dict[str, str]:
        """
        Lấy fresh tokens bằng cách trigger tạo ảnh.

        Returns:
            Dict với bearer, recaptcha, projectId
        """
        if not self._browser_ready:
            self._log("Browser chưa setup!")
            return {}

        # Trigger để capture fresh token
        self._trigger_image_generation(trigger_prompt)

        # Lấy tokens
        tokens = self._get_captured_tokens()

        if tokens.get('bearer'):
            self._bearer_token = tokens['bearer']
            self._bearer_token_time = time.time()
            self._log(f"Bearer: {self._bearer_token[:20]}...")

        if tokens.get('projectId'):
            self._project_id = tokens['projectId']
            self._log(f"Project: {self._project_id[:20]}...")

        if tokens.get('recaptcha'):
            self._log(f"reCAPTCHA: {tokens['recaptcha'][:30]}...")

        return tokens

    def generate_images(
        self,
        prompt: str,
        count: int = 2,
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        recaptcha_token: str = None,
        bearer_token: str = None,
        project_id: str = None
    ) -> Tuple[bool, List[GeneratedImage], str]:
        """
        Tạo ảnh bằng API trực tiếp.

        Args:
            prompt: Mô tả ảnh
            count: Số ảnh (1-4)
            aspect_ratio: Tỷ lệ khung hình
            recaptcha_token: Token reCAPTCHA (nếu có sẵn)
            bearer_token: Bearer token (nếu có sẵn)
            project_id: Project ID (nếu có sẵn)

        Returns:
            Tuple[success, images, error]
        """
        # Sử dụng token đã cung cấp hoặc cached
        bearer = bearer_token or self._bearer_token
        project = project_id or self._project_id or str(__import__('uuid').uuid4())
        recaptcha = recaptcha_token

        if not bearer:
            return False, [], "Thiếu Bearer token"

        if not recaptcha:
            return False, [], "Thiếu recaptchaToken"

        # Session ID
        session_id = self._session_id or f";{int(time.time() * 1000)}"

        # Build payload
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
                        "projectId": project,
                        "tool": "PINHOLE"
                    },
                    "seed": random.randint(1, 999999),
                    "imageModelName": "GEM_PIX_2",
                    "imageAspectRatio": aspect_ratio,
                    "prompt": prompt,
                    "imageInputs": []
                }
                for _ in range(count)
            ]
        }

        # Headers
        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }

        # API URL
        url = f"{self.BASE_URL}/v1/projects/{project}/flowMedia:batchGenerateImages"

        self._log(f"POST {url}")
        self._log(f"Prompt: {prompt[:50]}...")

        try:
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout
            )

            self._log(f"Status: {response.status_code}")

            if response.status_code == 401:
                return False, [], "Bearer token hết hạn (401)"

            if response.status_code == 403:
                error_text = response.text[:200]
                if 'recaptcha' in error_text.lower():
                    return False, [], "recaptchaToken không hợp lệ hoặc đã dùng (403)"
                return False, [], f"Access forbidden (403): {error_text}"

            if response.status_code != 200:
                return False, [], f"API error {response.status_code}: {response.text[:200]}"

            # Parse response
            result = response.json()
            images = self._parse_images(result)

            if images:
                self._log(f"✓ Tạo {len(images)} ảnh thành công!")
                return True, images, ""
            else:
                return False, [], "Không có ảnh trong response"

        except requests.exceptions.Timeout:
            return False, [], f"Timeout sau {self.timeout}s"
        except Exception as e:
            return False, [], str(e)

    def _parse_images(self, result: Dict) -> List[GeneratedImage]:
        """Parse ảnh từ API response."""
        images = []

        for media in result.get("media", []):
            image_data = media.get("image", {})
            generated = image_data.get("generatedImage", {})

            img = GeneratedImage(
                url=generated.get("fifeUrl", ""),
                base64_data=generated.get("encodedImage"),
                seed=generated.get("seed"),
                media_name=media.get("name")
            )

            if img.url or img.base64_data:
                images.append(img)

        return images

    def download_image(
        self,
        image: GeneratedImage,
        output_dir: Path,
        filename: str = None
    ) -> Optional[Path]:
        """Download ảnh về local."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"flow_{timestamp}"

        output_path = output_dir / f"{filename}.png"

        try:
            # Download từ URL
            if image.url:
                self._log(f"Download: {image.url[:60]}...")
                response = requests.get(image.url, timeout=60)
                if response.status_code == 200:
                    output_path.write_bytes(response.content)
                    image.local_path = output_path
                    self._log(f"✓ Saved: {output_path}")
                    return output_path

            # Decode base64
            if image.base64_data:
                self._log("Decoding base64...")
                b64 = image.base64_data
                if "," in b64:
                    b64 = b64.split(",")[1]
                output_path.write_bytes(base64.b64decode(b64))
                image.local_path = output_path
                self._log(f"✓ Saved: {output_path}")
                return output_path

        except Exception as e:
            self._log(f"Download error: {e}")

        return None


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_direct_api(profile_path: str = None) -> DirectFlowAPI:
    """Tạo DirectFlowAPI instance."""
    return DirectFlowAPI(profile_path=profile_path)


def test_direct_api():
    """Test DirectFlowAPI."""
    print("=" * 50)
    print("TEST DirectFlowAPI")
    print("=" * 50)

    api = DirectFlowAPI(verbose=True)

    # Setup browser
    print("\n1. Setup browser...")
    if not api.setup_browser():
        print("Setup failed!")
        return

    # Lấy tokens
    print("\n2. Lấy fresh tokens...")
    tokens = api.get_fresh_tokens("beautiful mountain landscape")

    if not tokens.get('bearer') or not tokens.get('recaptcha'):
        print("Không lấy được tokens!")
        return

    # Tạo ảnh
    print("\n3. Tạo ảnh...")
    success, images, error = api.generate_images(
        prompt="A majestic dragon flying over mountains, 4k, detailed",
        count=2,
        recaptcha_token=tokens['recaptcha'],
        bearer_token=tokens['bearer'],
        project_id=tokens.get('projectId')
    )

    if success:
        print(f"\n✅ Thành công! {len(images)} ảnh")
        for i, img in enumerate(images):
            path = api.download_image(img, Path("./test_output"), f"dragon_{i+1}")
            print(f"   {path}")
    else:
        print(f"\n❌ Thất bại: {error}")


if __name__ == "__main__":
    test_direct_api()
