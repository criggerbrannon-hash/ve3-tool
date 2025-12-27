"""
VE3 Tool - Video Service Manager
================================
Quản lý video generation từ nhiều services (Sora, Gemini, Grok) với:
- Limit detection cho mỗi service
- Tự động chuyển Chrome profile khi bị limit
- Retry với profile khác khi 3-5 lần thất bại liên tiếp

Services hỗ trợ:
- Sora (sora.com) - OpenAI
- Gemini Veo (labs.google/fx) - Google
- Grok (x.com/grok) - xAI

Mỗi Chrome profile đã đăng nhập tài khoản khác nhau.
Khi 1 tài khoản bị limit hàng ngày, chuyển sang profile khác.
"""

import time
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

# Optional selenium imports
SELENIUM_AVAILABLE = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
        StaleElementReferenceException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    webdriver = None
    Options = None
    Service = None
    By = None
    Keys = None
    WebDriverWait = None
    EC = None
    TimeoutException = Exception
    NoSuchElementException = Exception
    WebDriverException = Exception
    StaleElementReferenceException = Exception


class VideoService(Enum):
    """Các dịch vụ video generation được hỗ trợ."""
    SORA = "sora"
    GEMINI = "gemini"
    GROK = "grok"


@dataclass
class ServiceConfig:
    """Cấu hình cho mỗi dịch vụ video."""
    name: str
    url: str
    # Các dấu hiệu nhận biết limit (text trong page)
    limit_indicators: List[str] = field(default_factory=list)
    # CSS selectors
    prompt_input_selector: str = ""
    submit_button_selector: str = ""
    video_result_selector: str = ""
    error_message_selector: str = ""
    # Timeouts (giây)
    generation_timeout: int = 300
    page_load_timeout: int = 30


# Cấu hình mặc định cho các services
SERVICE_CONFIGS: Dict[VideoService, ServiceConfig] = {
    VideoService.SORA: ServiceConfig(
        name="Sora",
        url="https://sora.com",
        limit_indicators=[
            "You're out of video gens",
            "Limit reached for today",
            "out of video gens",
            "Buy more gens",
            "invite a friend to get more gens"
        ],
        prompt_input_selector="textarea[placeholder*='prompt']",
        submit_button_selector="button[type='submit']",
        video_result_selector="video",
        error_message_selector=".error-message",
        generation_timeout=300,
        page_load_timeout=30
    ),
    VideoService.GEMINI: ServiceConfig(
        name="Gemini Veo",
        url="https://labs.google/fx/vi/tools/flow",
        limit_indicators=[
            "đã đạt giới hạn",
            "limit reached",
            "quota exceeded",
            "rate limit"
        ],
        prompt_input_selector="textarea",
        submit_button_selector="button[aria-label='Generate']",
        video_result_selector="video",
        error_message_selector=".error",
        generation_timeout=300,
        page_load_timeout=30
    ),
    VideoService.GROK: ServiceConfig(
        name="Grok",
        url="https://x.com/i/grok",
        limit_indicators=[
            "limit reached",
            "too many requests",
            "quota exceeded",
            "try again later"
        ],
        prompt_input_selector="textarea",
        submit_button_selector="button[type='submit']",
        video_result_selector="video",
        error_message_selector=".error",
        generation_timeout=300,
        page_load_timeout=30
    )
}


@dataclass
class ProfileStatus:
    """Trạng thái của một Chrome profile."""
    path: str
    name: str
    is_limited: bool = False
    limit_detected_at: Optional[datetime] = None
    consecutive_failures: int = 0
    total_success: int = 0
    total_failed: int = 0
    last_used: Optional[datetime] = None

    def mark_limited(self):
        """Đánh dấu profile đã bị limit."""
        self.is_limited = True
        self.limit_detected_at = datetime.now()

    def mark_success(self):
        """Đánh dấu thành công."""
        self.consecutive_failures = 0
        self.total_success += 1
        self.last_used = datetime.now()

    def mark_failure(self):
        """Đánh dấu thất bại."""
        self.consecutive_failures += 1
        self.total_failed += 1
        self.last_used = datetime.now()

    def is_usable(self) -> bool:
        """Kiểm tra profile có thể dùng không."""
        if not self.is_limited:
            return True
        # Reset limit sau 24h
        if self.limit_detected_at:
            reset_time = self.limit_detected_at + timedelta(hours=24)
            if datetime.now() > reset_time:
                self.is_limited = False
                self.limit_detected_at = None
                return True
        return False


class VideoServiceManager:
    """
    Quản lý video generation với limit detection và profile rotation.

    Sử dụng:
    ```python
    manager = VideoServiceManager(
        chrome_path="C:/Program Files/Google/Chrome/Application/chrome.exe",
        profiles_dir="./chrome_profiles",
        log_callback=print
    )

    # Generate video - tự động xử lý limit và chuyển profile
    success, video_url, error = manager.generate_video(
        service=VideoService.SORA,
        prompt="A cat playing piano",
        output_dir="./output"
    )
    ```
    """

    # Số lần thất bại liên tiếp trước khi coi như limit
    MAX_CONSECUTIVE_FAILURES = 4

    def __init__(
        self,
        chrome_path: str = None,
        profiles_dir: str = "./chrome_profiles",
        headless: bool = False,
        log_callback: Optional[Callable] = None,
        status_file: str = None
    ):
        """
        Khởi tạo VideoServiceManager.

        Args:
            chrome_path: Đường dẫn Chrome executable
            profiles_dir: Thư mục chứa Chrome profiles
            headless: Chạy ẩn trình duyệt
            log_callback: Callback để log (message, level)
            status_file: File lưu trạng thái profiles (JSON)
        """
        self.chrome_path = chrome_path or self._find_chrome()
        self.profiles_dir = Path(profiles_dir)
        self.headless = headless
        self.log_callback = log_callback
        self.status_file = Path(status_file) if status_file else self.profiles_dir / "profile_status.json"

        # Profile management
        self.profiles: Dict[str, ProfileStatus] = {}
        self.current_profile_index = 0

        # Driver
        self.driver = None
        self.current_profile: Optional[ProfileStatus] = None

        # Load profiles
        self._load_profiles()
        self._load_status()

    def _log(self, message: str, level: str = "INFO"):
        """Log message."""
        if self.log_callback:
            self.log_callback(message, level)
        else:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [{level}] {message}")

    def _find_chrome(self) -> str:
        """Tìm Chrome executable."""
        import platform

        if platform.system() == "Windows":
            paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
        elif platform.system() == "Darwin":
            paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        else:
            paths = ["/usr/bin/google-chrome", "/usr/bin/chromium-browser"]

        for path in paths:
            if Path(path).exists():
                return path

        return "chrome"

    def _load_profiles(self):
        """Load danh sách Chrome profiles từ thư mục."""
        if not self.profiles_dir.exists():
            self.profiles_dir.mkdir(parents=True, exist_ok=True)
            self._log(f"Tạo thư mục profiles: {self.profiles_dir}")
            return

        for item in self.profiles_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                profile_path = str(item)
                if profile_path not in self.profiles:
                    self.profiles[profile_path] = ProfileStatus(
                        path=profile_path,
                        name=item.name
                    )

        self._log(f"Loaded {len(self.profiles)} Chrome profiles")
        for path, status in self.profiles.items():
            self._log(f"  - {status.name}: {'LIMITED' if status.is_limited else 'OK'}")

    def _load_status(self):
        """Load trạng thái profiles từ file."""
        if not self.status_file.exists():
            return

        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for path, status_data in data.items():
                if path in self.profiles:
                    profile = self.profiles[path]
                    profile.is_limited = status_data.get('is_limited', False)
                    profile.consecutive_failures = status_data.get('consecutive_failures', 0)
                    profile.total_success = status_data.get('total_success', 0)
                    profile.total_failed = status_data.get('total_failed', 0)

                    if status_data.get('limit_detected_at'):
                        profile.limit_detected_at = datetime.fromisoformat(status_data['limit_detected_at'])
                    if status_data.get('last_used'):
                        profile.last_used = datetime.fromisoformat(status_data['last_used'])

            self._log(f"Loaded profile status from {self.status_file}")
        except Exception as e:
            self._log(f"Error loading status: {e}", "WARN")

    def _save_status(self):
        """Lưu trạng thái profiles ra file."""
        try:
            data = {}
            for path, profile in self.profiles.items():
                data[path] = {
                    'name': profile.name,
                    'is_limited': profile.is_limited,
                    'consecutive_failures': profile.consecutive_failures,
                    'total_success': profile.total_success,
                    'total_failed': profile.total_failed,
                    'limit_detected_at': profile.limit_detected_at.isoformat() if profile.limit_detected_at else None,
                    'last_used': profile.last_used.isoformat() if profile.last_used else None
                }

            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._log(f"Error saving status: {e}", "WARN")

    def get_available_profiles(self) -> List[ProfileStatus]:
        """Lấy danh sách profiles có thể dùng (chưa bị limit)."""
        return [p for p in self.profiles.values() if p.is_usable()]

    def get_next_profile(self) -> Optional[ProfileStatus]:
        """
        Lấy profile tiếp theo để sử dụng.
        Bỏ qua các profile đã bị limit.
        """
        available = self.get_available_profiles()

        if not available:
            self._log("⚠️ TẤT CẢ profiles đều đã bị LIMIT!", "ERROR")
            return None

        # Round-robin qua các profile available
        self.current_profile_index = self.current_profile_index % len(available)
        profile = available[self.current_profile_index]
        self.current_profile_index += 1

        return profile

    def switch_profile(self, reason: str = ""):
        """
        Chuyển sang profile khác.

        Args:
            reason: Lý do chuyển profile
        """
        self._log(f"🔄 Chuyển profile: {reason}")

        # Đóng driver hiện tại
        self.close_driver()

        # Lấy profile mới
        new_profile = self.get_next_profile()

        if new_profile:
            self._log(f"→ Profile mới: {new_profile.name}")
            self.current_profile = new_profile
        else:
            self._log("❌ Không còn profile nào khả dụng!", "ERROR")

    def _create_driver(self, profile: ProfileStatus) -> bool:
        """
        Tạo Chrome driver với profile chỉ định.

        Returns:
            True nếu thành công
        """
        if not SELENIUM_AVAILABLE:
            self._log("Selenium không được cài đặt!", "ERROR")
            return False

        try:
            options = Options()

            # Profile
            options.add_argument(f"--user-data-dir={profile.path}")

            # Common options
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

            if self.headless:
                options.add_argument("--headless=new")

            # Disable automation flags
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            # Create driver
            if self.chrome_path and Path(self.chrome_path).exists():
                options.binary_location = self.chrome_path

            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(60)
            self.current_profile = profile

            self._log(f"✓ Chrome started với profile: {profile.name}")
            return True

        except Exception as e:
            self._log(f"Lỗi khởi tạo Chrome: {e}", "ERROR")
            return False

    def close_driver(self):
        """Đóng Chrome driver."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def _check_limit_indicators(self, service: VideoService) -> bool:
        """
        Kiểm tra xem page có chứa dấu hiệu limit không.

        Returns:
            True nếu phát hiện limit
        """
        if not self.driver:
            return False

        config = SERVICE_CONFIGS[service]
        page_source = self.driver.page_source.lower()

        for indicator in config.limit_indicators:
            if indicator.lower() in page_source:
                self._log(f"⚠️ LIMIT DETECTED: '{indicator}'", "WARN")
                return True

        return False

    def _detect_limit_from_element(self, service: VideoService) -> bool:
        """
        Kiểm tra limit từ các element cụ thể trên trang.

        Returns:
            True nếu phát hiện limit
        """
        if not self.driver:
            return False

        config = SERVICE_CONFIGS[service]

        # Tìm trong toàn bộ text của page
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()

            for indicator in config.limit_indicators:
                if indicator.lower() in body_text:
                    self._log(f"⚠️ LIMIT DETECTED trong body: '{indicator}'", "WARN")
                    return True
        except:
            pass

        # Tìm trong các div có class liên quan đến error/limit
        try:
            error_elements = self.driver.find_elements(By.CSS_SELECTOR,
                "[class*='error'], [class*='limit'], [class*='warning'], [class*='alert']")

            for elem in error_elements:
                text = elem.text.lower()
                for indicator in config.limit_indicators:
                    if indicator.lower() in text:
                        self._log(f"⚠️ LIMIT DETECTED trong element: '{indicator}'", "WARN")
                        return True
        except:
            pass

        return False

    def generate_video(
        self,
        service: VideoService,
        prompt: str,
        output_dir: str = "./output",
        max_retries: int = 3,
        retry_with_new_profile: bool = True
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate video từ service chỉ định.
        Tự động xử lý limit và chuyển profile khi cần.

        Args:
            service: Dịch vụ video (SORA, GEMINI, GROK)
            prompt: Prompt mô tả video
            output_dir: Thư mục lưu video
            max_retries: Số lần retry tối đa
            retry_with_new_profile: Chuyển profile khi gặp limit

        Returns:
            Tuple[success, video_url/path, error_message]
        """
        config = SERVICE_CONFIGS[service]
        self._log(f"🎬 [{config.name}] Generating video...")
        self._log(f"   Prompt: {prompt[:80]}...")

        attempts = 0
        profiles_tried = set()

        while attempts < max_retries:
            attempts += 1

            # Lấy profile
            if not self.current_profile or not self.current_profile.is_usable():
                profile = self.get_next_profile()
                if not profile:
                    return False, None, "Không còn profile nào khả dụng (tất cả đều đã bị limit)"
                self.current_profile = profile

            profile_path = self.current_profile.path

            # Kiểm tra đã thử profile này chưa
            if profile_path in profiles_tried and retry_with_new_profile:
                # Đã thử profile này rồi, chuyển sang profile khác
                self.switch_profile("Đã thử profile này")
                continue

            profiles_tried.add(profile_path)
            self._log(f"[{attempts}/{max_retries}] Sử dụng profile: {self.current_profile.name}")

            # Tạo driver nếu chưa có
            if not self.driver:
                if not self._create_driver(self.current_profile):
                    self.current_profile.mark_failure()
                    self._save_status()
                    continue

            # Thực hiện generate
            try:
                success, result, error = self._do_generate(service, prompt, output_dir)

                if success:
                    self.current_profile.mark_success()
                    self._save_status()
                    return True, result, None

                # Kiểm tra có phải limit không
                is_limit = self._check_limit_indicators(service) or \
                           self._detect_limit_from_element(service)

                if is_limit:
                    self._log(f"⛔ Profile {self.current_profile.name} đã bị LIMIT!")
                    self.current_profile.mark_limited()
                    self._save_status()

                    if retry_with_new_profile:
                        self.switch_profile("Limit detected")
                        continue
                    else:
                        return False, None, f"Limit detected: {error}"

                # Thất bại nhưng không phải limit
                self.current_profile.mark_failure()
                self._save_status()

                # Kiểm tra consecutive failures
                if self.current_profile.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    self._log(f"⚠️ {self.MAX_CONSECUTIVE_FAILURES} lần thất bại liên tiếp - có thể đã bị limit")
                    self.current_profile.mark_limited()
                    self._save_status()

                    if retry_with_new_profile:
                        self.switch_profile(f"{self.MAX_CONSECUTIVE_FAILURES} consecutive failures")
                        continue

                self._log(f"Lỗi: {error}", "WARN")

            except Exception as e:
                self._log(f"Exception: {e}", "ERROR")
                self.current_profile.mark_failure()
                self._save_status()

        return False, None, f"Đã thử {max_retries} lần với {len(profiles_tried)} profile(s) - không thành công"

    def _do_generate(
        self,
        service: VideoService,
        prompt: str,
        output_dir: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Thực hiện generate video.
        Override method này cho từng service cụ thể.

        Returns:
            Tuple[success, video_url/path, error_message]
        """
        config = SERVICE_CONFIGS[service]

        # Navigate to service URL
        try:
            self.driver.get(config.url)
            time.sleep(3)
        except Exception as e:
            return False, None, f"Không thể mở trang: {e}"

        # Kiểm tra limit ngay khi vào trang
        if self._check_limit_indicators(service):
            return False, None, "Limit detected on page load"

        # TODO: Implement specific generation logic for each service
        # This is a template - specific implementation needed for each service

        if service == VideoService.SORA:
            return self._generate_sora(prompt, output_dir)
        elif service == VideoService.GEMINI:
            return self._generate_gemini(prompt, output_dir)
        elif service == VideoService.GROK:
            return self._generate_grok(prompt, output_dir)

        return False, None, "Service không được hỗ trợ"

    def _generate_sora(self, prompt: str, output_dir: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Generate video với Sora."""
        try:
            # Đợi trang load
            time.sleep(2)

            # Kiểm tra limit message trước
            if self._check_limit_indicators(VideoService.SORA):
                return False, None, "Sora limit reached"

            # Tìm input prompt
            # Sora sử dụng div có contenteditable hoặc textarea
            prompt_input = None
            selectors = [
                "textarea[placeholder*='prompt']",
                "textarea[placeholder*='Describe']",
                "div[contenteditable='true']",
                "textarea"
            ]

            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        prompt_input = elements[0]
                        break
                except:
                    continue

            if not prompt_input:
                return False, None, "Không tìm thấy input prompt"

            # Nhập prompt
            prompt_input.clear()
            prompt_input.send_keys(prompt)
            time.sleep(1)

            # Tìm và click nút Generate
            submit_button = None
            button_selectors = [
                "button[type='submit']",
                "button[aria-label*='Generate']",
                "button[aria-label*='Create']",
                "button:contains('Generate')"
            ]

            for selector in button_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if buttons:
                        submit_button = buttons[0]
                        break
                except:
                    continue

            if submit_button:
                submit_button.click()
            else:
                # Thử Enter
                prompt_input.send_keys(Keys.RETURN)

            time.sleep(2)

            # Kiểm tra limit sau khi submit
            if self._check_limit_indicators(VideoService.SORA):
                return False, None, "Sora limit reached after submit"

            # Đợi video generate (timeout 5 phút)
            self._log("Đợi video generate...")
            config = SERVICE_CONFIGS[VideoService.SORA]

            start_time = time.time()
            while time.time() - start_time < config.generation_timeout:
                # Kiểm tra limit
                if self._check_limit_indicators(VideoService.SORA):
                    return False, None, "Sora limit reached during generation"

                # Tìm video element
                try:
                    videos = self.driver.find_elements(By.TAG_NAME, "video")
                    for video in videos:
                        src = video.get_attribute("src")
                        if src and "blob:" not in src:
                            self._log(f"✓ Video found: {src[:60]}...")
                            return True, src, None
                except:
                    pass

                time.sleep(5)

            return False, None, "Timeout chờ video"

        except Exception as e:
            return False, None, str(e)

    def _generate_gemini(self, prompt: str, output_dir: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Generate video với Gemini Veo."""
        # Similar implementation to Sora but for Gemini
        # TODO: Implement Gemini-specific logic
        return False, None, "Gemini generation chưa được implement"

    def _generate_grok(self, prompt: str, output_dir: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Generate video với Grok."""
        # TODO: Implement Grok-specific logic
        return False, None, "Grok generation chưa được implement"

    def process_batch(
        self,
        service: VideoService,
        items: List[Dict[str, Any]],
        output_dir: str = "./output",
        on_progress: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Xử lý batch nhiều video.
        Tự động chuyển profile khi bị limit.

        Args:
            service: Dịch vụ video
            items: Danh sách items [{prompt, filename, ...}]
            output_dir: Thư mục output
            on_progress: Callback(current, total, result)

        Returns:
            Dict với thống kê
        """
        results = {
            "total": len(items),
            "success": 0,
            "failed": 0,
            "limited": 0,
            "items": []
        }

        self._log(f"🚀 Bắt đầu batch {len(items)} videos với {service.value}")
        self._log(f"   Profiles khả dụng: {len(self.get_available_profiles())}")

        for i, item in enumerate(items):
            prompt = item.get("prompt", "")
            filename = item.get("filename", f"video_{i+1}")

            self._log(f"\n[{i+1}/{len(items)}] {filename}")

            success, result, error = self.generate_video(
                service=service,
                prompt=prompt,
                output_dir=output_dir,
                max_retries=3,
                retry_with_new_profile=True
            )

            item_result = {
                "filename": filename,
                "success": success,
                "result": result,
                "error": error
            }
            results["items"].append(item_result)

            if success:
                results["success"] += 1
            else:
                results["failed"] += 1
                if "limit" in (error or "").lower():
                    results["limited"] += 1

            if on_progress:
                on_progress(i + 1, len(items), item_result)

            # Kiểm tra còn profile không
            if not self.get_available_profiles():
                self._log("⛔ TẤT CẢ profiles đều bị LIMIT! Dừng batch.", "ERROR")
                break

            # Delay giữa các request
            if i < len(items) - 1:
                time.sleep(2)

        # Đóng driver
        self.close_driver()

        # Log kết quả
        self._log(f"\n{'='*50}")
        self._log(f"📊 Kết quả batch:")
        self._log(f"   ✓ Thành công: {results['success']}/{results['total']}")
        self._log(f"   ✗ Thất bại: {results['failed']}")
        self._log(f"   ⛔ Do limit: {results['limited']}")

        return results

    def get_status_summary(self) -> str:
        """Lấy tóm tắt trạng thái profiles."""
        lines = ["📊 Profile Status:"]

        for path, profile in self.profiles.items():
            status = "⛔ LIMITED" if profile.is_limited else "✓ OK"
            lines.append(f"  - {profile.name}: {status}")
            lines.append(f"    Success: {profile.total_success}, Failed: {profile.total_failed}")
            if profile.is_limited and profile.limit_detected_at:
                reset_time = profile.limit_detected_at + timedelta(hours=24)
                lines.append(f"    Reset at: {reset_time.strftime('%Y-%m-%d %H:%M')}")

        return "\n".join(lines)

    def reset_all_limits(self):
        """Reset tất cả limit status (test/debug)."""
        for profile in self.profiles.values():
            profile.is_limited = False
            profile.limit_detected_at = None
            profile.consecutive_failures = 0

        self._save_status()
        self._log("✓ Đã reset tất cả limit status")


# Tiện ích
def create_video_manager(
    chrome_path: str = None,
    profiles_dir: str = "./chrome_profiles",
    headless: bool = False,
    log_callback: Optional[Callable] = None
) -> VideoServiceManager:
    """Factory function để tạo VideoServiceManager."""
    return VideoServiceManager(
        chrome_path=chrome_path,
        profiles_dir=profiles_dir,
        headless=headless,
        log_callback=log_callback
    )
