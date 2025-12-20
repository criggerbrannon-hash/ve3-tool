#!/usr/bin/env python3
"""
VE3 Tool - Chrome Headers Extractor
====================================
Mở Chrome, intercept network requests để lấy headers real-time.
Sau đó dùng headers để gọi API.

Flow:
1. Mở Chrome với Selenium + CDP (Chrome DevTools Protocol)
2. Navigate tới labs.google/flow
3. Intercept network requests
4. Capture headers (x-browser-validation, authorization, etc.)
5. Return headers để gọi API
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass


@dataclass
class CapturedHeaders:
    """Headers captured từ Chrome."""
    authorization: str = ""
    x_browser_validation: str = ""
    x_browser_channel: str = ""
    x_browser_copyright: str = ""
    x_browser_year: str = ""
    x_client_data: str = ""
    cookies: str = ""
    user_agent: str = ""
    timestamp: float = 0

    def is_valid(self) -> bool:
        """Check if headers are valid."""
        return bool(self.authorization and self.x_browser_validation)

    def age_seconds(self) -> float:
        """Tuổi của headers (giây)."""
        return time.time() - self.timestamp if self.timestamp else 999999

    def to_dict(self) -> Dict[str, str]:
        """Convert to dict for requests."""
        return {
            "authorization": self.authorization,
            "content-type": "text/plain;charset=UTF-8",
            "accept": "*/*",
            "origin": "https://labs.google",
            "referer": "https://labs.google/",
            "x-browser-channel": self.x_browser_channel or "stable",
            "x-browser-copyright": self.x_browser_copyright or "Copyright 2025 Google LLC. All Rights reserved.",
            "x-browser-validation": self.x_browser_validation,
            "x-browser-year": self.x_browser_year or "2025",
            "x-client-data": self.x_client_data,
            "user-agent": self.user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
        }


class ChromeHeadersExtractor:
    """
    Extract headers từ Chrome real-time bằng CDP.
    """

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"
    API_PATTERN = "aisandbox-pa.googleapis.com"

    def __init__(
        self,
        chrome_profile_path: str = None,
        headless: bool = False,
        verbose: bool = True
    ):
        self.chrome_profile_path = chrome_profile_path
        self.headless = headless
        self.verbose = verbose

        self.driver = None
        self.captured_headers = CapturedHeaders()
        self._capture_lock = threading.Lock()

    def _log(self, msg: str):
        if self.verbose:
            print(f"[HeadersExtractor] {msg}")

    def start_browser(self) -> bool:
        """Khởi động Chrome với CDP enabled."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()

            if self.headless:
                options.add_argument("--headless=new")

            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--window-size=1920,1080")

            # Enable CDP
            options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

            if self.chrome_profile_path:
                options.add_argument(f"--user-data-dir={self.chrome_profile_path}")

            options.add_experimental_option("excludeSwitches", ["enable-automation"])

            self.driver = webdriver.Chrome(options=options)

            # Hide webdriver
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })

            self._log("Browser started!")
            return True

        except Exception as e:
            self._log(f"Error starting browser: {e}")
            return False

    def navigate_to_flow(self) -> bool:
        """Navigate tới Flow page."""
        if not self.driver:
            return False

        try:
            self._log(f"Navigating to {self.FLOW_URL}...")
            self.driver.get(self.FLOW_URL)
            time.sleep(3)
            return True
        except Exception as e:
            self._log(f"Error navigating: {e}")
            return False

    def capture_headers_from_network(self, timeout: int = 30) -> CapturedHeaders:
        """
        Capture headers từ network logs.
        Trigger 1 request để capture headers.
        """
        if not self.driver:
            return CapturedHeaders()

        self._log("Capturing headers from network...")

        # Enable network tracking
        self.driver.execute_cdp_cmd("Network.enable", {})

        # Trigger a request bằng cách click vào page hoặc scroll
        try:
            self.driver.execute_script("""
                // Trigger any API call
                if (typeof window.__VE3_TRIGGER__ === 'undefined') {
                    window.__VE3_TRIGGER__ = true;
                    // Scroll to trigger lazy load
                    window.scrollTo(0, 100);
                    window.scrollTo(0, 0);
                }
            """)
        except:
            pass

        # Wait và check logs
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                logs = self.driver.get_log("performance")

                for log in logs:
                    try:
                        message = json.loads(log["message"])
                        method = message.get("message", {}).get("method", "")

                        if method == "Network.requestWillBeSent":
                            params = message.get("message", {}).get("params", {})
                            request = params.get("request", {})
                            url = request.get("url", "")

                            if self.API_PATTERN in url:
                                headers = request.get("headers", {})

                                self._log(f"Found API request: {url[:60]}...")

                                with self._capture_lock:
                                    self.captured_headers = CapturedHeaders(
                                        authorization=headers.get("Authorization", ""),
                                        x_browser_validation=headers.get("x-browser-validation", ""),
                                        x_browser_channel=headers.get("x-browser-channel", ""),
                                        x_browser_copyright=headers.get("x-browser-copyright", ""),
                                        x_browser_year=headers.get("x-browser-year", ""),
                                        x_client_data=headers.get("x-client-data", ""),
                                        user_agent=headers.get("User-Agent", ""),
                                        timestamp=time.time()
                                    )

                                    if self.captured_headers.is_valid():
                                        self._log("✅ Captured valid headers!")
                                        self._log(f"   x-browser-validation: {self.captured_headers.x_browser_validation[:30]}...")
                                        return self.captured_headers
                    except:
                        continue

                time.sleep(0.5)

            except Exception as e:
                self._log(f"Error reading logs: {e}")
                time.sleep(1)

        self._log("Timeout waiting for headers")
        return self.captured_headers

    def trigger_api_and_capture(self) -> CapturedHeaders:
        """
        Trigger 1 API call và capture headers.
        """
        if not self.driver:
            return CapturedHeaders()

        self._log("Triggering API call to capture headers...")

        # Enable network
        self.driver.execute_cdp_cmd("Network.enable", {})

        # Inject và trigger API call
        result = self.driver.execute_script("""
            return new Promise((resolve) => {
                // Tìm và click nút tạo ảnh hoặc trigger API
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.includes('Tạo') || btn.textContent.includes('Generate')) {
                        btn.click();
                        setTimeout(() => resolve('clicked'), 1000);
                        return;
                    }
                }
                resolve('no_button');
            });
        """)

        # Capture headers
        return self.capture_headers_from_network(timeout=10)

    def get_headers(self) -> CapturedHeaders:
        """Get current captured headers."""
        with self._capture_lock:
            return self.captured_headers

    def stop_browser(self):
        """Đóng browser."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None


def extract_headers_for_api(chrome_profile: str = None) -> Dict[str, str]:
    """
    Helper function: Mở Chrome, capture headers, trả về dict.

    Usage:
        headers = extract_headers_for_api("path/to/chrome/profile")
        response = requests.post(url, headers=headers, json=payload)
    """
    extractor = ChromeHeadersExtractor(
        chrome_profile_path=chrome_profile,
        headless=False,
        verbose=True
    )

    try:
        if not extractor.start_browser():
            return {}

        if not extractor.navigate_to_flow():
            return {}

        # Wait for page load
        time.sleep(3)

        # Capture headers
        headers = extractor.capture_headers_from_network(timeout=30)

        if headers.is_valid():
            return headers.to_dict()

        # Try trigger API
        headers = extractor.trigger_api_and_capture()

        if headers.is_valid():
            return headers.to_dict()

        return {}

    finally:
        extractor.stop_browser()


if __name__ == "__main__":
    print("=" * 60)
    print("CHROME HEADERS EXTRACTOR - TEST")
    print("=" * 60)

    headers = extract_headers_for_api()

    if headers:
        print("\n✅ Captured headers:")
        for k, v in headers.items():
            print(f"   {k}: {v[:50]}..." if len(str(v)) > 50 else f"   {k}: {v}")
    else:
        print("\n❌ Failed to capture headers")
