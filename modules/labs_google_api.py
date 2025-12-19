"""
VE3 Tool - Labs Google API Module
=================================
Tạo ảnh qua labs.google API với Next.js session token + CAPTCHA solver.

Khác với google_flow_api.py (dùng Bearer token ya29.xxx),
module này dùng session token của labs.google.

Flow:
1. Lấy session token từ Cookie Editor (Next.js Auth)
2. Gọi CAPTCHA solver API để lấy reCAPTCHA token
3. Gọi API labs.google với session + captcha token
"""

import json
import time
import base64
import requests
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime


class LabsGoogleAPI:
    """
    Client để gọi labs.google API với session token.
    Sử dụng tRPC API endpoint thay vì aisandbox-pa.googleapis.com.
    """

    # API Endpoints - sử dụng tRPC API của labs.google
    BASE_URL = "https://labs.google"
    TRPC_URL = "https://labs.google/fx/api/trpc"

    # reCAPTCHA config cho labs.google
    RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
    RECAPTCHA_ACTION = "FLOW_GENERATION"

    def __init__(
        self,
        session_token: str,
        captcha_api_key: str = None,
        captcha_service: str = "capsolver",
        csrf_token: str = None,
        verbose: bool = True
    ):
        """
        Khởi tạo Labs Google API client.

        Args:
            session_token: __Secure-next-auth.session-token từ Cookie Editor
            captcha_api_key: API key của dịch vụ CAPTCHA solver
            captcha_service: Tên dịch vụ ("capsolver", "2captcha", etc.)
            csrf_token: __Host-next-auth.csrf-token (optional)
            verbose: In log chi tiết
        """
        self.session_token = session_token
        self.captcha_api_key = captcha_api_key
        self.captcha_service = captcha_service.lower()
        self.csrf_token = csrf_token
        self.verbose = verbose

        self.session = self._create_session()

    def _log(self, msg: str):
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [LabsAPI] {msg}")

    def _create_session(self) -> requests.Session:
        """Tạo HTTP session với cookies."""
        session = requests.Session()

        # Set session token cookie
        session.cookies.set(
            "__Secure-next-auth.session-token",
            self.session_token,
            domain=".labs.google",
            path="/",
            secure=True
        )

        # Set CSRF token if available
        if self.csrf_token:
            session.cookies.set(
                "__Host-next-auth.csrf-token",
                self.csrf_token,
                domain="labs.google",
                path="/"
            )

        # Headers giống browser
        session.headers.update({
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Content-Type": "application/json",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/fx/tools/flow",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        })

        return session

    # =========================================================================
    # CAPTCHA SOLVER
    # =========================================================================

    def _solve_captcha_capsolver(self) -> Optional[str]:
        """Giải reCAPTCHA v3 bằng Capsolver."""
        if not self.captcha_api_key:
            self._log("ERROR: Thiếu captcha_api_key! Vui lòng cấu hình trong Settings > Labs API")
            return None

        # Mask key for display
        key_masked = self.captcha_api_key[:8] + "..." if len(self.captcha_api_key) > 8 else "***"
        self._log(f"Đang giải CAPTCHA với Capsolver (key: {key_masked})...")

        try:
            # Tạo task
            create_task_url = "https://api.capsolver.com/createTask"
            task_data = {
                "clientKey": self.captcha_api_key,
                "task": {
                    "type": "ReCaptchaV3EnterpriseTaskProxyLess",
                    "websiteURL": "https://labs.google",
                    "websiteKey": self.RECAPTCHA_SITE_KEY,
                    "pageAction": self.RECAPTCHA_ACTION
                }
            }

            self._log(f"Creating task: {task_data['task']['type']}")
            response = requests.post(create_task_url, json=task_data, timeout=30)
            result = response.json()

            self._log(f"Capsolver response: errorId={result.get('errorId')}, errorCode={result.get('errorCode')}")

            if result.get("errorId") != 0:
                error_code = result.get('errorCode', 'UNKNOWN')
                error_desc = result.get('errorDescription', 'No description')
                self._log(f"Capsolver ERROR: [{error_code}] {error_desc}")

                # Common errors
                if error_code == "ERROR_INVALID_TASK_DATA":
                    self._log("  -> Kiểm tra lại cấu hình task (websiteKey, pageAction)")
                elif error_code == "ERROR_KEY_DOES_NOT_EXIST":
                    self._log("  -> API key không hợp lệ! Kiểm tra lại Capsolver API key")
                elif error_code == "ERROR_ZERO_BALANCE":
                    self._log("  -> Hết tiền trong tài khoản Capsolver! Nạp thêm credit")
                elif error_code == "ERROR_RECAPTCHA_INVALID_SITEKEY":
                    self._log("  -> Website key không đúng")

                return None

            task_id = result.get("taskId")
            self._log(f"Task created: {task_id}")

            # Poll for result
            get_result_url = "https://api.capsolver.com/getTaskResult"
            for _ in range(60):  # Max 60 attempts
                time.sleep(2)

                result_data = {
                    "clientKey": self.captcha_api_key,
                    "taskId": task_id
                }

                response = requests.post(get_result_url, json=result_data, timeout=30)
                result = response.json()

                if result.get("status") == "ready":
                    token = result.get("solution", {}).get("gRecaptchaResponse")
                    self._log("CAPTCHA solved!")
                    return token
                elif result.get("status") == "failed":
                    self._log(f"CAPTCHA failed: {result.get('errorDescription')}")
                    return None

            self._log("CAPTCHA timeout!")
            return None

        except requests.exceptions.RequestException as e:
            self._log(f"CAPTCHA network error: {e}")
            self._log("  -> Kiểm tra kết nối internet")
            return None
        except Exception as e:
            self._log(f"CAPTCHA error: {type(e).__name__}: {e}")
            import traceback
            self._log(f"Traceback: {traceback.format_exc()}")
            return None

    def _solve_captcha_2captcha(self) -> Optional[str]:
        """Giải reCAPTCHA v3 bằng 2Captcha."""
        if not self.captcha_api_key:
            return None

        self._log("Đang giải CAPTCHA với 2Captcha...")

        try:
            # Submit task
            submit_url = "https://2captcha.com/in.php"
            params = {
                "key": self.captcha_api_key,
                "method": "userrecaptcha",
                "googlekey": self.RECAPTCHA_SITE_KEY,
                "pageurl": "https://labs.google",
                "version": "v3",
                "action": self.RECAPTCHA_ACTION,
                "enterprise": 1,
                "json": 1
            }

            response = requests.get(submit_url, params=params, timeout=30)
            result = response.json()

            if result.get("status") != 1:
                self._log(f"2Captcha error: {result.get('error_text')}")
                return None

            request_id = result.get("request")
            self._log(f"Request ID: {request_id}")

            # Poll for result
            result_url = "https://2captcha.com/res.php"
            for _ in range(60):
                time.sleep(5)

                params = {
                    "key": self.captcha_api_key,
                    "action": "get",
                    "id": request_id,
                    "json": 1
                }

                response = requests.get(result_url, params=params, timeout=30)
                result = response.json()

                if result.get("status") == 1:
                    self._log("CAPTCHA solved!")
                    return result.get("request")
                elif "CAPCHA_NOT_READY" not in str(result.get("request", "")):
                    self._log(f"2Captcha error: {result}")
                    return None

            return None

        except Exception as e:
            self._log(f"2Captcha error: {e}")
            return None

    def solve_captcha(self) -> Optional[str]:
        """Giải reCAPTCHA tùy theo service được cấu hình."""
        if self.captcha_service == "capsolver":
            return self._solve_captcha_capsolver()
        elif self.captcha_service == "2captcha":
            return self._solve_captcha_2captcha()
        else:
            self._log(f"Unknown captcha service: {self.captcha_service}")
            return None

    # =========================================================================
    # IMAGE GENERATION
    # =========================================================================

    def generate_image(
        self,
        prompt: str,
        count: int = 1,
        aspect_ratio: str = "landscape",
        model: str = "IMAGEN_4",
        seed: int = None
    ) -> Tuple[bool, List[Dict], str]:
        """
        Tạo ảnh với labs.google tRPC API.

        Args:
            prompt: Text mô tả ảnh
            count: Số lượng ảnh (1-4)
            aspect_ratio: "landscape", "portrait", "square"
            model: Model tạo ảnh
            seed: Seed cho random (optional)

        Returns:
            Tuple[success, list_of_images, error_message]
        """
        self._log(f"Generating: {prompt[:50]}...")

        # Map aspect ratio
        ar_map = {
            "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT",
            "square": "IMAGE_ASPECT_RATIO_SQUARE"
        }
        aspect = ar_map.get(aspect_ratio.lower(), ar_map["landscape"])

        # Solve CAPTCHA first
        captcha_token = None
        if self.captcha_api_key:
            captcha_token = self.solve_captcha()
            if not captcha_token:
                return False, [], "Failed to solve CAPTCHA"

        # Build tRPC request for imageFx.generateImage
        # tRPC uses batch format with input as JSON
        import random
        if seed is None:
            seed = random.randint(1, 999999999)

        trpc_input = {
            "0": {
                "json": {
                    "generationParams": {
                        "prompts": [prompt],
                        "seed": seed,
                        "candidatesCount": count,
                        "aspectRatio": aspect,
                        "imageGenerationModel": model
                    },
                    "recaptchaToken": captcha_token or ""
                }
            }
        }

        # tRPC batch endpoint
        url = f"{self.TRPC_URL}/imageFx.generateImage?batch=1"

        headers = dict(self.session.headers)
        headers["Content-Type"] = "application/json"

        # Add x-recaptcha-token header
        if captcha_token:
            headers["x-recaptcha-token"] = captcha_token

        try:
            self._log(f"Calling tRPC: {url}")
            response = self.session.post(url, json=trpc_input, headers=headers, timeout=120)

            self._log(f"Response status: {response.status_code}")

            # Update session token if server sends new one
            new_token = response.cookies.get("__Secure-next-auth.session-token")
            if new_token:
                self._log("Got new session token from response")
                self.session_token = new_token
                self.session.cookies.set(
                    "__Secure-next-auth.session-token",
                    new_token,
                    domain=".labs.google"
                )

            if response.status_code == 200:
                data = response.json()
                self._log(f"Response data keys: {data[0].keys() if isinstance(data, list) and data else 'N/A'}")
                images = self._parse_trpc_response(data)
                if images:
                    return True, images, ""
                return False, [], f"No images in response: {str(data)[:200]}"

            elif response.status_code == 401:
                return False, [], "Session expired - cần lấy cookie mới"

            elif response.status_code == 403:
                return False, [], "Access denied - có thể cần CAPTCHA token"

            else:
                return False, [], f"API error: {response.status_code} - {response.text[:300]}"

        except Exception as e:
            import traceback
            self._log(f"Request error: {traceback.format_exc()}")
            return False, [], f"Request error: {e}"

    def _parse_trpc_response(self, data: Any) -> List[Dict]:
        """Parse tRPC response format."""
        images = []

        try:
            # tRPC batch response is array of results
            if isinstance(data, list) and len(data) > 0:
                result = data[0]

                # Check for error
                if "error" in result:
                    self._log(f"tRPC error: {result['error']}")
                    return []

                # Get result data
                result_data = result.get("result", {}).get("data", {}).get("json", {})

                # Parse images from response
                if "imagePanels" in result_data:
                    for panel in result_data.get("imagePanels", []):
                        for img in panel.get("generatedImages", []):
                            if img.get("encodedImage"):
                                images.append({
                                    "base64": img["encodedImage"],
                                    "seed": img.get("seed"),
                                    "id": img.get("mediaGenerationId")
                                })

                elif "media" in result_data:
                    for media in result_data.get("media", []):
                        gen_img = media.get("image", {}).get("generatedImage", {})
                        if gen_img.get("encodedImage"):
                            images.append({
                                "base64": gen_img["encodedImage"],
                                "url": gen_img.get("fifeUrl"),
                                "seed": gen_img.get("seed"),
                                "id": gen_img.get("mediaGenerationId")
                            })

                # Try direct image data
                elif "generatedImages" in result_data:
                    for img in result_data.get("generatedImages", []):
                        if img.get("encodedImage"):
                            images.append({
                                "base64": img["encodedImage"],
                                "seed": img.get("seed"),
                                "id": img.get("mediaGenerationId")
                            })

        except Exception as e:
            self._log(f"Parse error: {e}")

        return images

    def _parse_response(self, data: Dict) -> List[Dict]:
        """Parse response từ API."""
        images = []

        # Try different response formats
        if "imagePanels" in data:
            for panel in data.get("imagePanels", []):
                for img in panel.get("generatedImages", []):
                    if img.get("encodedImage"):
                        images.append({
                            "base64": img["encodedImage"],
                            "seed": img.get("seed"),
                            "id": img.get("mediaGenerationId")
                        })

        elif "media" in data:
            for media in data.get("media", []):
                gen_img = media.get("image", {}).get("generatedImage", {})
                if gen_img.get("encodedImage"):
                    images.append({
                        "base64": gen_img["encodedImage"],
                        "url": gen_img.get("fifeUrl"),
                        "seed": gen_img.get("seed"),
                        "id": gen_img.get("mediaGenerationId")
                    })

        return images

    def save_image(self, image: Dict, output_path: Path) -> bool:
        """Lưu ảnh từ base64."""
        try:
            if image.get("base64"):
                data = base64.b64decode(image["base64"])
                with open(output_path, "wb") as f:
                    f.write(data)
                return True
            elif image.get("url"):
                response = requests.get(image["url"], timeout=60)
                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    return True
            return False
        except Exception as e:
            self._log(f"Save error: {e}")
            return False

    # =========================================================================
    # CONVENIENCE
    # =========================================================================

    def test_connection(self) -> Tuple[bool, str]:
        """Test kết nối."""
        self._log("Testing connection...")

        success, images, error = self.generate_image(
            prompt="a simple blue circle",
            count=1
        )

        if success:
            return True, "Connection OK!"
        return False, error


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_cookie_json(cookie_json: str) -> str:
    """
    Parse JSON từ Cookie Editor và trả về session token.

    Args:
        cookie_json: JSON string từ Cookie Editor

    Returns:
        Session token string
    """
    try:
        cookies = json.loads(cookie_json)
        for cookie in cookies:
            if cookie.get("name") == "__Secure-next-auth.session-token":
                return cookie.get("value", "")
        return ""
    except:
        return ""


def parse_cookie_header(cookie_header: str) -> Dict[str, str]:
    """
    Parse cookie header string (format: name1=value1;name2=value2).

    Args:
        cookie_header: Cookie header string từ browser

    Returns:
        Dict với tất cả cookies
    """
    cookies = {}
    try:
        # Split by semicolon and parse each cookie
        for part in cookie_header.split(";"):
            part = part.strip()
            if "=" in part:
                # Find first = only (value may contain =)
                idx = part.index("=")
                name = part[:idx].strip()
                value = part[idx+1:].strip()
                cookies[name] = value
    except:
        pass
    return cookies


def extract_session_token(cookie_input: str) -> Tuple[str, str]:
    """
    Trích xuất session token và csrf token từ nhiều format khác nhau.

    Args:
        cookie_input: Cookie string (có thể là JSON, header string, hoặc token trực tiếp)

    Returns:
        Tuple[session_token, csrf_token]
    """
    session_token = ""
    csrf_token = ""

    cookie_input = cookie_input.strip()

    # Try JSON format first
    if cookie_input.startswith("["):
        try:
            cookies = json.loads(cookie_input)
            for cookie in cookies:
                name = cookie.get("name", "")
                value = cookie.get("value", "")
                if name == "__Secure-next-auth.session-token":
                    session_token = value
                elif name == "__Host-next-auth.csrf-token":
                    csrf_token = value
            return session_token, csrf_token
        except:
            pass

    # Try header string format (name=value;name=value)
    if "__Secure-next-auth.session-token=" in cookie_input or "=" in cookie_input:
        cookies = parse_cookie_header(cookie_input)
        session_token = cookies.get("__Secure-next-auth.session-token", "")
        csrf_token = cookies.get("__Host-next-auth.csrf-token", "")
        if session_token:
            return session_token, csrf_token

    # Assume it's direct token value
    if cookie_input.startswith("eyJ"):  # JWT format
        return cookie_input, ""

    return session_token, csrf_token


def parse_cookie_netscape(cookie_text: str) -> str:
    """
    Parse Netscape format từ Cookie Editor.

    Args:
        cookie_text: Netscape format cookie file

    Returns:
        Session token string
    """
    for line in cookie_text.split("\n"):
        if "__Secure-next-auth.session-token" in line:
            parts = line.strip().split("\t")
            if len(parts) >= 7:
                return parts[6]
    return ""


def auto_get_session_token(
    chrome_profile_path: str = None,
    chrome_exe_path: str = None,
    timeout: int = 30,
    verbose: bool = True
) -> Tuple[bool, str, str]:
    """
    Tự động lấy session token từ Chrome profile đã đăng nhập Google.

    Args:
        chrome_profile_path: Đường dẫn đến Chrome profile (User Data directory)
        chrome_exe_path: Đường dẫn đến chrome.exe
        timeout: Thời gian chờ tối đa (giây)
        verbose: In log

    Returns:
        Tuple[success, token, error_message]
    """
    def log(msg):
        if verbose:
            print(f"[AutoToken] {msg}")

    log("Đang tự động lấy session token...")

    # Try undetected-chromedriver first
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        driver_type = "undetected"
    except ImportError:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            driver_type = "selenium"
        except ImportError:
            return False, "", "Cần cài selenium: pip install selenium undetected-chromedriver"

    driver = None
    try:
        # Setup Chrome options
        if driver_type == "undetected":
            options = uc.ChromeOptions()
            if chrome_profile_path:
                # Extract user-data-dir and profile-directory
                profile_path = Path(chrome_profile_path)
                if profile_path.name.startswith("Profile"):
                    user_data_dir = str(profile_path.parent)
                    profile_name = profile_path.name
                    options.add_argument(f"--user-data-dir={user_data_dir}")
                    options.add_argument(f"--profile-directory={profile_name}")
                else:
                    options.add_argument(f"--user-data-dir={chrome_profile_path}")

            log("Khởi động Chrome (undetected-chromedriver)...")
            driver = uc.Chrome(options=options)

        else:  # selenium
            options = Options()
            if chrome_profile_path:
                profile_path = Path(chrome_profile_path)
                if profile_path.name.startswith("Profile"):
                    user_data_dir = str(profile_path.parent)
                    profile_name = profile_path.name
                    options.add_argument(f"--user-data-dir={user_data_dir}")
                    options.add_argument(f"--profile-directory={profile_name}")
                else:
                    options.add_argument(f"--user-data-dir={chrome_profile_path}")

            if chrome_exe_path:
                options.binary_location = chrome_exe_path

            log("Khởi động Chrome (selenium)...")
            driver = webdriver.Chrome(options=options)

        # Navigate to labs.google
        log("Đang mở labs.google...")
        driver.get("https://labs.google/fx/tools/flow")

        # Wait for page to load and check login
        log(f"Đang chờ trang load (tối đa {timeout}s)...")
        time.sleep(3)  # Initial wait

        # Check for session token cookie
        for attempt in range(timeout // 2):
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie.get("name") == "__Secure-next-auth.session-token":
                    token = cookie.get("value", "")
                    if token:
                        log(f"Đã lấy được token! (length: {len(token)})")
                        driver.quit()
                        return True, token, ""

            # Check if need login
            current_url = driver.current_url
            if "accounts.google.com" in current_url:
                log("Cần đăng nhập Google - đang chờ user đăng nhập...")

            time.sleep(2)

        driver.quit()
        return False, "", "Không tìm thấy session token. Kiểm tra xem đã đăng nhập Google chưa."

    except Exception as e:
        if driver:
            try:
                driver.quit()
            except:
                pass
        return False, "", f"Lỗi: {str(e)}"


def auto_get_token_from_config(config_path: str = "config/accounts.json", verbose: bool = True) -> Tuple[bool, str, str]:
    """
    Tự động lấy token sử dụng Chrome profile từ config.

    Args:
        config_path: Đường dẫn đến accounts.json
        verbose: In log

    Returns:
        Tuple[success, token, error_message]
    """
    import json
    from pathlib import Path

    config_file = Path(config_path)
    if not config_file.exists():
        return False, "", f"Không tìm thấy config: {config_path}"

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Get first available Chrome profile
        profiles = config.get("chrome_profiles", [])
        chrome_path = config.get("chrome_path", "")

        for profile in profiles:
            profile_path = profile if isinstance(profile, str) else profile.get("path", "")
            if profile_path and Path(profile_path).exists():
                if verbose:
                    print(f"[AutoToken] Sử dụng profile: {profile_path}")
                return auto_get_session_token(
                    chrome_profile_path=profile_path,
                    chrome_exe_path=chrome_path,
                    verbose=verbose
                )

        return False, "", "Không tìm thấy Chrome profile hợp lệ trong config"

    except Exception as e:
        return False, "", f"Lỗi đọc config: {str(e)}"


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════╗
║         LABS GOOGLE API - TEST                                 ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  Cách sử dụng:                                                 ║
║  1. Lấy cookie từ Cookie Editor (labs.google)                  ║
║  2. Lấy API key từ Capsolver/2Captcha                         ║
║  3. Chạy test                                                  ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
""")
