#!/usr/bin/env python3
"""
Start Chrome with IPv6 Proxy
============================
Chạy file này trước, sau đó chạy batch_generator.py
"""
import subprocess
import threading
import os
import sys

# Import proxy server
from ipv6_rotate_proxy import IPv6Rotator, ProxyServer, IPV6_LIST, PROXY_PORT, PROXY_HOST

def find_chrome():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "chrome.exe"

def main():
    print("=" * 50)
    print("  START CHROME WITH IPv6 PROXY")
    print("=" * 50)

    # Start proxy
    try:
        rotator = IPv6Rotator(IPV6_LIST)
    except Exception as e:
        print(f"[ERROR] {e}")
        print("[TIP] Chạy add_ipv6_windows.ps1 trước")
        return

    from ipv6_rotate_proxy import ProxyServer
    proxy = ProxyServer(rotator)
    proxy.start()

    # Launch Chrome
    chrome = find_chrome()
    cmd = [
        chrome,
        f"--proxy-server=socks5://127.0.0.1:{PROXY_PORT}",
        "--remote-debugging-port=9222",
    ]
    print(f"\n[CHROME] Launching...")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("\n[OK] Chrome đã mở với proxy IPv6!")
    print("\n[NEXT] Mở terminal khác và chạy:")
    print("  python batch_generator.py")
    print("\n[INFO] Nhấn Ctrl+C để dừng proxy")

    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n[STOP]")

if __name__ == "__main__":
    main()
