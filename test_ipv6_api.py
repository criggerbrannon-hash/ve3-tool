#!/usr/bin/env python3
"""
Test IPv6 với Google Flow API
=============================
Bạn capture dữ liệu từ Chrome, script sẽ test với nhiều IPv6.

Cách dùng:
1. Vào Chrome → labs.google/fx → Tạo 1 ảnh
2. Mở DevTools (F12) → Network
3. Tìm request "generateImages" hoặc "batchGenerate"
4. Copy Bearer token, recaptcha token, URL
5. Paste vào script này và chạy
"""

import socket
import ssl
import json
import time
import sys
from typing import List, Tuple
from urllib.parse import urlparse

# === PASTE DỮ LIỆU TỪ CHROME VÀO ĐÂY ===

# Bearer token (từ Authorization header)
BEARER_TOKEN = ""  # Paste: ya29.xxx...

# reCAPTCHA token (từ request body)
RECAPTCHA_TOKEN = ""  # Paste token dài

# API URL
API_URL = "https://aisandbox-pa.googleapis.com/v1/projects/YOUR_PROJECT_ID:batchGenerateImages"

# Request body (có thể để default nếu chỉ test connection)
REQUEST_BODY = {
    "requests": [{
        "generation_config": {
            "prompt": "test image",
            "image_count": 1
        }
    }],
    "recaptchaToken": ""  # Sẽ được fill tự động
}

# === DANH SÁCH IPv6 ĐỂ TEST ===
# Thay bằng subnet của bạn
IPV6_PREFIX = "2001:ee0:b004:1f"
IPV6_LIST = [
    f"{IPV6_PREFIX}00::2",
    f"{IPV6_PREFIX}01::2",
    f"{IPV6_PREFIX}02::3",
    f"{IPV6_PREFIX}03::4",
    f"{IPV6_PREFIX}04::5",
    f"{IPV6_PREFIX}05::6",
    f"{IPV6_PREFIX}06::7",
    f"{IPV6_PREFIX}07::8",
    f"{IPV6_PREFIX}08::9",
    f"{IPV6_PREFIX}09::10",
]


def test_ipv6_bindable(ipv6: str) -> bool:
    """Test xem có bind được IPv6 này không"""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind((ipv6, 0))
        sock.close()
        return True
    except:
        return False


def resolve_ipv6(hostname: str) -> str:
    """Resolve hostname thành IPv6"""
    try:
        infos = socket.getaddrinfo(hostname, 443, socket.AF_INET6, socket.SOCK_STREAM)
        if infos:
            return infos[0][4][0]
    except:
        pass
    return None


def make_https_request(
    source_ipv6: str,
    url: str,
    method: str = "POST",
    headers: dict = None,
    body: str = None,
    timeout: int = 30
) -> Tuple[int, str]:
    """
    Gửi HTTPS request với IPv6 source cụ thể.
    Returns: (status_code, response_body)
    """
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or 443
    path = parsed.path
    if parsed.query:
        path += "?" + parsed.query

    # Resolve host to IPv6
    dest_ipv6 = resolve_ipv6(host)
    if not dest_ipv6:
        return (0, f"Cannot resolve {host} to IPv6")

    try:
        # Create socket and bind to our IPv6
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.bind((source_ipv6, 0))

        # Connect
        sock.connect((dest_ipv6, port))

        # Wrap with SSL
        context = ssl.create_default_context()
        ssock = context.wrap_socket(sock, server_hostname=host)

        # Build HTTP request
        if headers is None:
            headers = {}

        headers.setdefault("Host", host)
        headers.setdefault("Connection", "close")

        if body:
            headers.setdefault("Content-Length", str(len(body)))
            headers.setdefault("Content-Type", "application/json")

        request_lines = [f"{method} {path} HTTP/1.1"]
        for k, v in headers.items():
            request_lines.append(f"{k}: {v}")
        request_lines.append("")

        if body:
            request_lines.append(body)
        else:
            request_lines.append("")

        request = "\r\n".join(request_lines)

        # Send
        ssock.sendall(request.encode())

        # Receive response
        response = b""
        while True:
            try:
                chunk = ssock.recv(8192)
                if not chunk:
                    break
                response += chunk
            except socket.timeout:
                break

        ssock.close()
        sock.close()

        # Parse response
        response_str = response.decode("utf-8", errors="ignore")
        parts = response_str.split("\r\n\r\n", 1)
        headers_str = parts[0]
        body_str = parts[1] if len(parts) > 1 else ""

        # Get status code
        first_line = headers_str.split("\r\n")[0]
        status_code = int(first_line.split()[1])

        return (status_code, body_str[:500])  # Truncate body

    except Exception as e:
        return (0, str(e))


def test_google_api_with_ipv6(ipv6: str, bearer: str, recaptcha: str, url: str) -> dict:
    """Test Google Flow API với IPv6 cụ thể"""
    result = {"ipv6": ipv6, "status": None, "error": None, "time": 0}

    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
    }

    body_data = dict(REQUEST_BODY)
    body_data["recaptchaToken"] = recaptcha
    body = json.dumps(body_data)

    start = time.time()
    status, response = make_https_request(ipv6, url, "POST", headers, body)
    elapsed = time.time() - start

    result["status"] = status
    result["time"] = elapsed

    if status == 0:
        result["error"] = response
    elif status == 403:
        result["error"] = "403 Forbidden"
        if "reCAPTCHA" in response:
            result["error"] = "403 reCAPTCHA failed"
    elif status == 200:
        result["error"] = None

    return result


def simple_connection_test(ipv6: str) -> dict:
    """Test kết nối đơn giản đến Google"""
    result = {"ipv6": ipv6, "status": None, "error": None, "time": 0}

    try:
        start = time.time()
        status, body = make_https_request(
            ipv6,
            "https://www.google.com/",
            method="GET",
            timeout=10
        )
        elapsed = time.time() - start

        result["status"] = status
        result["time"] = elapsed

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    print("=" * 60)
    print("TEST IPv6 VỚI GOOGLE API")
    print("=" * 60)

    # Check có data chưa
    if not BEARER_TOKEN or not RECAPTCHA_TOKEN or "YOUR_PROJECT" in API_URL:
        print("\n⚠️ CHƯA CÓ DỮ LIỆU!")
        print("\nCách lấy dữ liệu:")
        print("1. Vào Chrome → labs.google/fx → Login")
        print("2. Tạo 1 ảnh")
        print("3. F12 → Network → Tìm 'batchGenerate'")
        print("4. Copy:")
        print("   - Authorization header (Bearer ya29.xxx)")
        print("   - recaptchaToken trong body")
        print("   - Request URL")
        print("5. Paste vào script (dòng 24-32)")
        print("\n[TIP] Hoặc test connection đơn giản trước:")
        print()

    # Test bindable IPv6
    print("\n[1] Kiểm tra IPv6 có thể sử dụng...")
    bindable = []
    for ipv6 in IPV6_LIST:
        if test_ipv6_bindable(ipv6):
            bindable.append(ipv6)
            print(f"  ✓ {ipv6}")
        else:
            print(f"  ✗ {ipv6} (không bind được)")

    if not bindable:
        print("\n❌ Không có IPv6 nào sử dụng được!")
        print("\nChạy script add IPv6:")
        print("  Windows (Admin): netsh interface ipv6 add address \"Ethernet\" 2001:ee0:b004:1f00::2")
        return

    print(f"\n✓ {len(bindable)} IPv6 sẵn sàng")

    # Simple connection test
    print("\n[2] Test kết nối cơ bản đến Google...")
    for ipv6 in bindable[:3]:
        result = simple_connection_test(ipv6)
        if result["status"] == 200:
            print(f"  ✓ {ipv6} → HTTP {result['status']} ({result['time']:.2f}s)")
        else:
            print(f"  ✗ {ipv6} → {result.get('error') or result['status']}")
        time.sleep(0.5)

    # Full API test (if data available)
    if BEARER_TOKEN and RECAPTCHA_TOKEN and "YOUR_PROJECT" not in API_URL:
        print("\n[3] Test Google Flow API...")
        results = []

        for ipv6 in bindable[:5]:
            print(f"\n  Testing {ipv6}...")
            result = test_google_api_with_ipv6(ipv6, BEARER_TOKEN, RECAPTCHA_TOKEN, API_URL)
            results.append(result)

            if result["status"] == 200:
                print(f"    ✅ HTTP 200 OK ({result['time']:.2f}s)")
            elif result["status"] == 403:
                print(f"    ⚠️ HTTP 403 - {result['error']}")
            else:
                print(f"    ❌ {result.get('error') or result['status']}")

            time.sleep(2)  # Delay between requests

        # Summary
        print("\n" + "=" * 60)
        print("KẾT QUẢ API TEST")
        print("=" * 60)

        success = sum(1 for r in results if r["status"] == 200)
        blocked = sum(1 for r in results if r["status"] == 403)

        print(f"\n  ✅ Thành công: {success}")
        print(f"  ⚠️ Blocked (403): {blocked}")

        if success > 0:
            print("\n🎉 IPv6 ROTATION CÓ THỂ BYPASS 403!")
            print("   → Tích hợp vào tool với ipv6_rotate_proxy.py")
        elif blocked == len(results):
            print("\n❌ TẤT CẢ ĐỀU BỊ 403")
            print("   → reCAPTCHA token có thể đã hết hạn")
            print("   → Hoặc Google block theo token, không phải IP")


if __name__ == "__main__":
    main()
