#!/usr/bin/env python3
"""
Webshare.io Rotating Proxy Integration
======================================
Tích hợp proxy xoay từ Webshare.io với API đổi IP khi bị block.

Cách dùng:
1. Đăng ký tại https://webshare.io
2. Lấy API Key từ Dashboard
3. Cấu hình trong file này hoặc qua environment variables
"""

import os
import requests
import time
from typing import Optional, Dict, Tuple
from dataclasses import dataclass


@dataclass
class WebshareConfig:
    """Cấu hình Webshare proxy."""
    api_key: str = ""
    proxy_host: str = ""
    proxy_port: int = 0
    proxy_username: str = ""
    proxy_password: str = ""

    # Rotating proxy endpoint (dùng endpoint này thì tự động xoay)
    # Format: proxy.webshare.io:PORT hoặc p.webshare.io:PORT
    rotating_endpoint: str = ""

    @property
    def proxy_url(self) -> str:
        """URL proxy cho requests library."""
        if self.rotating_endpoint:
            # Dùng rotating endpoint
            if self.proxy_username and self.proxy_password:
                return f"http://{self.proxy_username}:{self.proxy_password}@{self.rotating_endpoint}"
            return f"http://{self.rotating_endpoint}"
        else:
            # Dùng static proxy
            if self.proxy_username and self.proxy_password:
                return f"http://{self.proxy_username}:{self.proxy_password}@{self.proxy_host}:{self.proxy_port}"
            return f"http://{self.proxy_host}:{self.proxy_port}"

    @property
    def chrome_proxy_url(self) -> str:
        """URL proxy cho Chrome (không có auth trong URL)."""
        if self.rotating_endpoint:
            return f"http://{self.rotating_endpoint}"
        return f"http://{self.proxy_host}:{self.proxy_port}"


class WebshareProxy:
    """
    Webshare.io Proxy Manager với auto-rotation.

    Features:
    - Gọi API để xoay IP khi bị 403
    - Đếm số lần rotate
    - Cooldown giữa các lần rotate
    """

    API_BASE = "https://proxy.webshare.io/api/v2"

    def __init__(self, config: WebshareConfig):
        self.config = config
        self.rotate_count = 0
        self.last_rotate_time = 0
        self.min_rotate_interval = 5  # Tối thiểu 5 giây giữa các lần rotate
        self.current_ip = None

    def get_proxies(self) -> Dict[str, str]:
        """Trả về dict proxies cho requests library."""
        proxy_url = self.config.proxy_url
        return {
            "http": proxy_url,
            "https": proxy_url
        }

    def get_chrome_proxy_arg(self) -> str:
        """Trả về proxy argument cho Chrome."""
        return self.config.chrome_proxy_url

    def rotate_ip(self) -> Tuple[bool, str]:
        """
        Gọi API Webshare để xoay sang IP mới.

        Returns:
            Tuple[success, message]
        """
        # Check cooldown
        now = time.time()
        if now - self.last_rotate_time < self.min_rotate_interval:
            wait = self.min_rotate_interval - (now - self.last_rotate_time)
            return False, f"Cooldown: đợi thêm {wait:.1f}s"

        if not self.config.api_key:
            return False, "Không có API key"

        try:
            headers = {
                "Authorization": f"Token {self.config.api_key}"
            }

            # Gọi API rotate
            resp = requests.post(
                f"{self.API_BASE}/proxy/rotate/",
                headers=headers,
                timeout=30
            )

            if resp.status_code == 200:
                self.rotate_count += 1
                self.last_rotate_time = now

                # Lấy IP mới (nếu có trong response)
                try:
                    data = resp.json()
                    self.current_ip = data.get("ip_address", "unknown")
                except:
                    self.current_ip = "rotated"

                return True, f"Đã xoay IP #{self.rotate_count} → {self.current_ip}"
            else:
                return False, f"API error {resp.status_code}: {resp.text[:100]}"

        except Exception as e:
            return False, f"Rotate error: {e}"

    def get_current_ip(self) -> Optional[str]:
        """Lấy IP hiện tại qua proxy."""
        try:
            resp = requests.get(
                "https://api.ipify.org?format=json",
                proxies=self.get_proxies(),
                timeout=10
            )
            if resp.status_code == 200:
                self.current_ip = resp.json().get("ip")
                return self.current_ip
        except:
            pass
        return None

    def test_connection(self) -> Tuple[bool, str]:
        """Test kết nối proxy."""
        try:
            ip = self.get_current_ip()
            if ip:
                return True, f"Connected via {ip}"
            return False, "Không lấy được IP"
        except Exception as e:
            return False, f"Connection error: {e}"

    def get_stats(self) -> Dict:
        """Thống kê proxy usage."""
        return {
            "rotate_count": self.rotate_count,
            "current_ip": self.current_ip,
            "last_rotate": self.last_rotate_time
        }


# ============= Cấu hình mặc định =============
# Có thể override bằng environment variables

DEFAULT_CONFIG = WebshareConfig(
    # API Key từ Webshare Dashboard
    api_key=os.environ.get("WEBSHARE_API_KEY", ""),

    # Proxy credentials
    proxy_username=os.environ.get("WEBSHARE_USERNAME", ""),
    proxy_password=os.environ.get("WEBSHARE_PASSWORD", ""),

    # Rotating proxy endpoint (lấy từ Webshare Dashboard)
    # Ví dụ: p.webshare.io:80 hoặc proxy.webshare.io:80
    rotating_endpoint=os.environ.get("WEBSHARE_ENDPOINT", ""),
)


def create_webshare_proxy(
    api_key: str = None,
    username: str = None,
    password: str = None,
    endpoint: str = None
) -> WebshareProxy:
    """
    Tạo WebshareProxy instance.

    Args:
        api_key: Webshare API key
        username: Proxy username
        password: Proxy password
        endpoint: Rotating proxy endpoint (e.g., p.webshare.io:80)

    Returns:
        WebshareProxy instance
    """
    config = WebshareConfig(
        api_key=api_key or DEFAULT_CONFIG.api_key,
        proxy_username=username or DEFAULT_CONFIG.proxy_username,
        proxy_password=password or DEFAULT_CONFIG.proxy_password,
        rotating_endpoint=endpoint or DEFAULT_CONFIG.rotating_endpoint,
    )
    return WebshareProxy(config)


# ============= Test =============
if __name__ == "__main__":
    print("=" * 50)
    print("  WEBSHARE PROXY TEST")
    print("=" * 50)

    # Kiểm tra config
    if not DEFAULT_CONFIG.api_key:
        print("\n[!] Chưa cấu hình API Key!")
        print("    Set environment variable: WEBSHARE_API_KEY")
        print("    Hoặc sửa trực tiếp trong file này")
        print("\n[INFO] Cách lấy thông tin từ Webshare:")
        print("    1. Đăng nhập https://webshare.io")
        print("    2. Vào Dashboard → API → Copy API Key")
        print("    3. Vào Proxy → Proxy List → Copy endpoint")
        exit(1)

    proxy = WebshareProxy(DEFAULT_CONFIG)

    # Test connection
    print("\n[1] Testing connection...")
    success, msg = proxy.test_connection()
    print(f"    {'✓' if success else '✗'} {msg}")

    if success:
        # Test rotate
        print("\n[2] Testing IP rotation...")
        success, msg = proxy.rotate_ip()
        print(f"    {'✓' if success else '✗'} {msg}")

        # Verify new IP
        print("\n[3] Verifying new IP...")
        new_ip = proxy.get_current_ip()
        print(f"    Current IP: {new_ip}")

        # Stats
        print("\n[4] Stats:")
        stats = proxy.get_stats()
        for k, v in stats.items():
            print(f"    {k}: {v}")
