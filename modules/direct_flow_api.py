#!/usr/bin/env python3
"""
VE3 Tool - Direct Flow API Module
=================================
Gọi Google Flow API trực tiếp, không qua proxy (nanoai.pics).

Sử dụng flow giống auto_token.py:
1. Mở Chrome với profile đã login
2. Click Dự án mới → Chọn Tạo hình ảnh
3. Gửi prompt → Capture bearer + recaptchaToken
4. Dùng tokens để gọi API trực tiếp

Ưu điểm:
- Miễn phí (không cần nanoai.pics)
- Dùng lại flow đã hoạt động tốt

Nhược điểm:
- recaptchaToken chỉ dùng 1 lần
- Mỗi request cần trigger browser để lấy token mới
"""

import json
import time
import random
import base64
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Callable
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
    Gọi Google Flow API trực tiếp với token tự động capture.

    Flow tận dụng Chrome session đã mở:
    1. Lần đầu: Mở Chrome → inject script → trigger → capture tokens
    2. Lần sau: Chỉ trigger lại để lấy recaptchaToken mới (Chrome đã mở)

    Ưu điểm: Không cần trả tiền captcha (nanoai.pics)
    """

    BASE_URL = "https://aisandbox-pa.googleapis.com"
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    # Singleton để giữ Chrome session
    _instance = None
    _chrome_ready = False

    def __new__(cls, *args, **kwargs):
        """Singleton pattern - chỉ 1 instance để giữ Chrome session."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        verbose: bool = True,
        timeout: int = 120
    ):
        # Chỉ init một lần
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.verbose = verbose
        self.timeout = timeout
        self.callback = None

        # Cached tokens
        self._bearer_token = None
        self._recaptcha_token = None
        self._project_id = None
        self._session_id = None
        self._x_browser_validation = None  # Header cần cho API

        self._initialized = True

    def log(self, msg: str):
        """Print log."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [DirectFlow] {msg}")
        if self.callback:
            self.callback(msg)

    def _open_chrome(self, url: str) -> bool:
        """Mở Chrome với profile."""
        try:
            cmd = [self.chrome_path]

            if self.profile_path and Path(self.profile_path).exists():
                profile_path = Path(self.profile_path)
                default_folder = profile_path / "Default"

                if default_folder.exists():
                    cmd.append(f"--user-data-dir={profile_path}")
                    self.log(f"Using user-data-dir: {profile_path}")
                else:
                    cmd.extend([
                        f"--user-data-dir={profile_path.parent}",
                        f"--profile-directory={profile_path.name}"
                    ])
                    self.log(f"Using profile: {profile_path.parent} / {profile_path.name}")

            cmd.append(url)
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception as e:
            self.log(f"Lỗi mở Chrome: {e}")
            return False

    def _inject_capture_with_recaptcha(self) -> bool:
        """
        Inject script capture CẢ bearer token VÀ recaptchaToken.
        Đây là điểm khác biệt với auto_token.py.
        """
        if not pag or not pyperclip:
            return False

        self.log("Inject capture script (bearer + recaptcha + x-browser-validation + BLOCK)...")

        # Script capture: bearer, recaptchaToken, x-browser-validation
        # Rồi CHẶN request (không gửi thật), trả về fake response
        capture_script = '''window._tk=null;window._pj=null;window._rc=null;window._xbv=null;window._blocked=0;(function(){var f=window.fetch;window.fetch=function(u,o){var s=u?u.toString():'';if(s.includes('batchGenerateImages')){var h=o&&o.headers?o.headers:{};var a=h.Authorization||h.authorization||'';if(a.startsWith('Bearer ')){window._tk=a.substring(7);var m=s.match(/\\/projects\\/([^\\/]+)\\//);if(m)window._pj=m[1];console.log('✓ BEARER!');}var xbv=h['x-browser-validation']||h['X-Browser-Validation']||'';if(xbv){window._xbv=xbv;console.log('✓ X-BROWSER-VALIDATION!');}if(o&&o.body){try{var body=JSON.parse(o.body);if(body.clientContext&&body.clientContext.recaptchaToken){window._rc=body.clientContext.recaptchaToken;window._blocked++;console.log('✓ RECAPTCHA! (blocked #'+window._blocked+')');return Promise.resolve(new Response(JSON.stringify({media:[]}),{status:200,headers:{'Content-Type':'application/json'}}));}}catch(e){}}}return f.apply(this,arguments);};console.log('[DirectFlow] Capture ready!');})();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)

            pyperclip.copy(capture_script)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)

            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)

            self.log("Capture script injected, DevTools closed")
            return True
        except Exception as e:
            self.log(f"Inject error: {e}")
            return False

    def _click_new_project_js(self) -> bool:
        """Click 'Dự án mới' bằng JS."""
        if not pag or not pyperclip:
            return False

        js = '''(function(){var btns=document.querySelectorAll('button');for(var b of btns){if(b.textContent.includes('Dự án mới')){b.click();console.log('Clicked Du an moi');return true;}}return false;})();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            return True
        except:
            return False

    def _click_image_mode_js(self) -> bool:
        """Click dropdown và chọn 'Tạo hình ảnh'."""
        if not pag or not pyperclip:
            return False

        js = '''(async function(){var dd=document.querySelector('button[role="combobox"]');if(dd){dd.click();await new Promise(r=>setTimeout(r,500));var all=document.querySelectorAll('*');for(var el of all){var t=el.textContent||'';if(t==='Tạo hình ảnh'||t.includes('Tạo hình ảnh từ văn bản')){var r=el.getBoundingClientRect();if(r.height>10&&r.height<80){el.click();console.log('Clicked: '+t.substring(0,40));return true;}}}}return false;})();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            return True
        except:
            return False

    def _focus_textarea_js(self) -> bool:
        """Focus vào textarea."""
        if not pag or not pyperclip:
            return False

        js = '''(function(){var ta=document.querySelector('textarea');if(ta){ta.focus();ta.click();console.log('Textarea focused');return true;}return false;})();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            return True
        except:
            return False

    def _send_prompt_manual(self, prompt: str) -> bool:
        """Gửi prompt bằng PyAutoGUI."""
        if not pag or not pyperclip:
            return False

        self.log(f"Gửi prompt: {prompt[:40]}...")

        try:
            pyperclip.copy(prompt)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.5)

            pag.press("enter")
            time.sleep(0.5)

            self.log("Prompt sent!")
            return True
        except Exception as e:
            self.log(f"Send prompt error: {e}")
            return False

    def _get_tokens_from_devtools(self) -> Dict[str, str]:
        """Lấy bearer, recaptchaToken, x-browser-validation từ DevTools."""
        if not pag or not pyperclip:
            return {}

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.2)

            # Lấy tất cả: token, project, recaptcha, x-browser-validation
            js = 'copy(JSON.stringify({t:window._tk,p:window._pj,r:window._rc,x:window._xbv}))'
            pyperclip.copy(js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.8)

            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)

            try:
                text = pyperclip.paste()
                if text and text.startswith('{'):
                    data = json.loads(text)
                    return {
                        'bearer': data.get('t'),
                        'project_id': data.get('p'),
                        'recaptcha': data.get('r'),
                        'x_browser_validation': data.get('x')  # Header quan trọng!
                    }
            except:
                pass
        except:
            pass

        return {}

    def get_fresh_recaptcha(
        self,
        callback: Callable = None,
        trigger_prompt: str = "test image"
    ) -> Optional[str]:
        """
        Lấy recaptchaToken MỚI từ Chrome đã mở.

        CHỈ dùng khi Chrome đã mở và có bearer token.
        Flow nhanh: Focus textarea → Gửi prompt → Capture recaptcha

        Returns:
            recaptchaToken mới hoặc None
        """
        self.callback = callback

        if not DirectFlowAPI._chrome_ready:
            self.log("Chrome chưa sẵn sàng! Gọi extract_tokens() trước.")
            return None

        if not pag or not pyperclip:
            return None

        try:
            self.log("=== LẤY RECAPTCHA MỚI (Chrome đã mở) ===")

            # Reset recaptcha cũ trong browser
            self._reset_recaptcha_in_browser()

            # Focus textarea và gửi prompt
            self.log("Focus textarea...")
            self._focus_textarea_js()
            time.sleep(1)

            self._send_prompt_manual(trigger_prompt)

            # recaptcha được gửi cùng request → capture ngay sau khi send
            # KHÔNG CẦN đợi image tạo xong!
            self.log("Đợi request gửi đi (3s)...")
            time.sleep(3)

            # Capture recaptcha từ request (nhanh!)
            for i in range(3):
                time.sleep(1)
                tokens = self._get_tokens_from_devtools()

                if tokens.get('recaptcha'):
                    self._recaptcha_token = tokens['recaptcha']
                    self.log(f"✓ Fresh reCAPTCHA (instant): {self._recaptcha_token[:30]}...")
                    return self._recaptcha_token

            self.log("Không capture được recaptcha!")
            return None

        except Exception as e:
            self.log(f"Lỗi get_fresh_recaptcha: {e}")
            return None

    def _reset_recaptcha_in_browser(self) -> bool:
        """Reset biến _rc trong browser để capture token mới."""
        if not pag or not pyperclip:
            return False

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            pyperclip.copy("window._rc=null;console.log('Recaptcha reset');")
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.3)

            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)
            return True
        except:
            return False

    def extract_tokens(
        self,
        project_id: str = None,
        project_url: str = None,
        callback: Callable = None,
        trigger_prompt: str = "beautiful sunset over ocean"
    ) -> Dict[str, str]:
        """
        Lấy bearer + recaptchaToken bằng cách trigger tạo ảnh.

        Flow:
        - Nếu Chrome chưa mở: Full flow (mở Chrome, inject, trigger, capture)
        - Nếu Chrome đã mở: Chỉ trigger để lấy recaptcha mới

        Returns:
            Dict với 'bearer', 'project_id', 'recaptcha'
        """
        self.callback = callback

        if not pag:
            self.log("Thiếu pyautogui!")
            return {}
        if not pyperclip:
            self.log("Thiếu pyperclip!")
            return {}

        # === CHROME ĐÃ MỞ → chỉ lấy recaptcha mới ===
        if DirectFlowAPI._chrome_ready and self._bearer_token:
            self.log("Chrome đã mở, lấy fresh recaptcha...")
            recaptcha = self.get_fresh_recaptcha(callback, trigger_prompt)
            if recaptcha:
                return {
                    'bearer': self._bearer_token,
                    'project_id': self._project_id,
                    'recaptcha': recaptcha
                }
            # Nếu không lấy được, thử full flow
            self.log("Không lấy được recaptcha, thử mở Chrome lại...")
            DirectFlowAPI._chrome_ready = False

        try:
            # === FULL FLOW: Mở Chrome mới ===
            if project_url:
                url = project_url
                self.log(f"Vào project URL: {url[:60]}...")
            elif project_id:
                url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}"
                self.log(f"Vào project ID: {project_id[:20]}...")
            else:
                url = self.FLOW_URL

            self.log("Mở Chrome...")
            if not self._open_chrome(url):
                return {}

            # === 2. Đợi trang load ===
            self.log("Đợi trang load (12s)...")
            time.sleep(12)

            # === 3. Inject capture script ===
            self._inject_capture_with_recaptcha()
            time.sleep(1)

            # === 4. Click Dự án mới (nếu chưa có project) ===
            if not project_id and not project_url:
                self.log("Click Dự án mới...")
                self._click_new_project_js()
                self.log("Đợi 5s...")
                time.sleep(5)
            else:
                self.log("Đã trong project → skip 'Dự án mới'")

            # === 5. Chọn Tạo hình ảnh ===
            self.log("Chọn mode Tạo hình ảnh...")
            self._click_image_mode_js()
            time.sleep(3)

            # === 6. Focus textarea ===
            self.log("Focus textarea...")
            self._focus_textarea_js()
            time.sleep(1)

            # === 7. Gửi prompt ===
            self._send_prompt_manual(trigger_prompt)

            # === 8. Capture tokens (NHANH - không cần đợi ảnh tạo xong!) ===
            # recaptcha được gửi trong request body → capture ngay!
            self.log("Đợi request gửi đi (5s)...")
            time.sleep(5)

            self.log("Capture tokens...")

            for i in range(5):
                time.sleep(1)
                self.log(f"Kiểm tra #{i+1}/5...")

                tokens = self._get_tokens_from_devtools()

                if tokens.get('bearer'):
                    self._bearer_token = tokens['bearer']
                    self.log(f"✓ Bearer: {self._bearer_token[:20]}...")

                if tokens.get('project_id'):
                    self._project_id = tokens['project_id']
                    self.log(f"✓ Project: {self._project_id[:20]}...")

                if tokens.get('recaptcha'):
                    self._recaptcha_token = tokens['recaptcha']
                    self.log(f"✓ reCAPTCHA: {self._recaptcha_token[:30]}...")

                if tokens.get('x_browser_validation'):
                    self._x_browser_validation = tokens['x_browser_validation']
                    self.log(f"✓ x-browser-validation: {self._x_browser_validation[:30]}...")

                # Cần cả bearer VÀ recaptcha
                if tokens.get('bearer') and tokens.get('recaptcha'):
                    self.log("=== ĐÃ LẤY ĐƯỢC TOKENS! ===")
                    # Đánh dấu Chrome đã sẵn sàng để reuse
                    DirectFlowAPI._chrome_ready = True
                    self.log("Chrome session ready for reuse!")
                    return tokens

            self.log("Không lấy được đủ tokens!")
            # Vẫn đánh dấu ready nếu có bearer (recaptcha có thể lấy sau)
            if self._bearer_token:
                DirectFlowAPI._chrome_ready = True
            return {'bearer': self._bearer_token, 'project_id': self._project_id, 'recaptcha': None}

        except Exception as e:
            self.log(f"Lỗi: {e}")
            return {}

    def generate_images_direct(
        self,
        prompt: str,
        count: int = 2,
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        bearer_token: str = None,
        recaptcha_token: str = None,
        project_id: str = None
    ) -> Tuple[bool, List[GeneratedImage], str]:
        """
        Gọi API trực tiếp với tokens đã có.

        Args:
            prompt: Mô tả ảnh
            count: Số ảnh (1-4)
            aspect_ratio: Tỷ lệ khung hình
            bearer_token: Bearer token (ya29.xxx)
            recaptcha_token: reCAPTCHA token
            project_id: Project ID

        Returns:
            Tuple[success, images, error]
        """
        bearer = bearer_token or self._bearer_token
        recaptcha = recaptcha_token or self._recaptcha_token
        project = project_id or self._project_id or str(__import__('uuid').uuid4())
        session_id = f";{int(time.time() * 1000)}"

        if not bearer:
            return False, [], "Thiếu Bearer token"

        if not recaptcha:
            return False, [], "Thiếu recaptchaToken"

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

        headers = {
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }

        url = f"{self.BASE_URL}/v1/projects/{project}/flowMedia:batchGenerateImages"

        self.log(f"POST API: {prompt[:40]}...")

        try:
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.timeout
            )

            self.log(f"Status: {response.status_code}")

            if response.status_code == 401:
                return False, [], "Bearer token hết hạn (401)"

            if response.status_code == 403:
                error_text = response.text[:200]
                if 'recaptcha' in error_text.lower():
                    return False, [], "recaptchaToken đã dùng hoặc hết hạn (403)"
                return False, [], f"Access forbidden (403): {error_text}"

            if response.status_code != 200:
                return False, [], f"API error {response.status_code}: {response.text[:200]}"

            result = response.json()
            images = self._parse_images(result)

            if images:
                self.log(f"✓ Tạo {len(images)} ảnh thành công!")
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
            if image.url:
                self.log(f"Download: {image.url[:60]}...")
                response = requests.get(image.url, timeout=60)
                if response.status_code == 200:
                    output_path.write_bytes(response.content)
                    image.local_path = output_path
                    self.log(f"✓ Saved: {output_path}")
                    return output_path

            if image.base64_data:
                self.log("Decoding base64...")
                b64 = image.base64_data
                if "," in b64:
                    b64 = b64.split(",")[1]
                output_path.write_bytes(base64.b64decode(b64))
                image.local_path = output_path
                self.log(f"✓ Saved: {output_path}")
                return output_path

        except Exception as e:
            self.log(f"Download error: {e}")

        return None


def test_direct_flow():
    """Test DirectFlowAPI."""
    print("=" * 60)
    print("  TEST DIRECT FLOW API")
    print("=" * 60)

    # Lấy profile path (nếu có)
    import sys
    profile = sys.argv[1] if len(sys.argv) > 1 else None

    api = DirectFlowAPI(profile_path=profile, verbose=True)

    # 1. Lấy tokens
    print("\n[1] Extracting tokens from browser...")
    tokens = api.extract_tokens(trigger_prompt="beautiful mountain landscape")

    if not tokens.get('bearer') or not tokens.get('recaptcha'):
        print("\n❌ Không lấy được đủ tokens!")
        print(f"   Bearer: {'✓' if tokens.get('bearer') else '✗'}")
        print(f"   reCAPTCHA: {'✓' if tokens.get('recaptcha') else '✗'}")
        return

    print(f"\n✓ Tokens captured!")
    print(f"   Bearer: {tokens['bearer'][:20]}...")
    print(f"   reCAPTCHA: {tokens['recaptcha'][:30]}...")

    # 2. Gọi API tạo ảnh mới
    print("\n[2] Calling API with captured tokens...")
    success, images, error = api.generate_images_direct(
        prompt="A majestic dragon flying over snowy mountains, 4k detailed",
        count=2
    )

    if success:
        print(f"\n✅ Tạo {len(images)} ảnh thành công!")
        output_dir = Path("./test_direct_output")
        for i, img in enumerate(images):
            path = api.download_image(img, output_dir, f"dragon_{i+1}")
            print(f"   💾 {path}")
    else:
        print(f"\n❌ Thất bại: {error}")


if __name__ == "__main__":
    test_direct_flow()
