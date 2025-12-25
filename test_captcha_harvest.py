"""
Test reCAPTCHA v3 Token Harvester
=================================
Script để tìm và capture reCAPTCHA v3 token từ Google Flow.

Chạy: python test_captcha_harvest.py
"""

import time
import json
from pathlib import Path

# ============================================================================
# CẤU HÌNH - ĐIỀN VÀO ĐÂY
# ============================================================================

# Đường dẫn Chrome
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# Chrome profile đã login Google
CHROME_PROFILE = r"C:\Users\admin\AppData\Local\Google\Chrome\User Data\Profile 2"

# Site key (nếu đã biết, để trống nếu chưa - script sẽ tự tìm)
RECAPTCHA_SITE_KEY = ""

# Action name (nếu đã biết, để trống nếu chưa)
RECAPTCHA_ACTION = ""

# ============================================================================


def create_driver():
    """Tạo Chrome driver với profile."""
    try:
        import undetected_chromedriver as uc

        options = uc.ChromeOptions()

        # Parse profile path
        profile_path = Path(CHROME_PROFILE)
        if "User Data" in str(profile_path):
            # System Chrome profile
            user_data = str(profile_path.parent)
            profile_name = profile_path.name
            options.add_argument(f"--user-data-dir={user_data}")
            options.add_argument(f"--profile-directory={profile_name}")
        else:
            options.add_argument(f"--user-data-dir={CHROME_PROFILE}")

        options.binary_location = CHROME_PATH
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        driver = uc.Chrome(options=options, use_subprocess=True)
        return driver

    except ImportError:
        print("Cần cài undetected-chromedriver:")
        print("  pip install undetected-chromedriver")
        return None


def find_recaptcha_info(driver):
    """Tìm thông tin reCAPTCHA trên trang."""

    print("\n" + "="*60)
    print("BƯỚC 1: TÌM THÔNG TIN reCAPTCHA")
    print("="*60)

    # Script để tìm tất cả thông tin reCAPTCHA
    find_script = """
    const info = {
        siteKeys: [],
        grecaptchaExists: typeof grecaptcha !== 'undefined',
        grecaptchaEnterprise: typeof grecaptcha !== 'undefined' && typeof grecaptcha.enterprise !== 'undefined',
        scripts: [],
        elements: [],
        tokens: []
    };

    // Tìm site key trong data attributes
    document.querySelectorAll('[data-sitekey]').forEach(el => {
        info.siteKeys.push(el.dataset.sitekey);
    });

    // Tìm trong scripts
    document.querySelectorAll('script').forEach(script => {
        const src = script.src || '';
        const text = script.textContent || '';

        if (src.includes('recaptcha') || src.includes('grecaptcha')) {
            info.scripts.push(src);
        }

        // Tìm site key trong script content
        const keyMatch = text.match(/['\"]?(6L[a-zA-Z0-9_-]{38})['\"]?/g);
        if (keyMatch) {
            keyMatch.forEach(k => info.siteKeys.push(k.replace(/['"]/g, '')));
        }
    });

    // Tìm iframe recaptcha
    document.querySelectorAll('iframe').forEach(iframe => {
        const src = iframe.src || '';
        if (src.includes('recaptcha')) {
            info.elements.push(src);
            // Extract site key from iframe src
            const match = src.match(/[?&]k=([^&]+)/);
            if (match) info.siteKeys.push(match[1]);
        }
    });

    // Tìm grecaptcha response nếu có
    const responseEl = document.querySelector('#g-recaptcha-response, [name="g-recaptcha-response"]');
    if (responseEl && responseEl.value) {
        info.tokens.push(responseEl.value.substring(0, 50) + '...');
    }

    // Unique site keys
    info.siteKeys = [...new Set(info.siteKeys)];

    return info;
    """

    try:
        info = driver.execute_script(find_script)

        print(f"\n✓ grecaptcha object tồn tại: {info.get('grecaptchaExists', False)}")
        print(f"✓ grecaptcha.enterprise: {info.get('grecaptchaEnterprise', False)}")

        if info.get('siteKeys'):
            print(f"\n✓ Site Keys tìm thấy:")
            for key in info['siteKeys']:
                print(f"  → {key}")
        else:
            print("\n✗ Không tìm thấy site key tự động")

        if info.get('scripts'):
            print(f"\n✓ reCAPTCHA Scripts:")
            for s in info['scripts']:
                print(f"  → {s[:80]}...")

        if info.get('elements'):
            print(f"\n✓ reCAPTCHA iframes:")
            for e in info['elements']:
                print(f"  → {e[:80]}...")

        return info

    except Exception as e:
        print(f"✗ Lỗi khi tìm info: {e}")
        return {}


def try_execute_recaptcha(driver, site_key=None, action="generate"):
    """Thử execute reCAPTCHA để lấy token."""

    print("\n" + "="*60)
    print("BƯỚC 2: THỬ LẤY TOKEN")
    print("="*60)

    if not site_key:
        print("✗ Cần site key để execute. Hãy điền RECAPTCHA_SITE_KEY ở đầu file.")
        return None

    print(f"\nĐang thử execute với:")
    print(f"  Site Key: {site_key}")
    print(f"  Action: {action}")

    # Script để execute và lấy token
    execute_script = f"""
    return new Promise((resolve, reject) => {{
        if (typeof grecaptcha === 'undefined') {{
            reject('grecaptcha không tồn tại');
            return;
        }}

        // Thử grecaptcha.enterprise trước (Google thường dùng enterprise)
        const recaptcha = grecaptcha.enterprise || grecaptcha;

        recaptcha.ready(() => {{
            recaptcha.execute('{site_key}', {{action: '{action}'}})
                .then(token => {{
                    resolve({{
                        success: true,
                        token: token,
                        length: token.length
                    }});
                }})
                .catch(err => {{
                    reject(err.toString());
                }});
        }});
    }});
    """

    try:
        result = driver.execute_script(execute_script)

        if result and result.get('success'):
            token = result.get('token', '')
            print(f"\n✓ LẤY TOKEN THÀNH CÔNG!")
            print(f"  Token length: {len(token)}")
            print(f"  Token preview: {token[:50]}...{token[-20:]}")
            return token
        else:
            print(f"✗ Không lấy được token: {result}")
            return None

    except Exception as e:
        print(f"✗ Lỗi execute: {e}")
        return None


def intercept_network_requests(driver):
    """Inject script để intercept các request có chứa captcha token."""

    print("\n" + "="*60)
    print("BƯỚC 3: INTERCEPT NETWORK REQUESTS")
    print("="*60)
    print("Đang inject script để capture token từ requests...")

    intercept_script = """
    window.__captcha_tokens__ = [];
    window.__captcha_requests__ = [];

    // Intercept fetch
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const [url, options] = args;

        // Log request
        const reqInfo = {
            url: typeof url === 'string' ? url : url.url,
            method: options?.method || 'GET',
            timestamp: Date.now()
        };

        // Check headers for captcha token
        const headers = options?.headers || {};
        for (const [key, value] of Object.entries(headers)) {
            if (key.toLowerCase().includes('captcha') ||
                key.toLowerCase().includes('recaptcha') ||
                key.toLowerCase().includes('token')) {
                reqInfo.captchaHeader = {key, value: value.substring(0, 50) + '...'};
                window.__captcha_tokens__.push({
                    type: 'header',
                    key: key,
                    value: value,
                    url: reqInfo.url
                });
            }
        }

        // Check body for captcha token
        if (options?.body) {
            const bodyStr = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
            if (bodyStr.includes('captcha') || bodyStr.includes('recaptcha') || bodyStr.includes('token')) {
                reqInfo.hasCaptchaInBody = true;

                // Try to extract token
                try {
                    const bodyObj = JSON.parse(bodyStr);
                    const findToken = (obj, path = '') => {
                        for (const [k, v] of Object.entries(obj)) {
                            if (typeof v === 'string' && v.length > 100 && v.length < 2000) {
                                window.__captcha_tokens__.push({
                                    type: 'body',
                                    key: path + k,
                                    value: v,
                                    url: reqInfo.url
                                });
                            } else if (typeof v === 'object' && v !== null) {
                                findToken(v, path + k + '.');
                            }
                        }
                    };
                    findToken(bodyObj);
                } catch(e) {}
            }
        }

        if (reqInfo.captchaHeader || reqInfo.hasCaptchaInBody) {
            window.__captcha_requests__.push(reqInfo);
        }

        return originalFetch.apply(this, args);
    };

    // Intercept XMLHttpRequest
    const originalXHROpen = XMLHttpRequest.prototype.open;
    const originalXHRSend = XMLHttpRequest.prototype.send;
    const originalXHRSetHeader = XMLHttpRequest.prototype.setRequestHeader;

    XMLHttpRequest.prototype.open = function(method, url) {
        this.__url__ = url;
        this.__method__ = method;
        this.__headers__ = {};
        return originalXHROpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
        this.__headers__[name] = value;

        if (name.toLowerCase().includes('captcha') ||
            name.toLowerCase().includes('recaptcha') ||
            name.toLowerCase().includes('token')) {
            window.__captcha_tokens__.push({
                type: 'xhr_header',
                key: name,
                value: value,
                url: this.__url__
            });
        }

        return originalXHRSetHeader.apply(this, arguments);
    };

    console.log('[Captcha Interceptor] Đã inject thành công!');
    return true;
    """

    try:
        driver.execute_script(intercept_script)
        print("✓ Đã inject interceptor")
        print("\nBây giờ hãy thử TẠO ẢNH trên trang Google Flow...")
        print("Script sẽ capture các request có chứa captcha token.")
        return True
    except Exception as e:
        print(f"✗ Lỗi inject: {e}")
        return False


def get_captured_tokens(driver):
    """Lấy các token đã capture được."""

    print("\n" + "="*60)
    print("BƯỚC 4: XEM TOKEN ĐÃ CAPTURE")
    print("="*60)

    try:
        tokens = driver.execute_script("return window.__captcha_tokens__ || [];")
        requests = driver.execute_script("return window.__captcha_requests__ || [];")

        if tokens:
            print(f"\n✓ Đã capture {len(tokens)} token(s):")
            for i, t in enumerate(tokens):
                print(f"\n  [{i+1}] Type: {t.get('type')}")
                print(f"      Key: {t.get('key')}")
                print(f"      URL: {t.get('url', '')[:60]}...")
                value = t.get('value', '')
                print(f"      Value: {value[:50]}...{value[-20:] if len(value) > 70 else ''}")
        else:
            print("\n✗ Chưa capture được token nào")
            print("  → Hãy thử tạo ảnh trên trang Flow")

        if requests:
            print(f"\n✓ Requests có captcha: {len(requests)}")
            for r in requests:
                print(f"  → {r.get('method')} {r.get('url', '')[:60]}...")

        return tokens

    except Exception as e:
        print(f"✗ Lỗi lấy tokens: {e}")
        return []


def main():
    print("="*60)
    print("reCAPTCHA v3 TOKEN HARVESTER - TEST")
    print("="*60)

    # Tạo driver
    print("\nĐang mở Chrome...")
    driver = create_driver()

    if not driver:
        return

    try:
        # Vào Google Flow
        print("Đang vào Google Flow...")
        driver.get("https://labs.google/fx/tools/flow")
        time.sleep(5)

        # Kiểm tra đã login chưa
        if "accounts.google.com" in driver.current_url:
            print("\n⚠️  Cần đăng nhập Google!")
            print("Vui lòng đăng nhập trong cửa sổ Chrome...")
            input("Nhấn Enter sau khi đã đăng nhập...")
            time.sleep(3)

        # Tìm thông tin reCAPTCHA
        info = find_recaptcha_info(driver)

        # Inject interceptor
        intercept_network_requests(driver)

        # Thử execute nếu có site key
        site_key = RECAPTCHA_SITE_KEY or (info.get('siteKeys', [None])[0] if info.get('siteKeys') else None)
        action = RECAPTCHA_ACTION or "generate"

        if site_key:
            token = try_execute_recaptcha(driver, site_key, action)
            if token:
                print("\n" + "="*60)
                print("✓ THÀNH CÔNG! Có thể lấy token tự động!")
                print("="*60)

        # Chờ user thao tác
        print("\n" + "="*60)
        print("HƯỚNG DẪN TIẾP THEO")
        print("="*60)
        print("""
1. Trên trang Google Flow, thử TẠO MỘT ẢNH
2. Quay lại đây nhấn Enter để xem token đã capture
3. Nhấn 'q' + Enter để thoát
        """)

        while True:
            cmd = input("\nNhấn Enter để xem captured tokens (q để thoát): ").strip().lower()

            if cmd == 'q':
                break

            get_captured_tokens(driver)

            # Thử lấy token mới
            if site_key:
                print("\nThử lấy token mới...")
                try_execute_recaptcha(driver, site_key, action)

    except Exception as e:
        print(f"\n✗ Lỗi: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\nĐang đóng Chrome...")
        try:
            driver.quit()
        except:
            pass
        print("Done!")


if __name__ == "__main__":
    main()
