"""
Auto Video Generator
====================
Tự động:
1. Mở Chrome, inject script capture
2. User tạo 1 video thủ công → capture token, recaptchaToken, headers
3. Dùng credentials đó để xử lý folder ảnh

Usage:
    python auto_video.py [folder_path] [prompt]
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
from typing import Optional, Dict, Any, List, Tuple

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


class CredentialCapture:
    """Capture credentials từ Chrome - TỰ ĐỘNG HOÀN TOÀN."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(self, chrome_path: str = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.credentials = {}

    def log(self, msg: str):
        print(f"[Capture] {msg}")

    def open_chrome(self, url: str = None) -> bool:
        """Mở Chrome."""
        try:
            cmd = [self.chrome_path, url or self.FLOW_URL]
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception as e:
            self.log(f"Lỗi: {e}")
            return False

    def run_js(self, js_code: str, wait_after: float = 0.5) -> bool:
        """Chạy JS trong DevTools."""
        if not pag or not pyperclip:
            return False
        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js_code)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(wait_after)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)
            return True
        except:
            return False

    def inject_capture_script(self) -> bool:
        """Inject script capture TẤT CẢ data cần thiết."""
        if not pag or not pyperclip:
            return False

        self.log("Injecting capture script...")

        script = '''
window._captured = {
    token: null,
    projectId: null,
    recaptchaToken: null,
    xBrowserValidation: null,
    xClientData: null,
    mediaId: null,
    operations: null,
    videoPayload: null,
    allHeaders: {}
};

(function(){
    function getHeader(hdrs, name) {
        if(!hdrs) return null;
        if(typeof hdrs.get === 'function') {
            return hdrs.get(name);
        }
        return hdrs[name] || hdrs[name.toLowerCase()] || null;
    }

    function extractHeaders(hdrs) {
        if(!hdrs) return;

        var auth = getHeader(hdrs, 'Authorization');
        if(auth && auth.startsWith('Bearer ')) {
            window._captured.token = auth.substring(7);
        }

        var xbv = getHeader(hdrs, 'x-browser-validation');
        if(xbv) {
            window._captured.xBrowserValidation = xbv;
            console.log('[CAPTURE] x-browser-validation:', xbv.substring(0, 30) + '...');
        }

        var xcd = getHeader(hdrs, 'x-client-data');
        if(xcd) {
            window._captured.xClientData = xcd;
        }
    }

    var origFetch = window.fetch;
    window.fetch = function(url, opts) {
        var urlStr = url ? url.toString() : '';

        if(urlStr.includes('aisandbox') || urlStr.includes('googleapis')) {
            console.log('[CAPTURE] Intercepted:', urlStr.substring(0, 80));
            extractHeaders(opts && opts.headers);

            if(urlStr.includes('video:batchAsyncGenerateVideo') && opts && opts.body) {
                window._captured.videoPayload = opts.body;
                try {
                    var pd = JSON.parse(opts.body);
                    if(pd.clientContext) {
                        window._captured.projectId = pd.clientContext.projectId;
                        window._captured.recaptchaToken = pd.clientContext.recaptchaToken;
                    }
                    if(pd.requests && pd.requests[0] && pd.requests[0].referenceImages) {
                        window._captured.mediaId = pd.requests[0].referenceImages[0].mediaId;
                    }
                } catch(e) {}
            }
        }

        return origFetch.apply(this, arguments).then(function(resp) {
            if(urlStr.includes('video:batchAsyncGenerateVideo') && !urlStr.includes('Check')) {
                resp.clone().json().then(function(data) {
                    if(data.operations) {
                        window._captured.operations = data.operations;
                    }
                }).catch(function(){});
            }
            return resp;
        });
    };

    var origXHR = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        if(name.toLowerCase() === 'x-browser-validation' && value) {
            window._captured.xBrowserValidation = value;
            console.log('[CAPTURE-XHR] x-browser-validation:', value.substring(0, 30) + '...');
        }
        if(name.toLowerCase() === 'authorization' && value && value.startsWith('Bearer ')) {
            window._captured.token = value.substring(7);
        }
        return origXHR.apply(this, arguments);
    };

    console.log('=== CAPTURE READY (fetch + XHR) ===');
})();
'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)
            pyperclip.copy(script)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)
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
        js = '''(function(){var btns=document.querySelectorAll('button');for(var b of btns){if(b.textContent.includes('Dự án mới')){b.click();return true;}}return false;})();'''
        return self.run_js(js)

    def click_video_mode(self) -> bool:
        """Chọn mode 'Tạo video từ các thành phần'."""
        self.log("Chọn VIDEO mode...")
        js = '''(async function(){
            var dd=document.querySelector('button[role="combobox"]');
            if(dd){
                dd.click();
                await new Promise(r=>setTimeout(r,800));
                var all=document.querySelectorAll('*');
                for(var el of all){
                    var t=el.textContent||'';
                    if(t.includes('Tạo video từ các thành phần')){
                        var r=el.getBoundingClientRect();
                        if(r.height>10 && r.height<80){
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
            await new Promise(r=>setTimeout(r,500));
            var all=document.querySelectorAll('button, div[role="button"], span, p');
            for(var el of all){
                var t=el.textContent||'';
                if(t.includes('Tạo một video bằng văn bản')){
                    var r=el.getBoundingClientRect();
                    if(r.height>10 && r.width>50){
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
        js = '''(function(){var ta=document.querySelector('textarea');if(ta){ta.focus();ta.click();return true;}return false;})();'''
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
        """Click nút ADD."""
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
            await new Promise(r=>setTimeout(r,500));
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    var t = span.textContent || '';
                    if(t.includes('đã tải lên') || t.includes('chọn trước đây') || t.includes('nội dung nghe nhìn')){
                        btn.click();
                        return true;
                    }
                }
            }
            var mediaItems = document.querySelectorAll('[role="listitem"] button, [role="option"] button');
            if(mediaItems.length > 0){
                mediaItems[0].click();
                return true;
            }
            return false;
        })();'''
        return self.run_js(js, 1.5)

    def click_create_button(self) -> bool:
        """Click nút TẠO (arrow_forward)."""
        self.log("Click nút TẠO...")
        js = '''(function(){
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'arrow_forward'){
                    btn.click();
                    return true;
                }
            }
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    if(span.textContent.trim() === 'Tạo'){
                        btn.click();
                        return true;
                    }
                }
            }
            return false;
        })();'''
        return self.run_js(js, 1)

    def get_captured_data(self) -> Dict:
        """Lấy data đã capture."""
        if not pag or not pyperclip:
            return {}

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            js = 'copy(JSON.stringify(window._captured))'
            pyperclip.copy(js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)

            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)

            text = pyperclip.paste()
            if text and text.startswith('{'):
                return json.loads(text)
            return {}
        except:
            return {}

    def wait_for_credentials(self, timeout: int = 120) -> Dict:
        """Đợi capture credentials sau khi click TẠO."""
        self.log(f"Đợi capture credentials (timeout: {timeout}s)...")

        start_time = time.time()

        while time.time() - start_time < timeout:
            time.sleep(3)
            elapsed = int(time.time() - start_time)

            data = self.get_captured_data()

            if data.get("token") and data.get("recaptchaToken"):
                self.log(f"\n✓ Captured sau {elapsed}s!")
                self.log(f"  Token: {data['token'][:50]}...")
                self.log(f"  ProjectID: {data.get('projectId')}")
                recaptcha = data.get('recaptchaToken') or ''
                self.log(f"  RecaptchaToken: {recaptcha[:50]}..." if recaptcha else "  RecaptchaToken: (none)")
                xbv = data.get('xBrowserValidation') or ''
                self.log(f"  X-Browser-Validation: {xbv[:30]}..." if xbv else "  X-Browser-Validation: (none)")

                self.credentials = data
                return data

            self.log(f"Đợi... ({elapsed}s) - Token: {'✓' if data.get('token') else '✗'}, Recaptcha: {'✓' if data.get('recaptchaToken') else '✗'}")

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


class VideoGenerator:
    """Generate video từ ảnh."""

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(self, credentials: Dict):
        self.creds = credentials
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()

        headers = {
            "Authorization": f"Bearer {self.creds.get('token')}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "x-browser-channel": "stable",
            "x-browser-copyright": "Copyright 2025 Google LLC. All Rights reserved.",
            "x-browser-year": "2025",
        }

        if self.creds.get("xBrowserValidation"):
            headers["x-browser-validation"] = self.creds["xBrowserValidation"]
        if self.creds.get("xClientData"):
            headers["x-client-data"] = self.creds["xClientData"]

        session.headers.update(headers)
        return session

    def log(self, msg: str):
        print(f"[VideoGen] {msg}")

    def upload_image(self, image_path: str) -> Optional[str]:
        """Upload ảnh → mediaId. Thử nhiều format."""
        self.log(f"Upload: {Path(image_path).name}")

        path = Path(image_path)
        if not path.exists():
            self.log(f"  ✗ File not found: {image_path}")
            return None

        file_size = path.stat().st_size
        self.log(f"  File size: {file_size / 1024:.1f} KB")

        with open(image_path, "rb") as f:
            image_data = f.read()

        raw_bytes = base64.b64encode(image_data).decode("utf-8")

        # Detect mime type
        mime_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

        url = f"{self.BASE_URL}/v1:uploadUserImage"

        # Thử nhiều payload format
        payloads_to_try = [
            # Format 1: Original
            {"imageInput": {"rawImageBytes": raw_bytes}},
            # Format 2: With mime type
            {"imageInput": {"rawImageBytes": raw_bytes, "mimeType": mime_type}},
            # Format 3: Direct rawImageBytes
            {"rawImageBytes": raw_bytes},
            # Format 4: image field
            {"image": {"rawImageBytes": raw_bytes}},
            # Format 5: bytesBase64Encoded
            {"imageInput": {"bytesBase64Encoded": raw_bytes}},
        ]

        self.log(f"  Token: {self.creds.get('token', '')[:30]}...")
        self.log(f"  x-browser-validation: {'✓' if self.creds.get('xBrowserValidation') else '✗'}")

        for i, payload in enumerate(payloads_to_try):
            self.log(f"  Trying format {i+1}...")

            try:
                # Try both content types
                for ct in ["text/plain;charset=UTF-8", "application/json"]:
                    headers = {"Content-Type": ct}

                    if ct == "application/json":
                        resp = self.session.post(url, json=payload, headers=headers, timeout=60)
                    else:
                        resp = self.session.post(url, data=json.dumps(payload), headers=headers, timeout=60)

                    if resp.status_code == 200:
                        data = resp.json()
                        media_id = data.get("mediaGenerationId", {}).get("mediaGenerationId")
                        if media_id:
                            self.log(f"  ✓ SUCCESS with format {i+1}, CT: {ct}")
                            self.log(f"  ✓ mediaId: {media_id[:40]}...")
                            return media_id
                        # Try other response structures
                        media_id = data.get("mediaId") or data.get("id")
                        if media_id:
                            self.log(f"  ✓ mediaId (alt): {media_id[:40]}...")
                            return media_id

            except Exception as e:
                continue

        # All failed - show last error
        self.log(f"  ✗ All formats failed")
        try:
            resp = self.session.post(url, json=payloads_to_try[0], timeout=60)
            self.log(f"  Last response: {resp.status_code} - {resp.text[:300]}")
        except:
            pass
        return None

    def generate_video(self, media_id: str, prompt: str) -> Optional[List[Dict]]:
        """Generate video → operations."""
        self.log(f"Generate video: {prompt[:50]}...")

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
            self.log(f"  ✗ Generate failed: {resp.status_code} - {resp.text[:200]}")
            return None
        except Exception as e:
            self.log(f"  ✗ Error: {e}")
            return None

    def check_status(self, operations: List[Dict]) -> Optional[Dict]:
        """Check status."""
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
                        status = op.get("status", "")
                        if "COMPLETED" in status:
                            continue
                        elif "FAILED" in status:
                            self.log(f"  ✗ FAILED")
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
        """Download video."""
        try:
            resp = requests.get(video_url, timeout=120)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                self.log(f"  ✓ Saved: {output_path}")
                return True
            return False
        except:
            return False

    def process_image(self, image_path: str, prompt: str, output_dir: str) -> Dict:
        """Xử lý 1 ảnh: upload → generate → wait → download."""
        result = {"image": image_path, "success": False}

        # Upload
        media_id = self.upload_image(image_path)
        if not media_id:
            result["error"] = "Upload failed"
            return result

        # Generate
        operations = self.generate_video(media_id, prompt)
        if not operations:
            result["error"] = "Generate failed"
            return result

        # Wait
        completed = self.wait_for_video(operations)
        if not completed:
            result["error"] = "Video generation failed"
            return result

        # Download
        for op in completed.get("operations", []):
            video_url = (
                op.get("videoUrl") or
                op.get("generatedVideo", {}).get("videoUrl") or
                op.get("generatedVideo", {}).get("fifeUrl")
            )

            if video_url:
                filename = Path(image_path).stem + "_video.mp4"
                output_path = str(Path(output_dir) / filename)
                if self.download_video(video_url, output_path):
                    result["success"] = True
                    result["output"] = output_path
                    result["video_url"] = video_url
                break

        return result


def process_folder(folder_path: str, prompt: str, credentials: Dict):
    """Xử lý tất cả ảnh trong folder."""
    folder = Path(folder_path)

    if not folder.exists():
        print(f"Folder không tồn tại: {folder_path}")
        return

    # Tìm ảnh
    images = list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg")) + list(folder.glob("*.png"))

    if not images:
        print(f"Không tìm thấy ảnh trong: {folder_path}")
        return

    print(f"\nTìm thấy {len(images)} ảnh")

    # Output folder
    output_dir = folder / "videos"
    output_dir.mkdir(exist_ok=True)

    # Process
    generator = VideoGenerator(credentials)
    results = []

    for i, img in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}] {img.name}")
        result = generator.process_image(str(img), prompt, str(output_dir))
        results.append(result)

        if result["success"]:
            print(f"  → {result.get('output')}")
        else:
            print(f"  → Error: {result.get('error')}")

    # Summary
    success = sum(1 for r in results if r["success"])
    print(f"\n{'='*50}")
    print(f"HOÀN THÀNH: {success}/{len(images)} videos")
    print(f"Output: {output_dir}")

    # Save results
    with open(output_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def main():
    print("=" * 60)
    print("AUTO VIDEO GENERATOR")
    print("=" * 60)

    # Load saved credentials
    creds_file = Path(__file__).parent / "auto_video_creds.json"
    credentials = {}

    if creds_file.exists():
        with open(creds_file, "r", encoding="utf-8") as f:
            credentials = json.load(f)

        use_saved = input(f"\nCó credentials đã lưu. Dùng lại? (y/n): ").strip().lower()
        if use_saved != 'y':
            credentials = {}

    # Capture nếu chưa có
    if not credentials.get("token") or not credentials.get("recaptchaToken"):
        capturer = CredentialCapture()
        credentials = capturer.capture()

        if not credentials.get("token"):
            print("✗ Không capture được credentials!")
            return

        # Save
        with open(creds_file, "w", encoding="utf-8") as f:
            json.dump(credentials, f, indent=2)
        print(f"✓ Đã lưu credentials vào {creds_file}")

    # Kiểm tra x-browser-validation
    if not credentials.get("xBrowserValidation"):
        print("\n" + "=" * 60)
        print("⚠️  THIẾU x-browser-validation!")
        print("=" * 60)
        print("Cần lấy thủ công từ Chrome DevTools:")
        print("1. Mở Chrome DevTools (F12)")
        print("2. Vào tab Network")
        print("3. Tìm request tới 'aisandbox-pa.googleapis.com'")
        print("4. Click vào request → Headers → Request Headers")
        print("5. Copy giá trị 'x-browser-validation'")
        print("=" * 60)

        xbv = input("\nDán x-browser-validation vào đây: ").strip()
        if xbv:
            credentials["xBrowserValidation"] = xbv
            # Save lại
            with open(creds_file, "w", encoding="utf-8") as f:
                json.dump(credentials, f, indent=2)
            print("✓ Đã lưu x-browser-validation!")
        else:
            print("✗ Không có x-browser-validation, upload sẽ fail!")
            cont = input("Tiếp tục không? (y/n): ").strip().lower()
            if cont != 'y':
                return

    # Get folder path
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
    else:
        folder_path = input("\nNhập đường dẫn folder ảnh: ").strip()

    if not folder_path:
        folder_path = r"D:\AUTO\ve3-tool\images"

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
