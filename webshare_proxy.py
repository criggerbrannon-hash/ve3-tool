#!/usr/bin/env python3
"""
Webshare.io Rotating Proxy Integration
======================================
Tích hợp proxy xoay từ Webshare.io.

2 chế độ:
1. Rotating Endpoint (p.webshare.io:80): Mỗi request = IP mới tự động
2. Direct Proxy (IP:PORT): IP cố định, cần replace thủ công

Cách dùng:
1. Đăng ký tại https://webshare.io
2. Vào Proxy List → Copy username, password
3. Dùng endpoint: p.webshare.io:80 (hoặc :1080 cho SOCKS5)
4. Thêm -rotate vào username để bật auto-rotate
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
    proxy_username: str = ""
    proxy_password: str = ""

    # Endpoint: p.webshare.io:80 hoặc IP:PORT
    endpoint: str = ""

    # Auto thêm -rotate vào username nếu dùng rotating endpoint
    auto_rotate_suffix: bool = True

    @property
    def is_rotating_endpoint(self) -> bool:
        """Check xem có phải rotating endpoint không."""
        return "webshare.io" in self.endpoint.lower()

    @property
    def effective_username(self) -> str:
        """Username với -rotate suffix nếu cần."""
        username = self.proxy_username
        if self.is_rotating_endpoint and self.auto_rotate_suffix:
            if not username.endswith("-rotate"):
                username = f"{username}-rotate"
        return username

    @property
    def is_ip_auth_mode(self) -> bool:
        """Check xem có dùng IP Authorization mode không (không cần username/password)."""
        return not self.proxy_username or not self.proxy_password

    @property
    def proxy_url(self) -> str:
        """URL proxy đầy đủ cho requests library."""
        if self.proxy_username and self.proxy_password:
            return f"http://{self.effective_username}:{self.proxy_password}@{self.endpoint}"
        # IP Authorization mode - không cần auth
        return f"http://{self.endpoint}"

    @property
    def socks5_url(self) -> str:
        """URL SOCKS5 proxy."""
        if self.proxy_username and self.proxy_password:
            return f"socks5://{self.effective_username}:{self.proxy_password}@{self.endpoint}"
        return f"socks5://{self.endpoint}"


class WebshareProxy:
    """
    Webshare.io Proxy Manager.

    Với Rotating Endpoint (p.webshare.io):
    - Mỗi request = IP mới tự động
    - Không cần gọi API để rotate
    - Restart Chrome để lấy IP mới

    Với Direct Proxy (IP cố định):
    - Cần gọi API refresh để đổi IP
    """

    API_BASE = "https://proxy.webshare.io/api/v2"

    def __init__(self, config: WebshareConfig):
        self.config = config
        self.rotate_count = 0
        self.last_rotate_time = 0
        self.min_rotate_interval = 3  # Tối thiểu 3 giây
        self.current_ip = None
        self._request_count = 0

    def get_proxies(self) -> Dict[str, str]:
        """Trả về dict proxies cho requests library."""
        proxy_url = self.config.proxy_url
        return {
            "http": proxy_url,
            "https": proxy_url
        }

    def get_chrome_proxy_arg(self) -> str:
        """
        Trả về proxy URL cho Chrome --proxy-server argument.
        Chrome cần restart để lấy IP mới từ rotating endpoint.
        """
        return f"http://{self.config.endpoint}"

    def get_chrome_auth(self) -> Tuple[str, str]:
        """Trả về (username, password) cho Chrome auth."""
        return self.config.effective_username, self.config.proxy_password

    def rotate_ip(self) -> Tuple[bool, str]:
        """
        Xoay IP.

        Với Rotating Endpoint: Chỉ cần đánh dấu để restart Chrome
        Với Direct Proxy: Gọi API refresh (nếu có)

        Returns:
            Tuple[success, message]
        """
        # Check cooldown
        now = time.time()
        if now - self.last_rotate_time < self.min_rotate_interval:
            wait = self.min_rotate_interval - (now - self.last_rotate_time)
            return False, f"Cooldown: đợi {wait:.1f}s"

        self.rotate_count += 1
        self.last_rotate_time = now

        if self.config.is_rotating_endpoint:
            # Rotating endpoint: Mỗi connection mới = IP mới
            # Chỉ cần restart Chrome là có IP mới
            return True, f"Rotating endpoint - restart Chrome để lấy IP #{self.rotate_count}"

        # Direct proxy: Thử gọi API refresh
        if self.config.api_key:
            try:
                headers = {"Authorization": f"Token {self.config.api_key}"}

                # Thử refresh proxy list
                resp = requests.post(
                    f"{self.API_BASE}/proxy/list/refresh/",
                    headers=headers,
                    timeout=30
                )

                if resp.status_code in [200, 201, 202]:
                    return True, f"Đã refresh proxy list #{self.rotate_count}"
                else:
                    return True, f"Rotate #{self.rotate_count} (API: {resp.status_code})"
            except Exception as e:
                return True, f"Rotate #{self.rotate_count} (no API: {e})"

        return True, f"Marked for rotation #{self.rotate_count}"

    def get_current_ip(self) -> Optional[str]:
        """Lấy IP hiện tại qua proxy."""
        try:
            # Dùng Webshare's own IP check endpoint
            resp = requests.get(
                "https://ipv4.webshare.io/",
                proxies=self.get_proxies(),
                timeout=15
            )
            if resp.status_code == 200:
                self.current_ip = resp.text.strip()
                self._request_count += 1
                return self.current_ip
        except:
            pass

        # Fallback
        try:
            resp = requests.get(
                "https://api.ipify.org",
                proxies=self.get_proxies(),
                timeout=10
            )
            if resp.status_code == 200:
                self.current_ip = resp.text.strip()
                return self.current_ip
        except:
            pass

        return None

    def test_connection(self) -> Tuple[bool, str]:
        """Test kết nối proxy và hiển thị IP."""
        try:
            start = time.time()
            ip = self.get_current_ip()
            elapsed = time.time() - start

            if ip:
                mode = "Rotating" if self.config.is_rotating_endpoint else "Direct"
                return True, f"OK! IP: {ip} ({mode}, {elapsed:.1f}s)"
            return False, "Không lấy được IP qua proxy"
        except requests.exceptions.ProxyError as e:
            return False, f"Proxy error: {e}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def test_rotation(self) -> Tuple[bool, str]:
        """Test xem IP có thực sự rotate không (với rotating endpoint)."""
        if not self.config.is_rotating_endpoint:
            return False, "Chỉ test được với rotating endpoint"

        ips = set()
        for i in range(3):
            ip = self.get_current_ip()
            if ip:
                ips.add(ip)
            time.sleep(0.5)

        if len(ips) > 1:
            return True, f"Rotation hoạt động! Thấy {len(ips)} IPs: {', '.join(ips)}"
        elif len(ips) == 1:
            return True, f"Rotation có thể chậm, thấy 1 IP: {list(ips)[0]}"
        else:
            return False, "Không lấy được IP nào"

    def get_stats(self) -> Dict:
        """Thống kê proxy usage."""
        return {
            "mode": "rotating" if self.config.is_rotating_endpoint else "direct",
            "endpoint": self.config.endpoint,
            "username": self.config.effective_username,
            "rotate_count": self.rotate_count,
            "request_count": self._request_count,
            "current_ip": self.current_ip,
            "last_rotate": self.last_rotate_time
        }


def create_webshare_proxy(
    api_key: str = None,
    username: str = None,
    password: str = None,
    endpoint: str = None
) -> WebshareProxy:
    """
    Tạo WebshareProxy instance.

    Args:
        api_key: Webshare API key (optional, dùng cho direct proxy refresh)
        username: Proxy username (không cần -rotate suffix, tự thêm)
        password: Proxy password
        endpoint: Proxy endpoint
                  - Rotating: p.webshare.io:80
                  - Direct: 166.88.64.59:6442

    Returns:
        WebshareProxy instance
    """
    config = WebshareConfig(
        api_key=api_key or os.environ.get("WEBSHARE_API_KEY", ""),
        proxy_username=username or os.environ.get("WEBSHARE_USERNAME", ""),
        proxy_password=password or os.environ.get("WEBSHARE_PASSWORD", ""),
        endpoint=endpoint or os.environ.get("WEBSHARE_ENDPOINT", "p.webshare.io:80"),
    )
    return WebshareProxy(config)


# ============= Test =============
if __name__ == "__main__":
    import sys

    print("=" * 50)
    print("  WEBSHARE PROXY TEST")
    print("=" * 50)

    # Check args hoặc dùng env
    if len(sys.argv) >= 4:
        username, password, endpoint = sys.argv[1], sys.argv[2], sys.argv[3]
        api_key = sys.argv[4] if len(sys.argv) > 4 else ""
    else:
        username = os.environ.get("WEBSHARE_USERNAME", "")
        password = os.environ.get("WEBSHARE_PASSWORD", "")
        endpoint = os.environ.get("WEBSHARE_ENDPOINT", "p.webshare.io:80")
        api_key = os.environ.get("WEBSHARE_API_KEY", "")

    if not username or not password:
        print("\nUsage: python webshare_proxy.py <username> <password> <endpoint> [api_key]")
        print("\nVí dụ:")
        print("  python webshare_proxy.py jhvbehdf cf1bi3yvq0t1 p.webshare.io:80")
        print("\nHoặc set environment variables:")
        print("  WEBSHARE_USERNAME, WEBSHARE_PASSWORD, WEBSHARE_ENDPOINT")
        sys.exit(1)

    proxy = create_webshare_proxy(
        api_key=api_key,
        username=username,
        password=password,
        endpoint=endpoint
    )

    print(f"\nEndpoint: {endpoint}")
    print(f"Username: {proxy.config.effective_username}")
    print(f"Mode: {'Rotating' if proxy.config.is_rotating_endpoint else 'Direct'}")

    # Test connection
    print("\n[1] Testing connection...")
    success, msg = proxy.test_connection()
    print(f"    {'✓' if success else '✗'} {msg}")

    if success and proxy.config.is_rotating_endpoint:
        # Test rotation
        print("\n[2] Testing IP rotation (3 requests)...")
        success, msg = proxy.test_rotation()
        print(f"    {'✓' if success else '✗'} {msg}")

    # Stats
    print("\n[3] Stats:")
    for k, v in proxy.get_stats().items():
        print(f"    {k}: {v}")
