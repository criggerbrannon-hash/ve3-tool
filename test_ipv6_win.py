#!/usr/bin/env python3
"""
Test IPv6 Rotation - Windows Version
====================================
Test xem đổi IPv6 có bypass được 403 không.

Yêu cầu:
- Windows với IPv6 subnet được assign từ ISP
- Chạy CMD/PowerShell với quyền Administrator

Usage:
    python test_ipv6_win.py
"""

import socket
import subprocess
import time
import sys
import ctypes

# === CẤU HÌNH ===
# Thay đổi theo subnet của bạn
IPV6_PREFIX = "2001:ee0:b004:1f01"  # /64 prefix
INTERFACE_NAME = "Ethernet"  # Tên adapter (dùng `ipconfig` để xem)

# Test URL
TEST_URL = "https://www.google.com"


def is_admin():
    """Kiểm tra có quyền Admin không"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def get_ipv6_address(suffix: int) -> str:
    """Tạo IPv6 address từ prefix + suffix"""
    return f"{IPV6_PREFIX}::{suffix}"


def add_ipv6_windows(ipv6: str, interface: str = INTERFACE_NAME) -> bool:
    """Thêm IPv6 vào network adapter trên Windows"""
    try:
        cmd = f'netsh interface ipv6 add address "{interface}" {ipv6}'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0 or "already" in result.stderr.lower():
            print(f"  ✓ Added {ipv6}")
            return True
        else:
            print(f"  ✗ Failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def remove_ipv6_windows(ipv6: str, interface: str = INTERFACE_NAME) -> bool:
    """Xóa IPv6 khỏi network adapter"""
    try:
        cmd = f'netsh interface ipv6 delete address "{interface}" {ipv6}'
        subprocess.run(cmd, shell=True, capture_output=True)
        return True
    except:
        return False


def test_connection_with_ipv6(ipv6: str) -> dict:
    """
    Test kết nối với IPv6 cụ thể bằng curl.
    """
    result = {
        "ipv6": ipv6,
        "status": None,
        "error": None,
        "time": 0
    }

    try:
        # Dùng curl với --interface để bind IPv6
        # Cần cài curl trên Windows (có sẵn từ Win10 1803+)
        start = time.time()
        cmd = [
            "curl", "-6", "-s", "-o", "NUL",
            "-w", "%{http_code}",
            "--interface", ipv6,
            "--connect-timeout", "10",
            "--max-time", "15",
            TEST_URL
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        elapsed = time.time() - start

        if proc.returncode == 0 and proc.stdout.strip().isdigit():
            result["status"] = int(proc.stdout.strip())
        else:
            result["error"] = proc.stderr or f"Exit code: {proc.returncode}"

        result["time"] = elapsed

    except FileNotFoundError:
        result["error"] = "curl not found - cài curl hoặc dùng Win10+"
    except subprocess.TimeoutExpired:
        result["error"] = "Timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def test_with_powershell(ipv6: str) -> dict:
    """Test bằng PowerShell (backup method)"""
    result = {
        "ipv6": ipv6,
        "status": None,
        "error": None,
        "time": 0
    }

    try:
        # PowerShell script để test
        ps_script = f'''
$tcpClient = New-Object System.Net.Sockets.TcpClient
$localEndPoint = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse("{ipv6}"), 0)
$tcpClient.Client.Bind($localEndPoint)
try {{
    $tcpClient.Connect("www.google.com", 443)
    Write-Output "OK"
}} catch {{
    Write-Output "FAIL: $_"
}} finally {{
    $tcpClient.Close()
}}
'''
        start = time.time()
        proc = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=15
        )
        elapsed = time.time() - start

        output = proc.stdout.strip()
        if "OK" in output:
            result["status"] = 200  # Connected successfully
        else:
            result["error"] = output

        result["time"] = elapsed

    except Exception as e:
        result["error"] = str(e)

    return result


def list_current_ipv6():
    """Liệt kê IPv6 addresses hiện tại"""
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-NetIPAddress -AddressFamily IPv6 | Select-Object IPAddress,InterfaceAlias | Format-Table -AutoSize"],
            capture_output=True, text=True
        )
        print(result.stdout)
    except Exception as e:
        print(f"Error: {e}")


def main():
    print("=" * 60)
    print("IPv6 ROTATION TEST - Windows")
    print("=" * 60)

    # Check admin
    if not is_admin():
        print("\n⚠ CẦN CHẠY VỚI QUYỀN ADMINISTRATOR!")
        print("  Right-click CMD/PowerShell → Run as Administrator")
        print("\n  Hoặc test thủ công:")
        print(f'  1. netsh interface ipv6 add address "{INTERFACE_NAME}" {IPV6_PREFIX}::3')
        print(f'  2. curl -6 --interface {IPV6_PREFIX}::3 https://www.google.com')
        sys.exit(1)

    print(f"\nIPv6 Prefix: {IPV6_PREFIX}::/64")
    print(f"Interface: {INTERFACE_NAME}")

    # Hiển thị IPv6 hiện tại
    print("\n[1] IPv6 addresses hiện tại:")
    list_current_ipv6()

    # Test với các suffix khác nhau
    print("\n[2] Test IPv6 rotation...")
    suffixes = [2, 3, 4, 5, 10]
    results = []

    for suffix in suffixes:
        ipv6 = get_ipv6_address(suffix)
        print(f"\n  → Testing {ipv6}")

        # Add IPv6
        if not add_ipv6_windows(ipv6):
            continue

        time.sleep(1)  # Đợi Windows cập nhật

        # Test connection
        result = test_connection_with_ipv6(ipv6)
        results.append(result)

        if result["status"]:
            icon = "✓" if result["status"] == 200 else "⚠"
            print(f"    {icon} HTTP {result['status']} ({result['time']:.2f}s)")
        else:
            print(f"    ✗ {result['error']}")

        time.sleep(2)  # Delay giữa các tests

    # Summary
    print("\n" + "=" * 60)
    print("KẾT QUẢ")
    print("=" * 60)

    success = sum(1 for r in results if r["status"] == 200)
    blocked = sum(1 for r in results if r["status"] == 403)
    errors = sum(1 for r in results if r["error"])

    print(f"\n  ✓ Thành công (200): {success}")
    print(f"  ⚠ Bị block (403):  {blocked}")
    print(f"  ✗ Lỗi:             {errors}")

    print("\nChi tiết:")
    for r in results:
        status = r["status"] or r["error"]
        print(f"  {r['ipv6']} → {status}")

    print("\n" + "=" * 60)

    if success > 0:
        print("✓ IPv6 ROTATION CÓ THỂ HOẠT ĐỘNG!")
        print("  → Có thể tích hợp vào tool để bypass 403")
    elif blocked > 0 and success == 0:
        print("⚠ TẤT CẢ ĐỀU BỊ 403")
        print("  → Google có thể đang block cả subnet")
        print("  → Hoặc cần đổi sang /64 khác")
    else:
        print("✗ KHÔNG THỂ KẾT NỐI")
        print("  Kiểm tra:")
        print("  - IPv6 có được ISP cấp không?")
        print("  - Interface name có đúng không?")
        print("  - Firewall có block không?")


if __name__ == "__main__":
    main()
