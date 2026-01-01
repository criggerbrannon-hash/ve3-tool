#!/usr/bin/env python3
"""
Test IPv6 đơn giản - Windows
============================
Test xem đổi IPv6 có bypass được 403 không.

Mạng của bạn: 2001:ee0:b004:1f06::7
Test với: ::8, ::9, ::10...
"""

import socket
import subprocess
import time
import sys

# === CẤU HÌNH - THAY ĐỔI THEO MẠNG CỦA BẠN ===
IPV6_PREFIX = "2001:ee0:b004:1f06"  # Prefix của bạn
IPV6_SUFFIXES = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]  # Các suffix để test

# Tạo danh sách IPv6
IPV6_LIST = [f"{IPV6_PREFIX}::{s}" for s in IPV6_SUFFIXES]


def test_bind(ipv6: str) -> bool:
    """Test xem có bind được IPv6 này không"""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind((ipv6, 0))
        sock.close()
        return True
    except Exception as e:
        return False


def test_curl(ipv6: str, url: str = "https://www.google.com") -> tuple:
    """
    Test HTTP request với IPv6 bằng curl.
    Returns: (status_code, time_seconds)
    """
    try:
        start = time.time()

        # Curl command cho Windows
        cmd = [
            "curl", "-6", "-s",
            "-o", "NUL",           # Không output body
            "-w", "%{http_code}",  # Chỉ output status code
            "--interface", ipv6,   # Bind IPv6
            "--connect-timeout", "10",
            "--max-time", "15",
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        elapsed = time.time() - start

        output = result.stdout.strip()
        if output.isdigit():
            return (int(output), elapsed)
        else:
            return (0, elapsed)  # Error

    except subprocess.TimeoutExpired:
        return (-1, 0)  # Timeout
    except FileNotFoundError:
        return (-2, 0)  # curl not found
    except Exception as e:
        return (-3, 0)  # Other error


def test_socket_connect(ipv6: str, host: str = "www.google.com", port: int = 443) -> tuple:
    """
    Test TCP connection với IPv6.
    Returns: (success: bool, time_seconds)
    """
    try:
        # Resolve Google IPv6
        infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
        if not infos:
            return (False, 0)

        dest_ipv6 = infos[0][4][0]

        start = time.time()

        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(10)

        # Bind to our IPv6
        sock.bind((ipv6, 0))

        # Connect to Google
        sock.connect((dest_ipv6, port))

        elapsed = time.time() - start
        sock.close()

        return (True, elapsed)

    except Exception as e:
        return (False, 0)


def main():
    print("=" * 60)
    print("  TEST IPv6 BYPASS 403")
    print("=" * 60)
    print(f"\n  Prefix: {IPV6_PREFIX}::/64")
    print(f"  Test: {len(IPV6_LIST)} IPv6 addresses")
    print()

    # === BƯỚC 1: Kiểm tra IPv6 có bind được không ===
    print("[1] Kiểm tra IPv6 có sử dụng được...")
    print("-" * 40)

    bindable = []
    for ipv6 in IPV6_LIST:
        if test_bind(ipv6):
            bindable.append(ipv6)
            print(f"  ✓ {ipv6}")
        else:
            print(f"  ✗ {ipv6} (chưa add vào adapter)")

    if not bindable:
        print("\n" + "=" * 60)
        print("❌ KHÔNG CÓ IPv6 NÀO SỬ DỤNG ĐƯỢC!")
        print("=" * 60)
        print("\nCần add IPv6 vào Windows trước:")
        print("\n  1. Mở PowerShell với quyền Administrator")
        print("  2. Chạy lệnh sau (thay Ethernet bằng tên adapter của bạn):")
        print()
        for suffix in IPV6_SUFFIXES[:5]:
            print(f'     netsh interface ipv6 add address "Ethernet" {IPV6_PREFIX}::{suffix}')
        print()
        print("  Hoặc chạy script:")
        print("     powershell -ExecutionPolicy Bypass -File add_ipv6.ps1")
        return

    print(f"\n✓ {len(bindable)}/{len(IPV6_LIST)} IPv6 sẵn sàng")

    # === BƯỚC 2: Test TCP connection ===
    print(f"\n[2] Test TCP connection đến Google...")
    print("-" * 40)

    tcp_ok = []
    for ipv6 in bindable[:5]:  # Test 5 cái đầu
        success, elapsed = test_socket_connect(ipv6)
        if success:
            tcp_ok.append(ipv6)
            print(f"  ✓ {ipv6} → OK ({elapsed:.2f}s)")
        else:
            print(f"  ✗ {ipv6} → FAIL")
        time.sleep(0.3)

    if not tcp_ok:
        print("\n❌ Không kết nối được đến Google qua IPv6!")
        print("   Có thể ISP không hỗ trợ IPv6 hoặc firewall block.")
        return

    # === BƯỚC 3: Test HTTP với curl ===
    print(f"\n[3] Test HTTP request (curl)...")
    print("-" * 40)

    results = []
    for ipv6 in bindable:
        status, elapsed = test_curl(ipv6)
        results.append({"ipv6": ipv6, "status": status, "time": elapsed})

        if status == 200:
            print(f"  ✓ {ipv6} → HTTP 200 ({elapsed:.2f}s)")
        elif status == 403:
            print(f"  ⚠ {ipv6} → HTTP 403 (blocked)")
        elif status == -2:
            print(f"  ? {ipv6} → curl không tìm thấy")
            print("    Cài curl: winget install curl")
            break
        elif status == -1:
            print(f"  ✗ {ipv6} → Timeout")
        else:
            print(f"  ✗ {ipv6} → Error (code: {status})")

        time.sleep(1)  # Delay giữa các request

    # === KẾT QUẢ ===
    print("\n" + "=" * 60)
    print("  KẾT QUẢ")
    print("=" * 60)

    success = sum(1 for r in results if r["status"] == 200)
    blocked = sum(1 for r in results if r["status"] == 403)
    errors = sum(1 for r in results if r["status"] <= 0)

    print(f"\n  ✓ Thành công (200): {success}")
    print(f"  ⚠ Bị block (403):  {blocked}")
    print(f"  ✗ Lỗi:             {errors}")

    print("\n" + "-" * 40)

    if success > 0:
        print("\n🎉 IPv6 ROTATION CÓ THỂ HOẠT ĐỘNG!")
        print("\n   Các IPv6 hoạt động:")
        for r in results:
            if r["status"] == 200:
                print(f"     {r['ipv6']}")
        print("\n   → Có thể tích hợp vào tool để bypass 403")
        print("   → Chạy: python ipv6_rotate_proxy.py")

    elif blocked > 0:
        print("\n⚠️  MỘT SỐ IPv6 BỊ 403")
        print("   → Google có thể đang rate limit")
        print("   → Thử đổi sang /64 khác hoặc đợi reset")

    else:
        print("\n❌ KHÔNG THỂ KẾT NỐI")
        print("   Kiểm tra:")
        print("   - curl đã cài chưa? (winget install curl)")
        print("   - Firewall có block không?")
        print("   - ISP có hỗ trợ IPv6 không?")


if __name__ == "__main__":
    main()
