"""
VE3 Tool - Chrome Auto Token Extractor v2
==========================================
Tu dong 100% lay Bearer Token tu Google Flow.
Ho tro chay an (headless) khi da co Project ID.
"""

import json
import os
import shutil
import tempfile
import time
import threading
from pathlib import Path
from typing import Optional, Tuple, Callable
from datetime import datetime


class ChromeAutoToken:
    """
    Tu dong lay Bearer Token tu Google Flow.
    
    Features:
    - Copy Chrome profile de tranh xung dot
    - Tu dong tao project hoac dung project co san
    - Tu dong click chuyen sang mode tao anh
    - Capture token tu network requests
    - Ho tro headless mode
    """
    
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"
    
    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        headless: bool = False,
        timeout: int = 60
    ):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.headless = headless
        self.timeout = timeout
        
        self.driver = None
        self.temp_profile_dir = None
        self.bearer_token = None
        self.project_id = None
    
    def _copy_profile(self) -> str:
        """Copy Chrome profile sang thu muc tam."""
        if not self.profile_path or not Path(self.profile_path).exists():
            return None
        
        # Tao thu muc tam
        self.temp_profile_dir = tempfile.mkdtemp(prefix="ve3_chrome_")
        
        # Copy cac file quan trong
        src = Path(self.profile_path)
        dst = Path(self.temp_profile_dir) / "Profile"
        dst.mkdir(parents=True, exist_ok=True)
        
        important_files = [
            "Cookies", "Login Data", "Web Data", 
            "Preferences", "Secure Preferences",
            "Local State"
        ]
        
        for item in important_files:
            src_path = src / item
            if src_path.exists():
                try:
                    if src_path.is_file():
                        shutil.copy2(src_path, dst / item)
                    else:
                        shutil.copytree(src_path, dst / item, dirs_exist_ok=True)
                except Exception as e:
                    print(f"Warning: Could not copy {item}: {e}")
        
        # Copy Network folder (chua cookies moi)
        network_src = src / "Network"
        if network_src.exists():
            try:
                shutil.copytree(network_src, dst / "Network", dirs_exist_ok=True)
            except:
                pass
        
        return self.temp_profile_dir
    
    def _create_driver(self, use_temp_profile: bool = True):
        """Tao Chrome WebDriver."""
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        
        options = Options()
        
        # Profile
        if use_temp_profile and self.profile_path:
            temp_dir = self._copy_profile()
            if temp_dir:
                options.add_argument(f"--user-data-dir={temp_dir}")
                options.add_argument("--profile-directory=Profile")
        
        # Chrome binary
        if self.chrome_path and Path(self.chrome_path).exists():
            options.binary_location = self.chrome_path
        
        # Headless
        if self.headless:
            options.add_argument("--headless=new")
        
        # Performance logging for network capture
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        
        # Common options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1400,900")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        
        # Disable images in headless for speed
        if self.headless:
            prefs = {"profile.managed_default_content_settings.images": 2}
            options.add_experimental_option("prefs", prefs)
        
        # Get chromedriver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except:
            service = Service()
        
        self.driver = webdriver.Chrome(service=service, options=options)
        
        # Enable Network domain for CDP
        self.driver.execute_cdp_cmd("Network.enable", {})
    
    def _wait_for_element(self, by, value, timeout=10, clickable=False):
        """Doi element xuat hien."""
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        condition = EC.element_to_be_clickable if clickable else EC.presence_of_element_located
        return WebDriverWait(self.driver, timeout).until(condition((by, value)))
    
    def _extract_token_from_logs(self) -> Tuple[Optional[str], Optional[str]]:
        """Extract Bearer Token tu performance logs."""
        try:
            logs = self.driver.get_log("performance")
        except:
            return None, None
        
        for log in logs:
            try:
                msg = json.loads(log["message"])
                method = msg.get("message", {}).get("method", "")
                
                if method == "Network.requestWillBeSent":
                    params = msg.get("message", {}).get("params", {})
                    request = params.get("request", {})
                    url = request.get("url", "")
                    headers = request.get("headers", {})
                    
                    if "aisandbox-pa.googleapis.com" in url and "flowMedia" in url:
                        auth = headers.get("Authorization") or headers.get("authorization")
                        if auth and auth.startswith("Bearer "):
                            self.bearer_token = auth[7:]
                            
                            # Extract project ID
                            if "/projects/" in url:
                                parts = url.split("/projects/")[1]
                                self.project_id = parts.split("/")[0]
                            
                            return self.bearer_token, self.project_id
            except:
                continue
        
        return None, None
    
    def _navigate_to_flow(self, project_id: str = None):
        """Navigate den Flow."""
        if project_id:
            url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}"
        else:
            url = self.FLOW_URL
        
        self.driver.get(url)
        time.sleep(3)
    
    def _click_new_project(self) -> bool:
        """Click nut Du an moi."""
        from selenium.webdriver.common.by import By
        
        try:
            # Tim nut Du an moi
            selectors = [
                "//span[contains(text(), 'Dự án mới')]/..",
                "//button[contains(., 'Dự án mới')]",
                "//div[contains(text(), 'Dự án mới')]/..",
                "//*[contains(text(), '+ Dự án mới')]",
            ]
            
            for sel in selectors:
                try:
                    btn = self._wait_for_element(By.XPATH, sel, timeout=5, clickable=True)
                    btn.click()
                    time.sleep(2)
                    return True
                except:
                    continue
            
            return False
        except:
            return False
    
    def _switch_to_image_mode(self) -> bool:
        """Chuyen sang che do Tao hinh anh."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        
        try:
            # Click dropdown "Tu van ban sang video"
            dropdown_selectors = [
                "//button[contains(., 'Từ văn bản sang video')]",
                "//span[contains(text(), 'Từ văn bản sang video')]/..",
                "//button[@role='combobox']",
            ]
            
            for sel in dropdown_selectors:
                try:
                    dropdown = self._wait_for_element(By.XPATH, sel, timeout=5, clickable=True)
                    dropdown.click()
                    time.sleep(1)
                    break
                except:
                    continue
            
            # Click "Tao hinh anh"
            image_selectors = [
                "//div[contains(text(), 'Tạo hình ảnh')]",
                "//span[contains(text(), 'Tạo hình ảnh')]",
                "//*[contains(text(), 'Tạo hình ảnh')]",
            ]
            
            for sel in image_selectors:
                try:
                    btn = self._wait_for_element(By.XPATH, sel, timeout=3, clickable=True)
                    btn.click()
                    time.sleep(2)
                    return True
                except:
                    continue
            
            return False
        except:
            return False
    
    def _send_test_prompt(self) -> bool:
        """Gui prompt test de capture token."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        
        try:
            # Tim textarea
            textarea = self._wait_for_element(
                By.ID, "PINHOLE_TEXT_AREA_ELEMENT_ID", timeout=10
            )
            
            # Clear va gui prompt
            textarea.clear()
            textarea.send_keys("test image generation")
            time.sleep(0.5)
            textarea.send_keys(Keys.RETURN)
            
            return True
        except Exception as e:
            print(f"Send prompt error: {e}")
            
            # Fallback: tim textarea khac
            try:
                textarea = self._wait_for_element(By.TAG_NAME, "textarea", timeout=5)
                textarea.clear()
                textarea.send_keys("test")
                textarea.send_keys(Keys.RETURN)
                return True
            except:
                return False
    
    def _check_login(self) -> bool:
        """Kiem tra da dang nhap chua."""
        current_url = self.driver.current_url
        return "accounts.google.com" not in current_url
    
    def _wait_for_login(self, callback: Callable = None, timeout: int = 120):
        """Doi user dang nhap."""
        if callback:
            callback("Vui long dang nhap Google trong cua so Chrome...")
        
        start = time.time()
        while time.time() - start < timeout:
            if self._check_login():
                return True
            time.sleep(2)
        
        return False
    
    def extract_token(
        self,
        project_id: str = None,
        callback: Callable = None
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Lay Bearer Token.
        
        Args:
            project_id: Project ID co san (neu co se dung, neu khong se tao moi)
            callback: Function(message) de cap nhat progress
            
        Returns:
            Tuple[bearer_token, project_id, error_message]
        """
        error = ""
        
        try:
            if callback:
                callback("Dang khoi dong Chrome...")
            
            self._create_driver(use_temp_profile=True)
            
            if callback:
                callback("Dang mo Google Flow...")
            
            # Navigate
            self._navigate_to_flow(project_id)
            
            # Check login
            if not self._check_login():
                if self.headless:
                    return None, None, "Can dang nhap! Hay tat che do an hoac dang nhap truoc."
                
                if callback:
                    callback("Can dang nhap Google...")
                
                if not self._wait_for_login(callback):
                    return None, None, "Timeout cho dang nhap"
                
                # Re-navigate after login
                time.sleep(2)
                self._navigate_to_flow(project_id)
            
            time.sleep(3)
            
            # Neu khong co project_id, tao moi
            if not project_id:
                if callback:
                    callback("Dang tao project moi...")
                
                self._click_new_project()
                time.sleep(2)
                
                # Lay project_id tu URL
                current_url = self.driver.current_url
                if "/project/" in current_url:
                    project_id = current_url.split("/project/")[1].split("/")[0].split("?")[0]
                    self.project_id = project_id
            
            # Chuyen sang mode tao anh
            if callback:
                callback("Dang chuyen sang che do tao anh...")
            
            self._switch_to_image_mode()
            time.sleep(2)
            
            # Gui prompt de capture token
            if callback:
                callback("Dang capture token...")
            
            self._send_test_prompt()
            
            # Cho va capture token
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                token, pid = self._extract_token_from_logs()
                if token:
                    if callback:
                        callback("Da lay duoc token!")
                    return token, pid or project_id, ""
                time.sleep(1)
            
            error = "Khong capture duoc token. Vui long thu lai."
            
        except ImportError as e:
            error = f"Thieu thu vien: {e}\nChay: pip install selenium webdriver-manager"
        except Exception as e:
            error = f"Loi: {str(e)}"
        finally:
            self._cleanup()
        
        return None, None, error
    
    def _cleanup(self):
        """Don dep."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        if self.temp_profile_dir and Path(self.temp_profile_dir).exists():
            try:
                shutil.rmtree(self.temp_profile_dir, ignore_errors=True)
            except:
                pass
            self.temp_profile_dir = None
    
    def extract_token_async(
        self,
        project_id: str = None,
        callback: Callable = None,
        on_complete: Callable = None
    ):
        """
        Lay token trong background thread.
        
        Args:
            project_id: Project ID (optional)
            callback: Function(message) cap nhat progress
            on_complete: Function(token, project_id, error) khi xong
        """
        def worker():
            token, pid, error = self.extract_token(project_id, callback)
            if on_complete:
                on_complete(token, pid, error)
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread


class TokenManager:
    """
    Quan ly nhieu tokens va project IDs.
    """
    
    def __init__(self):
        self.tokens = []  # List of (token, project_id, timestamp)
        self.current_index = 0
    
    def add_token(self, token: str, project_id: str = None):
        """Them token moi."""
        self.tokens.append({
            "token": token,
            "project_id": project_id,
            "timestamp": datetime.now(),
            "used_count": 0
        })
    
    def get_next_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Lay token tiep theo (round-robin)."""
        if not self.tokens:
            return None, None
        
        token_info = self.tokens[self.current_index]
        token_info["used_count"] += 1
        
        # Move to next
        self.current_index = (self.current_index + 1) % len(self.tokens)
        
        return token_info["token"], token_info["project_id"]
    
    def get_valid_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Lay token con hieu luc (duoi 50 phut)."""
        now = datetime.now()
        
        for token_info in self.tokens:
            age = (now - token_info["timestamp"]).total_seconds()
            if age < 3000:  # 50 phut
                return token_info["token"], token_info["project_id"]
        
        return None, None
    
    def remove_expired(self):
        """Xoa cac token het han."""
        now = datetime.now()
        self.tokens = [
            t for t in self.tokens
            if (now - t["timestamp"]).total_seconds() < 3600
        ]
        
        if self.current_index >= len(self.tokens):
            self.current_index = 0
    
    def count(self) -> int:
        return len(self.tokens)


if __name__ == "__main__":
    import sys
    
    print("Chrome Auto Token Test")
    print("=" * 50)
    
    def progress(msg):
        print(f"[Progress] {msg}")
    
    extractor = ChromeAutoToken(
        headless=False  # Hien thi de debug
    )
    
    # Test voi project ID cu the (neu co)
    project_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    token, pid, error = extractor.extract_token(project_id=project_id, callback=progress)
    
    if token:
        print(f"\n✅ Success!")
        print(f"Token: {token[:50]}...")
        print(f"Project ID: {pid}")
    else:
        print(f"\n❌ Failed: {error}")
