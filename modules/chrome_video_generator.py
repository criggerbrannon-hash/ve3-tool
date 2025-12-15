"""
Chrome Video Generator
======================
Tự động tạo video bằng Chrome automation (Selenium).
Dùng Chrome Profile có sẵn → tận dụng cookies/session.

Flow:
1. Mở Chrome với profile user
2. Điều hướng đến Google Flow
3. Upload ảnh + nhập prompt qua JavaScript
4. Đợi video hoàn thành
5. Download video

Không cần capture headers phức tạp vì Chrome tự xử lý auth!
"""

import os
import sys
import time
import json
import base64
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Callable, Any
from datetime import datetime

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from webdriver_manager.chrome import ChromeDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False


class ChromeVideoGenerator:
    """
    Tạo video AI từ ảnh bằng Chrome automation.
    Tận dụng Chrome Profile có sẵn để sử dụng cookies/session.
    """

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        headless: bool = False
    ):
        """
        Khởi tạo Chrome Video Generator.

        Args:
            chrome_path: Path đến Chrome executable
            profile_path: Path đến Chrome Profile (đã đăng nhập Google)
            headless: True để chạy ẩn (không mở cửa sổ)
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError("Cần cài selenium: pip install selenium")

        self.chrome_path = chrome_path or self._find_chrome()
        self.profile_path = profile_path
        self.headless = headless
        self.driver = None
        self.callback = None

        # Captured data
        self.captured_data = {
            "token": None,
            "projectId": None,
            "mediaIds": [],
            "operations": [],
            "videoUrls": []
        }

    def log(self, msg: str):
        """Log message."""
        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{ts}] [ChromeVideo] {msg}"
        print(full_msg)
        if self.callback:
            self.callback(full_msg)

    def _find_chrome(self) -> str:
        """Tìm Chrome executable."""
        if sys.platform == "win32":
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
            ]
        elif sys.platform == "darwin":
            paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        else:
            paths = ["/usr/bin/google-chrome", "/usr/bin/chromium-browser"]

        for p in paths:
            if os.path.exists(p):
                return p

        return "chrome"

    def _create_driver(self) -> webdriver.Chrome:
        """Tạo Chrome WebDriver với profile."""
        options = Options()

        # Profile settings
        if self.profile_path:
            profile_dir = Path(self.profile_path)
            if "User Data" in str(profile_dir):
                user_data_dir = str(profile_dir.parent)
                profile_name = profile_dir.name
                options.add_argument(f"--user-data-dir={user_data_dir}")
                options.add_argument(f"--profile-directory={profile_name}")
            else:
                options.add_argument(f"--user-data-dir={self.profile_path}")

        # Other options
        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1920,1080")

        # Anti-detection
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Chrome binary
        if self.chrome_path and os.path.exists(self.chrome_path):
            options.binary_location = self.chrome_path

        # Create driver
        if WEBDRIVER_MANAGER_AVAILABLE:
            service = Service(ChromeDriverManager().install())
        else:
            service = Service()

        driver = webdriver.Chrome(service=service, options=options)

        # Anti-detection script
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                window.chrome = {runtime: {}};
            """
        })

        return driver

    def _inject_capture_script(self):
        """Inject script để capture API responses."""
        script = """
        window._videoCapture = {
            token: null,
            projectId: null,
            mediaIds: [],
            operations: [],
            videoUrls: [],
            errors: []
        };

        // Intercept fetch
        (function() {
            var origFetch = window.fetch;
            window.fetch = function(url, opts) {
                var urlStr = url ? url.toString() : '';

                return origFetch.apply(this, arguments).then(function(response) {
                    // Capture từ response
                    if (urlStr.includes('aisandbox') || urlStr.includes('googleapis')) {
                        response.clone().json().then(function(data) {
                            console.log('[CAPTURE] Response from:', urlStr.substring(0, 60));

                            // Upload response - lấy mediaId
                            if (urlStr.includes('uploadUserImage')) {
                                var mediaId = data.mediaGenerationId?.mediaGenerationId;
                                if (mediaId) {
                                    window._videoCapture.mediaIds.push(mediaId);
                                    console.log('[CAPTURE] MediaID:', mediaId);
                                }
                            }

                            // Generate response - lấy operations
                            if (urlStr.includes('batchAsyncGenerateVideo') && !urlStr.includes('Check')) {
                                if (data.operations) {
                                    window._videoCapture.operations = data.operations;
                                    console.log('[CAPTURE] Operations:', JSON.stringify(data.operations).substring(0, 100));
                                }
                            }

                            // Check status response - lấy video URL
                            if (urlStr.includes('CheckAsyncVideoGeneration') || urlStr.includes('batchCheck')) {
                                if (data.operations) {
                                    data.operations.forEach(function(op) {
                                        var videoUrl = op.videoUrl ||
                                            op.generatedVideo?.videoUrl ||
                                            op.generatedVideo?.fifeUrl;
                                        if (videoUrl && !window._videoCapture.videoUrls.includes(videoUrl)) {
                                            window._videoCapture.videoUrls.push(videoUrl);
                                            console.log('[CAPTURE] VideoURL:', videoUrl.substring(0, 80));
                                        }
                                    });
                                }
                            }
                        }).catch(function(e) {
                            console.log('[CAPTURE] Parse error:', e);
                        });
                    }

                    return response;
                }).catch(function(error) {
                    window._videoCapture.errors.push(error.toString());
                    throw error;
                });
            };

            console.log('=== VIDEO CAPTURE SCRIPT READY ===');
        })();
        """
        self.driver.execute_script(script)
        self.log("Injected capture script")

    def _get_captured_data(self) -> Dict:
        """Lấy data đã capture từ JavaScript."""
        try:
            data = self.driver.execute_script("return window._videoCapture;")
            return data or {}
        except:
            return {}

    def _wait_for_element(self, selector: str, timeout: int = 30, by: str = "css") -> Any:
        """Đợi element xuất hiện."""
        by_type = By.CSS_SELECTOR if by == "css" else By.XPATH
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by_type, selector))
            )
            return element
        except TimeoutException:
            return None

    def _click_element(self, selector: str, by: str = "css") -> bool:
        """Click element."""
        try:
            by_type = By.CSS_SELECTOR if by == "css" else By.XPATH
            element = self.driver.find_element(by_type, selector)
            element.click()
            return True
        except:
            return False

    def _click_by_text(self, text: str, tag: str = "*") -> bool:
        """Click element by text content."""
        try:
            xpath = f"//{tag}[contains(text(), '{text}')]"
            elements = self.driver.find_elements(By.XPATH, xpath)
            for el in elements:
                if el.is_displayed() and el.is_enabled():
                    el.click()
                    return True
            return False
        except:
            return False

    def start(self) -> bool:
        """Khởi động Chrome và điều hướng đến Flow."""
        self.log("Khởi động Chrome...")

        try:
            self.driver = self._create_driver()
            self.log(f"Chrome started with profile: {self.profile_path}")

            # Navigate
            self.log(f"Điều hướng đến: {self.FLOW_URL}")
            self.driver.get(self.FLOW_URL)
            time.sleep(5)

            # Inject capture script
            self._inject_capture_script()

            # Check if logged in
            if "accounts.google.com" in self.driver.current_url:
                self.log("Cần đăng nhập Google!")
                return False

            self.log("Sẵn sàng!")
            return True

        except Exception as e:
            self.log(f"Lỗi khởi động: {e}")
            return False

    def stop(self):
        """Đóng Chrome."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        self.log("Chrome đã đóng")

    def create_new_project(self) -> bool:
        """Click tạo dự án mới."""
        self.log("Tạo dự án mới...")

        # Click "Dự án mới" button
        clicked = self._click_by_text("Dự án mới", "button")
        if not clicked:
            clicked = self._click_by_text("New project", "button")

        time.sleep(3)
        return clicked

    def select_video_mode(self) -> bool:
        """Chọn chế độ video."""
        self.log("Chọn VIDEO mode...")

        # Click dropdown
        try:
            dropdown = self.driver.find_element(By.CSS_SELECTOR, 'button[role="combobox"]')
            dropdown.click()
            time.sleep(1)

            # Select video option
            clicked = self._click_by_text("Tạo video từ các thành phần")
            if not clicked:
                clicked = self._click_by_text("Create video from components")

            time.sleep(2)
            return clicked
        except:
            return False

    def click_create_video_text(self) -> bool:
        """Click 'Tạo một video bằng văn bản'."""
        self.log("Click 'Tạo video bằng văn bản'...")

        clicked = self._click_by_text("Tạo một video bằng văn bản")
        if not clicked:
            clicked = self._click_by_text("Create a video with text")

        time.sleep(2)
        return clicked

    def enter_prompt(self, prompt: str) -> bool:
        """Nhập prompt vào textarea."""
        self.log(f"Nhập prompt: {prompt[:50]}...")

        try:
            textarea = self.driver.find_element(By.TAG_NAME, "textarea")
            textarea.clear()
            textarea.send_keys(prompt)
            time.sleep(1)
            return True
        except:
            return False

    def upload_image_via_js(self, image_path: str) -> bool:
        """Upload ảnh bằng JavaScript (base64)."""
        self.log(f"Upload ảnh: {Path(image_path).name}")

        if not Path(image_path).exists():
            self.log(f"File không tồn tại: {image_path}")
            return False

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine mime type
        ext = Path(image_path).suffix.lower()
        mime_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp"
        }.get(ext, "image/png")

        # Create file input and trigger upload
        script = f"""
        (async function() {{
            // Convert base64 to blob
            var base64 = "{image_data}";
            var mimeType = "{mime_type}";
            var byteCharacters = atob(base64);
            var byteNumbers = new Array(byteCharacters.length);
            for (var i = 0; i < byteCharacters.length; i++) {{
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }}
            var byteArray = new Uint8Array(byteNumbers);
            var blob = new Blob([byteArray], {{type: mimeType}});

            // Create File
            var file = new File([blob], "image{ext}", {{type: mimeType}});

            // Find file input
            var inputs = document.querySelectorAll('input[type="file"]');
            if (inputs.length > 0) {{
                var input = inputs[0];

                // Create DataTransfer and set files
                var dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                input.files = dataTransfer.files;

                // Dispatch change event
                var event = new Event('change', {{bubbles: true}});
                input.dispatchEvent(event);

                console.log('[UPLOAD] File dispatched to input');
                return true;
            }}

            console.log('[UPLOAD] No file input found');
            return false;
        }})();
        """

        try:
            result = self.driver.execute_script(script)
            time.sleep(3)  # Wait for upload
            return True
        except Exception as e:
            self.log(f"Upload error: {e}")
            return False

    def click_add_button(self) -> bool:
        """Click nút ADD."""
        self.log("Click ADD...")

        # Find button with 'add' icon
        script = """
        var buttons = document.querySelectorAll('button');
        for (var btn of buttons) {
            var icon = btn.querySelector('i.google-symbols');
            if (icon && icon.textContent.trim() === 'add') {
                btn.click();
                return true;
            }
        }
        return false;
        """
        result = self.driver.execute_script(script)
        time.sleep(2)
        return result

    def select_uploaded_media(self) -> bool:
        """Chọn media đã upload."""
        self.log("Chọn ảnh đã upload...")

        clicked = self._click_by_text("đã tải lên")
        if not clicked:
            clicked = self._click_by_text("uploaded")
        if not clicked:
            clicked = self._click_by_text("nội dung nghe nhìn")

        time.sleep(2)
        return clicked

    def click_create_button(self) -> bool:
        """Click nút TẠO."""
        self.log("Click TẠO...")

        # Try icon first
        script = """
        var buttons = document.querySelectorAll('button');
        for (var btn of buttons) {
            var icon = btn.querySelector('i.google-symbols');
            if (icon && icon.textContent.trim() === 'arrow_forward') {
                btn.click();
                return true;
            }
        }
        return false;
        """
        result = self.driver.execute_script(script)

        if not result:
            result = self._click_by_text("Tạo", "button")
            if not result:
                result = self._click_by_text("Create", "button")

        time.sleep(2)
        return result

    def wait_for_video(self, timeout: int = 300) -> Optional[str]:
        """Đợi video hoàn thành và lấy URL."""
        self.log(f"Đợi video (max {timeout}s)...")

        start = time.time()

        while time.time() - start < timeout:
            # Get captured data
            data = self._get_captured_data()
            video_urls = data.get("videoUrls", [])

            if video_urls:
                self.log(f"Video URL found!")
                return video_urls[0]

            # Check for completion in UI
            try:
                # Look for download button or video element
                video_elements = self.driver.find_elements(By.TAG_NAME, "video")
                if video_elements:
                    src = video_elements[0].get_attribute("src")
                    if src:
                        self.log(f"Video element found!")
                        return src
            except:
                pass

            elapsed = int(time.time() - start)
            if elapsed % 15 == 0:
                self.log(f"Đang đợi... {elapsed}s")

            time.sleep(5)

        self.log("Timeout!")
        return None

    def download_video(self, video_url: str, output_path: str) -> bool:
        """Download video từ URL."""
        self.log(f"Download video...")

        try:
            import requests
            resp = requests.get(video_url, timeout=120)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                self.log(f"Saved: {output_path}")
                return True
            return False
        except Exception as e:
            self.log(f"Download error: {e}")
            return False

    def process_image(
        self,
        image_path: str,
        prompt: str,
        output_dir: str
    ) -> Dict[str, Any]:
        """
        Xử lý 1 ảnh: setup → upload → generate → download.

        Args:
            image_path: Path đến file ảnh
            prompt: Prompt cho video
            output_dir: Thư mục output

        Returns:
            Dict với keys: success, output, video_url, error
        """
        result = {"image": image_path, "success": False}

        try:
            # 1. Create new project
            if not self.create_new_project():
                result["error"] = "Failed to create new project"
                return result

            # 2. Select video mode
            if not self.select_video_mode():
                result["error"] = "Failed to select video mode"
                return result

            # 3. Click create video text
            if not self.click_create_video_text():
                result["error"] = "Failed to click create video"
                return result

            # 4. Enter prompt
            if not self.enter_prompt(prompt):
                result["error"] = "Failed to enter prompt"
                return result

            # 5. Click ADD
            if not self.click_add_button():
                result["error"] = "Failed to click ADD"
                return result

            # 6. Upload image
            if not self.upload_image_via_js(image_path):
                result["error"] = "Failed to upload image"
                return result

            # 7. Select uploaded media
            time.sleep(2)
            self.select_uploaded_media()

            # 8. Click CREATE
            if not self.click_create_button():
                result["error"] = "Failed to click CREATE"
                return result

            # 9. Wait for video
            video_url = self.wait_for_video()
            if not video_url:
                result["error"] = "Video generation timeout"
                return result

            # 10. Download
            filename = Path(image_path).stem + "_video.mp4"
            output_path = str(Path(output_dir) / filename)

            if self.download_video(video_url, output_path):
                result["success"] = True
                result["output"] = output_path
                result["video_url"] = video_url
            else:
                result["error"] = "Download failed"

        except Exception as e:
            result["error"] = str(e)

        return result

    def process_folder(
        self,
        folder_path: str,
        prompt: str,
        output_dir: str = None,
        max_images: int = 10
    ) -> Dict[str, Any]:
        """
        Xử lý nhiều ảnh trong folder.

        Args:
            folder_path: Đường dẫn folder chứa ảnh
            prompt: Prompt cho video
            output_dir: Thư mục output (None = folder/videos)
            max_images: Số ảnh tối đa

        Returns:
            Dict với keys: success_count, failed_count, results
        """
        folder = Path(folder_path)

        if not folder.exists():
            return {"error": "Folder không tồn tại"}

        # Find images
        images = list(folder.glob("*.png")) + list(folder.glob("*.jpg")) + list(folder.glob("*.jpeg"))
        images = sorted(images)[:max_images]

        if not images:
            return {"error": "Không tìm thấy ảnh"}

        self.log(f"Tìm thấy {len(images)} ảnh")

        # Output dir
        if output_dir is None:
            output_dir = str(folder / "videos")
        Path(output_dir).mkdir(exist_ok=True)

        # Start Chrome
        if not self.start():
            return {"error": "Không thể khởi động Chrome"}

        try:
            results = []

            for i, img in enumerate(images, 1):
                self.log(f"\n[{i}/{len(images)}] {img.name}")
                result = self.process_image(str(img), prompt, output_dir)
                results.append(result)

                if result["success"]:
                    self.log(f"  ✓ {result.get('output')}")
                else:
                    self.log(f"  ✗ {result.get('error')}")

                # Wait between videos
                if i < len(images):
                    time.sleep(5)

            success_count = sum(1 for r in results if r["success"])

            return {
                "success_count": success_count,
                "failed_count": len(results) - success_count,
                "results": results,
                "output_dir": output_dir
            }

        finally:
            self.stop()


# ============================================================================
# CLI
# ============================================================================

def main():
    print("=" * 60)
    print("CHROME VIDEO GENERATOR")
    print("=" * 60)

    import sys

    # Get Chrome profile
    profile_path = input("Chrome profile path (Enter để dùng default): ").strip()
    if not profile_path:
        if sys.platform == "win32":
            profile_path = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default")

    # Get folder
    folder_path = input("Folder ảnh: ").strip()
    if not folder_path:
        print("Cần nhập folder!")
        return

    # Get prompt
    prompt = input("Prompt (Enter để dùng mặc định): ").strip()
    if not prompt:
        prompt = "Animate this image with smooth, natural motion"

    # Process
    generator = ChromeVideoGenerator(profile_path=profile_path)
    results = generator.process_folder(folder_path, prompt)

    if "error" in results:
        print(f"\n❌ Error: {results['error']}")
    else:
        print(f"\n✅ Hoàn thành: {results['success_count']}/{results['success_count'] + results['failed_count']}")
        print(f"Output: {results['output_dir']}")


if __name__ == "__main__":
    main()
