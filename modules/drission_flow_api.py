#!/usr/bin/env python3
"""
VE3 Tool - DrissionPage Flow API
================================
Gọi Google Flow API trực tiếp bằng DrissionPage.

Flow:
1. Tự động khởi động IPv6 proxy server (nếu use_proxy=True)
2. Mở Chrome với proxy → Vào Google Flow → Đợi user chọn project
3. Inject JS Interceptor để capture tokens + CANCEL request
4. Gọi API trực tiếp với captured URL + payload
"""

import json
import time
import random
import base64
import requests
import threading
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime

# Optional DrissionPage import
DRISSION_AVAILABLE = False
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_AVAILABLE = True
except ImportError:
    ChromiumPage = None
    ChromiumOptions = None

# IPv6 Proxy imports
PROXY_AVAILABLE = False
try:
    from ipv6_rotate_proxy import IPv6Rotator, ProxyServer, IPV6_LIST, PROXY_PORT
    PROXY_AVAILABLE = True
except ImportError:
    IPv6Rotator = None
    ProxyServer = None
    IPV6_LIST = []
    PROXY_PORT = 1080


@dataclass
class GeneratedImage:
    """Kết quả ảnh được tạo."""
    url: str = ""
    base64_data: Optional[str] = None
    seed: Optional[int] = None
    media_name: Optional[str] = None
    local_path: Optional[Path] = None


# JS Interceptor - Capture tokens và CANCEL request
# Giống batch_generator.py - đã test hoạt động
JS_INTERCEPTOR = '''
window._tk=null;window._pj=null;window._xbv=null;window._rct=null;window._payload=null;window._sid=null;window._url=null;
(function(){
    if(window.__interceptReady) return 'ALREADY_READY';
    window.__interceptReady = true;

    var orig = window.fetch;
    window.fetch = function(url, opts) {
        var urlStr = typeof url === 'string' ? url : url.url;

        // Match nhiều pattern hơn
        if (urlStr.includes('aisandbox') && (urlStr.includes('batchGenerate') || urlStr.includes('flowMedia') || urlStr.includes('generateContent'))) {
            console.log('[INTERCEPT] Capturing request to:', urlStr);

            // Capture URL gốc
            window._url = urlStr;

            // Extract projectId from URL: /v1/projects/{projectId}/flowMedia:batchGenerateImages
            var match = urlStr.match(/\\/projects\\/([a-f0-9\\-]+)/i);
            if (match && match[1]) {
                window._pj = match[1];
                console.log('[TOKEN] projectId from URL:', window._pj);
            } else {
                console.log('[TOKEN] projectId NOT FOUND in URL:', urlStr);
            }

            // Capture từ headers
            if (opts && opts.headers) {
                var h = opts.headers;
                if (h['Authorization']) {
                    window._tk = h['Authorization'].replace('Bearer ', '');
                    console.log('[TOKEN] Bearer captured!');
                }
                if (h['x-browser-validation']) {
                    window._xbv = h['x-browser-validation'];
                    console.log('[TOKEN] x-browser-validation captured!');
                }
            }

            // Capture payload và recaptchaToken
            if (opts && opts.body) {
                window._payload = opts.body;
                try {
                    var body = JSON.parse(opts.body);
                    // sessionId from clientContext
                    if (body.clientContext) {
                        window._sid = body.clientContext.sessionId;
                        // Fallback projectId from body if not in URL
                        if (!window._pj && body.clientContext.projectId) {
                            window._pj = body.clientContext.projectId;
                        }
                    }
                    // recaptchaToken có thể ở root hoặc trong requests[0]
                    if (body.recaptchaToken) {
                        window._rct = body.recaptchaToken;
                        console.log('[TOKEN] recaptchaToken captured (root)!');
                    } else if (body.requests && body.requests[0] && body.requests[0].clientContext && body.requests[0].clientContext.recaptchaToken) {
                        window._rct = body.requests[0].clientContext.recaptchaToken;
                        console.log('[TOKEN] recaptchaToken captured (requests[0])!');
                    }
                } catch(e) {
                    console.log('[ERROR] Parse body failed:', e);
                }
            }

            // CANCEL request - return fake response
            console.log('[INTERCEPT] Request cancelled, tokens captured!');
            return Promise.resolve(new Response(JSON.stringify({cancelled:true})));
        }

        return orig.apply(this, arguments);
    };
    console.log('[INTERCEPTOR] Ready - will capture batchGenerateImages requests');
    return 'READY';
})();
'''

# JS để click "Dự án mới"
JS_CLICK_NEW_PROJECT = '''
(function() {
    var btns = document.querySelectorAll('button');
    for (var b of btns) {
        var text = b.textContent || '';
        if (text.includes('Dự án mới') || text.includes('New project')) {
            b.click();
            console.log('[AUTO] Clicked: Du an moi');
            return 'CLICKED';
        }
    }
    return 'NOT_FOUND';
})();
'''

# JS để chọn "Tạo hình ảnh" từ dropdown
JS_SELECT_IMAGE_MODE = '''
(async function() {
    // 1. Click dropdown
    var dropdown = document.querySelector('button[role="combobox"]');
    if (!dropdown) {
        console.log('[AUTO] Dropdown not found');
        return 'NO_DROPDOWN';
    }
    dropdown.click();
    console.log('[AUTO] Clicked dropdown');

    // 2. Đợi dropdown mở
    await new Promise(r => setTimeout(r, 500));

    // 3. Tìm và click "Tạo hình ảnh"
    var allElements = document.querySelectorAll('*');
    for (var el of allElements) {
        var text = el.textContent || '';
        if (text === 'Tạo hình ảnh' || text.includes('Tạo hình ảnh từ văn bản') ||
            text === 'Generate image' || text.includes('Generate image from text')) {
            var rect = el.getBoundingClientRect();
            if (rect.height > 10 && rect.height < 80 && rect.width > 50) {
                el.click();
                console.log('[AUTO] Clicked: Tao hinh anh');
                return 'CLICKED';
            }
        }
    }
    return 'NOT_FOUND';
})();
'''


class DrissionFlowAPI:
    """
    Google Flow API client sử dụng DrissionPage.

    Sử dụng:
    ```python
    api = DrissionFlowAPI(
        profile_dir="./chrome_profiles/main",
        proxy_port=1080  # SOCKS5 proxy
    )

    # Setup Chrome và đợi user chọn project
    if api.setup():
        # Generate ảnh
        success, images, error = api.generate_image("a cat playing piano")
    ```
    """

    BASE_URL = "https://aisandbox-pa.googleapis.com"
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        profile_dir: str = "./chrome_profile",
        chrome_port: int = 9333,
        proxy_port: int = 1080,
        use_proxy: bool = True,  # BẬT proxy - chạy ipv6_rotate_proxy.py trước
        verbose: bool = True,
        log_callback: Optional[Callable] = None
    ):
        """
        Khởi tạo DrissionFlowAPI.

        Args:
            profile_dir: Thư mục Chrome profile
            chrome_port: Port cho Chrome debugging
            proxy_port: Port của SOCKS5 proxy (IPv6)
            use_proxy: Có dùng proxy không (cần chạy ipv6_rotate_proxy.py)
            verbose: In log chi tiết
            log_callback: Callback để log (msg, level)
        """
        self.profile_dir = Path(profile_dir)
        self.chrome_port = chrome_port
        self.proxy_port = proxy_port
        self.use_proxy = use_proxy
        self.verbose = verbose
        self.log_callback = log_callback

        # Chrome/DrissionPage
        self.driver: Optional[ChromiumPage] = None

        # IPv6 Proxy server
        self._proxy_server = None
        self._proxy_started = False

        # Captured tokens
        self.bearer_token: Optional[str] = None
        self.project_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self.recaptcha_token: Optional[str] = None
        self.x_browser_validation: Optional[str] = None
        self.captured_url: Optional[str] = None
        self.captured_payload: Optional[str] = None

        # State
        self._ready = False

    def log(self, msg: str, level: str = "INFO"):
        """Log message."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [{level}] {msg}")
        if self.log_callback:
            self.log_callback(msg, level)

    def _start_proxy_server(self) -> bool:
        """Khởi động IPv6 proxy server tự động."""
        if not PROXY_AVAILABLE:
            self.log("⚠️ ipv6_rotate_proxy.py không tìm thấy!", "WARN")
            self.log("   Chạy: python ipv6_rotate_proxy.py trong terminal khác", "WARN")
            return False

        if self._proxy_started:
            return True

        try:
            self.log("Khởi động IPv6 Proxy Server...")
            rotator = IPv6Rotator(IPV6_LIST)
            self._proxy_server = ProxyServer(rotator)
            self._proxy_server.start()
            self._proxy_started = True
            time.sleep(0.5)  # Đợi server start
            self.log(f"✓ Proxy server running on 127.0.0.1:{PROXY_PORT}")
            self.log(f"  → {len(rotator.ipv6_list)} IPv6 addresses available")
            return True
        except Exception as e:
            self.log(f"✗ Không khởi động được proxy: {e}", "ERROR")
            self.log("  → Kiểm tra đã chạy add_ipv6.bat chưa?", "WARN")
            return False

    def _auto_setup_project(self, timeout: int = 60) -> bool:
        """
        Tự động setup project:
        1. Click "Dự án mới" (New project)
        2. Chọn "Tạo hình ảnh" (Generate image)
        3. Đợi vào project

        Args:
            timeout: Timeout tổng (giây)

        Returns:
            True nếu thành công
        """
        self.log("→ Đang tự động tạo dự án mới...")

        # 1. Đợi trang load và tìm button "Dự án mới"
        for i in range(15):
            result = self.driver.run_js(JS_CLICK_NEW_PROJECT)
            if result == 'CLICKED':
                self.log("✓ Clicked 'Dự án mới'")
                time.sleep(2)
                break
            time.sleep(1)
            if i == 5:
                self.log("  ... đợi button 'Dự án mới' xuất hiện...")
        else:
            self.log("✗ Không tìm thấy button 'Dự án mới'", "ERROR")
            self.log("→ Hãy click thủ công vào dự án", "WARN")
            # Fallback: đợi user click thủ công
            return self._wait_for_project_manual(timeout)

        # 2. Chọn "Tạo hình ảnh" từ dropdown
        time.sleep(1)
        for i in range(10):
            result = self.driver.run_js(JS_SELECT_IMAGE_MODE)
            if result == 'CLICKED':
                self.log("✓ Chọn 'Tạo hình ảnh'")
                time.sleep(2)
                break
            time.sleep(0.5)
        else:
            self.log("⚠️ Không tìm thấy dropdown - có thể đã ở mode đúng", "WARN")

        # 3. Đợi vào project
        self.log("→ Đợi vào project...")
        for i in range(timeout):
            current_url = self.driver.url
            if "/project/" in current_url:
                self.log(f"✓ Đã vào dự án!")
                return True
            time.sleep(1)
            if i % 10 == 9:
                self.log(f"  ... đợi {i+1}s")

        self.log("✗ Timeout - chưa vào được dự án", "ERROR")
        return False

    def _wait_for_project_manual(self, timeout: int = 60) -> bool:
        """Fallback: đợi user chọn project thủ công."""
        self.log("Đợi chọn dự án thủ công...")
        self.log("→ Click vào dự án có sẵn hoặc tạo dự án mới")

        for i in range(timeout):
            current_url = self.driver.url
            if "/project/" in current_url:
                self.log(f"✓ Đã vào dự án!")
                return True
            time.sleep(1)
            if i % 15 == 14:
                self.log(f"... đợi {i+1}s - hãy click chọn dự án")

        self.log("✗ Timeout - chưa chọn dự án", "ERROR")
        return False

    def _warm_up_session(self, dummy_prompt: str = "a simple test image") -> bool:
        """
        Warm up session bằng cách tạo 1 ảnh thật trong Chrome.
        Điều này "activate" session và làm cho tokens hợp lệ.

        Args:
            dummy_prompt: Prompt đơn giản để warm up

        Returns:
            True nếu thành công
        """
        self.log("=" * 50)
        self.log("  WARM UP SESSION")
        self.log("=" * 50)
        self.log("→ Tạo 1 ảnh trong Chrome để activate session...")
        self.log(f"  Prompt: {dummy_prompt[:50]}...")

        # Tìm textarea và gửi prompt
        textarea = self._find_textarea()
        if not textarea:
            self.log("✗ Không tìm thấy textarea", "ERROR")
            return False

        textarea.clear()
        time.sleep(0.2)
        textarea.input(dummy_prompt)
        time.sleep(0.3)
        textarea.input('\n')
        self.log("✓ Đã gửi prompt, đợi Chrome tạo ảnh...")

        # Đợi ảnh được tạo - kiểm tra bằng cách tìm img elements mới
        # hoặc đợi loading indicator biến mất
        self.log("→ Đợi ảnh được tạo (có thể mất 10-30s)...")

        for i in range(60):  # Đợi tối đa 60s
            time.sleep(2)

            # Kiểm tra có ảnh được tạo không
            # Tìm elements chứa ảnh generated
            check_result = self.driver.run_js("""
                // Tìm các img elements có src chứa base64 hoặc googleusercontent
                var imgs = document.querySelectorAll('img');
                var found = 0;
                for (var img of imgs) {
                    var src = img.src || '';
                    if (src.includes('data:image') || src.includes('googleusercontent') || src.includes('ggpht')) {
                        // Kiểm tra kích thước - ảnh generated thường lớn
                        if (img.naturalWidth > 200 || img.width > 200) {
                            found++;
                        }
                    }
                }
                return {found: found, loading: !!document.querySelector('[data-loading="true"]')};
            """)

            if check_result and check_result.get('found', 0) > 0:
                self.log(f"✓ Phát hiện {check_result['found']} ảnh!")
                time.sleep(2)  # Đợi thêm để ổn định
                self.log("✓ Session đã được warm up!")
                return True

            if i % 5 == 4:
                self.log(f"  ... đợi {(i+1)*2}s")

        self.log("⚠️ Không phát hiện được ảnh, tiếp tục...", "WARN")
        return True  # Vẫn return True để tiếp tục

    def setup(self, wait_for_project: bool = True, timeout: int = 120, warm_up: bool = False) -> bool:
        """
        Setup Chrome và inject interceptor.
        Giống batch_generator.py - không cần warm_up.

        Args:
            wait_for_project: Đợi user chọn project
            timeout: Timeout đợi project (giây)
            warm_up: Tạo 1 ảnh trong Chrome trước (default False - không cần)

        Returns:
            True nếu thành công
        """
        if not DRISSION_AVAILABLE:
            self.log("DrissionPage không được cài đặt! pip install DrissionPage", "ERROR")
            return False

        self.log("=" * 50)
        self.log("  DRISSION FLOW API - Setup")
        self.log("=" * 50)

        # 0. Khởi động proxy server tự động (nếu use_proxy=True)
        if self.use_proxy:
            if not self._start_proxy_server():
                self.log("⚠️ Tiếp tục không có proxy...", "WARN")
                self.use_proxy = False

        # 1. Tạo thư mục profile
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"Profile: {self.profile_dir}")

        # 2. Khởi tạo Chrome
        self.log("Khởi động Chrome...")
        try:
            options = ChromiumOptions()
            options.set_user_data_path(str(self.profile_dir))
            options.set_local_port(self.chrome_port)

            if self.use_proxy:
                options.set_argument(f'--proxy-server=socks5://127.0.0.1:{self.proxy_port}')
                self.log(f"Proxy: socks5://127.0.0.1:{self.proxy_port}")

            self.driver = ChromiumPage(addr_or_opts=options)
            self.log("✓ Chrome started")
        except Exception as e:
            self.log(f"✗ Chrome error: {e}", "ERROR")
            return False

        # 3. Vào Google Flow
        self.log("Vào Google Flow...")
        try:
            self.driver.get(self.FLOW_URL)
            time.sleep(3)
            self.log(f"✓ URL: {self.driver.url}")
        except Exception as e:
            self.log(f"✗ Navigation error: {e}", "ERROR")
            return False

        # 4. Auto setup project (click "Dự án mới" + chọn "Tạo hình ảnh")
        if wait_for_project:
            # Kiểm tra đã ở trong project chưa
            if "/project/" not in self.driver.url:
                self.log("Auto setup project...")
                if not self._auto_setup_project(timeout):
                    return False
            else:
                self.log("✓ Đã ở trong project!")

        # 5. Đợi textarea sẵn sàng
        self.log("Đợi project load...")
        for i in range(30):
            if self._find_textarea():
                self.log("✓ Project đã sẵn sàng!")
                break
            time.sleep(1)
        else:
            self.log("✗ Timeout - không tìm thấy textarea", "ERROR")
            return False

        # 6. Warm up session (tạo 1 ảnh trong Chrome để activate)
        if warm_up:
            if not self._warm_up_session():
                self.log("⚠️ Warm up không thành công, tiếp tục...", "WARN")

        # 7. Inject interceptor (SAU khi warm up)
        self.log("Inject interceptor...")
        self._reset_tokens()
        result = self.driver.run_js(JS_INTERCEPTOR)
        self.log(f"✓ Interceptor: {result}")

        self._ready = True
        return True

    def _find_textarea(self):
        """Tìm textarea input."""
        for sel in ["tag:textarea", "css:textarea"]:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    return el
            except:
                pass
        return None

    def _reset_tokens(self):
        """Reset captured tokens trong browser. Giống batch_generator.py."""
        self.driver.run_js("""
            window.__interceptReady = false;
            window._tk = null;
            window._pj = null;
            window._xbv = null;
            window._rct = null;
            window._payload = null;
            window._sid = null;
            window._url = null;
        """)

    def _capture_tokens(self, prompt: str, timeout: int = 10) -> bool:
        """
        Gửi prompt để capture tất cả tokens cần thiết.
        Giống batch_generator.py get_tokens().

        Args:
            prompt: Prompt để gửi
            timeout: Timeout đợi tokens (giây)

        Returns:
            True nếu capture thành công
        """
        self.log(f"    Prompt: {prompt[:50]}...")

        # QUAN TRỌNG: Reset tokens trước khi capture để đợi giá trị MỚI
        # Nếu không reset, sẽ lấy tokens cũ từ lần capture trước!
        self.driver.run_js("""
            window._rct = null;
            window._payload = null;
            window._url = null;
        """)

        # Tìm và gửi prompt
        textarea = self._find_textarea()
        if not textarea:
            self.log("✗ Không tìm thấy textarea", "ERROR")
            return False

        textarea.clear()
        time.sleep(0.2)
        textarea.input(prompt)
        time.sleep(0.3)
        textarea.input('\n')  # Enter để gửi
        self.log("    ✓ Đã gửi, đợi capture...")

        # Đợi 3 giây theo hướng dẫn (giống batch_generator.py)
        time.sleep(3)

        # Đọc tokens từ window variables
        for i in range(timeout):
            tokens = self.driver.run_js("""
                return {
                    tk: window._tk,
                    pj: window._pj,
                    xbv: window._xbv,
                    rct: window._rct,
                    sid: window._sid,
                    url: window._url
                };
            """)

            # Debug output (giống batch_generator.py)
            if i == 0 or i == 5:
                self.log(f"    [DEBUG] Bearer: {'YES' if tokens.get('tk') else 'NO'}")
                self.log(f"    [DEBUG] recaptcha: {'YES' if tokens.get('rct') else 'NO'}")
                self.log(f"    [DEBUG] projectId: {'YES' if tokens.get('pj') else 'NO'}")
                self.log(f"    [DEBUG] URL: {'YES' if tokens.get('url') else 'NO'}")

            if tokens.get("tk") and tokens.get("rct"):
                self.bearer_token = f"Bearer {tokens['tk']}"
                self.project_id = tokens.get("pj")
                self.session_id = tokens.get("sid")
                self.recaptcha_token = tokens.get("rct")
                self.x_browser_validation = tokens.get("xbv")
                self.captured_url = tokens.get("url")

                self.log("    ✓ Got Bearer token!")
                self.log("    ✓ Got recaptchaToken!")
                if self.captured_url:
                    self.log(f"    ✓ Captured URL: {self.captured_url[:60]}...")
                return True

            time.sleep(1)

        self.log("    ✗ Không lấy được đủ tokens", "ERROR")
        return False

    def refresh_recaptcha(self, prompt: str) -> bool:
        """
        Gửi prompt mới để lấy fresh recaptchaToken.
        Giống batch_generator.py refresh_recaptcha().

        Args:
            prompt: Prompt để trigger recaptcha

        Returns:
            True nếu thành công
        """
        # Reset captured data (chỉ rct - giống batch_generator.py)
        self.driver.run_js("window._rct = null;")

        textarea = self._find_textarea()
        if not textarea:
            return False

        textarea.clear()
        time.sleep(0.2)
        textarea.input(prompt)
        time.sleep(0.3)
        textarea.input('\n')

        # Đợi 3 giây
        time.sleep(3)

        # Wait for new token
        for i in range(10):
            rct = self.driver.run_js("return window._rct;")
            if rct:
                self.recaptcha_token = rct
                self.log("    ✓ Got new recaptchaToken!")
                return True
            time.sleep(1)

        self.log("    ✗ Không lấy được recaptchaToken mới", "ERROR")
        return False

    def call_api(self, prompt: str = None) -> Tuple[List[GeneratedImage], Optional[str]]:
        """
        Gọi API với captured tokens.
        Giống batch_generator.py - lấy payload từ browser mỗi lần.

        Args:
            prompt: Prompt (nếu None, dùng payload đã capture)

        Returns:
            Tuple[list of GeneratedImage, error message]
        """
        if not self.captured_url:
            return [], "No URL captured"

        url = self.captured_url
        self.log(f"→ URL: {url[:80]}...")

        # Lấy payload gốc từ Chrome (giống batch_generator.py)
        original_payload = self.driver.run_js("return window._payload;")
        if not original_payload:
            return [], "No payload captured"

        # Headers
        headers = {
            "Authorization": self.bearer_token,
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
        }
        if self.x_browser_validation:
            headers["x-browser-validation"] = self.x_browser_validation

        # Proxy
        proxies = None
        if self.use_proxy:
            proxies = {
                "http": f"socks5://127.0.0.1:{self.proxy_port}",
                "https": f"socks5://127.0.0.1:{self.proxy_port}"
            }

        self.log(f"→ Calling API with captured payload ({len(original_payload)} chars)...")

        try:
            # Dùng data= vì original_payload đã là JSON string
            resp = requests.post(
                url,
                headers=headers,
                data=original_payload,
                timeout=120,
                proxies=proxies
            )

            if resp.status_code == 200:
                return self._parse_response(resp.json()), None
            else:
                error = f"{resp.status_code}: {resp.text[:200]}"
                self.log(f"✗ API Error: {error}", "ERROR")
                return [], error

        except Exception as e:
            self.log(f"✗ Request error: {e}", "ERROR")
            return [], str(e)

    def _parse_response(self, data: Dict) -> List[GeneratedImage]:
        """Parse API response để lấy images."""
        images = []

        for media_item in data.get("media", data.get("images", [])):
            if isinstance(media_item, dict):
                gen_image = media_item.get("image", {}).get("generatedImage", media_item)
                img = GeneratedImage()

                # Base64 encoded image
                if gen_image.get("encodedImage"):
                    img.base64_data = gen_image["encodedImage"]

                # URL
                if gen_image.get("fifeUrl"):
                    img.url = gen_image["fifeUrl"]

                # Media name (for video generation)
                if media_item.get("name"):
                    img.media_name = media_item["name"]

                # Seed
                if gen_image.get("seed"):
                    img.seed = gen_image["seed"]

                if img.base64_data or img.url:
                    images.append(img)

        self.log(f"✓ Parsed {len(images)} images")
        return images

    def generate_image(
        self,
        prompt: str,
        save_dir: Optional[Path] = None,
        filename: str = None,
        max_retries: int = 3
    ) -> Tuple[bool, List[GeneratedImage], Optional[str]]:
        """
        Generate image - full flow với retry khi gặp 403.

        Args:
            prompt: Prompt mô tả ảnh
            save_dir: Thư mục lưu ảnh (optional)
            filename: Tên file (không có extension)
            max_retries: Số lần retry khi gặp 403 (mặc định 3)

        Returns:
            Tuple[success, list of images, error]
        """
        if not self._ready:
            return False, [], "API chưa setup! Gọi setup() trước."

        last_error = None

        for attempt in range(max_retries):
            # 1. Capture tokens với prompt (mỗi lần retry lấy token mới)
            if not self._capture_tokens(prompt):
                return False, [], "Không capture được tokens"

            # 2. Gọi API
            images, error = self.call_api()

            if error:
                last_error = error

                # Nếu lỗi 403, đánh dấu IPv6 và retry với token mới
                if "403" in error:
                    self.log(f"⚠️ 403 error (attempt {attempt+1}/{max_retries})", "WARN")

                    # Đánh dấu IPv6 bị block
                    if self._proxy_server and hasattr(self._proxy_server, 'rotator'):
                        self._proxy_server.rotator.mark_blocked()

                    if attempt < max_retries - 1:
                        self.log(f"  → Đợi 3s rồi retry với token mới...", "WARN")
                        time.sleep(3)
                        continue
                    else:
                        return False, [], error
                else:
                    # Lỗi khác, không retry
                    return False, [], error

            if not images:
                return False, [], "Không có ảnh trong response"

            # Thành công!
            break
        else:
            return False, [], last_error or "Max retries exceeded"

        # 3. Download và save nếu cần
        if save_dir:
            save_dir = Path(save_dir)
            save_dir.mkdir(parents=True, exist_ok=True)

            for i, img in enumerate(images):
                fname = filename or f"image_{int(time.time())}"
                if len(images) > 1:
                    fname = f"{fname}_{i+1}"

                if img.base64_data:
                    img_path = save_dir / f"{fname}.png"
                    img_path.write_bytes(base64.b64decode(img.base64_data))
                    img.local_path = img_path
                    self.log(f"✓ Saved: {img_path.name}")
                elif img.url:
                    # Download from URL
                    try:
                        proxies = None
                        if self.use_proxy:
                            proxies = {
                                "http": f"socks5://127.0.0.1:{self.proxy_port}",
                                "https": f"socks5://127.0.0.1:{self.proxy_port}"
                            }
                        resp = requests.get(img.url, timeout=60, proxies=proxies)
                        if resp.status_code == 200:
                            img_path = save_dir / f"{fname}.png"
                            img_path.write_bytes(resp.content)
                            img.local_path = img_path
                            img.base64_data = base64.b64encode(resp.content).decode()
                            self.log(f"✓ Downloaded: {img_path.name}")
                    except Exception as e:
                        self.log(f"✗ Download error: {e}", "WARN")

        return True, images, None

    def generate_batch(
        self,
        prompts: List[str],
        save_dir: Path,
        on_progress: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Generate batch nhiều ảnh.

        Args:
            prompts: Danh sách prompts
            save_dir: Thư mục lưu ảnh
            on_progress: Callback(index, total, success, error)

        Returns:
            Dict với thống kê
        """
        results = {
            "total": len(prompts),
            "success": 0,
            "failed": 0,
            "images": []
        }

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        for i, prompt in enumerate(prompts):
            self.log(f"\n[{i+1}/{len(prompts)}] {prompt[:50]}...")

            # Lần đầu capture tất cả, sau đó chỉ refresh recaptcha
            if i == 0:
                if not self._capture_tokens(prompt):
                    results["failed"] += 1
                    if on_progress:
                        on_progress(i+1, len(prompts), False, "Không capture được tokens")
                    continue
            else:
                if not self.refresh_recaptcha(prompt):
                    results["failed"] += 1
                    if on_progress:
                        on_progress(i+1, len(prompts), False, "Không refresh được recaptcha")
                    continue

            # Gọi API
            images, error = self.call_api()

            if error:
                results["failed"] += 1
                if on_progress:
                    on_progress(i+1, len(prompts), False, error)

                # Token hết hạn → dừng
                if "401" in error:
                    self.log("Bearer token hết hạn!", "ERROR")
                    break
                continue

            if images:
                # Save images
                for j, img in enumerate(images):
                    fname = f"batch_{i+1:03d}_{j+1}"
                    if img.base64_data:
                        img_path = save_dir / f"{fname}.png"
                        img_path.write_bytes(base64.b64decode(img.base64_data))
                        img.local_path = img_path

                results["success"] += 1
                results["images"].extend(images)
                if on_progress:
                    on_progress(i+1, len(prompts), True, None)
            else:
                results["failed"] += 1
                if on_progress:
                    on_progress(i+1, len(prompts), False, "No images")

            time.sleep(1)  # Rate limit

        self.log(f"\n{'='*50}")
        self.log(f"DONE: {results['success']}/{results['total']}")
        return results

    def close(self):
        """Đóng Chrome."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        self._ready = False

    @property
    def is_ready(self) -> bool:
        """Kiểm tra API đã sẵn sàng chưa."""
        return self._ready and self.driver is not None


# Factory function
def create_drission_api(
    profile_dir: str = "./chrome_profile",
    proxy_port: int = 1080,
    use_proxy: bool = True,  # BẬT proxy
    log_callback: Optional[Callable] = None
) -> DrissionFlowAPI:
    """
    Tạo DrissionFlowAPI instance.

    Args:
        profile_dir: Thư mục Chrome profile
        proxy_port: Port SOCKS5 proxy
        use_proxy: Có dùng proxy không (cần chạy ipv6_rotate_proxy.py)
        log_callback: Callback để log

    Returns:
        DrissionFlowAPI instance
    """
    return DrissionFlowAPI(
        profile_dir=profile_dir,
        proxy_port=proxy_port,
        use_proxy=use_proxy,
        log_callback=log_callback
    )
