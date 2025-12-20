"""
CapSolver Integration for Google Labs reCAPTCHA Enterprise
==========================================================
Tự động giải reCAPTCHA để lấy token cho Flow API.

Flow:
1. Gửi task tạo CAPTCHA đến CapSolver
2. Đợi kết quả (polling)
3. Nhận recaptchaToken
4. Dùng token để gọi API

Usage:
    from modules.capsolver_api import CapSolverClient

    solver = CapSolverClient("CAP-xxx")
    token = solver.solve_recaptcha_enterprise(
        website_url="https://labs.google/fx/vi/tools/flow",
        website_key="6LdyahgqAAAAALTi8Bqpun_12345"  # Cần tìm key này
    )
"""

import time
import json
import requests
from typing import Optional, Dict, Any


class CapSolverClient:
    """Client để giải CAPTCHA qua CapSolver API."""

    BASE_URL = "https://api.capsolver.com"

    def __init__(self, api_key: str, verbose: bool = True):
        """
        Khởi tạo CapSolver client.

        Args:
            api_key: API key từ CapSolver (bắt đầu bằng CAP-)
            verbose: In log chi tiết
        """
        self.api_key = api_key.strip()
        self.verbose = verbose

        if not self.api_key.startswith("CAP-"):
            print("⚠️  Warning: CapSolver API key should start with 'CAP-'")

    def _log(self, message: str) -> None:
        """Print log message if verbose."""
        if self.verbose:
            print(f"[CapSolver] {message}")

    def get_balance(self) -> float:
        """Lấy số dư tài khoản."""
        try:
            response = requests.post(
                f"{self.BASE_URL}/getBalance",
                json={"clientKey": self.api_key},
                timeout=30
            )

            self._log(f"Response status: {response.status_code}")

            if response.status_code != 200:
                self._log(f"HTTP Error: {response.status_code}")
                return -1

            if not response.text:
                self._log("Empty response")
                return -1

            data = response.json()

            if data.get("errorId") == 0:
                balance = data.get("balance", 0)
                self._log(f"Balance: ${balance}")
                return balance
            else:
                self._log(f"Error: {data.get('errorDescription', 'Unknown')}")
                return -1
        except Exception as e:
            self._log(f"Exception: {e}")
            return -1

    def solve_recaptcha_enterprise(
        self,
        website_url: str,
        website_key: str,
        page_action: str = "submit",
        timeout: int = 120
    ) -> Optional[str]:
        """
        Giải reCAPTCHA Enterprise.

        Args:
            website_url: URL của trang web
            website_key: Site key của reCAPTCHA
            page_action: Action name (default: submit)
            timeout: Timeout in seconds

        Returns:
            recaptchaToken hoặc None nếu thất bại
        """
        self._log(f"Solving reCAPTCHA Enterprise for {website_url}")

        # Step 1: Create task
        create_response = requests.post(
            f"{self.BASE_URL}/createTask",
            json={
                "clientKey": self.api_key,
                "task": {
                    "type": "ReCaptchaV3EnterpriseTaskProxyLess",
                    "websiteURL": website_url,
                    "websiteKey": website_key,
                    "pageAction": page_action
                }
            }
        )

        create_data = create_response.json()

        if create_data.get("errorId") != 0:
            self._log(f"Create task failed: {create_data.get('errorDescription')}")
            return None

        task_id = create_data.get("taskId")
        self._log(f"Task created: {task_id}")

        # Step 2: Poll for result
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(3)  # Wait 3 seconds between polls

            result_response = requests.post(
                f"{self.BASE_URL}/getTaskResult",
                json={
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
            )

            result_data = result_response.json()

            if result_data.get("errorId") != 0:
                self._log(f"Error: {result_data.get('errorDescription')}")
                return None

            status = result_data.get("status")

            if status == "ready":
                token = result_data.get("solution", {}).get("gRecaptchaResponse")
                self._log(f"✅ Solved! Token: {token[:50] if token else 'None'}...")
                return token
            elif status == "processing":
                self._log("Processing...")
            else:
                self._log(f"Unknown status: {status}")

        self._log("❌ Timeout!")
        return None

    def solve_recaptcha_v2(
        self,
        website_url: str,
        website_key: str,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Giải reCAPTCHA v2 (invisible hoặc checkbox).

        Args:
            website_url: URL của trang web
            website_key: Site key của reCAPTCHA
            timeout: Timeout in seconds

        Returns:
            recaptchaToken hoặc None nếu thất bại
        """
        self._log(f"Solving reCAPTCHA v2 for {website_url}")

        # Create task
        create_response = requests.post(
            f"{self.BASE_URL}/createTask",
            json={
                "clientKey": self.api_key,
                "task": {
                    "type": "ReCaptchaV2TaskProxyLess",
                    "websiteURL": website_url,
                    "websiteKey": website_key,
                    "isInvisible": True
                }
            }
        )

        create_data = create_response.json()

        if create_data.get("errorId") != 0:
            self._log(f"Create task failed: {create_data.get('errorDescription')}")
            return None

        task_id = create_data.get("taskId")
        self._log(f"Task created: {task_id}")

        # Poll for result
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(3)

            result_response = requests.post(
                f"{self.BASE_URL}/getTaskResult",
                json={
                    "clientKey": self.api_key,
                    "taskId": task_id
                }
            )

            result_data = result_response.json()

            if result_data.get("errorId") != 0:
                self._log(f"Error: {result_data.get('errorDescription')}")
                return None

            status = result_data.get("status")

            if status == "ready":
                token = result_data.get("solution", {}).get("gRecaptchaResponse")
                self._log(f"✅ Solved! Token: {token[:50] if token else 'None'}...")
                return token
            elif status == "processing":
                self._log("Processing...")

        self._log("❌ Timeout!")
        return None


# Quick test
if __name__ == "__main__":
    # Test với API key
    API_KEY = "CAP-0F2D4A374AB3E24FFD576CBBC9C114804A32E4BD5D82C162A2044D18A4E46977"

    solver = CapSolverClient(API_KEY)

    # Check balance
    balance = solver.get_balance()
    print(f"\nBalance: ${balance}")

    # Test solve (cần tìm website_key của Google Labs)
    # token = solver.solve_recaptcha_enterprise(
    #     website_url="https://labs.google/fx/vi/tools/flow",
    #     website_key="WEBSITE_KEY_HERE"
    # )
