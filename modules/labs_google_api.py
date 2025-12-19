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
    """

    # API Endpoints
    BASE_URL = "https://labs.google"
    API_URL = "https://aisandbox-pa.googleapis.com"

    # reCAPTCHA config cho labs.google
    RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
    RECAPTCHA_ACTION = "FLOW_GENERATION"

    def __init__(
        self,
        session_token: str,
        captcha_api_key: str = None,
        captcha_service: str = "capsolver",
        verbose: bool = True
    ):
        """
        Khởi tạo Labs Google API client.

        Args:
            session_token: __Secure-next-auth.session-token từ Cookie Editor
            captcha_api_key: API key của dịch vụ CAPTCHA solver
            captcha_service: Tên dịch vụ ("capsolver", "2captcha", etc.)
            verbose: In log chi tiết
        """
        self.session_token = session_token
        self.captcha_api_key = captcha_api_key
        self.captcha_service = captcha_service.lower()
        self.verbose = verbose

        self.session = self._create_session()

    def _log(self, msg: str):
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [LabsAPI] {msg}")

    def _create_session(self) -> requests.Session:
        """Tạo HTTP session với cookies."""
        session = requests.Session()

        # Set cookies cho labs.google
        session.cookies.set(
            "__Secure-next-auth.session-token",
            self.session_token,
            domain="labs.google"
        )

        session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        return session

    # =========================================================================
    # CAPTCHA SOLVER
    # =========================================================================

    def _solve_captcha_capsolver(self) -> Optional[str]:
        """Giải reCAPTCHA v3 bằng Capsolver."""
        if not self.captcha_api_key:
            self._log("ERROR: Thiếu captcha_api_key!")
            return None

        self._log("Đang giải CAPTCHA với Capsolver...")

        try:
            # Tạo task
            create_task_url = "https://api.capsolver.com/createTask"
            task_data = {
                "clientKey": self.captcha_api_key,
                "task": {
                    "type": "ReCaptchaV3TaskProxyLess",
                    "websiteURL": "https://labs.google",
                    "websiteKey": self.RECAPTCHA_SITE_KEY,
                    "pageAction": self.RECAPTCHA_ACTION,
                    "isEnterprise": True
                }
            }

            response = requests.post(create_task_url, json=task_data, timeout=30)
            result = response.json()

            if result.get("errorId") != 0:
                self._log(f"Capsolver error: {result.get('errorDescription')}")
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

        except Exception as e:
            self._log(f"CAPTCHA error: {e}")
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
        model: str = "IMAGEN_4"
    ) -> Tuple[bool, List[Dict], str]:
        """
        Tạo ảnh với labs.google API.

        Args:
            prompt: Text mô tả ảnh
            count: Số lượng ảnh (1-4)
            aspect_ratio: "landscape", "portrait", "square"
            model: Model tạo ảnh

        Returns:
            Tuple[success, list_of_images, error_message]
        """
        self._log(f"Generating: {prompt[:50]}...")

        # Map aspect ratio
        ar_map = {
            "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE_16_9",
            "portrait": "IMAGE_ASPECT_RATIO_PORTRAIT_16_9",
            "square": "IMAGE_ASPECT_RATIO_SQUARE"
        }
        aspect = ar_map.get(aspect_ratio.lower(), ar_map["landscape"])

        # Solve CAPTCHA first
        captcha_token = None
        if self.captcha_api_key:
            captcha_token = self.solve_captcha()
            if not captcha_token:
                return False, [], "Failed to solve CAPTCHA"

        # Build request
        # Note: Endpoint và format có thể cần điều chỉnh dựa trên actual API
        url = f"{self.API_URL}/v1:runImageFx"

        payload = {
            "userInput": {
                "candidatesCount": count,
                "prompts": [prompt],
            },
            "generationParams": {
                "imageGenerationModel": model,
                "aspectRatio": aspect,
            },
            "clientContext": {
                "tool": "IMAGE_FX"
            }
        }

        headers = dict(self.session.headers)

        # Add CAPTCHA token if available
        if captcha_token:
            headers["x-recaptcha-token"] = captcha_token
            # Or it might be in the payload
            payload["recaptchaToken"] = captcha_token

        try:
            response = self.session.post(url, json=payload, headers=headers, timeout=120)

            self._log(f"Response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                images = self._parse_response(data)
                if images:
                    return True, images, ""
                return False, [], "No images in response"

            elif response.status_code == 401:
                return False, [], "Session expired - cần lấy cookie mới"

            elif response.status_code == 403:
                return False, [], "Access denied - có thể cần CAPTCHA token"

            else:
                return False, [], f"API error: {response.status_code} - {response.text[:200]}"

        except Exception as e:
            return False, [], f"Request error: {e}"

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
