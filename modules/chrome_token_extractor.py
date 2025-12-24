"""
VE3 Tool - Chrome Token Extractor
=================================
Tự động lấy Bearer Token từ Google Flow bằng Chrome profile.

Sử dụng Selenium với Chrome DevTools Protocol (CDP) để capture
Authorization header từ network requests.
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime


class ChromeTokenExtractor:
    """
    Tự động mở Chrome và lấy Bearer Token từ Google Flow.
    
    Sử dụng Chrome profile của user để bypass login.
    """
    
    FLOW_URL = "https://labs.google/fx/tools/flow"
    
    def __init__(
        self,
        chrome_path: str,
        profile_path: str,
        headless: bool = False,
        timeout: int = 60,
        debug_port: int = None
    ):
        """
        Khởi tạo extractor.

        Args:
            chrome_path: Đường dẫn đến chrome.exe
            profile_path: Đường dẫn đến Chrome User Data
            headless: Chạy ẩn không hiện UI
            timeout: Timeout cho việc lấy token (giây)
            debug_port: Port cho Chrome DevTools (mặc định random 9222-9322)
        """
        self.chrome_path = chrome_path
        self.profile_path = profile_path
        self.headless = headless
        self.timeout = timeout

        # Random port để tránh xung đột khi chạy nhiều instance
        import random
        self.debug_port = debug_port or random.randint(9222, 9322)

        self.driver = None
        self.bearer_token = None
        self.project_id = None

        # Extract profile info from path
        profile_path = Path(profile_path)
        default_folder = profile_path / "Default"

        if default_folder.exists():
            # Tool's user-data-dir (has Default inside)
            self.user_data_dir = str(profile_path)
            self.profile_name = None  # Chrome uses Default automatically
        else:
            # System Chrome profile folder
            self.profile_name = profile_path.name  # e.g., "Profile 2"
            self.user_data_dir = str(profile_path.parent)  # e.g., "C:\Users\...\User Data"

    def _create_driver(self):
        """Tạo Chrome WebDriver với CDP enabled."""
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options

        options = Options()

        # Use existing Chrome profile
        options.add_argument(f"--user-data-dir={self.user_data_dir}")
        if self.profile_name:
            options.add_argument(f"--profile-directory={self.profile_name}")
        
        # Chrome binary location
        options.binary_location = self.chrome_path
        
        # Enable CDP for network interception
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        
        if self.headless:
            options.add_argument("--headless=new")
        
        # Common options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,800")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Unique debug port để chạy nhiều instance song song
        options.add_argument(f"--remote-debugging-port={self.debug_port}")
        
        # Try to use webdriver-manager
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except ImportError:
            # Fallback to default
            service = Service()
        
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Execute CDP command to enable network tracking
        self.driver.execute_cdp_cmd("Network.enable", {})
    
    def _extract_token_from_logs(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract Bearer Token và Project ID từ Chrome performance logs.
        
        Returns:
            Tuple[bearer_token, project_id]
        """
        logs = self.driver.get_log("performance")
        
        for log in logs:
            try:
                message = json.loads(log["message"])
                method = message.get("message", {}).get("method", "")
                
                # Look for network request with Authorization header
                if method == "Network.requestWillBeSent":
                    params = message.get("message", {}).get("params", {})
                    request = params.get("request", {})
                    url = request.get("url", "")
                    headers = request.get("headers", {})
                    
                    # Check if this is a Flow API request
                    if "aisandbox-pa.googleapis.com" in url and "flowMedia" in url:
                        # Extract Authorization header
                        auth = headers.get("Authorization") or headers.get("authorization")
                        if auth and auth.startswith("Bearer "):
                            self.bearer_token = auth[7:]  # Remove "Bearer " prefix
                            
                            # Extract project ID from URL
                            # URL format: .../projects/{project_id}/flowMedia:...
                            if "/projects/" in url:
                                parts = url.split("/projects/")[1]
                                self.project_id = parts.split("/")[0]
                            
                            return self.bearer_token, self.project_id
                            
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
        
        return None, None
    
    def _trigger_image_generation(self):
        """
        Trigger một request tạo ảnh để capture token.
        
        Click vào nút Generate trên trang Flow.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        try:
            # Wait for page to load
            time.sleep(3)
            
            # Try to find and click generate button
            # Note: Selector có thể cần điều chỉnh
            selectors = [
                "button[aria-label*='Generate']",
                "button[aria-label*='Create']",
                "button:contains('Generate')",
                "[data-test='generate-button']",
                ".generate-button",
                "button.primary",
            ]
            
            for selector in selectors:
                try:
                    element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    element.click()
                    return True
                except:
                    continue
            
            # If no button found, try pressing Enter on textarea
            try:
                textarea = self.driver.find_element(By.TAG_NAME, "textarea")
                textarea.send_keys("test image for token extraction")
                textarea.submit()
                return True
            except:
                pass
            
            return False
            
        except Exception as e:
            print(f"Error triggering generation: {e}")
            return False
    
    def extract_token(
        self,
        callback=None
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Mở Chrome và lấy Bearer Token.
        
        Args:
            callback: Function để cập nhật progress (optional)
            
        Returns:
            Tuple[bearer_token, project_id, error_message]
        """
        error = ""
        
        try:
            if callback:
                callback("Đang khởi động Chrome...")
            
            self._create_driver()
            
            if callback:
                callback("Đang mở Google Flow...")
            
            # Navigate to Flow
            self.driver.get(self.FLOW_URL)
            time.sleep(5)  # Wait for page load and potential redirects
            
            if callback:
                callback("Đang chờ đăng nhập (nếu cần)...")
            
            # Check if we need to login
            current_url = self.driver.current_url
            if "accounts.google.com" in current_url:
                # Wait for manual login
                if callback:
                    callback("⚠️ Vui lòng đăng nhập Google trong cửa sổ Chrome...")
                
                # Wait up to 2 minutes for login
                for _ in range(120):
                    time.sleep(1)
                    if "labs.google" in self.driver.current_url:
                        break
                else:
                    return None, None, "Timeout waiting for login"
            
            if callback:
                callback("Đang capture token...")
            
            # Method 1: Wait for existing requests
            start_time = time.time()
            while time.time() - start_time < 10:
                token, project_id = self._extract_token_from_logs()
                if token:
                    if callback:
                        callback("✅ Đã lấy được token!")
                    return token, project_id, ""
                time.sleep(1)
            
            # Method 2: Trigger a generation to capture token
            if callback:
                callback("Đang trigger request để lấy token...")
            
            self._trigger_image_generation()
            
            # Wait for the request
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                token, project_id = self._extract_token_from_logs()
                if token:
                    if callback:
                        callback("✅ Đã lấy được token!")
                    return token, project_id, ""
                time.sleep(1)
            
            error = "Không thể capture được token. Thử tạo một ảnh thủ công trên trang Flow."
            
        except ImportError as e:
            error = f"Thiếu thư viện: {e}. Chạy: pip install selenium webdriver-manager"
        except Exception as e:
            error = f"Lỗi: {str(e)}"
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
        
        return None, None, error
    
    def extract_token_async(self, callback=None, on_complete=None):
        """
        Lấy token trong background thread.
        
        Args:
            callback: Function(message) để cập nhật progress
            on_complete: Function(token, project_id, error) khi hoàn thành
        """
        def worker():
            token, project_id, error = self.extract_token(callback)
            if on_complete:
                on_complete(token, project_id, error)
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread


class SimpleTokenCapture:
    """
    Cách đơn giản hơn: Dùng requests với cookies từ Chrome.
    
    Không cần mở browser, chỉ đọc cookies từ Chrome profile.
    """
    
    @staticmethod
    def get_chrome_cookies(profile_path: str, domain: str = ".google.com") -> Dict[str, str]:
        """
        Đọc cookies từ Chrome profile.
        
        Args:
            profile_path: Đường dẫn Chrome profile
            domain: Domain cần lấy cookies
            
        Returns:
            Dict cookies
        """
        import sqlite3
        import shutil
        import tempfile
        
        cookies_path = Path(profile_path) / "Network" / "Cookies"
        
        if not cookies_path.exists():
            # Try old location
            cookies_path = Path(profile_path) / "Cookies"
        
        if not cookies_path.exists():
            return {}
        
        # Copy to temp file (Chrome locks the original)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            tmp_path = tmp.name
        
        shutil.copy2(cookies_path, tmp_path)
        
        cookies = {}
        try:
            conn = sqlite3.connect(tmp_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT name, value, encrypted_value FROM cookies WHERE host_key LIKE ?",
                (f"%{domain}%",)
            )
            
            for name, value, encrypted_value in cursor.fetchall():
                if value:
                    cookies[name] = value
                # Note: encrypted_value needs DPAPI decryption on Windows
            
            conn.close()
        except Exception as e:
            print(f"Error reading cookies: {e}")
        finally:
            try:
                Path(tmp_path).unlink()
            except:
                pass
        
        return cookies


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    
    print("Chrome Token Extractor Test")
    print("=" * 50)
    
    # Default paths for Windows
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    profile_path = r"C:\Users\admin\AppData\Local\Google\Chrome\User Data\Profile 2"
    
    if len(sys.argv) >= 3:
        chrome_path = sys.argv[1]
        profile_path = sys.argv[2]
    
    print(f"Chrome: {chrome_path}")
    print(f"Profile: {profile_path}")
    
    def progress(msg):
        print(f"[Progress] {msg}")
    
    extractor = ChromeTokenExtractor(
        chrome_path=chrome_path,
        profile_path=profile_path,
        headless=False
    )
    
    token, project_id, error = extractor.extract_token(callback=progress)
    
    if token:
        print(f"\n✅ Success!")
        print(f"Token: {token[:50]}...")
        print(f"Project ID: {project_id}")
    else:
        print(f"\n❌ Failed: {error}")
