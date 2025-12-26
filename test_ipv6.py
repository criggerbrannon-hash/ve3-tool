#!/usr/bin/env python3
"""
Test IPv6 connectivity
======================
Kiểm tra xem các IPv6 của bạn có hoạt động không.
"""

import socket
import urllib.request
import ssl

IPV6_LIST = [
    "2001:ee0:b004:1f00::2",
    "2001:ee0:b004:1f01::2",
    "2001:ee0:b004:1f02::3",
    "2001:ee0:b004:1f03::4",
    "2001:ee0:b004:1f04::5",
    "2001:ee0:b004:1f05::6",
    "2001:ee0:b004:1f06::7",
    "2001:ee0:b004:1f07::8",
    "2001:ee0:b004:1f08::9",
    "2001:ee0:b004:1f09::10",
]

def test_ipv6_bind(ipv6_addr):
    """Test if we can bind to this IPv6 address"""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind((ipv6_addr, 0))
        sock.close()
        return True, "Bind OK"
    except Exception as e:
        return False, str(e)

def test_ipv6_connect(ipv6_addr):
    """Test if we can make outbound connection from this IPv6"""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((ipv6_addr, 0))
        sock.settimeout(10)
        # Try to connect to Google's IPv6
        sock.connect(("ipv6.google.com", 80))
        sock.close()
        return True, "Connect OK"
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("  IPv6 CONNECTIVITY TEST")
    print("=" * 60)
    print()

    # Test first few IPs
    for ipv6 in IPV6_LIST[:5]:
        print(f"Testing: {ipv6}")

        # Test bind
        ok, msg = test_ipv6_bind(ipv6)
        print(f"  Bind:    {'✓' if ok else '✗'} {msg}")

        if ok:
            # Test connect
            ok, msg = test_ipv6_connect(ipv6)
            print(f"  Connect: {'✓' if ok else '✗'} {msg}")

        print()

    print("\n[INFO] Nếu tất cả đều ✓, bạn có thể chạy proxy server!")
    print("[CMD]  python ipv6_rotate_proxy.py")

if __name__ == "__main__":
    main()
