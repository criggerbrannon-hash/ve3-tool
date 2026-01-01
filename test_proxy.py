#!/usr/bin/env python3
"""
Quick Webshare Proxy Test
=========================
Test kết nối proxy giống như tool sử dụng.
"""

import socket
import time
import requests
import yaml

def load_config():
    """Load settings từ config/settings.yaml"""
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def test_socket_connection(host, port, timeout=10):
    """Test kết nối socket trực tiếp"""
    try:
        start = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        elapsed = time.time() - start
        s.close()
        return True, elapsed
    except Exception as e:
        return False, str(e)

def test_requests_proxy(proxy_url, test_url="https://httpbin.org/ip"):
    """Test proxy qua requests library"""
    try:
        start = time.time()
        resp = requests.get(
            test_url,
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=30
        )
        elapsed = time.time() - start
        if resp.status_code == 200:
            return True, elapsed, resp.json().get("origin", "?")
        return False, elapsed, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, 0, str(e)

def main():
    print("=" * 60)
    print("WEBSHARE PROXY TEST")
    print("=" * 60)

    config = load_config()
    ws = config.get("webshare_proxy", {})

    host = ws.get("rotating_host", "p.webshare.io")
    port = ws.get("rotating_port", 80)
    username = ws.get("rotating_base_username", "")
    password = ws.get("rotating_password", "")

    print(f"\nConfig:")
    print(f"  Host: {host}:{port}")
    print(f"  Username: {username}")
    print(f"  Password: {'*' * len(password)}")

    # Test 1: Socket connection
    print(f"\n[TEST 1] Socket connection to {host}:{port}...")
    for i in range(3):
        ok, result = test_socket_connection(host, port)
        if ok:
            print(f"  ✅ OK ({result:.2f}s)")
        else:
            print(f"  ❌ FAIL: {result}")
        time.sleep(0.5)

    # Test 2: Requests with proxy
    proxy_url = f"http://{username}:{password}@{host}:{port}"
    print(f"\n[TEST 2] Requests qua proxy...")
    print(f"  URL: http://{username}:****@{host}:{port}")

    for i in range(5):
        ok, elapsed, result = test_requests_proxy(proxy_url)
        if ok:
            print(f"  ✅ OK ({elapsed:.1f}s) - IP: {result}")
        else:
            print(f"  ❌ FAIL: {result}")
        time.sleep(1)

    # Test 3: Simulate proxy_bridge behavior
    print(f"\n[TEST 3] Mô phỏng proxy_bridge...")

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(30)

        start = time.time()
        print(f"  Connecting to {host}:{port}...")
        s.connect((host, port))
        elapsed = time.time() - start
        print(f"  ✅ Connected in {elapsed:.2f}s")

        # Send CONNECT request (như Chrome HTTPS)
        import base64
        auth = base64.b64encode(f"{username}:{password}".encode()).decode()
        connect_req = (
            f"CONNECT httpbin.org:443 HTTP/1.1\r\n"
            f"Host: httpbin.org:443\r\n"
            f"Proxy-Authorization: Basic {auth}\r\n"
            f"\r\n"
        )

        print(f"  Sending CONNECT request...")
        s.send(connect_req.encode())

        response = s.recv(4096).decode("utf-8", errors="ignore")
        first_line = response.split("\r\n")[0]
        print(f"  Response: {first_line}")

        if "200" in first_line:
            print(f"  ✅ Tunnel established!")
        else:
            print(f"  ❌ Tunnel failed!")
            print(f"  Full response:\n{response[:500]}")

        s.close()

    except Exception as e:
        print(f"  ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)

if __name__ == "__main__":
    main()
