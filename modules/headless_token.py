"""
VE3 Tool - Headless Token Extractor
===================================
Lay token tu Google Flow API KHONG CAN MO CHROME.
Su dung Playwright chay an hoan toan.

Features:
- Chay headless (an hoan toan)
- Luu cookies de khong can dang nhap lai
- Ho tro nhieu accounts
- Bypass bot detection
"""

import json
import time
import asyncio
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from datetime import datetime


class HeadlessTokenExtractor:
    """
    Lay token tu Google Flow API bang Playwright headless.
    Chay AN HOAN TOAN - khong hien window.
    """

    FLOW_URL = "https://aisandbox.google.com/ai-video/create"
    COOKIES_DIR = Path("config/cookies")

    def __init__(self, account_id: str = "default"):
        """
        Args:
            account_id: ID de phan biet cac accounts (vd: "acc1", "acc2")
        """
        self.account_id = account_id
        self.cookies_file = self.COOKIES_DIR / f"{account_id}_cookies.json"
        self.COOKIES_DIR.mkdir(parents=True, exist_ok=True)

        # State
        self.browser = None
        self.context = None
        self.page = None

    def log(self, msg: str, level: str = "INFO"):
        """Log message."""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{level}] [{self.account_id}] {msg}")

    # ========== COOKIE MANAGEMENT ==========

    def save_cookies(self, cookies: List[Dict]):
        """Luu cookies vao file."""
        try:
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2)
            self.log(f"Saved {len(cookies)} cookies")
        except Exception as e:
            self.log(f"Save cookies error: {e}", "ERROR")

    def load_cookies(self) -> List[Dict]:
        """Load cookies tu file."""
        if not self.cookies_file.exists():
            return []
        try:
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            self.log(f"Loaded {len(cookies)} cookies")
            return cookies
        except Exception as e:
            self.log(f"Load cookies error: {e}", "ERROR")
            return []

    def has_valid_cookies(self) -> bool:
        """Kiem tra co cookies chua."""
        cookies = self.load_cookies()
        if not cookies:
            return False
        # Check if Google cookies exist
        google_cookies = [c for c in cookies if 'google' in c.get('domain', '')]
        return len(google_cookies) > 0

    # ========== PLAYWRIGHT HEADLESS ==========

    async def _init_browser(self, headless: bool = True):
        """Khoi tao Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Chua cai Playwright! Chay:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self.playwright = await async_playwright().start()

        # Launch browser - HEADLESS
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        # Create context with stealth settings
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Load cookies if available
        cookies = self.load_cookies()
        if cookies:
            await self.context.add_cookies(cookies)

        # Create page
        self.page = await self.context.new_page()

        # Stealth: Remove webdriver flag
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        self.log("Browser initialized (headless)" if headless else "Browser initialized (visible)")

    async def _close_browser(self):
        """Dong browser."""
        if self.context:
            # Save cookies before closing
            cookies = await self.context.cookies()
            self.save_cookies(cookies)

        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def _extract_token_async(self, headless: bool = True, timeout: int = 120) -> Tuple[str, str, str]:
        """
        Lay token (async version).

        Returns:
            Tuple: (token, project_id, error)
        """
        try:
            await self._init_browser(headless=headless)

            # Navigate to Flow
            self.log("Navigating to Google Flow...")
            await self.page.goto(self.FLOW_URL, wait_until='domcontentloaded', timeout=60000)

            # Check if need login
            current_url = self.page.url
            if 'accounts.google.com' in current_url or 'signin' in current_url:
                if headless:
                    self.log("Can dang nhap! Chay lai voi headless=False de dang nhap.", "WARN")
                    await self._close_browser()
                    return "", "", "need_login"
                else:
                    self.log("Dang cho dang nhap... (timeout: 120s)")
                    # Wait for redirect back to flow
                    try:
                        await self.page.wait_for_url("**/aisandbox.google.com/**", timeout=120000)
                        self.log("Dang nhap thanh cong!")
                    except Exception:
                        return "", "", "login_timeout"

            # Wait for page to load
            self.log("Waiting for page to load...")
            await asyncio.sleep(3)

            # Extract token from network requests
            token = ""
            project_id = ""

            # Method 1: Check localStorage/sessionStorage
            try:
                local_data = await self.page.evaluate("""
                    () => {
                        const result = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const key = localStorage.key(i);
                            if (key.includes('token') || key.includes('auth') || key.includes('credential')) {
                                result[key] = localStorage.getItem(key);
                            }
                        }
                        return result;
                    }
                """)
                if local_data:
                    self.log(f"Found localStorage data: {list(local_data.keys())}")
            except Exception as e:
                self.log(f"localStorage check failed: {e}", "WARN")

            # Method 2: Intercept network requests
            self.log("Intercepting API calls to get token...")

            captured_token = {"value": "", "project": ""}

            async def handle_request(request):
                """Capture authorization headers."""
                headers = request.headers
                auth = headers.get('authorization', '')
                if auth.startswith('Bearer '):
                    captured_token["value"] = auth[7:]  # Remove "Bearer " prefix

                # Get project ID from URL
                url = request.url
                if 'projects/' in url:
                    parts = url.split('projects/')
                    if len(parts) > 1:
                        project_part = parts[1].split('/')[0]
                        if project_part:
                            captured_token["project"] = project_part

            self.page.on('request', handle_request)

            # Trigger an API call by interacting with the page
            try:
                # Try to find and click on something that triggers API
                # Look for buttons or interactive elements
                await self.page.evaluate("""
                    () => {
                        // Trigger any pending requests
                        window.dispatchEvent(new Event('focus'));
                    }
                """)
                await asyncio.sleep(2)

                # Try clicking on create/generate button if exists
                buttons = await self.page.query_selector_all('button')
                for btn in buttons[:5]:  # Check first 5 buttons
                    try:
                        text = await btn.inner_text()
                        if any(word in text.lower() for word in ['create', 'generate', 'new']):
                            await btn.click()
                            await asyncio.sleep(2)
                            break
                    except:
                        continue

            except Exception as e:
                self.log(f"Interaction error: {e}", "WARN")

            token = captured_token["value"]
            project_id = captured_token["project"]

            # Method 3: If still no token, try to get from cookies
            if not token:
                cookies = await self.context.cookies()
                for cookie in cookies:
                    if 'token' in cookie['name'].lower() or 'auth' in cookie['name'].lower():
                        self.log(f"Found token cookie: {cookie['name']}")
                        # Token might be in cookie

            if token:
                self.log(f"Token extracted: {token[:50]}...")
                if project_id:
                    self.log(f"Project ID: {project_id}")
                return token, project_id, ""
            else:
                return "", "", "token_not_found"

        except Exception as e:
            return "", "", str(e)
        finally:
            await self._close_browser()

    def extract_token(self, headless: bool = True, timeout: int = 120) -> Tuple[str, str, str]:
        """
        Lay token (sync wrapper).

        Args:
            headless: True = chay an, False = hien browser de dang nhap
            timeout: Timeout in seconds

        Returns:
            Tuple: (token, project_id, error)
        """
        return asyncio.run(self._extract_token_async(headless, timeout))

    def login_interactive(self) -> bool:
        """
        Mo browser de dang nhap (chi chay 1 lan).
        Sau khi dang nhap, cookies se duoc luu de dung lai.

        Returns:
            True neu dang nhap thanh cong
        """
        self.log("Mo browser de dang nhap...")
        token, project_id, error = self.extract_token(headless=False)

        if error == "need_login":
            # Already handled in extract_token with headless=False
            pass

        if token:
            self.log("Dang nhap va lay token thanh cong!", "OK")
            return True
        else:
            self.log(f"Dang nhap that bai: {error}", "ERROR")
            return False


class HeadlessTokenManager:
    """
    Quan ly nhieu accounts headless.
    """

    def __init__(self, config_path: str = "config/accounts.json"):
        self.config_path = Path(config_path)
        self.accounts: List[HeadlessTokenExtractor] = []
        self.tokens: Dict[str, Dict] = {}  # account_id -> {token, project_id, time}

        self.load_accounts()

    def load_accounts(self):
        """Load accounts tu config."""
        if not self.config_path.exists():
            print("[HeadlessManager] Config not found, creating default...")
            self._create_default_config()
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Load headless accounts
            headless_accounts = data.get('headless_accounts', [])
            for acc in headless_accounts:
                if isinstance(acc, str):
                    acc_id = acc
                else:
                    acc_id = acc.get('id', '')

                if acc_id:
                    self.accounts.append(HeadlessTokenExtractor(acc_id))

            print(f"[HeadlessManager] Loaded {len(self.accounts)} accounts")

        except Exception as e:
            print(f"[HeadlessManager] Load error: {e}")

    def _create_default_config(self):
        """Tao config mac dinh."""
        default = {
            "headless_accounts": [
                "google_acc1",
                "google_acc2",
                "google_acc3"
            ],
            "note": "Moi account can dang nhap 1 lan bang: python -m modules.headless_token login <account_id>"
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=2)

    def login_account(self, account_id: str) -> bool:
        """Dang nhap 1 account (mo browser 1 lan)."""
        extractor = HeadlessTokenExtractor(account_id)
        return extractor.login_interactive()

    def login_all_accounts(self):
        """Dang nhap tat ca accounts (chay 1 lan khi setup)."""
        print(f"\n=== DANG NHAP {len(self.accounts)} ACCOUNTS ===")
        print("Moi account se mo browser de ban dang nhap.")
        print("Sau khi dang nhap, cookies se duoc luu de dung lai.\n")

        success = 0
        for acc in self.accounts:
            print(f"\n--- Account: {acc.account_id} ---")
            if acc.has_valid_cookies():
                print("  -> Da co cookies, skip (xoa file cookies neu muon dang nhap lai)")
                success += 1
            else:
                if acc.login_interactive():
                    success += 1
                input("Nhan Enter de tiep tuc account tiep theo...")

        print(f"\n=== XONG: {success}/{len(self.accounts)} accounts ===")
        return success

    def get_token(self, account_id: str = None) -> Tuple[str, str]:
        """
        Lay token cho 1 account (headless).

        Args:
            account_id: ID account, None = dung account dau tien co cookies

        Returns:
            Tuple: (token, project_id)
        """
        if account_id:
            extractor = HeadlessTokenExtractor(account_id)
        else:
            # Tim account co cookies
            for acc in self.accounts:
                if acc.has_valid_cookies():
                    extractor = acc
                    break
            else:
                print("[HeadlessManager] Khong co account nao co cookies!")
                print("Chay: python -m modules.headless_token login <account_id>")
                return "", ""

        # Extract token headless
        token, project_id, error = extractor.extract_token(headless=True)

        if error == "need_login":
            print(f"[HeadlessManager] Account {extractor.account_id} can dang nhap lai!")
            print(f"Chay: python -m modules.headless_token login {extractor.account_id}")
            return "", ""

        if token:
            self.tokens[extractor.account_id] = {
                'token': token,
                'project_id': project_id,
                'time': time.time()
            }

        return token, project_id

    def get_all_tokens(self) -> Dict[str, Dict]:
        """
        Lay token cho TAT CA accounts (headless, song song).

        Returns:
            Dict: {account_id: {token, project_id}}
        """
        print(f"\n[HeadlessManager] Lay token cho {len(self.accounts)} accounts...")

        results = {}
        for acc in self.accounts:
            if not acc.has_valid_cookies():
                print(f"  {acc.account_id}: SKIP (chua dang nhap)")
                continue

            token, project_id, error = acc.extract_token(headless=True)
            if token:
                results[acc.account_id] = {
                    'token': token,
                    'project_id': project_id
                }
                print(f"  {acc.account_id}: OK")
            else:
                print(f"  {acc.account_id}: FAIL ({error})")

        self.tokens = results
        print(f"[HeadlessManager] Lay duoc {len(results)} tokens")
        return results


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
VE3 Tool - Headless Token Extractor
===================================

Usage:
  python -m modules.headless_token login <account_id>   # Dang nhap 1 account (mo browser 1 lan)
  python -m modules.headless_token login-all            # Dang nhap tat ca accounts
  python -m modules.headless_token get <account_id>     # Lay token (headless)
  python -m modules.headless_token get-all              # Lay tat ca tokens (headless)
  python -m modules.headless_token test                 # Test headless browser

Examples:
  python -m modules.headless_token login google_acc1
  python -m modules.headless_token get google_acc1
""")
        sys.exit(0)

    cmd = sys.argv[1]
    manager = HeadlessTokenManager()

    if cmd == "login":
        if len(sys.argv) < 3:
            print("Error: Can account_id")
            print("Usage: python -m modules.headless_token login <account_id>")
            sys.exit(1)
        account_id = sys.argv[2]
        manager.login_account(account_id)

    elif cmd == "login-all":
        manager.login_all_accounts()

    elif cmd == "get":
        if len(sys.argv) < 3:
            # Get from any available account
            token, project_id = manager.get_token()
        else:
            account_id = sys.argv[2]
            token, project_id = manager.get_token(account_id)

        if token:
            print(f"\nToken: {token[:50]}...")
            print(f"Project: {project_id}")
        else:
            print("\nKhong lay duoc token!")

    elif cmd == "get-all":
        tokens = manager.get_all_tokens()
        print(f"\nKet qua: {len(tokens)} tokens")
        for acc_id, data in tokens.items():
            print(f"  {acc_id}: {data['token'][:30]}...")

    elif cmd == "test":
        print("Testing headless browser...")
        extractor = HeadlessTokenExtractor("test")
        token, project_id, error = extractor.extract_token(headless=True)
        if error:
            print(f"Error: {error}")
        else:
            print(f"Token: {token[:50] if token else 'None'}...")

    else:
        print(f"Unknown command: {cmd}")
