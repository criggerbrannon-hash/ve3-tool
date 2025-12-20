#!/usr/bin/env python3
"""
VE3 Tool - CAPTCHA Solver Module
================================
Tích hợp các dịch vụ giải CAPTCHA: 2Captcha, Anti-Captcha, CapSolver.

Hỗ trợ:
- reCAPTCHA v2
- reCAPTCHA v3
- reCAPTCHA Enterprise
- hCaptcha
"""

import os
import time
import json
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class CaptchaService(Enum):
    """Các dịch vụ giải CAPTCHA được hỗ trợ."""
    TWOCAPTCHA = "2captcha"
    ANTICAPTCHA = "anticaptcha"
    CAPSOLVER = "capsolver"


@dataclass
class CaptchaResult:
    """Kết quả giải CAPTCHA."""
    success: bool
    token: Optional[str] = None
    task_id: Optional[str] = None
    cost: Optional[float] = None
    solve_time: Optional[float] = None
    error: Optional[str] = None


class TwoCaptchaSolver:
    """
    2Captcha API integration.
    Website: https://2captcha.com

    Hỗ trợ:
    - reCAPTCHA v2/v3
    - reCAPTCHA Enterprise
    - hCaptcha
    """

    API_URL = "https://2captcha.com"

    def __init__(self, api_key: str, timeout: int = 120, poll_interval: int = 5):
        """
        Khởi tạo 2Captcha solver.

        Args:
            api_key: API key từ 2captcha.com
            timeout: Timeout tối đa (seconds)
            poll_interval: Khoảng thời gian poll kết quả (seconds)
        """
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval

    def get_balance(self) -> float:
        """Kiểm tra số dư tài khoản."""
        response = requests.get(
            f"{self.API_URL}/res.php",
            params={"key": self.api_key, "action": "getbalance", "json": 1}
        )
        data = response.json()
        if data.get("status") == 1:
            return float(data.get("request", 0))
        return 0.0

    def solve_recaptcha_v2(
        self,
        site_key: str,
        page_url: str,
        invisible: bool = False
    ) -> CaptchaResult:
        """
        Giải reCAPTCHA v2.

        Args:
            site_key: reCAPTCHA site key
            page_url: URL trang web
            invisible: True nếu là invisible reCAPTCHA
        """
        start_time = time.time()

        # Submit task
        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "json": 1
        }
        if invisible:
            params["invisible"] = 1

        response = requests.post(f"{self.API_URL}/in.php", data=params)
        data = response.json()

        if data.get("status") != 1:
            return CaptchaResult(
                success=False,
                error=data.get("request", "Unknown error")
            )

        task_id = data.get("request")
        print(f"   📤 Task submitted: {task_id}")

        # Poll for result
        return self._poll_result(task_id, start_time)

    def solve_recaptcha_v3(
        self,
        site_key: str,
        page_url: str,
        action: str = "verify",
        min_score: float = 0.7
    ) -> CaptchaResult:
        """
        Giải reCAPTCHA v3.

        Args:
            site_key: reCAPTCHA site key
            page_url: URL trang web
            action: Action name
            min_score: Minimum score yêu cầu (0.1 - 0.9)
        """
        start_time = time.time()

        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "version": "v3",
            "action": action,
            "min_score": min_score,
            "json": 1
        }

        response = requests.post(f"{self.API_URL}/in.php", data=params)
        data = response.json()

        if data.get("status") != 1:
            return CaptchaResult(
                success=False,
                error=data.get("request", "Unknown error")
            )

        task_id = data.get("request")
        print(f"   📤 Task submitted: {task_id}")

        return self._poll_result(task_id, start_time)

    def solve_recaptcha_enterprise(
        self,
        site_key: str,
        page_url: str,
        action: str = "verify",
        enterprise_payload: Dict = None,
        api_domain: str = None
    ) -> CaptchaResult:
        """
        Giải reCAPTCHA Enterprise.

        Args:
            site_key: reCAPTCHA Enterprise site key
            page_url: URL trang web
            action: Action name
            enterprise_payload: Payload bổ sung (nếu có)
            api_domain: Domain của reCAPTCHA (thường là recaptcha.net hoặc google.com)
        """
        start_time = time.time()

        print(f"\n🔐 Solving reCAPTCHA Enterprise...")
        print(f"   Site Key: {site_key}")
        print(f"   Page URL: {page_url}")
        print(f"   Action: {action}")

        params = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "version": "v3",
            "action": action,
            "enterprise": 1,
            "json": 1
        }

        if enterprise_payload:
            params["data-s"] = json.dumps(enterprise_payload)

        if api_domain:
            params["domain"] = api_domain

        response = requests.post(f"{self.API_URL}/in.php", data=params)
        data = response.json()

        if data.get("status") != 1:
            error = data.get("request", "Unknown error")
            print(f"   ❌ Submit failed: {error}")
            return CaptchaResult(
                success=False,
                error=error
            )

        task_id = data.get("request")
        print(f"   📤 Task submitted: {task_id}")

        return self._poll_result(task_id, start_time)

    def _poll_result(self, task_id: str, start_time: float) -> CaptchaResult:
        """Poll để lấy kết quả."""
        elapsed = 0

        while elapsed < self.timeout:
            time.sleep(self.poll_interval)
            elapsed = time.time() - start_time

            response = requests.get(
                f"{self.API_URL}/res.php",
                params={
                    "key": self.api_key,
                    "action": "get",
                    "id": task_id,
                    "json": 1
                }
            )
            data = response.json()

            if data.get("status") == 1:
                token = data.get("request")
                solve_time = time.time() - start_time
                print(f"   ✅ Solved in {solve_time:.1f}s!")
                print(f"   Token: {token[:50]}...")

                return CaptchaResult(
                    success=True,
                    token=token,
                    task_id=task_id,
                    solve_time=solve_time
                )

            if data.get("request") == "CAPCHA_NOT_READY":
                print(f"   ⏳ Waiting... ({elapsed:.0f}s)")
                continue

            # Error
            return CaptchaResult(
                success=False,
                task_id=task_id,
                error=data.get("request", "Unknown error"),
                solve_time=time.time() - start_time
            )

        return CaptchaResult(
            success=False,
            task_id=task_id,
            error=f"Timeout after {self.timeout}s",
            solve_time=self.timeout
        )


class AntiCaptchaSolver:
    """
    Anti-Captcha API integration.
    Website: https://anti-captcha.com
    """

    API_URL = "https://api.anti-captcha.com"

    def __init__(self, api_key: str, timeout: int = 120, poll_interval: int = 5):
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval

    def get_balance(self) -> float:
        """Kiểm tra số dư."""
        response = requests.post(
            f"{self.API_URL}/getBalance",
            json={"clientKey": self.api_key}
        )
        data = response.json()
        return data.get("balance", 0.0)

    def solve_recaptcha_enterprise(
        self,
        site_key: str,
        page_url: str,
        action: str = "verify",
        enterprise_payload: Dict = None
    ) -> CaptchaResult:
        """Giải reCAPTCHA Enterprise."""
        start_time = time.time()

        print(f"\n🔐 [Anti-Captcha] Solving reCAPTCHA Enterprise...")

        task = {
            "type": "RecaptchaV3TaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "pageAction": action,
            "isEnterprise": True,
            "minScore": 0.7
        }

        if enterprise_payload:
            task["enterprisePayload"] = enterprise_payload

        # Create task
        response = requests.post(
            f"{self.API_URL}/createTask",
            json={"clientKey": self.api_key, "task": task}
        )
        data = response.json()

        if data.get("errorId") != 0:
            return CaptchaResult(
                success=False,
                error=data.get("errorDescription", "Unknown error")
            )

        task_id = data.get("taskId")
        print(f"   📤 Task submitted: {task_id}")

        # Poll result
        return self._poll_result(task_id, start_time)

    def _poll_result(self, task_id: int, start_time: float) -> CaptchaResult:
        """Poll để lấy kết quả."""
        elapsed = 0

        while elapsed < self.timeout:
            time.sleep(self.poll_interval)
            elapsed = time.time() - start_time

            response = requests.post(
                f"{self.API_URL}/getTaskResult",
                json={"clientKey": self.api_key, "taskId": task_id}
            )
            data = response.json()

            if data.get("status") == "ready":
                token = data.get("solution", {}).get("gRecaptchaResponse")
                solve_time = time.time() - start_time
                print(f"   ✅ Solved in {solve_time:.1f}s!")

                return CaptchaResult(
                    success=True,
                    token=token,
                    task_id=str(task_id),
                    solve_time=solve_time
                )

            if data.get("status") == "processing":
                print(f"   ⏳ Processing... ({elapsed:.0f}s)")
                continue

            if data.get("errorId") != 0:
                return CaptchaResult(
                    success=False,
                    task_id=str(task_id),
                    error=data.get("errorDescription"),
                    solve_time=time.time() - start_time
                )

        return CaptchaResult(
            success=False,
            task_id=str(task_id),
            error=f"Timeout after {self.timeout}s"
        )


class CapSolverSolver:
    """
    CapSolver API integration (faster, cheaper).
    Website: https://capsolver.com
    """

    API_URL = "https://api.capsolver.com"

    def __init__(self, api_key: str, timeout: int = 120, poll_interval: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval

    def get_balance(self) -> float:
        """Kiểm tra số dư."""
        response = requests.post(
            f"{self.API_URL}/getBalance",
            json={"clientKey": self.api_key}
        )
        data = response.json()
        return data.get("balance", 0.0)

    def solve_recaptcha_enterprise(
        self,
        site_key: str,
        page_url: str,
        action: str = "verify",
        enterprise_payload: Dict = None
    ) -> CaptchaResult:
        """Giải reCAPTCHA Enterprise."""
        start_time = time.time()

        print(f"\n🔐 [CapSolver] Solving reCAPTCHA Enterprise...")

        task = {
            "type": "ReCaptchaV3EnterpriseTaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "pageAction": action
        }

        if enterprise_payload:
            task["enterprisePayload"] = enterprise_payload

        # Create task
        response = requests.post(
            f"{self.API_URL}/createTask",
            json={"clientKey": self.api_key, "task": task}
        )
        data = response.json()

        if data.get("errorId") != 0:
            return CaptchaResult(
                success=False,
                error=data.get("errorDescription", "Unknown error")
            )

        task_id = data.get("taskId")
        print(f"   📤 Task submitted: {task_id}")

        # Poll result
        return self._poll_result(task_id, start_time)

    def _poll_result(self, task_id: str, start_time: float) -> CaptchaResult:
        """Poll để lấy kết quả."""
        elapsed = 0

        while elapsed < self.timeout:
            time.sleep(self.poll_interval)
            elapsed = time.time() - start_time

            response = requests.post(
                f"{self.API_URL}/getTaskResult",
                json={"clientKey": self.api_key, "taskId": task_id}
            )
            data = response.json()

            if data.get("status") == "ready":
                token = data.get("solution", {}).get("gRecaptchaResponse")
                solve_time = time.time() - start_time
                print(f"   ✅ Solved in {solve_time:.1f}s!")

                return CaptchaResult(
                    success=True,
                    token=token,
                    task_id=task_id,
                    solve_time=solve_time
                )

            if data.get("status") == "processing":
                print(f"   ⏳ Processing... ({elapsed:.0f}s)")
                continue

            if data.get("errorId") != 0:
                return CaptchaResult(
                    success=False,
                    task_id=task_id,
                    error=data.get("errorDescription"),
                    solve_time=time.time() - start_time
                )

        return CaptchaResult(
            success=False,
            task_id=task_id,
            error=f"Timeout after {self.timeout}s"
        )


class CaptchaSolver:
    """
    Unified CAPTCHA solver interface.
    Tự động chọn service dựa trên API key hoặc config.
    """

    # reCAPTCHA Enterprise Site Key từ Google Labs Flow
    FLOW_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        api_key: str,
        service: CaptchaService = CaptchaService.TWOCAPTCHA,
        timeout: int = 120
    ):
        """
        Khởi tạo solver.

        Args:
            api_key: API key của dịch vụ CAPTCHA
            service: Dịch vụ sử dụng (2captcha, anticaptcha, capsolver)
            timeout: Timeout tối đa
        """
        self.api_key = api_key
        self.service = service
        self.timeout = timeout

        # Khởi tạo solver phù hợp
        if service == CaptchaService.TWOCAPTCHA:
            self.solver = TwoCaptchaSolver(api_key, timeout)
        elif service == CaptchaService.ANTICAPTCHA:
            self.solver = AntiCaptchaSolver(api_key, timeout)
        elif service == CaptchaService.CAPSOLVER:
            self.solver = CapSolverSolver(api_key, timeout)
        else:
            raise ValueError(f"Unknown service: {service}")

    def get_balance(self) -> float:
        """Kiểm tra số dư tài khoản."""
        return self.solver.get_balance()

    def solve_flow_recaptcha(self, action: str = "pageview") -> CaptchaResult:
        """
        Giải reCAPTCHA Enterprise cho Google Labs Flow.

        Args:
            action: Action name (pageview, submit, etc.)

        Returns:
            CaptchaResult với token nếu thành công
        """
        return self.solver.solve_recaptcha_enterprise(
            site_key=self.FLOW_SITE_KEY,
            page_url=self.FLOW_URL,
            action=action
        )

    def solve_recaptcha_enterprise(
        self,
        site_key: str,
        page_url: str,
        action: str = "verify"
    ) -> CaptchaResult:
        """Giải reCAPTCHA Enterprise bất kỳ."""
        return self.solver.solve_recaptcha_enterprise(
            site_key=site_key,
            page_url=page_url,
            action=action
        )


# ============= Helper Functions =============

def test_captcha_service(api_key: str, service: str = "2captcha"):
    """
    Test CAPTCHA service.

    Args:
        api_key: API key
        service: "2captcha", "anticaptcha", or "capsolver"
    """
    print("=" * 60)
    print(f"🧪 TEST CAPTCHA SERVICE: {service}")
    print("=" * 60)

    service_enum = {
        "2captcha": CaptchaService.TWOCAPTCHA,
        "anticaptcha": CaptchaService.ANTICAPTCHA,
        "capsolver": CaptchaService.CAPSOLVER
    }.get(service.lower(), CaptchaService.TWOCAPTCHA)

    solver = CaptchaSolver(api_key, service_enum)

    # Check balance
    print(f"\n💰 Checking balance...")
    balance = solver.get_balance()
    print(f"   Balance: ${balance:.4f}")

    if balance <= 0:
        print("❌ No balance! Please top up.")
        return None

    # Solve Flow reCAPTCHA
    print(f"\n🔐 Solving Google Flow reCAPTCHA Enterprise...")
    result = solver.solve_flow_recaptcha(action="pageview")

    if result.success:
        print(f"\n✅ SUCCESS!")
        print(f"   Token: {result.token[:80]}...")
        print(f"   Solve time: {result.solve_time:.1f}s")
        return result.token
    else:
        print(f"\n❌ FAILED: {result.error}")
        return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python captcha_solver.py <API_KEY> [service]")
        print("  service: 2captcha (default), anticaptcha, capsolver")
        sys.exit(1)

    api_key = sys.argv[1]
    service = sys.argv[2] if len(sys.argv) > 2 else "2captcha"

    test_captcha_service(api_key, service)
