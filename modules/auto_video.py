"""
Auto Video Generator
====================
Tự động tạo video AI từ ảnh bằng Google Flow API:
1. Mở Chrome, inject script capture
2. User tạo 1 video thủ công → capture token, recaptchaToken, headers
3. Dùng credentials đó để xử lý folder ảnh

Usage:
    python auto_video.py [folder_path] [prompt]

Requirements:
    pip install pyautogui pyperclip requests
"""

import sys
import time
import subprocess
import json
import base64
import uuid
import random
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

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


# ============================================================================
# CREDENTIAL CAPTURE
# ============================================================================

class CredentialCapture:
    """Capture credentials từ Chrome - TỰ ĐỘNG HOÀN TOÀN."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(self, chrome_path: str = None, profile_path: str = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.credentials = {}
        self.callback = None

    def log(self, msg: str):
        print(f"[Capture] {msg}")
        if self.callback:
            self.callback(msg)

    def open_chrome(self, url: str = None) -> bool:
        """Mở Chrome với profile nếu có."""
        try:
            cmd = [self.chrome_path]

            if self.profile_path:
                # Extract user-data-dir và profile-directory
                profile_dir = Path(self.profile_path)
                if "User Data" in str(profile_dir):
                    # Format: C:\Users\X\AppData\Local\Google\Chrome\User Data\Profile 1
                    user_data = profile_dir.parent
                    profile_name = profile_dir.name
                    cmd.extend([
                        f"--user-data-dir={user_data}",
                        f"--profile-directory={profile_name}"
                    ])

            cmd.append(url or self.FLOW_URL)
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception as e:
            self.log(f"Lỗi: {e}")
            return False

    def run_js(self, js_code: str, wait_after: float = 0.5) -> bool:
        """Chạy JS trong DevTools Console."""
        if not pag or not pyperclip:
            self.log("Cần cài: pip install pyautogui pyperclip")
            return False

        try:
            # Mở DevTools Console
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            # Paste và execute
            pyperclip.copy(js_code)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(wait_after)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)
            return True
        except Exception as e:
            self.log(f"JS error: {e}")
            return False

    def get_xbv_from_network(self) -> Optional[str]:
        """
        Lấy x-browser-validation từ Network tab (cách thủ công).
        Hướng dẫn user copy từ DevTools.
        """
        self.log("\n" + "=" * 60)
        self.log("CẦN LẤY x-browser-validation THỦ CÔNG:")
        self.log("=" * 60)
        self.log("1. Trong Chrome, nhấn F12 mở DevTools")
        self.log("2. Vào tab Network")
        self.log("3. Tạo 1 video bất kỳ (upload ảnh + click Tạo)")
        self.log("4. Tìm request 'uploadUserImage' hoặc 'batchAsyncGenerateVideo'")
        self.log("5. Click vào → Headers → Request Headers")
        self.log("6. Copy giá trị 'x-browser-validation'")
        self.log("=" * 60)

        xbv = input("\nDán x-browser-validation vào đây: ").strip()
        if xbv and len(xbv) > 50:
            self.log(f"✓ Received x-browser-validation ({len(xbv)} chars)")
            return xbv
        return None

    def inject_capture_script(self) -> bool:
        """Inject script capture TẤT CẢ data cần thiết (IMPROVED)."""
        if not pag or not pyperclip:
            return False

        self.log("Injecting capture script (improved)...")

        # Script capture cải tiến - bắt cả XHR, fetch, và PerformanceObserver
        script = '''
(function() {
    // Storage cho captured data
    window._captured = {
        token: null,
        projectId: null,
        recaptchaToken: null,
        xBrowserValidation: null,
        xClientData: null,
        mediaId: null,
        operations: null,
        videoPayload: null,
        allRequests: [],
        allHeaders: {}
    };

    // ============ PERFORMANCE OBSERVER ============
    // Bắt headers từ Resource Timing API
    try {
        var perfObserver = new PerformanceObserver(function(list) {
            list.getEntries().forEach(function(entry) {
                if (entry.name && entry.name.includes('aisandbox')) {
                    console.log('[PERF] ' + entry.name.substring(0, 60));
                    window._captured.allRequests.push({
                        type: 'perf',
                        url: entry.name,
                        time: Date.now()
                    });
                }
            });
        });
        perfObserver.observe({ entryTypes: ['resource'] });
    } catch(e) {}

    // ============ INTERCEPT Request CONSTRUCTOR ============
    // Bắt headers trước khi gửi request
    var OrigRequest = window.Request;
    window.Request = function(input, init) {
        var url = input ? input.toString() : '';
        if (url.includes('aisandbox') || url.includes('googleapis')) {
            if (init && init.headers) {
                var hdrs = init.headers;
                if (hdrs instanceof Headers) {
                    hdrs.forEach(function(v, k) {
                        window._captured.allHeaders[k.toLowerCase()] = v;
                        if (k.toLowerCase() === 'x-browser-validation') {
                            window._captured.xBrowserValidation = v;
                            console.log('[REQ] x-browser-validation: ' + v.substring(0, 40) + '...');
                        }
                    });
                } else {
                    for (var k in hdrs) {
                        window._captured.allHeaders[k.toLowerCase()] = hdrs[k];
                        if (k.toLowerCase() === 'x-browser-validation') {
                            window._captured.xBrowserValidation = hdrs[k];
                            console.log('[REQ] x-browser-validation: ' + hdrs[k].substring(0, 40) + '...');
                        }
                    }
                }
            }
        }
        return new OrigRequest(input, init);
    };

    // Helper: extract headers
    function extractHeaders(headers) {
        if (!headers) return {};
        var result = {};

        // Headers object hoặc plain object
        if (typeof headers.forEach === 'function') {
            headers.forEach(function(value, key) {
                result[key.toLowerCase()] = value;
            });
        } else if (typeof headers.entries === 'function') {
            for (var pair of headers.entries()) {
                result[pair[0].toLowerCase()] = pair[1];
            }
        } else {
            for (var key in headers) {
                result[key.toLowerCase()] = headers[key];
            }
        }
        return result;
    }

    // Helper: save important headers
    function saveImportantHeaders(headers) {
        var h = extractHeaders(headers);

        // Authorization
        var auth = h['authorization'];
        if (auth && auth.startsWith('Bearer ')) {
            window._captured.token = auth.substring(7);
            console.log('[CAPTURE] Token:', window._captured.token.substring(0, 40) + '...');
        }

        // x-browser-validation (QUAN TRỌNG!)
        var xbv = h['x-browser-validation'];
        if (xbv && xbv.length > 10) {
            window._captured.xBrowserValidation = xbv;
            console.log('[CAPTURE] x-browser-validation:', xbv.substring(0, 30) + '...');
        }

        // x-client-data
        var xcd = h['x-client-data'];
        if (xcd) {
            window._captured.xClientData = xcd;
        }
    }

    // === INTERCEPT FETCH ===
    var origFetch = window.fetch;
    window.fetch = function(input, init) {
        var url = input ? input.toString() : '';
        var opts = init || {};

        // Log all requests to aisandbox
        if (url.includes('aisandbox') || url.includes('googleapis')) {
            console.log('[CAPTURE-FETCH] ' + url.substring(0, 80));

            // Save headers
            saveImportantHeaders(opts.headers);

            // Track request
            window._captured.allRequests.push({
                type: 'fetch',
                url: url,
                time: Date.now()
            });

            // Parse body nếu là video request
            if (url.includes('video:') && opts.body) {
                try {
                    var body = JSON.parse(opts.body);
                    window._captured.videoPayload = body;

                    if (body.clientContext) {
                        window._captured.projectId = body.clientContext.projectId;
                        window._captured.recaptchaToken = body.clientContext.recaptchaToken;
                        console.log('[CAPTURE] ProjectID:', window._captured.projectId);
                        console.log('[CAPTURE] RecaptchaToken:', (window._captured.recaptchaToken || '').substring(0, 40) + '...');
                    }

                    if (body.requests && body.requests[0] && body.requests[0].referenceImages) {
                        var ref = body.requests[0].referenceImages[0];
                        if (ref && ref.mediaId) {
                            window._captured.mediaId = ref.mediaId;
                        }
                    }
                } catch(e) {}
            }
        }

        return origFetch.apply(this, arguments).then(function(response) {
            // Capture response cho operations
            if (url.includes('batchAsyncGenerateVideo') && !url.includes('Check')) {
                response.clone().json().then(function(data) {
                    if (data.operations) {
                        window._captured.operations = data.operations;
                        console.log('[CAPTURE] Operations:', JSON.stringify(data.operations).substring(0, 100));
                    }
                }).catch(function(){});
            }
            return response;
        });
    };

    // === INTERCEPT XMLHttpRequest ===
    var XHROpen = XMLHttpRequest.prototype.open;
    var XHRSetHeader = XMLHttpRequest.prototype.setRequestHeader;
    var XHRSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(method, url) {
        this._captureUrl = url;
        this._captureMethod = method;
        this._captureHeaders = {};
        return XHROpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        this._captureHeaders = this._captureHeaders || {};
        this._captureHeaders[name.toLowerCase()] = value;

        // Capture important headers ngay
        if (name.toLowerCase() === 'x-browser-validation' && value) {
            window._captured.xBrowserValidation = value;
            console.log('[CAPTURE-XHR] x-browser-validation:', value.substring(0, 30) + '...');
        }
        if (name.toLowerCase() === 'authorization' && value && value.startsWith('Bearer ')) {
            window._captured.token = value.substring(7);
            console.log('[CAPTURE-XHR] Token:', window._captured.token.substring(0, 40) + '...');
        }

        return XHRSetHeader.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function(body) {
        var url = this._captureUrl || '';

        if (url.includes('aisandbox') || url.includes('googleapis')) {
            console.log('[CAPTURE-XHR] ' + url.substring(0, 80));
            saveImportantHeaders(this._captureHeaders);

            window._captured.allRequests.push({
                type: 'xhr',
                url: url,
                time: Date.now()
            });
        }

        return XHRSend.apply(this, arguments);
    };

    console.log('='.repeat(50));
    console.log('CAPTURE SCRIPT READY (fetch + XHR)');
    console.log('Bạn có thể tạo video thủ công, script sẽ capture credentials');
    console.log('='.repeat(50));
})();
'''

        try:
            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)

            # Paste script
            pyperclip.copy(script)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools (giữ capture active)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)

            self.log("Script injected!")
            return True

        except Exception as e:
            self.log(f"Inject error: {e}")
            return False

    def click_new_project(self) -> bool:
        """Click 'Dự án mới'."""
        self.log("Click 'Dự án mới'...")
        js = '''(function(){
            var btns = document.querySelectorAll('button');
            for(var b of btns){
                if(b.textContent.includes('Dự án mới') || b.textContent.includes('New project')){
                    b.click();
                    return true;
                }
            }
            return false;
        })();'''
        return self.run_js(js)

    def click_video_mode(self) -> bool:
        """Chọn mode 'Tạo video từ các thành phần'."""
        self.log("Chọn VIDEO mode...")
        js = '''(async function(){
            // Click dropdown
            var dd = document.querySelector('button[role="combobox"]');
            if(dd){
                dd.click();
                await new Promise(r => setTimeout(r, 800));

                // Tìm option video
                var all = document.querySelectorAll('*');
                for(var el of all){
                    var t = el.textContent || '';
                    if(t.includes('Tạo video từ các thành phần') || t.includes('Create video from components')){
                        var r = el.getBoundingClientRect();
                        if(r.height > 10 && r.height < 80){
                            el.click();
                            return true;
                        }
                    }
                }
            }
            return false;
        })();'''
        return self.run_js(js, 1.5)

    def click_create_video_button(self) -> bool:
        """Click 'Tạo một video bằng văn bản...'."""
        self.log("Click 'Tạo một video bằng văn bản...'...")
        js = '''(async function(){
            await new Promise(r => setTimeout(r, 500));
            var all = document.querySelectorAll('button, div[role="button"], span, p');
            for(var el of all){
                var t = el.textContent || '';
                if(t.includes('Tạo một video bằng văn bản') || t.includes('Create a video with text')){
                    var r = el.getBoundingClientRect();
                    if(r.height > 10 && r.width > 50){
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        })();'''
        return self.run_js(js, 1)

    def focus_and_paste_prompt(self, prompt: str) -> bool:
        """Focus textarea và paste prompt."""
        self.log(f"Paste prompt: {prompt[:40]}...")
        js = '''(function(){
            var ta = document.querySelector('textarea');
            if(ta){
                ta.focus();
                ta.click();
                return true;
            }
            return false;
        })();'''

        if not self.run_js(js):
            return False

        time.sleep(0.5)

        if pyperclip:
            pyperclip.copy(prompt)
            pag.hotkey("ctrl", "v")
            time.sleep(0.5)
            return True

        return False

    def click_add_button(self) -> bool:
        """Click nút ADD (icon add)."""
        self.log("Click ADD button...")
        js = '''(function(){
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'add'){
                    btn.click();
                    return true;
                }
            }
            return false;
        })();'''
        return self.run_js(js, 1)

    def click_uploaded_media(self) -> bool:
        """Click chọn ảnh đã upload."""
        self.log("Chọn ảnh đã tải...")
        js = '''(async function(){
            await new Promise(r => setTimeout(r, 500));

            // Tìm tab/button cho media đã upload
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    var t = span.textContent || '';
                    if(t.includes('đã tải lên') || t.includes('uploaded') ||
                       t.includes('chọn trước đây') || t.includes('previously selected') ||
                       t.includes('nội dung nghe nhìn') || t.includes('media')){
                        btn.click();
                        return true;
                    }
                }
            }

            // Fallback: click first media item
            var mediaItems = document.querySelectorAll('[role="listitem"] button, [role="option"] button');
            if(mediaItems.length > 0){
                mediaItems[0].click();
                return true;
            }

            return false;
        })();'''
        return self.run_js(js, 1.5)

    def click_create_button(self) -> bool:
        """Click nút TẠO (arrow_forward icon hoặc text 'Tạo')."""
        self.log("Click nút TẠO...")
        js = '''(function(){
            var buttons = document.querySelectorAll('button');

            // Ưu tiên tìm icon arrow_forward
            for(var btn of buttons){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'arrow_forward'){
                    btn.click();
                    return true;
                }
            }

            // Fallback: tìm text "Tạo" hoặc "Create"
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    var t = span.textContent.trim();
                    if(t === 'Tạo' || t === 'Create'){
                        btn.click();
                        return true;
                    }
                }
            }

            return false;
        })();'''
        return self.run_js(js, 1)

    def get_captured_data(self) -> Dict:
        """Lấy data đã capture từ window._captured."""
        if not pag or not pyperclip:
            return {}

        try:
            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            # Copy captured data
            js = 'copy(JSON.stringify(window._captured))'
            pyperclip.copy(js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)

            # Parse
            text = pyperclip.paste()
            if text and text.startswith('{'):
                return json.loads(text)

            return {}

        except Exception as e:
            self.log(f"Get data error: {e}")
            return {}

    def wait_for_credentials(self, timeout: int = 120) -> Dict:
        """Đợi capture credentials sau khi click TẠO."""
        self.log(f"Đợi capture credentials (timeout: {timeout}s)...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            time.sleep(3)
            elapsed = int(time.time() - start_time)

            data = self.get_captured_data()

            # Check đủ credentials
            has_token = bool(data.get("token"))
            has_recaptcha = bool(data.get("recaptchaToken"))
            has_xbv = bool(data.get("xBrowserValidation"))

            if has_token and has_recaptcha:
                self.log(f"\n✓ Captured sau {elapsed}s!")
                self.log(f"  Token: {'✓' if has_token else '✗'}")
                self.log(f"  RecaptchaToken: {'✓' if has_recaptcha else '✗'}")
                self.log(f"  x-browser-validation: {'✓' if has_xbv else '✗ (cần lấy thủ công)'}")
                self.log(f"  ProjectID: {data.get('projectId')}")

                self.credentials = data
                return data

            # Progress
            status = f"Token: {'✓' if has_token else '✗'}, Recaptcha: {'✓' if has_recaptcha else '✗'}, XBV: {'✓' if has_xbv else '✗'}"
            self.log(f"Đợi... ({elapsed}s) - {status}")

        self.log("✗ Timeout!")
        return {}

    def capture(self, prompt: str = "Animate this image with smooth motion") -> Dict:
        """
        Full flow TỰ ĐỘNG:
        1. Mở Chrome
        2. Inject script
        3. Click Dự án mới
        4. Chọn VIDEO mode
        5. Click tạo video bằng văn bản
        6. Paste prompt
        7. Click ADD
        8. Chọn ảnh đã upload
        9. Click TẠO
        10. Capture credentials
        """
        self.log("=" * 50)
        self.log("TỰ ĐỘNG CAPTURE CREDENTIALS")
        self.log("=" * 50)

        # Kiểm tra dependencies
        if not pag or not pyperclip:
            self.log("Cần cài: pip install pyautogui pyperclip")
            return {}

        # 1. Mở Chrome
        self.log("\n[1] Mở Chrome...")
        if not self.open_chrome():
            return {}

        self.log("Đợi trang load (12s)...")
        time.sleep(12)

        # 2. Inject script
        self.log("\n[2] Inject capture script...")
        if not self.inject_capture_script():
            return {}
        time.sleep(1)

        # 3. Click Dự án mới
        self.log("\n[3] Click 'Dự án mới'...")
        self.click_new_project()
        time.sleep(5)

        # 4. Chọn VIDEO mode
        self.log("\n[4] Chọn VIDEO mode...")
        self.click_video_mode()
        time.sleep(3)

        # 5. Click tạo video bằng văn bản
        self.log("\n[5] Click 'Tạo một video bằng văn bản...'...")
        self.click_create_video_button()
        time.sleep(2)

        # 6. Paste prompt
        self.log("\n[6] Paste prompt...")
        self.focus_and_paste_prompt(prompt)
        time.sleep(1)

        # 7. Click ADD
        self.log("\n[7] Click ADD button...")
        self.click_add_button()
        time.sleep(2)

        # 8. Chọn ảnh đã upload
        self.log("\n[8] Chọn ảnh đã tải...")
        self.click_uploaded_media()
        time.sleep(2)

        # 9. Click TẠO
        self.log("\n[9] Click nút TẠO...")
        self.click_create_button()

        # 10. Đợi capture
        self.log("\n[10] Đợi capture credentials...")
        return self.wait_for_credentials()

    def capture_manual(self) -> Dict:
        """
        Semi-manual capture - chỉ inject script và đợi user làm thủ công.
        Phù hợp khi auto click không hoạt động.
        """
        self.log("=" * 50)
        self.log("SEMI-MANUAL CAPTURE")
        self.log("=" * 50)

        # 1. Mở Chrome
        self.log("\n[1] Mở Chrome...")
        if not self.open_chrome():
            return {}

        self.log("Đợi trang load (10s)...")
        time.sleep(10)

        # 2. Inject script
        self.log("\n[2] Inject capture script...")
        if not self.inject_capture_script():
            return {}

        # 3. Hướng dẫn user
        self.log("\n" + "=" * 50)
        self.log("VUI LÒNG LÀM THỦ CÔNG:")
        self.log("1. Click 'Dự án mới'")
        self.log("2. Chọn 'Tạo video từ các thành phần'")
        self.log("3. Click 'Tạo một video bằng văn bản...'")
        self.log("4. Nhập prompt")
        self.log("5. Click ADD và chọn ảnh")
        self.log("6. Click TẠO")
        self.log("=" * 50)
        self.log("\nĐang đợi bạn tạo video thủ công...")

        return self.wait_for_credentials(timeout=180)


# ============================================================================
# VIDEO GENERATOR
# ============================================================================

class VideoGenerator:
    """Generate video từ ảnh sử dụng Google Flow API.

    Có 2 flow:
    - Flow 1: uploadUserImage → batchAsyncGenerateVideoReferenceImages (cần nhiều headers)
    - Flow 2: Dùng projectId trong URL path (giống flow tạo ảnh) - CHỈ CẦN token + projectId

    Flow 2 được ưu tiên vì đơn giản hơn và tương thích với các tool khác.
    """

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(self, credentials: Dict):
        self.creds = credentials
        self.project_id = credentials.get('projectId')
        self.session = self._create_session()
        self.callback = None

        # Detect which flow to use based on available credentials
        self.use_project_url = bool(self.project_id)

    def _create_session(self) -> requests.Session:
        """Tạo session với headers từ credentials."""
        session = requests.Session()

        headers = {
            "Authorization": f"Bearer {self.creds.get('token')}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Ch-Ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "x-browser-channel": "stable",
            "x-browser-copyright": "Copyright 2025 Google LLC. All Rights reserved.",
            "x-browser-year": "2025",
            "priority": "u=1, i",
        }

        # Headers optional - có thể không cần cho một số trường hợp
        if self.creds.get("xBrowserValidation"):
            headers["x-browser-validation"] = self.creds["xBrowserValidation"]

        if self.creds.get("xClientData"):
            headers["x-client-data"] = self.creds["xClientData"]

        self.log(f"Session created - Token: ✓, ProjectID: {self.creds.get('projectId', 'N/A')}")

        session.headers.update(headers)
        return session

    def log(self, msg: str):
        print(f"[VideoGen] {msg}")
        if self.callback:
            self.callback(msg)

    def upload_image(self, image_path: str) -> Optional[str]:
        """Upload ảnh → lấy mediaId.

        Sử dụng projectId-in-URL nếu có projectId (Flow 2).
        """
        self.log(f"Upload: {Path(image_path).name}")

        path = Path(image_path)
        if not path.exists():
            self.log(f"  ✗ File not found: {image_path}")
            return None

        # Read và encode
        with open(image_path, "rb") as f:
            raw_bytes = base64.b64encode(f.read()).decode("utf-8")

        # Chọn URL endpoint dựa trên flow
        if self.use_project_url and self.project_id:
            # Flow 2: projectId trong URL path (giống image generation)
            url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:uploadImage"
            payload = {
                "rawImageBytes": raw_bytes,
                "mimeType": "image/png" if image_path.lower().endswith('.png') else "image/jpeg"
            }
            self.log(f"  Using project URL: /projects/{self.project_id[:8]}...")
        else:
            # Flow 1: Original endpoint
            url = f"{self.BASE_URL}/v1:uploadUserImage"
            payload = {"imageInput": {"rawImageBytes": raw_bytes}}

        try:
            resp = self.session.post(url, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                data = resp.json()

                # Try multiple response formats
                media_id = (
                    data.get("mediaGenerationId", {}).get("mediaGenerationId") or
                    data.get("mediaId") or
                    data.get("id") or
                    data.get("name", "").split("/")[-1] if data.get("name") else None
                )

                if media_id:
                    self.log(f"  ✓ mediaId: {media_id[:40]}...")
                    return media_id
                else:
                    # Log full response to debug
                    self.log(f"  ✗ No mediaId. Response keys: {list(data.keys())}")
                    self.log(f"  Response preview: {str(data)[:200]}")
                    return None
            else:
                self.log(f"  ✗ Upload failed: {resp.status_code}")
                self.log(f"  Response: {resp.text[:300]}")

                # Fallback: try alternate endpoint if project URL failed
                if self.use_project_url:
                    self.log("  Trying fallback endpoint...")
                    return self._upload_image_fallback(image_path, raw_bytes)

                return None

        except Exception as e:
            self.log(f"  ✗ Error: {e}")
            return None

    def _upload_image_fallback(self, image_path: str, raw_bytes: str) -> Optional[str]:
        """Fallback upload using original endpoint."""
        url = f"{self.BASE_URL}/v1:uploadUserImage"
        payload = {"imageInput": {"rawImageBytes": raw_bytes}}

        try:
            resp = self.session.post(url, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                media_id = data.get("mediaGenerationId", {}).get("mediaGenerationId")
                if media_id:
                    self.log(f"  ✓ (fallback) mediaId: {media_id[:40]}...")
                    return media_id
            return None
        except:
            return None

    def generate_video(self, media_id: str, prompt: str) -> Optional[List[Dict]]:
        """Generate video từ mediaId → operations.

        Thử nhiều endpoint khác nhau:
        1. Project URL: /v1/projects/{projectId}/flowMedia:batchGenerateVideos
        2. Original: /v1/video:batchAsyncGenerateVideoReferenceImages
        """
        self.log(f"Generate video: {prompt[:50]}...")

        # Thử project URL trước nếu có projectId
        if self.use_project_url and self.project_id:
            result = self._generate_video_project_url(media_id, prompt)
            if result:
                return result
            self.log("  Project URL failed, trying fallback...")

        # Fallback: Original endpoint
        return self._generate_video_original(media_id, prompt)

    def _generate_video_project_url(self, media_id: str, prompt: str) -> Optional[List[Dict]]:
        """Generate video using project-based URL (Flow 2).

        Endpoint pattern giống với image: /v1/projects/{projectId}/flowMedia:batchGenerateVideos
        """
        # Try multiple possible video endpoints
        endpoints_to_try = [
            f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateVideos",
            f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:generateVideo",
            f"{self.BASE_URL}/v1/projects/{self.project_id}/video:batchAsyncGenerate",
        ]

        # Simplified payload for project-based flow
        payload = {
            "requests": [{
                "referenceImages": [{
                    "mediaId": media_id,
                    "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"
                }],
                "textInput": {"prompt": prompt},
                "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                "videoModelKey": "veo_3_0_r2v_fast_ultra",
                "seed": random.randint(1000, 99999),
                "metadata": {"sceneId": str(uuid.uuid4())}
            }]
        }

        for url in endpoints_to_try:
            try:
                self.log(f"  Trying: {url.split('/')[-1]}")
                resp = self.session.post(url, data=json.dumps(payload), timeout=120)

                if resp.status_code == 200:
                    data = resp.json()

                    # Try multiple response formats
                    ops = (
                        data.get("operations") or
                        data.get("results") or
                        [data] if data.get("name") else None
                    )

                    if ops:
                        self.log(f"  ✓ Got {len(ops)} operation(s)")
                        return ops

                    self.log(f"  Response (no ops): {str(data)[:200]}")

                elif resp.status_code == 404:
                    continue  # Try next endpoint
                else:
                    self.log(f"  Response ({resp.status_code}): {resp.text[:200]}")

            except Exception as e:
                self.log(f"  Error: {e}")
                continue

        return None

    def _generate_video_original(self, media_id: str, prompt: str) -> Optional[List[Dict]]:
        """Generate video using original endpoint (Flow 1)."""
        url = f"{self.BASE_URL}/v1/video:batchAsyncGenerateVideoReferenceImages"

        payload = {
            "clientContext": {
                "recaptchaToken": self.creds.get("recaptchaToken", ""),
                "sessionId": f";{int(time.time() * 1000)}",
                "projectId": self.creds.get("projectId"),
                "tool": "PINHOLE",
                "userPaygateTier": "PAYGATE_TIER_TWO"
            },
            "requests": [{
                "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                "metadata": {"sceneId": str(uuid.uuid4())},
                "referenceImages": [{
                    "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                    "mediaId": media_id
                }],
                "seed": random.randint(1000, 99999),
                "textInput": {"prompt": prompt},
                "videoModelKey": "veo_3_0_r2v_fast_ultra"
            }]
        }

        try:
            resp = self.session.post(url, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                ops = resp.json().get("operations", [])
                if ops:
                    self.log(f"  ✓ Got {len(ops)} operation(s)")
                    return ops

            self.log(f"  ✗ Generate failed: {resp.status_code}")
            self.log(f"  Response: {resp.text[:300]}")
            return None

        except Exception as e:
            self.log(f"  ✗ Error: {e}")
            return None

    def check_status(self, operations: List[Dict]) -> Optional[Dict]:
        """Check status của video generation.

        Hỗ trợ cả 2 flows:
        - Project URL: check via operation name
        - Original: batchCheckAsyncVideoGenerationStatus
        """
        # Check nếu operation có format của project-based flow
        if operations and operations[0].get("name"):
            return self._check_status_project(operations)

        return self._check_status_original(operations)

    def _check_status_project(self, operations: List[Dict]) -> Optional[Dict]:
        """Check status for project-based operations."""
        try:
            results = []
            for op in operations:
                name = op.get("name", "")
                if name:
                    # Operation name format: projects/{projectId}/operations/{opId}
                    url = f"{self.BASE_URL}/v1/{name}"
                    resp = self.session.get(url, timeout=60)

                    if resp.status_code == 200:
                        data = resp.json()
                        results.append(data)
                    else:
                        results.append(op)

            return {"operations": results} if results else None
        except:
            return None

    def _check_status_original(self, operations: List[Dict]) -> Optional[Dict]:
        """Check status using original endpoint."""
        url = f"{self.BASE_URL}/v1/video:batchCheckAsyncVideoGenerationStatus"
        payload = {"operations": operations}

        try:
            resp = self.session.post(url, data=json.dumps(payload), timeout=60)
            if resp.status_code == 200:
                return resp.json()
            return None
        except:
            return None

    def wait_for_video(self, operations: List[Dict], max_wait: int = 300) -> Optional[Dict]:
        """Đợi video hoàn thành."""
        self.log(f"  Waiting (max {max_wait}s)...")

        start = time.time()
        current_ops = operations

        while time.time() - start < max_wait:
            result = self.check_status(current_ops)

            if result:
                updated = result.get("operations", [])
                if updated:
                    current_ops = updated

                    all_done = True
                    for op in updated:
                        # Check status - support multiple formats
                        status = (
                            op.get("status", "") or
                            op.get("metadata", {}).get("state", "") or
                            ("done" if op.get("done") else "")
                        )

                        # Normalize status
                        status_str = str(status).upper()

                        if "COMPLETED" in status_str or "DONE" in status_str or op.get("done"):
                            continue
                        elif "FAILED" in status_str or "ERROR" in status_str:
                            error = op.get("error", {}).get("message", "Unknown error")
                            self.log(f"  ✗ FAILED: {error}")
                            return None
                        else:
                            all_done = False

                    if all_done:
                        self.log(f"  ✓ COMPLETED!")
                        return result

            elapsed = int(time.time() - start)
            self.log(f"  ... {elapsed}s")
            time.sleep(10)

        self.log(f"  ✗ Timeout")
        return None

    def download_video(self, video_url: str, output_path: str) -> bool:
        """Download video từ URL."""
        try:
            resp = requests.get(video_url, timeout=120)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                self.log(f"  ✓ Saved: {output_path}")
                return True
            return False
        except Exception as e:
            self.log(f"  ✗ Download error: {e}")
            return False

    def process_image(
        self,
        image_path: str,
        prompt: str,
        output_dir: str
    ) -> Dict[str, Any]:
        """
        Xử lý 1 ảnh: upload → generate → wait → download.

        Returns:
            Dict với keys: image, success, output, video_url, error
        """
        result = {"image": image_path, "success": False}

        # 1. Upload
        media_id = self.upload_image(image_path)
        if not media_id:
            result["error"] = "Upload failed"
            return result

        # 2. Generate
        operations = self.generate_video(media_id, prompt)
        if not operations:
            result["error"] = "Generate failed"
            return result

        # 3. Wait
        completed = self.wait_for_video(operations)
        if not completed:
            result["error"] = "Video generation failed or timeout"
            return result

        # 4. Download - support multiple response formats
        for op in completed.get("operations", []):
            video_url = self._extract_video_url(op)

            if video_url:
                filename = Path(image_path).stem + "_video.mp4"
                output_path = str(Path(output_dir) / filename)

                if self.download_video(video_url, output_path):
                    result["success"] = True
                    result["output"] = output_path
                    result["video_url"] = video_url
                break

        return result

    def _extract_video_url(self, op: Dict) -> Optional[str]:
        """Extract video URL from operation result - support multiple formats."""
        # Try various possible locations for video URL
        video_url = (
            op.get("videoUrl") or
            op.get("generatedVideo", {}).get("videoUrl") or
            op.get("generatedVideo", {}).get("fifeUrl") or
            op.get("response", {}).get("videoUrl") or
            op.get("response", {}).get("generatedVideo", {}).get("videoUrl") or
            op.get("result", {}).get("videoUrl") or
            op.get("metadata", {}).get("videoUrl")
        )

        # Also check for media outputs
        if not video_url:
            media_outputs = (
                op.get("mediaOutputs") or
                op.get("response", {}).get("mediaOutputs") or
                []
            )
            for media in media_outputs:
                if media.get("type") == "VIDEO" or media.get("mimeType", "").startswith("video/"):
                    video_url = media.get("url") or media.get("fifeUrl")
                    if video_url:
                        break

        return video_url


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_simple_credentials(token: str, project_id: str) -> Dict:
    """
    Tạo credentials đơn giản CHỈ CẦN token + projectId.

    Đây là cách dễ nhất để sử dụng - chỉ cần 2 thông tin:
    1. token (ya29.xxx) - lấy từ Chrome DevTools
    2. projectId (uuid) - lấy từ URL hoặc Chrome DevTools

    Args:
        token: Bearer token (ya29.xxx)
        project_id: Project ID (uuid format)

    Returns:
        Dict credentials để dùng với VideoGenerator

    Example:
        creds = create_simple_credentials(
            token="ya29.a0AfH6SMB...",
            project_id="fdac9d59-0fed-48a3-9120-4a2c30efda4e"
        )
        generator = VideoGenerator(creds)
    """
    return {
        "token": token,
        "projectId": project_id
    }


def quick_generate_video(
    image_path: str,
    token: str,
    project_id: str,
    prompt: str = "Animate this image with smooth, natural motion",
    output_dir: str = None
) -> Dict[str, Any]:
    """
    Quick function để generate video - CHỈ CẦN 3 THÔNG TIN.

    Args:
        image_path: Đường dẫn đến ảnh
        token: Bearer token (ya29.xxx)
        project_id: Project ID (uuid)
        prompt: Prompt cho video (optional)
        output_dir: Thư mục output (optional, mặc định cùng folder với ảnh)

    Returns:
        Dict với keys: success, output, video_url, error

    Example:
        result = quick_generate_video(
            image_path="path/to/image.jpg",
            token="ya29.a0AfH6SMB...",
            project_id="fdac9d59-0fed-48a3-9120-4a2c30efda4e"
        )
        if result["success"]:
            print(f"Video saved to: {result['output']}")
    """
    creds = create_simple_credentials(token, project_id)
    generator = VideoGenerator(creds)

    if output_dir is None:
        output_dir = str(Path(image_path).parent)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    return generator.process_image(image_path, prompt, output_dir)


# ============================================================================
# BATCH PROCESSOR
# ============================================================================

def process_folder(
    folder_path: str,
    prompt: str,
    credentials: Dict,
    callback: Callable[[str], None] = None
) -> Dict[str, Any]:
    """
    Xử lý tất cả ảnh trong folder.

    Args:
        folder_path: Đường dẫn folder chứa ảnh
        prompt: Prompt cho video generation
        credentials: Credentials từ capture
        callback: Callback để log progress

    Returns:
        Dict với keys: success_count, failed_count, results, output_dir
    """
    folder = Path(folder_path)

    def log(msg):
        print(msg)
        if callback:
            callback(msg)

    if not folder.exists():
        log(f"Folder không tồn tại: {folder_path}")
        return {"error": "Folder not found"}

    # Tìm ảnh
    images = list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg")) + list(folder.glob("*.png"))

    if not images:
        log(f"Không tìm thấy ảnh trong: {folder_path}")
        return {"error": "No images found"}

    log(f"\nTìm thấy {len(images)} ảnh")

    # Output folder
    output_dir = folder / "videos"
    output_dir.mkdir(exist_ok=True)

    # Process
    generator = VideoGenerator(credentials)
    generator.callback = callback
    results = []

    for i, img in enumerate(images, 1):
        log(f"\n[{i}/{len(images)}] {img.name}")
        result = generator.process_image(str(img), prompt, str(output_dir))
        results.append(result)

        if result["success"]:
            log(f"  → {result.get('output')}")
        else:
            log(f"  → Error: {result.get('error')}")

    # Summary
    success_count = sum(1 for r in results if r["success"])
    failed_count = len(results) - success_count

    log(f"\n{'='*50}")
    log(f"HOÀN THÀNH: {success_count}/{len(images)} videos")
    log(f"Output: {output_dir}")

    # Save results
    with open(output_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return {
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
        "output_dir": str(output_dir)
    }


# ============================================================================
# CLI
# ============================================================================

def main():
    print("=" * 60)
    print("AUTO VIDEO GENERATOR")
    print("=" * 60)

    # Load saved credentials
    creds_file = Path(__file__).parent.parent / "config" / "video_credentials.json"
    credentials = {}

    if creds_file.exists():
        with open(creds_file, "r", encoding="utf-8") as f:
            credentials = json.load(f)

        print(f"\n✓ Có credentials đã lưu:")
        print(f"  - Token: {'✓' if credentials.get('token') else '✗'}")
        print(f"  - ProjectID: {credentials.get('projectId', 'N/A')[:20]}...")

        use_saved = input("\nDùng lại credentials? (y/n): ").strip().lower()
        if use_saved != 'y':
            credentials = {}

    # Nếu chưa có credentials, cho phép nhập đơn giản
    if not credentials.get("token") or not credentials.get("projectId"):
        print("\n" + "=" * 60)
        print("NHẬP CREDENTIALS")
        print("=" * 60)
        print("Chọn phương thức:")
        print("1. Nhập đơn giản (CHỈ CẦN token + projectId)")
        print("2. Tự động capture (auto click)")
        print("3. Bán tự động (inject script, làm thủ công)")
        print("=" * 60)

        choice = input("\nChọn (1/2/3): ").strip()

        if choice == "1":
            # Simple input - CHỈ CẦN 2 THÔNG TIN
            print("\n" + "-" * 40)
            print("CÁCH LẤY TOKEN + PROJECT ID:")
            print("-" * 40)
            print("1. Mở Chrome → labs.google/fx/vi/tools/flow")
            print("2. Nhấn F12 (DevTools) → tab Network")
            print("3. Tạo 1 project mới bất kỳ")
            print("4. Tìm request tới 'aisandbox-pa.googleapis.com'")
            print("5. Click vào → Headers:")
            print("   - Authorization: Bearer ya29.xxx → copy phần sau Bearer")
            print("   - Request URL: .../projects/{projectId}/... → copy projectId")
            print("-" * 40)

            token = input("\nNhập token (ya29.xxx): ").strip()
            if token.startswith("Bearer "):
                token = token[7:]

            project_id = input("Nhập projectId (uuid): ").strip()

            if token and project_id:
                credentials = create_simple_credentials(token, project_id)
                print(f"\n✓ Credentials OK! (Simple mode - chỉ token + projectId)")
            else:
                print("✗ Cần cả token và projectId!")
                return

        elif choice == "3":
            capturer = CredentialCapture()
            credentials = capturer.capture_manual()
        else:
            capturer = CredentialCapture()
            credentials = capturer.capture()

        if not credentials.get("token"):
            print("✗ Không capture được credentials!")
            return

        # Save
        creds_file.parent.mkdir(exist_ok=True)
        with open(creds_file, "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=2)
        print(f"✓ Đã lưu credentials vào {creds_file}")

    # Thông báo mode
    if credentials.get("projectId") and not credentials.get("recaptchaToken"):
        print("\n✓ Using SIMPLE mode (token + projectId only)")
    else:
        print("\n✓ Using FULL mode (all credentials)")

    # Get folder path
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
    else:
        folder_path = input("\nNhập đường dẫn folder ảnh: ").strip()

    if not folder_path:
        print("Cần nhập đường dẫn folder!")
        return

    # Get prompt
    if len(sys.argv) > 2:
        prompt = sys.argv[2]
    else:
        prompt = input("Nhập prompt (Enter để dùng mặc định): ").strip()

    if not prompt:
        prompt = "Animate this image with smooth, natural motion"

    # Process
    process_folder(folder_path, prompt, credentials)


if __name__ == "__main__":
    main()
