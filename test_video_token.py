"""
Test Video Token Extraction
============================
Flow:
1. Mo Chrome
2. Inject capture script (capture token + full request info)
3. Click dropdown -> "Tạo video từ các thành phần"
4. Click "Tạo một video bằng văn bản và các thành phần…"
5. Paste prompt
6. Click nút "add" để thêm media
7. Click chọn ảnh đã tải trước đó
8. Click nút "Tạo" (arrow_forward) -> Lấy token + request info
9. Test tạo video từ ảnh
"""

import sys
import time
import subprocess
import json
import base64
import requests
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

try:
    import pyautogui as pag
    pag.FAILSAFE = True
    pag.PAUSE = 0.1
except ImportError:
    pag = None
    print("Cần cài: pip install pyautogui")

try:
    import pyperclip
except ImportError:
    pyperclip = None
    print("Cần cài: pip install pyperclip")


class VideoTokenTest:
    """Test lấy token cho video generation."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(self, chrome_path: str = None, profile_path: str = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        # Store captured data
        self.captured_data = {
            "token": None,
            "project_id": None,
            "requests": [],  # All captured requests
            "last_url": None,
            "last_payload": None
        }

    def log(self, msg: str):
        print(f"[VideoToken] {msg}")

    def open_chrome(self, url: str) -> bool:
        """Mở Chrome với profile."""
        try:
            cmd = [self.chrome_path]
            if self.profile_path and Path(self.profile_path).exists():
                cmd.extend([
                    f"--user-data-dir={Path(self.profile_path).parent}",
                    f"--profile-directory={Path(self.profile_path).name}"
                ])
            cmd.append(url)
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception as e:
            self.log(f"Lỗi mở Chrome: {e}")
            return False

    def inject_capture_script(self) -> bool:
        """
        Inject script để bắt TOÀN BỘ thông tin từ network requests:
        - Token
        - URL endpoint
        - Request payload
        - Response data
        """
        if not pag or not pyperclip:
            return False

        self.log("Inject FULL capture script...")

        # Script hook fetch để capture token + full request info + ALL HEADERS
        capture_script = '''
window._tk=null;
window._pj=null;
window._requests=[];
window._lastUrl=null;
window._lastPayload=null;
window._lastResponse=null;
window._browserHeaders={};
window._videoEndpoint=null;
window._videoPayload=null;

(function(){
    var originalFetch = window.fetch;

    window.fetch = function(url, options) {
        var urlStr = url ? url.toString() : '';

        // Capture requests liên quan đến video/media
        if(urlStr.includes('flowMedia') || urlStr.includes('aisandbox') || urlStr.includes('video') || urlStr.includes('generateVideo')) {

            var headers = options && options.headers ? options.headers : {};
            var auth = headers.Authorization || headers.authorization || '';

            // Capture token
            if(auth.startsWith('Bearer ')) {
                window._tk = auth.substring(7);
                var match = urlStr.match(/\\/projects\\/([^\\/]+)\\//);
                if(match) window._pj = match[1];
            }

            // Capture ALL headers including x-browser-*
            var allHeaders = {};
            if(options && options.headers) {
                if(options.headers instanceof Headers) {
                    options.headers.forEach(function(v, k) { allHeaders[k] = v; });
                } else {
                    for(var k in options.headers) { allHeaders[k] = options.headers[k]; }
                }
            }

            // Capture x-browser-* headers specifically
            for(var k in allHeaders) {
                if(k.toLowerCase().startsWith('x-browser') || k.toLowerCase().startsWith('x-client')) {
                    window._browserHeaders[k] = allHeaders[k];
                }
            }

            // Capture full request
            var reqData = {
                url: urlStr,
                method: options ? options.method : 'GET',
                headers: allHeaders,
                body: options ? options.body : null,
                timestamp: new Date().toISOString()
            };

            window._requests.push(reqData);
            window._lastUrl = urlStr;
            window._lastPayload = options ? options.body : null;

            // Capture video generation endpoint specifically
            if(urlStr.includes('video:batchAsyncGenerateVideo') || urlStr.includes('video:generate')) {
                window._videoEndpoint = urlStr;
                window._videoPayload = options ? options.body : null;
                console.log('=== VIDEO GENERATION REQUEST ===');
                console.log('Endpoint:', urlStr);
                console.log('Headers:', JSON.stringify(allHeaders, null, 2));
            }

            console.log('=== CAPTURED REQUEST ===');
            console.log('URL:', urlStr);
            console.log('Method:', reqData.method);
            console.log('x-browser headers:', JSON.stringify(window._browserHeaders));
            if(reqData.body) console.log('Body preview:', String(reqData.body).substring(0, 500));
        }

        // Call original fetch and capture response
        return originalFetch.apply(this, arguments).then(function(response) {
            if(urlStr.includes('flowMedia') || urlStr.includes('video') || urlStr.includes('generateVideo')) {
                response.clone().text().then(function(text) {
                    window._lastResponse = text;
                    console.log('=== CAPTURED RESPONSE ===');
                    console.log('Status:', response.status);
                    console.log('Response preview:', text.substring(0, 500));
                });
            }
            return response;
        });
    };

    console.log('=== FULL CAPTURE READY (v2) ===');
    console.log('Will capture: token, URL, payload, response, x-browser headers');
})();
'''

        try:
            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)

            # Paste và chạy
            pyperclip.copy(capture_script)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)

            self.log("FULL capture script injected!")
            return True
        except Exception as e:
            self.log(f"Inject error: {e}")
            return False

    def click_new_project(self) -> bool:
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
            self.log("Clicked 'Dự án mới'")
            return True
        except:
            return False

    def click_video_mode(self) -> bool:
        """
        Click dropdown và chọn "Tạo video từ các thành phần"
        (Khác với image mode là "Tạo hình ảnh")
        """
        if not pag or not pyperclip:
            return False

        # Script click dropdown rồi tìm option video
        js = '''(async function(){
            var dd=document.querySelector('button[role="combobox"]');
            if(dd){
                dd.click();
                await new Promise(r=>setTimeout(r,800));
                var all=document.querySelectorAll('*');
                for(var el of all){
                    var t=el.textContent||'';
                    // Tìm "Tạo video từ các thành phần" hoặc tương tự
                    if(t.includes('Tạo video từ các thành phần') || t.includes('video từ các thành phần')){
                        var r=el.getBoundingClientRect();
                        if(r.height>10 && r.height<80){
                            el.click();
                            console.log('Clicked VIDEO mode: '+t.substring(0,50));
                            return true;
                        }
                    }
                }
                console.log('Khong tim thay option video');
            }
            return false;
        })();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            self.log("Đã chọn VIDEO mode")
            return True
        except:
            return False

    def click_create_video_button(self) -> bool:
        """
        Click nút "Tạo một video bằng văn bản và các thành phần…"
        để mở form nhập prompt
        """
        if not pag or not pyperclip:
            return False

        # Tìm và click button/element chứa text này
        js = '''(async function(){
            await new Promise(r=>setTimeout(r,500));
            var all=document.querySelectorAll('button, div[role="button"], span, p');
            for(var el of all){
                var t=el.textContent||'';
                // Tìm "Tạo một video bằng văn bản và các thành phần"
                if(t.includes('Tạo một video bằng văn bản') || t.includes('video bằng văn bản và các thành phần')){
                    var r=el.getBoundingClientRect();
                    if(r.height>10 && r.width>50){
                        el.click();
                        console.log('Clicked: '+t.substring(0,60));
                        return true;
                    }
                }
            }
            console.log('Khong tim thay button tao video');
            return false;
        })();'''

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
            self.log("Clicked 'Tạo một video bằng văn bản...'")
            return True
        except:
            return False

    def focus_textarea(self) -> bool:
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

    def paste_prompt(self, prompt: str) -> bool:
        """Paste prompt (KHÔNG nhấn Enter, chờ thêm ảnh trước)."""
        if not pag or not pyperclip:
            return False

        self.log(f"Paste prompt: {prompt[:50]}...")

        try:
            pyperclip.copy(prompt)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.5)
            self.log("Prompt pasted! (chưa gửi)")
            return True
        except Exception as e:
            self.log(f"Paste error: {e}")
            return False

    def click_add_button(self) -> bool:
        """
        Click nút "add" để thêm media.
        Button có class chứa icon "add" google-symbols
        """
        if not pag or not pyperclip:
            return False

        self.log("Click nút ADD...")

        # Tìm button có icon "add"
        js = '''(function(){
            // Tìm button có icon add
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'add'){
                    btn.click();
                    console.log('Clicked ADD button');
                    return true;
                }
            }
            console.log('Khong tim thay ADD button');
            return false;
        })();'''

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
            self.log("Đã click ADD button")
            return True
        except Exception as e:
            self.log(f"Click ADD error: {e}")
            return False

    def click_uploaded_media(self) -> bool:
        """
        Click chọn ảnh đã tải lên trước đó.
        Button có span text: "Một thành phần nội dung nghe nhìn mà bạn đã tải lên hoặc chọn trước đây"
        """
        if not pag or not pyperclip:
            return False

        self.log("Click chọn ảnh đã tải...")

        # Tìm button chứa text về uploaded media
        js = '''(async function(){
            await new Promise(r=>setTimeout(r,500));

            // Cách 1: Tìm button có span chứa text về uploaded media
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    var t = span.textContent || '';
                    if(t.includes('đã tải lên') || t.includes('chọn trước đây') || t.includes('nội dung nghe nhìn')){
                        btn.click();
                        console.log('Clicked uploaded media button (by span)');
                        return true;
                    }
                }
            }

            // Cách 2: Tìm theo class pattern
            var mediaBtn = document.querySelector('button[class*="fbea20b2"]');
            if(mediaBtn){
                mediaBtn.click();
                console.log('Clicked uploaded media button (by class)');
                return true;
            }

            // Cách 3: Click vào item đầu tiên trong media grid/list
            var mediaItems = document.querySelectorAll('[role="listitem"] button, [role="option"] button');
            if(mediaItems.length > 0){
                mediaItems[0].click();
                console.log('Clicked first media item');
                return true;
            }

            console.log('Khong tim thay uploaded media button');
            return false;
        })();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            self.log("Đã chọn ảnh")
            return True
        except Exception as e:
            self.log(f"Click media error: {e}")
            return False

    def click_create_button(self) -> bool:
        """
        Click nút "Tạo" (có icon arrow_forward) để gửi prompt + media.
        KHÔNG dùng Enter mà click trực tiếp vào button.
        """
        if not pag or not pyperclip:
            return False

        self.log("Click nút TẠO (arrow_forward)...")

        # Tìm button có icon arrow_forward hoặc text "Tạo"
        js = '''(function(){
            // Cách 1: Tìm button có icon arrow_forward
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'arrow_forward'){
                    btn.click();
                    console.log('Clicked CREATE button (by icon)');
                    return true;
                }
            }

            // Cách 2: Tìm button có span text "Tạo"
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    if(span.textContent.trim() === 'Tạo'){
                        btn.click();
                        console.log('Clicked CREATE button (by text)');
                        return true;
                    }
                }
            }

            // Cách 3: Tìm theo class pattern
            var createBtn = document.querySelector('button[class*="408537d4"]');
            if(createBtn){
                createBtn.click();
                console.log('Clicked CREATE button (by class)');
                return true;
            }

            console.log('Khong tim thay CREATE button');
            return false;
        })();'''

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
            self.log("Đã click nút TẠO")
            return True
        except Exception as e:
            self.log(f"Click CREATE error: {e}")
            return False

    def get_captured_data(self) -> Dict[str, Any]:
        """Lấy TOÀN BỘ data đã capture từ DevTools bao gồm x-browser headers."""
        if not pag or not pyperclip:
            return {}

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.2)

            # Lấy tất cả captured data bao gồm browser headers
            js = '''copy(JSON.stringify({
                token: window._tk,
                project_id: window._pj,
                requests: window._requests,
                last_url: window._lastUrl,
                last_payload: window._lastPayload,
                last_response: window._lastResponse,
                browser_headers: window._browserHeaders,
                video_endpoint: window._videoEndpoint,
                video_payload: window._videoPayload
            }))'''

            pyperclip.copy(js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1)

            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)

            try:
                text = pyperclip.paste()
                if text and text.startswith('{'):
                    return json.loads(text)
            except:
                pass
            return {}
        except:
            return {}

    def get_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Lấy token từ DevTools."""
        data = self.get_captured_data()
        return data.get("token"), data.get("project_id")

    def extract_token(self, timeout: int = 90) -> Tuple[Optional[str], Optional[str], str]:
        """
        Main function - Lấy token cho video generation.

        Flow:
        1. Mở Chrome
        2. Inject capture script
        3. Click "Dự án mới"
        4. Click dropdown -> "Tạo video từ các thành phần"
        5. Click "Tạo một video bằng văn bản và các thành phần…"
        6. Focus textarea
        7. Paste prompt (CHƯA gửi)
        8. Click nút ADD để thêm media
        9. Click chọn ảnh đã tải trước đó
        10. Click nút "Tạo" (arrow_forward) để gửi
        11. Đợi và lấy token + request info
        """
        if not pag:
            return None, None, "Thiếu pyautogui"
        if not pyperclip:
            return None, None, "Thiếu pyperclip"

        try:
            # === 1. Mở Chrome ===
            self.log("Mở Chrome...")
            if not self.open_chrome(self.FLOW_URL):
                return None, None, "Không mở được Chrome"

            # === 2. Đợi trang load ===
            self.log("Đợi trang load (12s)...")
            time.sleep(12)

            # === 3. Inject capture ===
            self.inject_capture_script()
            time.sleep(1)

            # === 4. Click "Dự án mới" ===
            self.log("Click 'Dự án mới'...")
            self.click_new_project()
            self.log("Đợi 5s...")
            time.sleep(5)

            # === 5. Chọn VIDEO mode (khác với image!) ===
            self.log("Chọn mode VIDEO...")
            self.click_video_mode()
            time.sleep(3)

            # === 6. Click "Tạo một video bằng văn bản..." ===
            self.log("Click 'Tạo một video bằng văn bản...'...")
            self.click_create_video_button()
            time.sleep(2)

            # === 7. Focus textarea ===
            self.log("Focus textarea...")
            self.focus_textarea()
            time.sleep(1)

            # === 8. Paste prompt (CHƯA gửi) ===
            prompt = "A beautiful sunset over the ocean with waves crashing"
            self.paste_prompt(prompt)
            time.sleep(1)

            # === 9. Click nút ADD để thêm media ===
            self.log("Click ADD button...")
            self.click_add_button()
            time.sleep(2)

            # === 10. Click chọn ảnh đã tải trước đó ===
            self.log("Chọn ảnh đã tải...")
            self.click_uploaded_media()
            time.sleep(2)

            # === 11. Click nút "Tạo" (KHÔNG dùng Enter) ===
            self.log("Click nút TẠO...")
            self.click_create_button()

            # === 12. Đợi và lấy token + full data ===
            self.log("Đợi capture token + request info (60s)...")

            for i in range(20):
                time.sleep(3)
                self.log(f"Kiểm tra #{i+1}...")

                data = self.get_captured_data()
                token = data.get("token")
                proj = data.get("project_id")

                if token:
                    self.log("=== ĐÃ LẤY ĐƯỢC TOKEN! ===")
                    self.log(f"Token: {token[:50]}...")
                    self.log(f"Project ID: {proj}")

                    # Lưu thêm request info
                    self.captured_data = data

                    if data.get("last_url"):
                        self.log(f"Last URL: {data['last_url']}")
                    if data.get("requests"):
                        self.log(f"Captured {len(data['requests'])} requests")

                    return token, proj, ""

            return None, None, "Không lấy được token. Thử lại."

        except Exception as e:
            return None, None, f"Lỗi: {e}"


# =============================================================================
# VIDEO API TEST
# =============================================================================

class VideoAPITest:
    """Test gọi API tạo video từ ảnh."""

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(self, token: str, project_id: str, browser_headers: Dict[str, str] = None):
        self.token = token
        self.project_id = project_id
        self.browser_headers = browser_headers or {}
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()

        # Base headers
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        }

        # Add x-browser-* headers if available (IMPORTANT for bypassing recaptcha!)
        if self.browser_headers:
            for k, v in self.browser_headers.items():
                headers[k] = v
            self.log(f"Added {len(self.browser_headers)} browser headers")

        session.headers.update(headers)
        return session

    def log(self, msg: str):
        print(f"[VideoAPI] {msg}")

    def image_to_base64(self, image_path: str) -> Optional[str]:
        """Convert ảnh sang base64."""
        try:
            path = Path(image_path)
            if not path.exists():
                self.log(f"File không tồn tại: {image_path}")
                return None

            with open(path, "rb") as f:
                data = f.read()

            b64 = base64.b64encode(data).decode("utf-8")
            self.log(f"Converted image to base64: {len(b64)} chars")
            return b64
        except Exception as e:
            self.log(f"Error: {e}")
            return None

    def generate_video_from_image(
        self,
        media_id: str,
        prompt: str = "Animate this image with smooth motion",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    ) -> Dict[str, Any]:
        """
        Tạo video từ ảnh đã upload (có mediaId).

        Args:
            media_id: MediaID của ảnh đã upload lên Google (format: CAMaJDI0...)
            prompt: Mô tả video cần tạo
            aspect_ratio: Tỷ lệ video (LANDSCAPE, PORTRAIT, SQUARE)
        """
        self.log(f"Generating video from mediaId: {media_id[:50]}...")
        self.log(f"Prompt: {prompt}")

        import uuid
        import random

        # Endpoint chính xác từ captured data
        endpoint = "/v1/video:batchAsyncGenerateVideoReferenceImages"
        url = f"{self.BASE_URL}{endpoint}"

        # Payload đúng format từ captured data
        payload = {
            "clientContext": {
                "sessionId": f";{int(time.time() * 1000)}",
                "projectId": self.project_id,
                "tool": "PINHOLE",
                "userPaygateTier": "PAYGATE_TIER_TWO"
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "metadata": {"sceneId": str(uuid.uuid4())},
                "referenceImages": [{
                    "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                    "mediaId": media_id
                }],
                "seed": random.randint(1000, 9999),
                "textInput": {"prompt": prompt},
                "videoModelKey": "veo_3_0_r2v_fast_ultra"
            }]
        }

        self.log(f"POST {url}")
        self.log(f"Payload: {json.dumps(payload, indent=2)[:500]}...")

        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=120
            )

            self.log(f"Status: {response.status_code}")

            result = {
                "endpoint": endpoint,
                "status": response.status_code,
                "response_text": response.text[:1000] if response.text else None
            }

            if response.status_code == 200:
                self.log("SUCCESS!")
                result["success"] = True
                try:
                    result["response_json"] = response.json()
                except:
                    pass
            else:
                result["success"] = False
                self.log(f"Failed: {response.text[:500]}")

            return result

        except Exception as e:
            self.log(f"Error: {e}")
            return {"success": False, "error": str(e)}

    def check_video_status(self, generation_ids: list) -> Dict[str, Any]:
        """Kiểm tra status của video đang generate."""
        endpoint = "/v1/video:batchCheckAsyncVideoGenerationStatus"
        url = f"{self.BASE_URL}{endpoint}"

        payload = {
            "clientContext": {
                "sessionId": f";{int(time.time() * 1000)}",
                "projectId": self.project_id,
                "tool": "PINHOLE"
            },
            "generationIds": generation_ids
        }

        self.log(f"Checking status for {len(generation_ids)} videos...")

        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=60
            )

            return {
                "status": response.status_code,
                "response": response.json() if response.status_code == 200 else response.text
            }
        except Exception as e:
            return {"error": str(e)}

    def generate_video_from_local_image(
        self,
        image_path: str,
        prompt: str = "Animate this image with smooth motion"
    ) -> Dict[str, Any]:
        """
        Thử tạo video từ ảnh local (cần upload trước để có mediaId).

        NOTE: Hiện tại chưa có API upload ảnh, cần dùng mediaId từ ảnh đã upload qua Chrome.
        """
        self.log(f"Local image: {image_path}")
        self.log("⚠️  Cần upload ảnh qua Chrome trước để có mediaId")
        self.log("   Hoặc dùng mediaId từ ảnh đã có trong Flow")

        # Convert image to base64 for reference
        image_b64 = self.image_to_base64(image_path)
        if not image_b64:
            return {"success": False, "error": "Cannot read image"}

        return {
            "success": False,
            "message": "Cần mediaId từ ảnh đã upload. Chạy test với Chrome để capture mediaId của ảnh.",
            "image_size": len(image_b64),
            "hint": "Dùng generate_video_from_image(media_id, prompt) với mediaId đã capture"
        }


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Test function."""
    print("=" * 60)
    print("VIDEO TOKEN + API TEST (v2)")
    print("=" * 60)

    # Config - thay đổi theo máy của bạn
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    profile_path = None  # Hoặc path đến profile: r"C:\Users\...\Profile 1"

    # Test image path
    test_image = r"D:\AUTO\ve3-tool\1.png"

    # Load từ config nếu có
    config_file = Path(__file__).parent / "config" / "accounts.json"
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            chrome_path = config.get("chrome_path", chrome_path)
            profiles = config.get("chrome_profiles", [])
            if profiles:
                profile_path = profiles[0]
                print(f"Loaded profile: {profile_path}")
        except:
            pass

    print(f"Chrome: {chrome_path}")
    print(f"Profile: {profile_path}")
    print(f"Test image: {test_image}")
    print()

    # === STEP 1: Lấy token ===
    print("=" * 60)
    print("STEP 1: LẤY TOKEN + HEADERS + MEDIA ID")
    print("=" * 60)

    tester = VideoTokenTest(chrome_path, profile_path)
    token, project_id, error = tester.extract_token()

    if not token:
        print(f"✗ LỖI: {error}")
        return False

    print(f"✓ TOKEN: {token[:80]}...")
    print(f"✓ PROJECT ID: {project_id}")

    # Get captured data
    captured_data = tester.captured_data
    browser_headers = captured_data.get("browser_headers", {})
    video_payload = captured_data.get("video_payload")

    print()
    print("=== BROWSER HEADERS ===")
    if browser_headers:
        for k, v in browser_headers.items():
            print(f"  {k}: {v[:50]}..." if len(str(v)) > 50 else f"  {k}: {v}")
    else:
        print("  (Không capture được x-browser headers)")

    # Extract mediaId từ captured video payload
    media_id = None
    if video_payload:
        try:
            payload_data = json.loads(video_payload) if isinstance(video_payload, str) else video_payload
            requests_list = payload_data.get("requests", [])
            if requests_list:
                ref_images = requests_list[0].get("referenceImages", [])
                if ref_images:
                    media_id = ref_images[0].get("mediaId")
                    print(f"\n✓ CAPTURED MEDIA ID: {media_id[:60]}...")
        except Exception as e:
            print(f"  Error parsing video_payload: {e}")

    # Save captured data
    result = {
        "token": token,
        "project_id": project_id,
        "browser_headers": browser_headers,
        "media_id": media_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "captured_data": captured_data
    }

    with open("video_token_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print("\n✓ Đã lưu vào video_token_result.json")

    # In thông tin captured requests
    if captured_data.get("requests"):
        print()
        print("=== CAPTURED REQUESTS (last 5) ===")
        for req in captured_data["requests"][-5:]:
            url = req.get('url', 'N/A')
            if 'video' in url.lower():
                print(f"  🎬 VIDEO: {url[:80]}")
            else:
                print(f"  📄 {url[:80]}")

    # === STEP 2: Test Video API với mediaId đã capture ===
    print()
    print("=" * 60)
    print("STEP 2: TEST VIDEO API")
    print("=" * 60)

    if not media_id:
        print("⚠️  Không có mediaId từ captured data")
        print("   Cần chọn 1 ảnh đã upload trong Flow để capture mediaId")
        return True

    # Tạo API tester với browser headers
    api_tester = VideoAPITest(
        token=token,
        project_id=project_id or "test-project",
        browser_headers=browser_headers
    )

    # Test với mediaId đã capture
    video_result = api_tester.generate_video_from_image(
        media_id=media_id,
        prompt="A beautiful sunset over the ocean with waves crashing"
    )

    print()
    print("=== VIDEO API RESULT ===")
    print(json.dumps(video_result, indent=2, ensure_ascii=False)[:1500])

    # Save video result
    with open("video_api_result.json", "w", encoding="utf-8") as f:
        json.dump(video_result, f, indent=2, ensure_ascii=False)
    print("\n✓ Đã lưu vào video_api_result.json")

    if video_result.get("success"):
        print("\n🎉 VIDEO GENERATION REQUEST THÀNH CÔNG!")
        print("   Video đang được generate...")
    else:
        print("\n⚠️  Request failed - cần kiểm tra lại headers hoặc payload")

    return video_result.get("success", False)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
