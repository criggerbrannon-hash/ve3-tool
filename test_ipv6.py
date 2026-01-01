#!/usr/bin/env python3
"""
Test IPv6 Rotation
==================
Test xem đổi IPv6 có bypass được 403 không.

Yêu cầu:
- Linux với IPv6 subnet được assign
- Chạy với sudo (để add IP vào interface)

Usage:
    sudo python test_ipv6.py
"""

import socket
import subprocess
import requests
import time
import sys

# === CẤU HÌNH ===
# Thay đổi theo subnet của bạn
IPV6_PREFIX = "2001:ee0:b004:1f01"  # /64 prefix
INTERFACE = "eth0"  # Network interface (dùng `ip a` để xem)

# Test URL (Google endpoint)
TEST_URL = "https://www.google.com"


def get_ipv6_address(suffix: int) -> str:
    """Tạo IPv6 address từ prefix + suffix"""
    return f"{IPV6_PREFIX}::{suffix}"


def add_ipv6_to_interface(ipv6: str, interface: str = INTERFACE) -> bool:
    """Thêm IPv6 vào network interface"""
    try:
        cmd = f"ip -6 addr add {ipv6}/128 dev {interface}"
        result = subprocess.run(cmd.split(), capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✓ Added {ipv6} to {interface}")
            return True
        elif "exists" in result.stderr:
            print(f"  ℹ {ipv6} already exists")
            return True
        else:
            print(f"  ✗ Failed to add {ipv6}: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def remove_ipv6_from_interface(ipv6: str, interface: str = INTERFACE) -> bool:
    """Xóa IPv6 khỏi network interface"""
    try:
        cmd = f"ip -6 addr del {ipv6}/128 dev {interface}"
        subprocess.run(cmd.split(), capture_output=True)
        return True
    except:
        return False


def test_request_with_ipv6(ipv6: str, url: str = TEST_URL) -> dict:
    """
    Gửi HTTP request với IPv6 source address cụ thể.
    """
    result = {
        "ipv6": ipv6,
        "status": None,
        "error": None,
        "time": 0
    }

    try:
        # Tạo custom adapter để bind IPv6
        import urllib3
        from requests.adapters import HTTPAdapter

        class IPv6Adapter(HTTPAdapter):
            def __init__(self, source_address, **kwargs):
                self.source_address = source_address
                super().__init__(**kwargs)

            def init_poolmanager(self, *args, **kwargs):
                kwargs['source_address'] = (self.source_address, 0)
                super().init_poolmanager(*args, **kwargs)

        # Tạo session với IPv6 source
        session = requests.Session()
        session.mount('https://', IPv6Adapter(ipv6))
        session.mount('http://', IPv6Adapter(ipv6))

        start = time.time()
        response = session.get(url, timeout=15)
        elapsed = time.time() - start

        result["status"] = response.status_code
        result["time"] = elapsed

    except Exception as e:
        result["error"] = str(e)

    return result


def test_curl_with_ipv6(ipv6: str, url: str = TEST_URL) -> dict:
    """Test bằng curl (đơn giản hơn)"""
    result = {
        "ipv6": ipv6,
        "status": None,
        "error": None,
        "time": 0
    }

    try:
        start = time.time()
        cmd = [
            "curl", "-6", "-s", "-o", "/dev/null",
            "-w", "%{http_code}",
            "--interface", ipv6,
            "--connect-timeout", "10",
            url
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        elapsed = time.time() - start

        if proc.returncode == 0:
            result["status"] = int(proc.stdout.strip())
        else:
            result["error"] = proc.stderr or f"curl exit {proc.returncode}"
        result["time"] = elapsed

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    print("=" * 60)
    print("IPv6 ROTATION TEST")
    print("=" * 60)
    print(f"\nPrefix: {IPV6_PREFIX}::/64")
    print(f"Interface: {INTERFACE}")
    print(f"Test URL: {TEST_URL}")

    # Kiểm tra interface
    print(f"\n[1] Kiểm tra interface {INTERFACE}...")
    try:
        result = subprocess.run(
            ["ip", "-6", "addr", "show", INTERFACE],
            capture_output=True, text=True
        )
        if IPV6_PREFIX in result.stdout:
            print(f"  ✓ Interface có IPv6 prefix: {IPV6_PREFIX}")
        else:
            print(f"  ⚠ Interface chưa có prefix {IPV6_PREFIX}")
            print(f"  Có thể cần add thủ công hoặc kiểm tra lại")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    # Test nhiều IPv6 addresses
    print(f"\n[2] Test với các IPv6 addresses khác nhau...")

    suffixes = [2, 3, 4, 5, 10, 100, 1000]  # Các suffix để test
    results = []

    for suffix in suffixes:
        ipv6 = get_ipv6_address(suffix)
        print(f"\n  Testing {ipv6}...")

        # Add IP to interface (cần sudo)
        add_ipv6_to_interface(ipv6)
        time.sleep(0.5)  # Đợi interface cập nhật

        # Test request
        result = test_curl_with_ipv6(ipv6)
        results.append(result)

        if result["status"]:
            status_icon = "✓" if result["status"] == 200 else "⚠"
            print(f"  {status_icon} Status: {result['status']} ({result['time']:.2f}s)")
        else:
            print(f"  ✗ Error: {result['error']}")

        # Cleanup - xóa IP sau khi test
        # remove_ipv6_from_interface(ipv6)

        time.sleep(1)  # Delay giữa các requests

    # Summary
    print("\n" + "=" * 60)
    print("KẾT QUẢ")
    print("=" * 60)

    success = sum(1 for r in results if r["status"] == 200)
    total = len(results)

    print(f"\nThành công: {success}/{total}")

    for r in results:
        status = r["status"] or r["error"]
        print(f"  {r['ipv6']} → {status}")

    print("\n" + "=" * 60)

    if success > 0:
        print("✓ IPv6 rotation CÓ THỂ HOẠT ĐỘNG!")
        print("  → Có thể tích hợp vào tool để bypass 403")
    else:
        print("✗ IPv6 rotation KHÔNG hoạt động")
        print("  → Có thể do:")
        print("     - Interface chưa được cấu hình đúng")
        print("     - ISP không hỗ trợ")
        print("     - Cần enable ip_nonlocal_bind")


if __name__ == "__main__":
    if sys.platform != "linux":
        print("⚠ Script này chỉ chạy trên Linux!")
        print("  Windows cần cách khác để bind IPv6")
        sys.exit(1)

    import os
    if os.geteuid() != 0:
        print("⚠ Cần chạy với sudo để add IPv6 vào interface!")
        print("  sudo python test_ipv6.py")
        sys.exit(1)

    main()
