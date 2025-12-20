#!/usr/bin/env python3
"""
Test thủ công: Mở Chrome, user tạo ảnh, capture headers.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from modules.chrome_headers_extractor import ChromeHeadersExtractor

def main():
    print("=" * 60)
    print("TEST THỦ CÔNG - CAPTURE HEADERS")
    print("=" * 60)

    # Tìm profile
    profile_dir = Path("chrome_profiles/main")
    if not profile_dir.exists():
        profile_dir = Path("chrome_profiles/Profile 2")

    print(f"Profile: {profile_dir}")

    # Khởi động Chrome
    extractor = ChromeHeadersExtractor(
        chrome_profile_path=str(profile_dir),
        headless=False,
        verbose=True
    )

    print("\n[1] Đang mở Chrome...")
    if not extractor.start_browser():
        print("❌ Không mở được Chrome!")
        return

    print("\n[2] Navigate đến Flow...")
    if not extractor.navigate_to_flow():
        print("❌ Không navigate được!")
        extractor.stop_browser()
        return

    print("\n" + "=" * 60)
    print("👉 BÂY GIỜ BẠN HÃY:")
    print("   1. Tạo project mới (nếu cần)")
    print("   2. Nhập prompt bất kỳ")
    print("   3. Click 'Tạo' để tạo ảnh")
    print("   4. Đợi ảnh tạo xong")
    print("=" * 60)
    input("\n>>> Nhấn ENTER sau khi tạo ảnh xong...")

    print("\n[3] Đang capture headers từ network logs...")
    headers = extractor.capture_headers_from_network(timeout=5)

    print("\n" + "=" * 60)
    print("KẾT QUẢ CAPTURE:")
    print("=" * 60)
    print(f"Authorization: {headers.authorization[:50]}..." if headers.authorization else "Authorization: ❌ KHÔNG CÓ")
    print(f"x-browser-validation: {headers.x_browser_validation[:50]}..." if headers.x_browser_validation else "x-browser-validation: ❌ KHÔNG CÓ")
    print(f"x-browser-channel: {headers.x_browser_channel}" if headers.x_browser_channel else "x-browser-channel: -")
    print(f"x-client-data: {headers.x_client_data[:30]}..." if headers.x_client_data else "x-client-data: -")

    if headers.is_valid():
        print("\n✅ HEADERS ĐẦY ĐỦ - CÓ THỂ GỌI API!")
    else:
        print("\n❌ THIẾU HEADERS - CẦN DEBUG THÊM")

    input("\n>>> Nhấn ENTER để đóng Chrome...")
    extractor.stop_browser()
    print("Done!")

if __name__ == "__main__":
    main()
