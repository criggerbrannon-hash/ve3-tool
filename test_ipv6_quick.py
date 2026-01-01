#!/usr/bin/env python3
"""
Quick IPv6 Test - Kiểm tra xem đổi IPv6 có bypass 403 không
===========================================================
Dùng danh sách IPv6 từ ipv6_rotate_proxy.py
"""

import socket
import time
import subprocess
import sys

# Lấy danh sách IPv6 từ file có sẵn
from ipv6_rotate_proxy import IPV6_LIST, test_ipv6_bindable

# Test URL - Google API endpoint
TEST_URLS = [
    "https://www.google.com",
    "https://labs.google/fx/vi/tools/flow",
]


def test_curl_ipv6(ipv6: str, url: str = "https://www.google.com") -> dict:
    """Test request với IPv6 cụ thể bằng curl"""
    result = {"ipv6": ipv6, "status": None, "error": None, "time": 0}

    try:
        start = time.time()

        # Windows curl command
        if sys.platform == "win32":
            cmd = [
                "curl", "-6", "-s", "-o", "NUL", "-w", "%{http_code}",
                "--interface", ipv6,
                "--connect-timeout", "10",
                "--max-time", "20",
                url
            ]
        else:
            cmd = [
                "curl", "-6", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                "--interface", ipv6,
                "--connect-timeout", "10",
                "--max-time", "20",
                url
            ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        elapsed = time.time() - start

        output = proc.stdout.strip()
        if output.isdigit():
            result["status"] = int(output)
        else:
            result["error"] = proc.stderr or output or f"Exit {proc.returncode}"

        result["time"] = elapsed

    except FileNotFoundError:
        result["error"] = "curl not found"
    except subprocess.TimeoutExpired:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def test_socket_ipv6(ipv6: str, host: str = "www.google.com", port: int = 443) -> dict:
    """Test kết nối TCP với IPv6"""
    result = {"ipv6": ipv6, "status": None, "error": None, "time": 0}

    try:
        # Resolve host to IPv6
        infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
        if not infos:
            result["error"] = f"No IPv6 for {host}"
            return result

        dest_ipv6 = infos[0][4][0]

        start = time.time()

        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(10)

        # Bind to our IPv6
        sock.bind((ipv6, 0))

        # Connect
        sock.connect((dest_ipv6, port))

        elapsed = time.time() - start
        result["status"] = "OK"
        result["time"] = elapsed

        sock.close()

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    print("=" * 60)
    print("QUICK IPv6 TEST")
    print("=" * 60)
    print(f"\nTổng số IPv6: {len(IPV6_LIST)}")

    # Test bindable
    print("\n[1] Kiểm tra IPv6 có thể bind...")
    bindable = []
    for ipv6 in IPV6_LIST[:10]:  # Test 10 cái đầu
        if test_ipv6_bindable(ipv6):
            bindable.append(ipv6)
            print(f"  ✓ {ipv6}")
        else:
            print(f"  ✗ {ipv6}")

    if not bindable:
        print("\n❌ Không có IPv6 nào bind được!")
        print("\n[TIP] Chạy script add IPv6 trước:")
        print("  PowerShell (Admin): ./add_ipv6_windows.ps1")
        return

    print(f"\n✓ {len(bindable)} IPv6 có thể sử dụng")

    # Test socket connection
    print("\n[2] Test kết nối TCP đến Google...")
    for ipv6 in bindable[:5]:
        result = test_socket_ipv6(ipv6)
        if result["status"] == "OK":
            print(f"  ✓ {ipv6} → OK ({result['time']:.2f}s)")
        else:
            print(f"  ✗ {ipv6} → {result['error']}")

    # Test HTTP với curl
    print("\n[3] Test HTTP request (curl)...")
    results = []

    for ipv6 in bindable[:5]:
        print(f"\n  Testing {ipv6}...")
        result = test_curl_ipv6(ipv6, "https://www.google.com")
        results.append(result)

        if result["status"]:
            icon = "✓" if result["status"] == 200 else "⚠"
            print(f"    {icon} HTTP {result['status']} ({result['time']:.2f}s)")
        else:
            print(f"    ✗ {result['error']}")

        time.sleep(1)

    # Summary
    print("\n" + "=" * 60)
    print("KẾT QUẢ")
    print("=" * 60)

    success = sum(1 for r in results if r.get("status") == 200)
    blocked = sum(1 for r in results if r.get("status") == 403)

    print(f"\n  ✓ Thành công: {success}")
    print(f"  ⚠ Blocked (403): {blocked}")

    if success > 0:
        print("\n✅ IPv6 ROTATION HOẠT ĐỘNG!")
        print("   → Có thể dùng để bypass 403")
        print("\n[NEXT] Chạy proxy server:")
        print("   python ipv6_rotate_proxy.py")
        print("\n   Sau đó Chrome dùng:")
        print("   --proxy-server=socks5://127.0.0.1:1080")
    else:
        print("\n❌ IPv6 KHÔNG bypass được 403")
        print("   → Có thể Google block cả subnet")


if __name__ == "__main__":
    main()
