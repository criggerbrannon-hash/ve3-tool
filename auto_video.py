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
    """Capture credentials từ Chrome."""

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
    videoPayload: null
};

(function(){
    var origFetch = window.fetch;

    window.fetch = function(url, opts) {
        var urlStr = url ? url.toString() : '';

        // Capture từ mọi request đến aisandbox
        if(urlStr.includes('aisandbox')) {
            var hdrs = opts && opts.headers ? opts.headers : {};

            // Token
            var auth = hdrs.Authorization || hdrs.authorization || '';
            if(auth.startsWith('Bearer ')) {
                window._captured.token = auth.substring(7);
            }

            // X-browser headers
            if(hdrs['x-browser-validation']) {
                window._captured.xBrowserValidation = hdrs['x-browser-validation'];
            }
            if(hdrs['x-client-data']) {
                window._captured.xClientData = hdrs['x-client-data'];
            }

            // Capture video generate payload
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
                console.log('=== CAPTURED VIDEO REQUEST ===');
            }
        }

        return origFetch.apply(this, arguments).then(function(resp) {
            // Capture operations từ response
            if(urlStr.includes('video:batchAsyncGenerateVideo') && !urlStr.includes('Check')) {
                resp.clone().json().then(function(data) {
                    if(data.operations) {
                        window._captured.operations = data.operations;
                        console.log('=== CAPTURED OPERATIONS ===');
                    }
                }).catch(function(){});
            }
            return resp;
        });
    };

    console.log('=== CAPTURE SCRIPT READY ===');
    console.log('Hãy tạo 1 video thủ công để capture credentials!');
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

    def wait_for_credentials(self, timeout: int = 180) -> Dict:
        """
        Đợi user tạo video thủ công và capture credentials.
        """
        self.log(f"Đợi bạn tạo 1 video thủ công (timeout: {timeout}s)...")
        self.log("Sau khi video bắt đầu generate, credentials sẽ được capture.")

        start_time = time.time()

        while time.time() - start_time < timeout:
            time.sleep(5)
            elapsed = int(time.time() - start_time)

            data = self.get_captured_data()

            # Check if we have all required data
            if data.get("token") and data.get("recaptchaToken"):
                self.log(f"\n✓ Captured sau {elapsed}s!")
                self.log(f"  Token: {data['token'][:50]}...")
                self.log(f"  ProjectID: {data.get('projectId')}")
                self.log(f"  RecaptchaToken: {data.get('recaptchaToken', '')[:50]}...")
                self.log(f"  X-Browser-Validation: {data.get('xBrowserValidation', '')[:30]}...")

                self.credentials = data
                return data

            self.log(f"Đợi... ({elapsed}s) - Token: {'✓' if data.get('token') else '✗'}, Recaptcha: {'✓' if data.get('recaptchaToken') else '✗'}")

        self.log("✗ Timeout! Không capture được đủ credentials.")
        return {}

    def capture(self) -> Dict:
        """
        Full flow: Mở Chrome → Inject → Đợi user → Capture
        """
        self.log("=" * 50)
        self.log("CAPTURE CREDENTIALS TỪ CHROME")
        self.log("=" * 50)

        # Mở Chrome
        self.log("\n[1] Mở Chrome...")
        if not self.open_chrome():
            return {}

        self.log("Đợi trang load (10s)...")
        time.sleep(10)

        # Inject script
        self.log("\n[2] Inject capture script...")
        if not self.inject_capture_script():
            return {}

        # Hướng dẫn user
        print("\n" + "=" * 50)
        print("HƯỚNG DẪN:")
        print("1. Trong Chrome, tạo 1 dự án mới")
        print("2. Chọn mode 'Tạo video từ các thành phần'")
        print("3. Upload hoặc chọn 1 ảnh")
        print("4. Nhập prompt và click TẠO")
        print("5. Đợi tool capture credentials...")
        print("=" * 50 + "\n")

        # Đợi capture
        self.log("\n[3] Đợi capture credentials...")
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
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
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
        """Upload ảnh → mediaId."""
        self.log(f"Upload: {Path(image_path).name}")

        with open(image_path, "rb") as f:
            raw_bytes = base64.b64encode(f.read()).decode("utf-8")

        url = f"{self.BASE_URL}/v1:uploadUserImage"
        payload = {"imageInput": {"rawImageBytes": raw_bytes}}

        try:
            resp = self.session.post(url, data=json.dumps(payload), timeout=120)

            if resp.status_code == 200:
                media_id = resp.json().get("mediaGenerationId", {}).get("mediaGenerationId")
                if media_id:
                    self.log(f"  ✓ mediaId: {media_id[:40]}...")
                    return media_id
            self.log(f"  ✗ Upload failed: {resp.status_code}")
            return None
        except Exception as e:
            self.log(f"  ✗ Error: {e}")
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
