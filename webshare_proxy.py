#!/usr/bin/env python3
"""
Webshare.io Proxy Manager with Rotation
========================================
Quản lý pool 100 proxy từ Webshare với auto-rotation.

Features:
- Load proxy list từ file hoặc API
- Tự động xoay sang proxy khác khi bị block
- Đánh dấu proxy bị block để tránh dùng lại
- Hỗ trợ cả username/password và IP Authorization
"""

import os
import requests
import time
import random
from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProxyInfo:
    """Thông tin một proxy."""
    host: str
    port: int
    username: str = ""
    password: str = ""
    blocked: bool = False
    last_used: float = 0
    fail_count: int = 0

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def proxy_url(self) -> str:
        """URL cho requests library."""
        if self.username and self.password:
            return f"http://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"http://{self.host}:{self.port}"

    @property
    def chrome_url(self) -> str:
        """URL cho Chrome --proxy-server (không có auth)."""
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_string(cls, line: str) -> Optional['ProxyInfo']:
        """
        Parse proxy từ string.
        Formats:
        - IP:PORT:USER:PASS
        - IP:PORT (IP Authorization)
        - USER:PASS@IP:PORT
        """
        line = line.strip()
        if not line or line.startswith('#'):
            return None

        try:
            # Format: IP:PORT:USER:PASS
            if line.count(':') == 3:
                parts = line.split(':')
                return cls(
                    host=parts[0],
                    port=int(parts[1]),
                    username=parts[2],
                    password=parts[3]
                )
            # Format: USER:PASS@IP:PORT
            elif '@' in line:
                auth, endpoint = line.rsplit('@', 1)
                user, pwd = auth.split(':', 1)
                host, port = endpoint.split(':')
                return cls(host=host, port=int(port), username=user, password=pwd)
            # Format: IP:PORT (IP Authorization)
            elif line.count(':') == 1:
                host, port = line.split(':')
                return cls(host=host, port=int(port))
        except:
            pass
        return None


class WebshareProxyManager:
    """
    Quản lý pool proxy với auto-rotation.

    Khi một proxy bị block (403), tự động chuyển sang proxy khác.
    """

    API_BASE = "https://proxy.webshare.io/api/v2"

    def __init__(
        self,
        api_key: str = "",
        default_username: str = "",
        default_password: str = ""
    ):
        self.api_key = api_key
        self.default_username = default_username
        self.default_password = default_password

        self.proxies: List[ProxyInfo] = []
        self.current_index = 0
        self.rotate_count = 0
        self.block_timeout = 300  # 5 phút timeout cho blocked proxy

    def load_from_list(self, proxy_lines: List[str]) -> int:
        """
        Load proxies từ danh sách strings.
        Returns số proxy đã load.
        """
        count = 0
        for line in proxy_lines:
            proxy = ProxyInfo.from_string(line)
            if proxy:
                # Dùng default credentials nếu proxy không có
                if not proxy.username and self.default_username:
                    proxy.username = self.default_username
                if not proxy.password and self.default_password:
                    proxy.password = self.default_password
                self.proxies.append(proxy)
                count += 1
        return count

    def load_from_file(self, filepath: str) -> int:
        """Load proxies từ file."""
        path = Path(filepath)
        if not path.exists():
            return 0
        lines = path.read_text().strip().split('\n')
        return self.load_from_list(lines)

    def load_from_api(self) -> int:
        """
        Load proxies từ Webshare API.
        Cần API key.
        """
        if not self.api_key:
            return 0

        try:
            headers = {"Authorization": f"Token {self.api_key}"}
            resp = requests.get(
                f"{self.API_BASE}/proxy/list/?mode=direct&page_size=100",
                headers=headers,
                timeout=30
            )

            if resp.status_code != 200:
                print(f"API error: {resp.status_code}")
                return 0

            data = resp.json()
            results = data.get('results', [])

            for item in results:
                proxy = ProxyInfo(
                    host=item.get('proxy_address', ''),
                    port=int(item.get('port', 0)),
                    username=item.get('username', self.default_username),
                    password=item.get('password', self.default_password)
                )
                if proxy.host and proxy.port:
                    self.proxies.append(proxy)

            return len(results)

        except Exception as e:
            print(f"API error: {e}")
            return 0

    @property
    def current_proxy(self) -> Optional[ProxyInfo]:
        """Proxy hiện tại đang dùng."""
        if not self.proxies:
            return None
        return self.proxies[self.current_index % len(self.proxies)]

    @property
    def available_count(self) -> int:
        """Số proxy còn dùng được (không bị block)."""
        now = time.time()
        return sum(
            1 for p in self.proxies
            if not p.blocked or (now - p.last_used > self.block_timeout)
        )

    def get_proxies_dict(self) -> Dict[str, str]:
        """Dict proxies cho requests library."""
        proxy = self.current_proxy
        if not proxy:
            return {}
        return {
            "http": proxy.proxy_url,
            "https": proxy.proxy_url
        }

    def get_chrome_proxy_arg(self) -> str:
        """Proxy URL cho Chrome."""
        proxy = self.current_proxy
        if not proxy:
            return ""
        return proxy.chrome_url

    def get_chrome_auth(self) -> Tuple[str, str]:
        """Username, password cho Chrome auth."""
        proxy = self.current_proxy
        if not proxy:
            return "", ""
        return proxy.username, proxy.password

    def mark_current_blocked(self):
        """Đánh dấu proxy hiện tại bị block."""
        proxy = self.current_proxy
        if proxy:
            proxy.blocked = True
            proxy.fail_count += 1
            proxy.last_used = time.time()

    def rotate(self) -> Tuple[bool, str]:
        """
        Xoay sang proxy tiếp theo.
        Returns (success, message).
        """
        if not self.proxies:
            return False, "Không có proxy nào"

        if self.available_count == 0:
            # Reset tất cả blocked proxies
            for p in self.proxies:
                p.blocked = False
            return False, "Tất cả proxy đều bị block, đã reset"

        # Đánh dấu current là blocked
        self.mark_current_blocked()

        # Tìm proxy tiếp theo không bị block
        now = time.time()
        start_index = self.current_index
        attempts = 0

        while attempts < len(self.proxies):
            self.current_index = (self.current_index + 1) % len(self.proxies)
            proxy = self.proxies[self.current_index]

            # Proxy không bị block hoặc đã hết timeout
            if not proxy.blocked or (now - proxy.last_used > self.block_timeout):
                proxy.blocked = False  # Reset nếu hết timeout
                self.rotate_count += 1
                return True, f"Rotated to {proxy.endpoint} (#{self.rotate_count})"

            attempts += 1

        return False, "Không tìm được proxy khả dụng"

    def test_current(self) -> Tuple[bool, str]:
        """Test proxy hiện tại."""
        proxy = self.current_proxy
        if not proxy:
            return False, "Không có proxy"

        try:
            start = time.time()
            resp = requests.get(
                "https://ipv4.webshare.io/",
                proxies=self.get_proxies_dict(),
                timeout=15
            )
            elapsed = time.time() - start

            if resp.status_code == 200:
                ip = resp.text.strip()
                return True, f"OK! IP: {ip} ({elapsed:.1f}s)"
            return False, f"HTTP {resp.status_code}"

        except requests.exceptions.ProxyError as e:
            return False, f"Proxy error: {e}"
        except Exception as e:
            return False, f"Error: {e}"

    def get_stats(self) -> Dict:
        """Thống kê."""
        blocked = sum(1 for p in self.proxies if p.blocked)
        return {
            "total": len(self.proxies),
            "available": self.available_count,
            "blocked": blocked,
            "current": self.current_proxy.endpoint if self.current_proxy else None,
            "rotate_count": self.rotate_count
        }


# ============= Singleton instance =============
_manager: Optional[WebshareProxyManager] = None


def get_proxy_manager() -> WebshareProxyManager:
    """Get global proxy manager instance."""
    global _manager
    if _manager is None:
        _manager = WebshareProxyManager()
    return _manager


def init_proxy_manager(
    api_key: str = "",
    username: str = "",
    password: str = "",
    proxy_list: List[str] = None,
    proxy_file: str = None
) -> WebshareProxyManager:
    """
    Khởi tạo proxy manager.

    Args:
        api_key: Webshare API key (để auto-fetch proxy list)
        username: Default username cho tất cả proxy
        password: Default password
        proxy_list: List các proxy strings
        proxy_file: Path đến file chứa proxy list

    Returns:
        WebshareProxyManager instance
    """
    global _manager
    _manager = WebshareProxyManager(
        api_key=api_key,
        default_username=username,
        default_password=password
    )

    # Load từ các nguồn
    if proxy_list:
        count = _manager.load_from_list(proxy_list)
        print(f"Loaded {count} proxies from list")

    if proxy_file:
        count = _manager.load_from_file(proxy_file)
        print(f"Loaded {count} proxies from file")

    if api_key and not _manager.proxies:
        count = _manager.load_from_api()
        print(f"Loaded {count} proxies from API")

    # Shuffle để random thứ tự
    if _manager.proxies:
        random.shuffle(_manager.proxies)

    return _manager


# ============= Legacy compatibility =============
# Để tương thích với code cũ

class WebshareProxy:
    """Legacy wrapper cho WebshareProxyManager."""

    def __init__(self, config=None):
        self._manager = get_proxy_manager()

    def get_proxies(self) -> Dict[str, str]:
        return self._manager.get_proxies_dict()

    def get_chrome_proxy_arg(self) -> str:
        return self._manager.get_chrome_proxy_arg()

    def get_chrome_auth(self) -> Tuple[str, str]:
        return self._manager.get_chrome_auth()

    def rotate_ip(self) -> Tuple[bool, str]:
        return self._manager.rotate()

    def test_connection(self) -> Tuple[bool, str]:
        return self._manager.test_current()

    def get_stats(self) -> Dict:
        return self._manager.get_stats()

    @property
    def config(self):
        """Fake config cho legacy code."""
        class FakeConfig:
            endpoint = ""
            is_ip_auth_mode = False
        cfg = FakeConfig()
        proxy = self._manager.current_proxy
        if proxy:
            cfg.endpoint = proxy.endpoint
            cfg.is_ip_auth_mode = not proxy.username
        return cfg


def create_webshare_proxy(
    api_key: str = None,
    username: str = None,
    password: str = None,
    endpoint: str = None
) -> WebshareProxy:
    """
    Factory function cho legacy compatibility.
    Với code mới, dùng init_proxy_manager() thay thế.
    """
    manager = get_proxy_manager()

    # Nếu chưa có proxy, thử load
    if not manager.proxies:
        if endpoint:
            # Single proxy mode
            proxy = ProxyInfo.from_string(
                f"{endpoint}:{username or ''}:{password or ''}"
                if username else endpoint
            )
            if proxy:
                if not proxy.username and username:
                    proxy.username = username
                if not proxy.password and password:
                    proxy.password = password
                manager.proxies.append(proxy)

        if api_key:
            manager.api_key = api_key
            manager.load_from_api()

    return WebshareProxy()


# ============= Test =============
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  WEBSHARE PROXY MANAGER TEST")
    print("=" * 60)

    # Test với proxy list
    test_proxies = """
166.88.64.59:6442:jhvbehdf:cf1bi3yvq0t1
82.24.221.235:6086:jhvbehdf:cf1bi3yvq0t1
92.112.200.224:6807:jhvbehdf:cf1bi3yvq0t1
    """.strip().split('\n')

    manager = init_proxy_manager(proxy_list=test_proxies)

    print(f"\nLoaded {len(manager.proxies)} proxies")
    print(f"Current: {manager.current_proxy.endpoint}")

    # Test connection
    print("\n[1] Testing current proxy...")
    success, msg = manager.test_current()
    print(f"    {'✓' if success else '✗'} {msg}")

    # Test rotation
    print("\n[2] Testing rotation...")
    for i in range(3):
        success, msg = manager.rotate()
        print(f"    {msg}")

    # Stats
    print("\n[3] Stats:")
    for k, v in manager.get_stats().items():
        print(f"    {k}: {v}")
