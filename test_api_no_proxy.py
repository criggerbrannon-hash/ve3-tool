#!/usr/bin/env python3
"""
VE3 Tool - Test API Mode WITHOUT Proxy (No nanoai.pics)
========================================================
Script này test việc gọi API trực tiếp bằng cách:
1. Capture headers (x-browser-validation) từ Chrome
2. Gọi Google Flow API với headers đó
3. Không cần proxy, không cần giải captcha!

Yêu cầu:
- Chrome đã cài đặt
- Đã đăng nhập Google trong Chrome
- Selenium + ChromeDriver

Usage:
    python test_api_no_proxy.py
    python test_api_no_proxy.py --profile "path/to/chrome/profile"
    python test_api_no_proxy.py --headless  # Chạy ẩn (sau khi đã test thành công)
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.chrome_headers_extractor import ChromeHeadersExtractor, CapturedHeaders
from modules.google_flow_api import GoogleFlowAPI, AspectRatio


# =============================================================================
# CONFIGURATION
# =============================================================================
TEST_PROMPT = "A cute orange cat sitting on a wooden table, studio lighting, 4k photography"
OUTPUT_DIR = Path("./test_output")


def print_header(text: str):
    """Print formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_step(step: int, text: str):
    """Print step."""
    print(f"\n[STEP {step}] {text}")
    print("-" * 50)


def print_result(success: bool, message: str):
    """Print result."""
    icon = "✅" if success else "❌"
    print(f"\n{icon} {message}")


# =============================================================================
# STEP 1: CAPTURE HEADERS FROM CHROME
# =============================================================================
def capture_headers_from_chrome(
    profile_path: str = None,
    profile_directory: str = None,
    headless: bool = False
) -> CapturedHeaders:
    """
    Mở Chrome, trigger API request, capture headers.

    Args:
        profile_path: Path to Chrome User Data folder
        profile_directory: Profile folder name (e.g., "Profile 2")
        headless: Chạy ẩn (không hiện cửa sổ Chrome)

    Returns:
        CapturedHeaders object
    """
    print_step(1, "CAPTURE HEADERS FROM CHROME")

    # Find default Chrome profile if not specified
    if not profile_path:
        # Common Chrome User Data locations
        possible_paths = [
            Path.home() / "AppData/Local/Google/Chrome/User Data",  # Windows
            Path.home() / ".config/google-chrome",  # Linux
            Path.home() / "Library/Application Support/Google/Chrome",  # macOS
        ]
        for p in possible_paths:
            if p.exists():
                profile_path = str(p)
                print(f"Found Chrome User Data: {profile_path}")
                break

    if profile_path:
        print(f"User Data Dir: {profile_path}")
        if profile_directory:
            print(f"Profile Directory: {profile_directory}")
        else:
            print("Profile Directory: Default")
    else:
        print("No profile specified, Chrome will use temporary profile")
        print("⚠️  You may need to login to Google manually!")

    print("\n⚠️  QUAN TRỌNG: Đóng tất cả cửa sổ Chrome trước khi chạy!")
    print("   (Script cần dùng profile đang có, Chrome không thể mở 2 lần cùng profile)")

    # Create extractor
    extractor = ChromeHeadersExtractor(
        chrome_profile_path=profile_path,
        profile_directory=profile_directory,
        headless=headless,
        verbose=True
    )

    try:
        # Start browser
        print("\n📂 Starting Chrome browser...")
        if not extractor.start_browser():
            print("❌ Failed to start Chrome")
            return CapturedHeaders()

        # Navigate to Flow
        print("\n🌐 Navigating to Google Flow...")
        if not extractor.navigate_to_flow():
            print("❌ Failed to navigate")
            return CapturedHeaders()

        # Wait for page to fully load
        print("\n⏳ Waiting for page load (5s)...")
        time.sleep(5)

        # Check if logged in
        print("\n🔍 Checking login status...")
        try:
            # Look for textarea (indicates logged in and ready)
            textarea = extractor.driver.find_elements("css selector", "textarea")
            if textarea:
                print("✅ Logged in and ready!")
            else:
                print("⚠️  May not be logged in. Please check browser window.")
                if not headless:
                    print("   Waiting 30s for you to login...")
                    time.sleep(30)
        except Exception as e:
            print(f"Login check error: {e}")

        # Trigger API and capture headers
        print("\n🎯 Triggering API request to capture headers...")
        print("   This will create a test image in Google Flow")

        headers = extractor.trigger_api_and_capture()

        if headers.is_valid():
            print("\n✅ Headers captured successfully!")
            print(f"   Authorization: {headers.authorization[:50]}...")
            print(f"   x-browser-validation: {headers.x_browser_validation[:50]}...")
            return headers
        else:
            # Try fallback method
            print("\n⚠️  First method failed, trying network logs...")
            headers = extractor.capture_headers_from_network(timeout=30)

            if headers.is_valid():
                print("\n✅ Headers captured from network logs!")
                return headers
            else:
                print("\n❌ Failed to capture headers")
                print(f"   Has Authorization: {bool(headers.authorization)}")
                print(f"   Has x-browser-validation: {bool(headers.x_browser_validation)}")
                return headers

    finally:
        print("\n🔒 Closing browser...")
        extractor.stop_browser()


# =============================================================================
# STEP 2: TEST DIRECT API CALL
# =============================================================================
def test_direct_api_call(headers: CapturedHeaders) -> bool:
    """
    Test gọi API trực tiếp với headers đã capture.

    Args:
        headers: CapturedHeaders từ Chrome

    Returns:
        True nếu thành công
    """
    print_step(2, "TEST DIRECT API CALL (NO PROXY)")

    if not headers.is_valid():
        print("❌ Invalid headers - cannot test API")
        return False

    # Extract bearer token from Authorization header
    auth = headers.authorization
    if auth.startswith("Bearer "):
        bearer_token = auth[7:]
    else:
        bearer_token = auth

    print(f"Bearer token: {bearer_token[:30]}...{bearer_token[-10:]}")

    # Create output dir
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create API client with extra_headers (x-browser-validation, etc.)
    extra_headers = {
        "x-browser-validation": headers.x_browser_validation,
        "x-browser-channel": headers.x_browser_channel or "stable",
        "x-browser-copyright": headers.x_browser_copyright or "Copyright 2025 Google LLC. All Rights reserved.",
        "x-browser-year": headers.x_browser_year or "2025",
    }
    if headers.x_client_data:
        extra_headers["x-client-data"] = headers.x_client_data

    print("\n📋 Extra headers to send:")
    for k, v in extra_headers.items():
        v_preview = v[:40] + "..." if len(v) > 40 else v
        print(f"   {k}: {v_preview}")

    # Create API client
    api = GoogleFlowAPI(
        bearer_token=bearer_token,
        verbose=True,
        use_proxy=False,  # ← KHÔNG DÙNG PROXY!
        extra_headers=extra_headers
    )

    print(f"\n🎨 Generating image with prompt:")
    print(f"   \"{TEST_PROMPT[:60]}...\"")
    print(f"\n⏳ Calling Google Flow API directly...")

    # Generate image
    success, images, error = api.generate_images(
        prompt=TEST_PROMPT,
        count=1,
        aspect_ratio=AspectRatio.LANDSCAPE
    )

    if success and images:
        print(f"\n✅ API call successful! Got {len(images)} image(s)")

        # Download image
        for i, img in enumerate(images):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_no_proxy_{timestamp}_{i+1}"

            path = api.download_image(img, OUTPUT_DIR, filename)
            if path:
                print(f"   📁 Saved: {path}")
                print(f"   🌐 URL: {img.url[:60]}..." if img.url else "")
                print(f"   🎲 Seed: {img.seed}")

        return True
    else:
        print(f"\n❌ API call failed!")
        print(f"   Error: {error}")

        # Check if captcha error
        if "captcha" in error.lower() or "403" in error:
            print("\n⚠️  Có thể x-browser-validation đã hết hạn hoặc không hợp lệ")
            print("   Thử chạy lại script để capture headers mới")

        return False


# =============================================================================
# STEP 3: COMPARE WITH PROXY MODE
# =============================================================================
def show_comparison():
    """Show comparison between proxy and no-proxy modes."""
    print_step(3, "COMPARISON: PROXY vs NO-PROXY")

    print("""
┌─────────────────────────────────────────────────────────────────────┐
│                    SO SÁNH 2 PHƯƠNG PHÁP                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  PROXY MODE (nanoai.pics):                                         │
│  ─────────────────────────                                         │
│  ✓ Không cần Chrome                                                │
│  ✓ Đơn giản, chỉ cần token                                        │
│  ✗ Phụ thuộc vào service bên thứ 3                                │
│  ✗ Có thể mất phí                                                  │
│  ✗ Dữ liệu đi qua server khác                                     │
│                                                                     │
│  NO-PROXY MODE (x-browser-validation):                             │
│  ──────────────────────────────────────                            │
│  ✓ Miễn phí 100%                                                   │
│  ✓ Không phụ thuộc bên thứ 3                                      │
│  ✓ Dữ liệu đi thẳng tới Google                                    │
│  ✗ Cần Chrome + profile đã đăng nhập                              │
│  ✗ Headers có thể hết hạn (cần refresh)                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
    """)


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Test API without proxy (using x-browser-validation)"
    )
    parser.add_argument(
        "--profile", "-p",
        help="Path to Chrome User Data folder (e.g., C:\\Users\\admin\\AppData\\Local\\Google\\Chrome\\User Data)"
    )
    parser.add_argument(
        "--profile-dir", "-d",
        help="Chrome profile directory name (e.g., 'Profile 2', 'Default')"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode"
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip header capture (use cached headers)"
    )

    args = parser.parse_args()

    print_header("VE3 TOOL - TEST API WITHOUT PROXY")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output dir: {OUTPUT_DIR.absolute()}")

    # Check dependencies
    print("\n📦 Checking dependencies...")
    try:
        from selenium import webdriver
        print("   ✅ Selenium installed")
    except ImportError:
        print("   ❌ Selenium not installed!")
        print("   Run: pip install selenium")
        return 1

    try:
        import requests
        print("   ✅ Requests installed")
    except ImportError:
        print("   ❌ Requests not installed!")
        return 1

    # Step 1: Capture headers
    headers = capture_headers_from_chrome(
        profile_path=args.profile,
        profile_directory=getattr(args, 'profile_dir', None),
        headless=args.headless
    )

    if not headers.is_valid():
        print_result(False, "Failed to capture headers from Chrome")
        print("\n💡 Tips:")
        print("   1. Make sure you're logged into Google in Chrome")
        print("   2. Try running without --headless first")
        print("   3. Specify --profile path to your Chrome profile")
        return 1

    # Step 2: Test API
    success = test_direct_api_call(headers)

    # Step 3: Show comparison
    show_comparison()

    # Final result
    print_header("FINAL RESULT")

    if success:
        print_result(True, "API WITHOUT PROXY WORKS!")
        print("""
🎉 Kết luận:
   - Bạn CÓ THỂ gọi API trực tiếp mà không cần nanoai.pics
   - Chỉ cần capture x-browser-validation từ Chrome
   - Headers được lưu trong CapturedHeaders object

📝 Để tích hợp vào code chính:
   1. Capture headers 1 lần khi bắt đầu session
   2. Truyền extra_headers vào GoogleFlowAPI
   3. Set use_proxy=False
   4. Refresh headers nếu bị 403/captcha error
        """)
        return 0
    else:
        print_result(False, "API call failed")
        print("""
⚠️  Có thể do:
   1. x-browser-validation đã hết hạn
   2. Chưa đăng nhập Google trong Chrome
   3. Account Google bị rate limit

💡 Giải pháp:
   - Thử chạy lại script
   - Đảm bảo đã đăng nhập Google
   - Đợi vài phút nếu bị rate limit
        """)
        return 1


if __name__ == "__main__":
    sys.exit(main())
