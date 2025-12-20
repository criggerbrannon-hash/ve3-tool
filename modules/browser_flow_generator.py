"""
VE3 Tool - Browser Flow Generator Module
========================================
Tich hop browser automation voi Excel workflow.

Workflow:
1. Doc Excel prompts (PromptWorkbook)
2. Lay cac scenes chua tao anh (status_img != 'done')
3. Mo trinh duyet, inject JS
4. Goi VE3.run() voi [{sceneId, prompt}]
5. Di chuyen file tu Downloads -> project/img/
6. Cap nhat Excel (img_path, status_img = 'done')

Usage:
    from modules.browser_flow_generator import BrowserFlowGenerator

    gen = BrowserFlowGenerator("PROJECTS/KA1-0001")
    gen.generate_all_images()
"""

import os
import sys
import time
import json
import shutil
import glob
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

# Import PromptWorkbook
from modules.excel_manager import PromptWorkbook, Scene
from modules.utils import get_logger, load_settings

# Browser driver imports - PREFER SELENIUM (more stable)
DRIVER_TYPE = None

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        WebDriverException,
        JavascriptException
    )
    DRIVER_TYPE = "selenium"
except ImportError:
    DRIVER_TYPE = None

SELENIUM_AVAILABLE = DRIVER_TYPE is not None


def _is_child_character(prompt: str) -> bool:
    """
    Kiểm tra xem prompt có mô tả nhân vật trẻ em không (< 18 tuổi).

    Trẻ em không nên tạo ảnh tham chiếu vì:
    1. AI có thể có hạn chế với hình trẻ em
    2. Ảnh tham chiếu trẻ em thường không dùng được
    3. Thay vào đó, mô tả trẻ em trực tiếp trong scene prompt

    Args:
        prompt: english_prompt của nhân vật

    Returns:
        True nếu là trẻ em (< 18 tuổi), False nếu không
    """
    import re

    if not prompt:
        return False

    # Pattern để tìm tuổi: "8-year-old", "12 year old", "15yo", etc.
    age_patterns = [
        r'(\d{1,2})[-\s]?year[-\s]?old',  # 8-year-old, 12 year old
        r'(\d{1,2})[-\s]?yo\b',            # 8yo, 12-yo
        r'\bage\s*(\d{1,2})\b',            # age 8, age 12
        r'\b(\d{1,2})[-\s]?tuoi\b',        # 8 tuổi (Vietnamese)
    ]

    for pattern in age_patterns:
        match = re.search(pattern, prompt.lower())
        if match:
            age = int(match.group(1))
            if age < 18:
                return True

    # Các từ khóa chỉ trẻ em
    child_keywords = [
        r'\bchild\b', r'\bkid\b', r'\bboy\b', r'\bgirl\b',
        r'\bteen\b', r'\bteenager\b', r'\btoddler\b', r'\bbaby\b',
        r'\binfant\b', r'\byoung child\b', r'\blittle\s+(boy|girl)\b',
        r'\btre em\b', r'\bcon trai\b', r'\bcon gai\b',  # Vietnamese
    ]

    prompt_lower = prompt.lower()
    for keyword in child_keywords:
        if re.search(keyword, prompt_lower):
            # Kiểm tra thêm - "boy" hoặc "girl" phải đi kèm với context trẻ em
            # Ví dụ: "8-year-old boy" là trẻ em, nhưng "young man" không phải
            if 'boy' in prompt_lower or 'girl' in prompt_lower:
                # Nếu có số tuổi >= 18 thì không phải trẻ em
                for pattern in age_patterns[:2]:  # Chỉ check year-old pattern
                    match = re.search(pattern, prompt_lower)
                    if match and int(match.group(1)) >= 18:
                        return False
                # Nếu không có tuổi, coi "boy/girl" là trẻ em
                return True
            return True

    return False


class BrowserFlowGenerator:
    """
    Tao anh tu Excel bang browser automation.

    Su dung JavaScript injection de dieu khien Google Flow.
    Tu dong di chuyen file tu Downloads va cap nhat Excel.
    """

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        project_path: str,
        profile_name: str = "main",
        headless: bool = False,
        verbose: bool = True,
        config_path: str = "config/settings.yaml"
    ):
        """
        Khoi tao BrowserFlowGenerator.

        Args:
            project_path: Duong dan den thu muc project (PROJECTS/KA1-0001)
            profile_name: Ten Chrome profile (luu trong chrome_profiles/)
            headless: Chay an (khong hien UI) - nen False lan dau de dang nhap
            verbose: In log chi tiet
            config_path: Duong dan file config
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "Selenium chua duoc cai dat. "
                "Chay: pip install selenium undetected-chromedriver"
            )

        self.project_path = Path(project_path)
        self.profile_name = profile_name
        self.headless = headless
        self.verbose = verbose

        # Load config
        self.config = {}
        config_file = Path(config_path)
        if config_file.exists():
            self.config = load_settings(config_file)  # Pass Path object, not string

        # Paths
        self.img_path = self.project_path / "img"
        self.prompts_path = self.project_path / "prompts"
        self.nv_path = self.project_path / "nv"

        # Tao thu muc neu chua co
        self.img_path.mkdir(parents=True, exist_ok=True)
        self.nv_path.mkdir(parents=True, exist_ok=True)

        # Chrome profile
        base_dir = Path(__file__).parent.parent
        profiles_dir = self.config.get("browser_profiles_dir", "./chrome_profiles")
        if not os.path.isabs(profiles_dir):
            profiles_dir = base_dir / profiles_dir
        self.profile_dir = Path(profiles_dir) / profile_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        # Downloads folder - noi browser tai anh ve
        self.downloads_dir = Path.home() / "Downloads"

        # Project code (dung cho ten file)
        self.project_code = self.project_path.name  # VD: KA1-0001

        # Driver
        self.driver = None
        self._js_injected = False
        self._project_url = ""  # Luu project URL de giu nguyen phien lam viec

        # Logger
        self.logger = get_logger("browser_flow")

        # Stats
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

    def _log(self, message: str, level: str = "info") -> None:
        """Print log message."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            icons = {
                "info": "[INFO]",
                "success": "[OK]",
                "error": "[ERROR]",
                "warn": "[WARN]",
            }
            print(f"[{timestamp}] {icons.get(level, '')} {message}")

    def _find_excel_file(self) -> Optional[Path]:
        """Tim file Excel prompts trong project."""
        # Tim trong prompts/
        for pattern in ["*_prompts.xlsx", "*.xlsx"]:
            files = list(self.prompts_path.glob(pattern))
            if files:
                return files[0]

        # Tim trong project root
        for pattern in ["*_prompts.xlsx", "*.xlsx"]:
            files = list(self.project_path.glob(pattern))
            if files:
                return files[0]

        return None

    def _get_js_script(self) -> str:
        """Doc file JavaScript automation."""
        script_path = Path(__file__).parent.parent / "scripts" / "ve3_browser_automation.js"

        if script_path.exists():
            with open(script_path, "r", encoding="utf-8") as f:
                return f.read()

        raise FileNotFoundError(f"JS script khong tim thay: {script_path}")

    def _create_driver(self):
        """
        Tao Chrome WebDriver - PARALLEL SAFE.
        - Moi instance dung port rieng (khong xung dot)
        - Dung working profile rieng (giu nguyen settings nhu download permission)
        - Mac dinh headless (chay an)
        """
        import random

        # Download prefs
        prefs = {
            "download.default_directory": str(self.downloads_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }

        self._log(f"Headless: {self.headless}")
        self._log("Su dung Selenium WebDriver (Parallel Safe)")

        try:
            options = Options()

            # Tim Chrome binary
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
            ]
            for chrome_path in chrome_paths:
                if os.path.exists(chrome_path):
                    options.binary_location = chrome_path
                    self._log(f"Chrome: {chrome_path}")
                    break

            # Tao working profile rieng (khong phai temp, giu nguyen settings)
            # Vi tri: ~/.ve3_chrome_profiles/{profile_name}
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            working_profile_base = Path.home() / ".ve3_chrome_profiles"
            working_profile_base.mkdir(parents=True, exist_ok=True)
            working_profile = working_profile_base / self.profile_name

            self._log(f"Profile goc: {self.profile_dir}")
            self._log(f"Working profile: {working_profile}")

            # Copy data tu profile goc sang working profile (chi lan dau)
            import shutil
            if not working_profile.exists():
                working_profile.mkdir(parents=True, exist_ok=True)
                if any(self.profile_dir.iterdir()):  # Neu profile goc co data
                    for item in self.profile_dir.iterdir():
                        try:
                            dest = working_profile / item.name
                            if item.is_dir():
                                shutil.copytree(item, dest, dirs_exist_ok=True)
                            else:
                                shutil.copy2(item, dest)
                        except Exception:
                            pass  # Skip locked files
                    self._log(f"Da copy profile data lan dau")
            else:
                self._log(f"Su dung working profile da co (giu settings)")

            self._working_profile = str(working_profile)  # Luu de reference
            options.add_argument(f"--user-data-dir={working_profile}")

            # PARALLEL SAFE: Moi instance dung port rieng
            debug_port = random.randint(9222, 9999)
            options.add_argument(f"--remote-debugging-port={debug_port}")

            # Headless mac dinh (chay an, toi uu cho auto)
            if self.headless:
                options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")

            # Cac options cho automation
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-infobars")
            options.add_argument("--window-size=1920,1080")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("prefs", prefs)

            self._log(f"Dang khoi dong Chrome (port {debug_port})...")
            driver = webdriver.Chrome(options=options)

            # An webdriver flag
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            self._log("Chrome da san sang!", "success")

            return driver

        except Exception as e:
            self._log(f"Loi khoi dong Chrome: {e}", "error")
            import traceback
            traceback.print_exc()
            raise

    def start_browser(self) -> bool:
        """
        Khoi dong trinh duyet va navigate den Google Flow.

        Returns:
            True neu thanh cong
        """
        self._log("Khoi dong trinh duyet...")

        try:
            self.driver = self._create_driver()
            self._log("Da khoi dong Chrome", "success")

            # Tang timeout cho async script (mac dinh 30s, can nhieu hon cho upload/generate)
            self.driver.set_script_timeout(300)  # 5 phut
            self._log("Set script timeout: 300s")

            # Navigate den Google Flow
            self._log(f"Navigate den: {self.FLOW_URL}")
            self.driver.get(self.FLOW_URL)

            # Cho page load
            time.sleep(5)

            return True

        except Exception as e:
            self._log(f"Loi khoi dong: {e}", "error")
            return False

    def stop_browser(self) -> None:
        """Dong trinh duyet (giu nguyen working profile de luu settings)."""
        if self.driver:
            self._log("Dong trinh duyet...")
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self._js_injected = False
            # Khong xoa working profile - giu nguyen de luu settings (download permission, etc.)

    def wait_for_login(self, timeout: int = 300) -> bool:
        """
        Cho nguoi dung dang nhap.

        Args:
            timeout: Thoi gian cho (giay)

        Returns:
            True neu da dang nhap
        """
        self._log(f"Cho dang nhap (timeout: {timeout}s)...")
        self._log("Vui long dang nhap Google account tren trinh duyet")

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                textarea = self.driver.find_element(By.CSS_SELECTOR, "textarea")
                if textarea:
                    self._log("Da phat hien dang nhap thanh cong!", "success")
                    return True
            except:
                pass

            time.sleep(2)

        self._log("Timeout - chua dang nhap", "error")
        return False

    def _inject_js(self) -> bool:
        """Inject JavaScript automation script."""
        if self._js_injected:
            return True

        try:
            self._log("Buoc 1: Inject JavaScript script...")
            js_code = self._get_js_script()
            self.driver.execute_script(js_code)

            # Init VE3 voi project name
            self._log("Buoc 2: Init VE3...")
            self.driver.execute_script(f'VE3.init("{self.project_code}")')

            # Setup UI: Click "Du an moi" + Chon "Tao hinh anh"
            self._log("Buoc 3: Setup UI (Du an moi + Tao hinh anh)...")
            setup_result = self.driver.execute_async_script("""
                const callback = arguments[arguments.length - 1];
                (async () => {
                    try {
                        await VE3.setup();
                        callback({success: true});
                    } catch(e) {
                        callback({success: false, error: e.message});
                    }
                })();
            """)

            if setup_result and setup_result.get('success'):
                self._log("Setup UI thanh cong!", "success")
                # Luu project URL de giu nguyen phien
                self._project_url = self._get_project_url_from_js()
                if self._project_url:
                    self._log(f"Project URL: {self._project_url}", "info")
            else:
                error = setup_result.get('error', 'Unknown') if setup_result else 'No response'
                self._log(f"Setup UI that bai: {error}", "warn")

            self._js_injected = True
            self._log("Da san sang tao anh!", "success")
            return True

        except Exception as e:
            self._log(f"Loi inject JS: {e}", "error")
            import traceback
            traceback.print_exc()
            return False

    # =========================================================================
    # MEDIA NAMES CACHE - Luu media_name de reference
    # =========================================================================

    def _get_media_cache_path(self) -> Path:
        """Duong dan file cache media_names."""
        return self.project_path / "prompts" / ".media_cache.json"

    def _load_media_cache(self) -> Dict[str, Any]:
        """
        Load media_names tu cache file.

        Format moi: {id: {mediaName: str, seed: int|null}}
        Backward compatible voi format cu: {id: str}
        """
        cache_path = self._get_media_cache_path()
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._log(f"Loaded {len(data)} media_names from cache")
                    return data
            except:
                pass
        return {}

    def _save_media_cache(self, media_names: Dict[str, Any]) -> None:
        """
        Luu media_names vao cache file.

        Format: {id: {mediaName: str, seed: int|null}}
        """
        cache_path = self._get_media_cache_path()
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(media_names, f, indent=2)
            self._log(f"Saved {len(media_names)} media_names to cache")
        except Exception as e:
            self._log(f"Loi save cache: {e}", "warn")

    def _get_media_names_from_js(self) -> Dict[str, Any]:
        """
        Lay tat ca media_names tu JS.

        Returns:
            Dict voi format: {id: {mediaName: str, seed: int|null}}
        """
        if not self.driver:
            return {}
        try:
            return self.driver.execute_script("return VE3.getMediaNames();") or {}
        except:
            return {}

    def _get_project_url_from_js(self) -> str:
        """Lay project URL tu JS."""
        if not self.driver:
            return ""
        try:
            return self.driver.execute_script("return VE3.getProjectUrl();") or ""
        except:
            return ""

    def _load_media_names_to_js(self, media_names: Dict[str, Any]) -> None:
        """
        Load media_names vao JS tu cache.

        Supports ca format cu (string) va moi ({mediaName, seed}).
        JS se xu ly chinh xac dua vao format.
        """
        if not self.driver or not media_names:
            return
        try:
            self.driver.execute_script(f"VE3.setMediaNames({json.dumps(media_names)});")
        except Exception as e:
            self._log(f"Loi load media_names to JS: {e}", "warn")

    def _is_child_character(self, char_id: str) -> bool:
        """
        Check if a character ID represents a child (under 15 years old).
        Children cannot use reference images due to API policy.

        Child patterns:
        - nvc1 (exactly) = narrator as child
        - nv1c (exactly) = character 1 as child
        - *_child, *-child = any character with child suffix
        - *child* (but not just containing 'child' in middle of word)
        """
        if not char_id:
            return False

        char_id_clean = char_id.replace('.png', '').replace('.jpg', '').replace('.jpeg', '').replace('.webp', '').lower().strip()

        # Exact child character IDs (narrator/character as child)
        exact_child_ids = ['nvc1', 'nv1c', 'nvc_child', 'nv1_child', 'child']

        if char_id_clean in exact_child_ids:
            self._log(f"[CHILD] {char_id} matched exact child ID: {char_id_clean}", "info")
            return True

        # Suffix patterns for child characters
        if char_id_clean.endswith('_child') or char_id_clean.endswith('-child'):
            self._log(f"[CHILD] {char_id} matched child suffix pattern", "info")
            return True

        # Pattern: nvc followed by single digit 1 (nvc1 but not nvc10, nvc11, etc.)
        # This is for narrator-child-version-1
        import re
        if re.match(r'^nvc1$', char_id_clean):  # Exactly nvc1
            self._log(f"[CHILD] {char_id} matched nvc1 pattern", "info")
            return True

        return False

    def _simplify_prompt_for_reference(self, prompt: str, reference_files: List[str]) -> str:
        """
        Đơn giản hóa prompt khi có ảnh reference - loại bỏ mô tả ngoại hình chi tiết.

        Khi đã có ảnh tham chiếu, việc mô tả chi tiết (tóc, mắt, râu, da...)
        sẽ khiến Flow tạo ra nhân vật MỚI thay vì dùng ảnh reference.

        Giữ lại: cảm xúc, hành động, tư thế, bối cảnh
        Loại bỏ: tuổi, chủng tộc, màu tóc, màu mắt, râu, mô tả da

        Args:
            prompt: Prompt gốc
            reference_files: List các file reference (nvc.png, nv1.png, loc.png...)

        Returns:
            Prompt đã được đơn giản hóa
        """
        import re

        if not prompt or not reference_files:
            return prompt

        # Tìm các character references (nvc, nv1, nv2... không phải loc)
        char_refs = [r for r in reference_files if r.startswith('nv') and not r.startswith('loc')]

        if not char_refs:
            return prompt  # Không có character reference, giữ nguyên

        result = prompt

        # Patterns cần loại bỏ (mô tả ngoại hình CỐ ĐỊNH của nhân vật)
        # GIỮ LẠI: quần áo (vì mỗi bối cảnh cần trang phục khác nhau theo kế hoạch đạo diễn)
        # LOẠI BỎ: tuổi, chủng tộc, tóc, mắt, râu, da, thể hình (đã có trong ảnh reference)
        appearance_patterns = [
            # Tuổi + chủng tộc: "30-year-old Caucasian man"
            r'\d{1,2}[-\s]?year[-\s]?old\s+',  # "30-year-old "
            r'(?:Caucasian|Asian|African|European|American|Vietnamese|Korean|Japanese|Chinese|Latino|Hispanic|Indian)\s+',  # chủng tộc

            # Tóc: "short brown hair"
            r'(?:short|long|medium|curly|straight|wavy|messy|neat|slicked)\s+(?:brown|black|blonde|red|gray|grey|white|dark|light)\s+hair,?\s*',

            # Mắt: "tired blue eyes"
            r'(?:tired|bright|piercing|gentle|kind|cold|warm|deep)?\s*(?:brown|blue|green|hazel|gray|grey|black|dark)\s+eyes,?\s*',

            # Râu: "light stubble"
            r'(?:light|heavy|thick|thin|full)?\s*(?:stubble|beard|mustache|goatee),?\s*',

            # Da: "fair skin"
            r'(?:fair|dark|tan|pale|olive|brown|light|medium)\s+skin,?\s*',

            # Thể hình: "slim build"
            r'(?:slim|athletic|muscular|heavy|petite|tall|short)\s+build,?\s*',

            # LƯU Ý: KHÔNG loại bỏ quần áo - giữ nguyên để đạo diễn kiểm soát trang phục theo từng bối cảnh
        ]

        # Áp dụng các pattern
        for pattern in appearance_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # Dọn dẹp: loại bỏ dấu phẩy thừa, khoảng trắng thừa
        result = re.sub(r',\s*,', ',', result)  # ",," -> ","
        result = re.sub(r'\s+,', ',', result)   # " ," -> ","
        result = re.sub(r',\s*\.', '.', result)  # ",." -> "."
        result = re.sub(r'\s+', ' ', result)    # multiple spaces -> single space
        result = result.strip()

        # Log nếu có thay đổi
        if result != prompt:
            removed_chars = len(prompt) - len(result)
            self._log(f"[SIMPLIFY] Đã loại bỏ {removed_chars} ký tự mô tả ngoại hình", "info")
            self._log(f"[SIMPLIFY] Trước: {prompt[:100]}...", "info")
            self._log(f"[SIMPLIFY] Sau: {result[:100]}...", "info")

        return result

    def _filter_children_from_refs(self, ref_files: List[str]) -> List[str]:
        """
        Filter out child characters from reference_files list.
        Children under 15 should not be uploaded as reference.
        """
        if not ref_files:
            return []

        filtered = []
        for ref in ref_files:
            if self._is_child_character(ref):
                self._log(f"[FILTER] Bo qua tre em: {ref}", "info")
                continue
            filtered.append(ref)

        return filtered

    def _upload_reference_images(self, reference_files: List[str]) -> bool:
        """
        Upload cac anh reference truoc khi tao scene.

        Args:
            reference_files: List ten file (vd: ["nvc.png", "nv1.png"])

        Returns:
            True neu upload thanh cong
        """
        if not reference_files or not self.driver:
            return True

        self._log(f"[UPLOAD] Input reference_files: {reference_files}", "info")
        self._log(f"[UPLOAD] nv_path: {self.nv_path}", "info")

        # Filter out children under 15
        filtered_refs = self._filter_children_from_refs(reference_files)
        if not filtered_refs:
            self._log("[UPLOAD] Khong con anh nao sau khi filter tre em", "info")
            return True

        self._log(f"[UPLOAD] After filter children: {filtered_refs}", "info")

        images_to_upload = []

        for ref_file in filtered_refs:
            # Xac dinh duong dan file - ref_file co the la "nvc.png" hoac "nvc"
            ref_id = ref_file.replace('.png', '').replace('.jpg', '').replace('.jpeg', '').replace('.webp', '')

            # Tim file voi nhieu extension
            file_path = None
            filename = None

            # Thu cac extension khac nhau
            extensions = ['.png', '.jpg', '.jpeg', '.webp', '']
            search_dirs = [self.nv_path, self.project_path / "img"]

            for search_dir in search_dirs:
                if file_path:
                    break
                for ext in extensions:
                    test_path = search_dir / f"{ref_id}{ext}"
                    if test_path.exists():
                        file_path = test_path
                        filename = f"{ref_id}{ext}" if ext else ref_id
                        self._log(f"[UPLOAD] Found: {test_path}", "info")
                        break

            if not file_path:
                self._log(f"[UPLOAD] Khong tim thay file: {ref_id} (searched in nv/ and img/)", "warn")
                # List available files in nv/ for debugging
                if self.nv_path.exists():
                    available = list(self.nv_path.glob("*.*"))
                    self._log(f"[UPLOAD] Files in nv/: {[f.name for f in available[:10]]}", "info")
                continue

            # Doc file va convert sang base64
            try:
                with open(file_path, 'rb') as f:
                    image_data = f.read()
                    base64_data = base64.b64encode(image_data).decode('utf-8')
                    images_to_upload.append({
                        'base64': base64_data,
                        'filename': filename
                    })
                    self._log(f"[UPLOAD] Doc file: {filename} ({len(image_data)/1024:.1f} KB)")
            except Exception as e:
                self._log(f"[UPLOAD] Loi doc file {filename}: {e}", "error")
                continue

        if not images_to_upload:
            self._log("[UPLOAD] Khong co anh nao de upload", "warn")
            return True

        # Upload qua JS
        try:
            self._log(f"[UPLOAD] Goi JS VE3.uploadReferences() voi {len(images_to_upload)} files...", "info")
            images_json = json.dumps(images_to_upload)

            # Timeout dai hon cho upload nhieu file
            timeout_ms = 60000 + (len(images_to_upload) * 30000)  # 60s + 30s per file
            self._log(f"[UPLOAD] Timeout: {timeout_ms/1000:.0f}s", "info")

            result = self.driver.execute_async_script(f"""
                const callback = arguments[arguments.length - 1];
                const timeout = setTimeout(() => {{
                    callback({{ success: false, error: 'JS timeout' }});
                }}, {timeout_ms});

                try {{
                    VE3.uploadReferences({images_json}).then(result => {{
                        clearTimeout(timeout);
                        // Pass result truc tiep, khong wrap lai
                        callback(result);
                    }}).catch(e => {{
                        clearTimeout(timeout);
                        callback({{ success: false, error: e.message || 'Upload exception' }});
                    }});
                }} catch (e) {{
                    clearTimeout(timeout);
                    callback({{ success: false, error: 'JS error: ' + e.message }});
                }}
            """)

            self._log(f"[UPLOAD] JS result: {result}", "info")

            if result and result.get('success'):
                success_count = result.get('successCount', 0)
                total_count = result.get('totalCount', len(images_to_upload))
                self._log(f"[UPLOAD] Da upload {success_count}/{total_count} anh reference", "success")
                return True
            else:
                # Log chi tiet loi tu JS
                errors = result.get('errors', []) if result else []
                if errors:
                    for err in errors:
                        self._log(f"[UPLOAD] - {err.get('file', '?')}: {err.get('error', 'Unknown')}", "error")
                else:
                    error = result.get('error', 'Unknown') if result else 'No response from JS'
                    self._log(f"[UPLOAD] Loi upload: {error}", "error")
                # Tiep tuc du co loi - khong block generation
                return False

        except Exception as e:
            self._log(f"[UPLOAD] Python Exception: {e}", "error")
            import traceback
            self._log(f"[UPLOAD] Traceback: {traceback.format_exc()}", "error")
            return False

    def _find_downloaded_files(self, pattern: str, wait_timeout: int = 30) -> List[Path]:
        """
        Tim file vua download trong Downloads folder.

        Args:
            pattern: Pattern de match (vd: KA1-0001_scene_*)
            wait_timeout: Thoi gian cho file xuat hien

        Returns:
            List cac file tim duoc
        """
        start_time = time.time()
        search_pattern = str(self.downloads_dir / pattern)

        while time.time() - start_time < wait_timeout:
            files = glob.glob(search_pattern)
            # Loai bo file .crdownload (dang tai)
            files = [f for f in files if not f.endswith('.crdownload')]

            if files:
                return [Path(f) for f in files]

            time.sleep(0.5)

        return []

    def _select_best_image(self, files: List[Path], is_character: bool = False) -> Tuple[Path, float]:
        """
        Chon anh tot nhat tu nhieu files.
        Su dung ImageEvaluator de danh gia chat luong anh (sharpness, brightness, contrast, faces).
        Fallback: dung file size neu khong co opencv.

        Args:
            files: List cac file anh
            is_character: Co phai anh nhan vat (nvc/nv*/loc*) - uu tien face detection

        Returns:
            Tuple[Path den file tot nhat, score]
        """
        if len(files) == 1:
            # Van danh gia de biet score
            try:
                from modules.image_evaluator import ImageEvaluator
                evaluator = ImageEvaluator(verbose=False)
                _, score = evaluator.evaluate(files[0], is_character)
                return files[0], score.total_score
            except ImportError:
                return files[0], 100.0  # Assume good if can't evaluate

        # Thu dung ImageEvaluator (tot hon)
        try:
            from modules.image_evaluator import ImageEvaluator
            evaluator = ImageEvaluator(verbose=False)
            best_path, best_score = evaluator.select_best(files, is_character)

            self._log(f"Chon anh tot nhat: {best_path.name} (score={best_score.total_score}, grade={best_score.grade})")

            # Log comparison
            if len(files) > 1:
                scores_str = []
                for f in files:
                    _, score = evaluator.evaluate(f, is_character)
                    scores_str.append(f"{f.name}={score.total_score}")
                self._log(f"  So sanh: {', '.join(scores_str)}")

            return best_path, best_score.total_score

        except ImportError:
            self._log("ImageEvaluator khong co, dung file size", "warn")

        # Fallback: Lay file size cua moi file
        file_sizes = []
        for f in files:
            try:
                size = f.stat().st_size
                file_sizes.append((f, size))
            except:
                file_sizes.append((f, 0))

        # Sort theo size giam dan (lon nhat = tot nhat)
        file_sizes.sort(key=lambda x: x[1], reverse=True)

        best_file = file_sizes[0][0]
        best_size = file_sizes[0][1]

        self._log(f"Chon anh tot nhat: {best_file.name} ({best_size/1024:.1f}KB)")

        # Log comparison
        if len(file_sizes) > 1:
            sizes_str = ", ".join([f"{f.name}={s/1024:.1f}KB" for f, s in file_sizes])
            self._log(f"  So sanh: {sizes_str}")

        return best_file, 70.0  # Assume decent score for fallback

    def _move_downloaded_images(
        self,
        scene_id: str,
        min_score: float = 50.0
    ) -> Tuple[Optional[Path], float, bool]:
        """
        Di chuyen anh vua download tu Downloads vao project/img/ hoac nv/.
        Neu co 2 anh, chon anh tot nhat bang ImageEvaluator.
        Tra ve score de biet co can tao lai khong.

        Args:
            scene_id: ID cua scene (1, 2, ... hoac nvc, nv1, loc1...)
            min_score: Diem toi thieu de pass (0-100)

        Returns:
            Tuple[Path da di chuyen, score, needs_regeneration]
        """
        # Pattern: {project_code}_{scene_id}*.png
        pattern = f"{self.project_code}_{scene_id}*.png"

        files = self._find_downloaded_files(pattern, wait_timeout=120)

        if not files:
            self._log(f"Khong tim thay file: {pattern}", "warn")
            return None, 0.0, True

        # Xac dinh co phai nhan vat/dia diem khong (uu tien face detection)
        scene_id_str = str(scene_id)
        is_character = scene_id_str.startswith('nv') or scene_id_str.startswith('loc')

        # QUAN TRONG: Chon anh tot nhat va danh gia chat luong
        best_file, score = self._select_best_image(files, is_character)

        # Check neu can tao lai
        needs_regeneration = score < min_score
        if needs_regeneration:
            self._log(f"Anh {scene_id} chua dat chuan: {score:.1f} < {min_score}", "warn")

        # Xac dinh thu muc dich: nv/ cho nvc/nv*/loc*, img/ cho scenes
        if is_character:
            dst_dir = self.nv_path
        else:
            dst_dir = self.img_path

        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_file = dst_dir / f"{scene_id}.png"

        try:
            # Lưu tên file gốc trước khi move
            best_file_name = best_file.name

            shutil.move(str(best_file), str(dst_file))
            self._log(f"Da di chuyen: {best_file_name} -> {dst_file} (score={score:.1f})", "success")

            # Xoa cac file con lai (khong can nua)
            # QUAN TRỌNG: So sánh bằng tên file, không phải Path (vì best_file đã bị move)
            deleted_count = 0
            for f in files:
                if f.name != best_file_name:
                    try:
                        if f.exists():
                            os.remove(f)
                            deleted_count += 1
                            self._log(f"  Xoa file khong chon: {f.name}")
                        else:
                            self._log(f"  File da bi xoa truoc do: {f.name}")
                    except Exception as e:
                        self._log(f"  Loi xoa file {f.name}: {e}", "warn")

            if deleted_count > 0:
                self._log(f"  Da xoa {deleted_count} file khong duoc chon")
            elif len(files) > 1:
                self._log(f"  Khong xoa duoc file nao (co {len(files)} files)")

            return dst_file, score, needs_regeneration

        except Exception as e:
            self._log(f"Loi di chuyen file: {e}", "error")
            return None, 0.0, True

    def generate_scene_images(
        self,
        excel_path: Optional[Path] = None,
        start_scene: int = 1,
        end_scene: Optional[int] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Tao anh cho cac scenes trong Excel.

        Args:
            excel_path: Duong dan file Excel (tu tim neu khong chi dinh)
            start_scene: Scene bat dau (1-indexed)
            end_scene: Scene ket thuc (None = tat ca)
            overwrite: Ghi de anh da co

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("BROWSER FLOW GENERATOR - TAO ANH TU EXCEL")
        self._log("=" * 60)

        # Tim file Excel
        if excel_path is None:
            excel_path = self._find_excel_file()

        if excel_path is None or not excel_path.exists():
            return {"success": False, "error": "Khong tim thay file Excel"}

        self._log(f"Excel: {excel_path}")
        self._log(f"Project: {self.project_code}")

        # Load Excel
        workbook = PromptWorkbook(excel_path)
        workbook.load_or_create()

        # Lay cac scene can tao anh
        all_scenes = workbook.get_scenes()
        scenes_to_process = []

        for scene in all_scenes:
            # Filter theo range
            if scene.scene_id < start_scene:
                continue
            if end_scene is not None and scene.scene_id > end_scene:
                break

            # Skip neu khong co prompt
            if not scene.img_prompt:
                continue

            # Skip neu da done va khong overwrite
            if scene.status_img == "done" and not overwrite:
                self.stats["skipped"] += 1
                continue

            scenes_to_process.append(scene)

        if not scenes_to_process:
            self._log("Khong co scene nao can tao anh", "warn")
            return {"success": True, "message": "No scenes to process"}

        self._log(f"Se tao {len(scenes_to_process)} anh")
        self.stats["total"] = len(scenes_to_process)

        # Khoi dong browser
        if not self.driver:
            if not self.start_browser():
                return {"success": False, "error": "Khong khoi dong duoc browser"}

            # Cho dang nhap
            if not self.wait_for_login(timeout=120):
                self.stop_browser()
                return {"success": False, "error": "Chua dang nhap"}

        # Inject JS
        if not self._inject_js():
            return {"success": False, "error": "Khong inject duoc JS"}

        # IMPORTANT: Load media_names tu cache de reference characters
        cached_media_names = self._load_media_cache()
        if cached_media_names:
            self._load_media_names_to_js(cached_media_names)
            self._log(f"Loaded {len(cached_media_names)} media references (nv/loc)")
        else:
            self._log("Khong co media cache - scenes se khong co reference", "warn")

        # Chuan bi prompts cho VE3.run()
        # QUAN TRONG: Dung numeric ID (1, 2, 3) de khop voi SmartEngine video composer
        prompts_data = []
        for scene in scenes_to_process:
            scene_id = str(scene.scene_id)  # Dung numeric ID, khong phai scene_001
            prompts_data.append({
                "sceneId": scene_id,
                "prompt": scene.img_prompt
            })

        self._log(f"\nBat dau tao {len(prompts_data)} anh...")

        # DEBUG: List files trong thu muc nv/
        self._log("\n" + "=" * 60)
        self._log("[DEBUG] FILES TRONG THU MUC NV/:")
        self._log(f"  nv_path: {self.nv_path}")
        if self.nv_path.exists():
            nv_files = list(self.nv_path.glob("*.*"))
            self._log(f"  Found {len(nv_files)} files:")
            for f in nv_files:
                self._log(f"    - {f.name} ({f.stat().st_size / 1024:.1f} KB)")
        else:
            self._log(f"  [ERROR] Thu muc nv/ KHONG TON TAI!")
        self._log("=" * 60)

        # DEBUG: Hien thi cac scene de kiem tra reference_files
        self._log("\n" + "=" * 60)
        self._log("[DEBUG] KIEM TRA REFERENCE_FILES TU EXCEL:")
        self._log("=" * 60)
        for idx, s in enumerate(scenes_to_process[:5]):  # Hien thi 5 scene dau
            ref_raw = getattr(s, 'reference_files', None)
            self._log(f"  Scene {s.scene_id}: reference_files = '{ref_raw}'")
        self._log("=" * 60 + "\n")

        # Goi VE3.run() - xu ly tung prompt mot de cap nhat Excel theo thoi gian thuc
        for i, item in enumerate(prompts_data):
            scene = scenes_to_process[i]
            scene_id = item["sceneId"]
            prompt = item["prompt"]

            # Lay reference_files tu scene (JSON string hoac list)
            reference_files = []
            ref_str = getattr(scene, 'reference_files', '') or ''

            self._log(f"\n[DEBUG] Scene {scene_id} raw reference_files: '{ref_str}' (type={type(ref_str).__name__})")

            if ref_str:
                try:
                    # Thu parse JSON truoc
                    if ref_str.startswith('['):
                        parsed = json.loads(ref_str)
                        reference_files = parsed if isinstance(parsed, list) else [parsed]
                        self._log(f"[DEBUG] Parsed JSON: {reference_files}")
                    else:
                        # Khong phai JSON, split by comma
                        reference_files = [f.strip() for f in str(ref_str).split(',') if f.strip()]
                        self._log(f"[DEBUG] Split by comma: {reference_files}")
                except Exception as e:
                    self._log(f"[DEBUG] Parse error: {e}, trying split...")
                    reference_files = [f.strip() for f in str(ref_str).split(',') if f.strip()]

            self._log(f"\n[{i+1}/{len(prompts_data)}] Scene {scene_id}")
            self._log(f"Prompt ({len(prompt)} chars): {prompt[:100]}...")
            self._log(f"[REF] Final reference_files: {reference_files}")

            # NOTE: Không cần simplify nữa vì prompts.yaml đã yêu cầu AI không mô tả ngoại hình
            # khi có reference images. AI sẽ tạo prompt đúng từ đầu.

            # VERIFY: Check if prompt has filename annotations
            has_annotations = False
            for ref in reference_files:
                ref_name = ref.replace('.png', '').replace('.jpg', '')
                if f"({ref})" in prompt or f"({ref_name}.png)" in prompt:
                    has_annotations = True
                    break
            if "(reference:" in prompt:
                has_annotations = True

            if reference_files:
                if has_annotations:
                    self._log(f"[ANNOTATION] ✓ Prompt DA CO annotations", "success")
                else:
                    self._log(f"[ANNOTATION] ⚠️ Prompt CHUA CO annotations - them vao cuoi...", "warn")
                    # Them annotation neu chua co
                    refs_str = ", ".join(reference_files)
                    prompt = prompt.rstrip('. ') + f" (reference: {refs_str})."
                    self._log(f"[ANNOTATION] Prompt sau khi them: ...{prompt[-80:]}", "info")

            try:
                # QUAN TRONG: Upload reference images TRUOC KHI tao anh
                if reference_files:
                    self._log(f"[UPLOAD] Dang upload {len(reference_files)} anh reference...")
                    upload_success = self._upload_reference_images(reference_files)
                    if upload_success:
                        self._log(f"[UPLOAD] Upload thanh cong!", "success")
                    else:
                        self._log("[UPLOAD] Upload that bai, tiep tuc khong co reference", "warn")

                # Goi VE3.run() cho 1 prompt (voi reference_files)
                # Có error detection inline để phát hiện toast lỗi
                ref_files_json = json.dumps(reference_files)
                result = self.driver.execute_async_script(f"""
                    const callback = arguments[arguments.length - 1];
                    let resolved = false;

                    const timeoutId = setTimeout(() => {{
                        if (!resolved) {{
                            resolved = true;
                            callback({{ success: false, error: 'Timeout 120s' }});
                        }}
                    }}, 120000);

                    // ERROR DETECTION: Poll cho error toast
                    const errorCheckId = setInterval(() => {{
                        const toastDivs = document.querySelectorAll('div[class*="sc-f6076f05"]');
                        for (const div of toastDivs) {{
                            const buttons = div.querySelectorAll('button');
                            for (const btn of buttons) {{
                                const text = btn.textContent?.trim() || '';
                                if (text === 'Đóng' || text.includes('Đóng')) {{
                                    clearInterval(errorCheckId);
                                    clearTimeout(timeoutId);
                                    if (!resolved) {{
                                        resolved = true;
                                        callback({{ success: false, error: 'UI Error: Generation failed (toast)' }});
                                    }}
                                    return;
                                }}
                            }}
                        }}
                    }}, 1000);

                    VE3.run([{{
                        sceneId: "{scene_id}",
                        prompt: `{self._escape_js_string(prompt)}`,
                        referenceFiles: {ref_files_json}
                    }}]).then(r => {{
                        clearInterval(errorCheckId);
                        clearTimeout(timeoutId);
                        if (!resolved) {{
                            resolved = true;
                            callback({{ success: true, result: r }});
                        }}
                    }}).catch(e => {{
                        clearInterval(errorCheckId);
                        clearTimeout(timeoutId);
                        if (!resolved) {{
                            resolved = true;
                            callback({{ success: false, error: e.message }});
                        }}
                    }});
                """)

                if result and result.get("success"):
                    # Di chuyen file - scene_id la numeric ("1", "2", ...)
                    img_file, score, needs_regen = self._move_downloaded_images(scene_id)

                    if img_file:
                        # Cap nhat Excel - dung numeric ID
                        relative_path = f"img/{scene_id}.png"
                        workbook.update_scene(
                            scene.scene_id,  # scene.scene_id la int
                            img_path=relative_path,
                            status_img="done" if not needs_regen else "low_quality"
                        )
                        workbook.save()

                        if needs_regen:
                            self._log(f"Anh {scene_id} chua dat chuan (score={score:.1f}), can tao lai", "warn")
                            self.stats["low_quality"] = self.stats.get("low_quality", 0) + 1
                        else:
                            self._log(f"Da cap nhat Excel: {scene_id} = done (score={score:.1f})", "success")
                        self.stats["success"] += 1
                    else:
                        workbook.update_scene(scene.scene_id, status_img="error")
                        workbook.save()
                        self.stats["failed"] += 1
                else:
                    error = result.get("error", "Unknown") if result else "No response"
                    self._log(f"Loi: {error}", "error")
                    workbook.update_scene(scene.scene_id, status_img="error")
                    workbook.save()
                    self.stats["failed"] += 1

                # Delay giua cac prompt
                if i < len(prompts_data) - 1:
                    time.sleep(2)

            except Exception as e:
                self._log(f"Exception: {e}", "error")
                workbook.update_scene(scene.scene_id, status_img="error")
                workbook.save()
                self.stats["failed"] += 1

        # Summary
        self._log("\n" + "=" * 60)
        self._log("HOAN THANH")
        self._log("=" * 60)
        self._log(f"Tong: {self.stats['total']}")
        self._log(f"Thanh cong: {self.stats['success']}")
        self._log(f"That bai: {self.stats['failed']}")
        self._log(f"Bo qua: {self.stats['skipped']}")

        return {
            "success": True,
            "stats": self.stats.copy()
        }

    def _build_prompt_json(self, prompt: str, reference_files: List[str] = None) -> str:
        """
        Tạo prompt_json đầy đủ trước khi gửi API.
        prompt_json là nguồn dữ liệu chính - prompt gửi đi sẽ lấy từ đây.

        Args:
            prompt: Nội dung prompt
            reference_files: Danh sách file reference (optional)

        Returns:
            JSON string chứa prompt hoàn chỉnh
        """
        payload = {
            "prompt": prompt
        }
        # Có thể thêm các field khác nếu cần (seed, imageInputs, etc.)
        if reference_files:
            payload["reference_files"] = reference_files

        return json.dumps(payload, ensure_ascii=False)

    def _process_single_prompt(self, prompt_data: Dict, index: int, total: int) -> Tuple[bool, Optional[Path], float, str]:
        """
        Xu ly mot prompt don le.

        Returns:
            Tuple[success, image_path, score, prompt_json]
        """
        pid = str(prompt_data.get('id', index + 1))
        prompt = prompt_data.get('prompt', '')

        # Lay reference_files tu prompt_data (JSON string hoac list)
        reference_files = []
        ref_str = prompt_data.get('reference_files', '')
        if ref_str:
            try:
                parsed = json.loads(ref_str) if isinstance(ref_str, str) else ref_str
                reference_files = parsed if isinstance(parsed, list) else [parsed]
            except:
                reference_files = [f.strip() for f in str(ref_str).split(',') if f.strip()]

        self._log(f"\n[{index+1}/{total}] ID: {pid}")
        self._log(f"Prompt ({len(prompt)} chars): {prompt[:100]}...")
        if reference_files:
            self._log(f"[REF] reference_files: {reference_files}")
        else:
            self._log(f"[REF] ⚠️ NO REFERENCES - Excel cot 'reference_files' trong!")
            self._log(f"[REF] raw value from Excel: '{ref_str}'")

        if not prompt:
            self._log("Skip - prompt rong", "warn")
            return False, None, 0.0, ""

        # =====================================================
        # BƯỚC 1: Lấy hoặc tạo prompt_json
        # Nếu caller đã pre-save, dùng prompt_json đã có
        # =====================================================
        if 'prompt_json' in prompt_data and prompt_data['prompt_json']:
            prompt_json = prompt_data['prompt_json']
            self._log(f"[PROMPT_JSON] Sử dụng từ Excel: {prompt_json[:100]}...")
        else:
            # Fallback: tạo mới nếu chưa có
            prompt_json = self._build_prompt_json(prompt, reference_files)
            prompt_data['prompt_json'] = prompt_json
            self._log(f"[PROMPT_JSON] Đã tạo mới: {prompt_json[:100]}...")

        try:
            # UPLOAD REFERENCE IMAGES TRUOC KHI TAO ANH
            if reference_files:
                self._log(f"[UPLOAD] Dang upload {len(reference_files)} anh reference...")
                upload_success = self._upload_reference_images(reference_files)
                if not upload_success:
                    self._log("[UPLOAD] Upload that bai, tiep tuc khong co reference", "warn")

            # =====================================================
            # BƯỚC 2: Gửi prompt_json tới JS (thay vì gửi prompt riêng)
            # JS sẽ extract prompt từ prompt_json
            # Có 2 cơ chế phát hiện lỗi:
            #   1. JS-side: FetchHook.waitForImages() poll cho error toast
            #   2. JS-side (inline): Poll cho error toast trong async script
            # =====================================================
            ref_files_json = json.dumps(reference_files)
            result = self.driver.execute_async_script(f"""
                const callback = arguments[arguments.length - 1];
                let resolved = false;

                // Timeout sau 120 giây
                const timeoutId = setTimeout(() => {{
                    if (!resolved) {{
                        resolved = true;
                        callback({{ success: false, error: 'Timeout 120s' }});
                    }}
                }}, 120000);

                // ERROR DETECTION: Poll cho error toast mỗi 1 giây
                // Khi lỗi: <div class="sc-f6076f05-1"><button>Đóng</button></div>
                const errorCheckId = setInterval(() => {{
                    // Tìm div có class chứa "sc-f6076f05" với button "Đóng"
                    const toastDivs = document.querySelectorAll('div[class*="sc-f6076f05"]');
                    for (const div of toastDivs) {{
                        const buttons = div.querySelectorAll('button');
                        for (const btn of buttons) {{
                            const text = btn.textContent?.trim() || '';
                            if (text === 'Đóng' || text.includes('Đóng')) {{
                                console.log('[ERROR-DETECT] Found error toast!');
                                clearInterval(errorCheckId);
                                clearTimeout(timeoutId);
                                if (!resolved) {{
                                    resolved = true;
                                    callback({{ success: false, error: 'UI Error: Generation failed (toast detected)' }});
                                }}
                                return;
                            }}
                        }}
                    }}
                }}, 1000);

                VE3.run([{{
                    sceneId: "{pid}",
                    prompt: `{self._escape_js_string(prompt)}`,
                    referenceFiles: {ref_files_json},
                    promptJson: {prompt_json}
                }}]).then(r => {{
                    clearInterval(errorCheckId);
                    clearTimeout(timeoutId);
                    if (!resolved) {{
                        resolved = true;
                        callback({{ success: true, result: r }});
                    }}
                }}).catch(e => {{
                    clearInterval(errorCheckId);
                    clearTimeout(timeoutId);
                    if (!resolved) {{
                        resolved = true;
                        callback({{ success: false, error: e.message }});
                    }}
                }});
            """)

            if result and result.get("success"):
                # Lay prompt_json va images tu result
                js_result = result.get("result", {})
                prompt_json = js_result.get("prompt_json", "") if isinstance(js_result, dict) else ""
                js_images = js_result.get("images", []) if isinstance(js_result, dict) else []

                self._log(f"[DEBUG] prompt_json: {prompt_json[:100] if prompt_json else '(empty)'}...")
                self._log(f"[DEBUG] JS returned {len(js_images)} images with mediaNames")

                # Di chuyen file tu Downloads (timeout 2 phut)
                img_file, score, needs_regen = self._move_downloaded_images(pid)

                if img_file:
                    # TIM MEDIA_NAME VA SEED DUNG CHO ANH DA CHON
                    selected_media_name = ""
                    selected_seed = None
                    if js_images:
                        # Neu chi co 1 anh, lay mediaName va seed cua no
                        if len(js_images) == 1:
                            selected_media_name = js_images[0].get("mediaName", "")
                            selected_seed = js_images[0].get("seed")
                            self._log(f"[MEDIA] 1 image -> mediaName: {selected_media_name[:50] if selected_media_name else 'NONE'}, seed={selected_seed}")
                        else:
                            # Neu co nhieu anh, lay anh dau tien (thuong la best)
                            # TODO: Match filename de lay dung anh duoc chon
                            selected_media_name = js_images[0].get("mediaName", "")
                            selected_seed = js_images[0].get("seed")
                            self._log(f"[MEDIA] {len(js_images)} images, selected first -> mediaName: {selected_media_name[:50] if selected_media_name else 'NONE'}, seed={selected_seed}")

                    # Set mediaName + seed vao JS STATE de reference sau
                    if selected_media_name and self.driver:
                        try:
                            # Pass ca mediaName va seed
                            seed_arg = f", {selected_seed}" if selected_seed else ", null"
                            self.driver.execute_script(
                                f"VE3.setMediaName('{pid}', '{selected_media_name}'{seed_arg});"
                            )
                            self._log(f"[MEDIA] Saved mediaInfo for {pid}: mediaName + seed={selected_seed}")
                        except Exception as e:
                            self._log(f"[MEDIA] Warning: Could not set mediaName: {e}", "warn")

                    if needs_regen:
                        self._log(f"OK - Da tao anh nhung chua dat chuan (score={score:.1f})", "warn")
                    else:
                        self._log(f"OK - Da tao va luu anh (score={score:.1f})", "success")
                    return True, img_file, score, prompt_json
                else:
                    self._log(f"Khong tim thay file download sau 2 phut", "warn")
                    return False, None, 0.0, prompt_json
            else:
                error = result.get("error", "Unknown") if result else "No response"
                self._log(f"Loi: {error}", "error")
                return False, None, 0.0, ""

        except Exception as e:
            self._log(f"Exception: {e}", "error")
            return False, None, 0.0, ""

    def _restart_browser_and_setup(self) -> bool:
        """
        Khoi dong lai browser va setup (dung khi setup that bai).
        Neu da co project URL, navigate ve do thay vi tao project moi.

        Returns:
            True neu thanh cong
        """
        self._log("Khoi dong lai browser...", "warn")

        # Luu project URL truoc khi dong browser
        saved_project_url = self._project_url

        # Dong browser cu
        self.stop_browser()
        self._js_injected = False

        # Doi 3 giay
        time.sleep(3)

        # Khoi dong lai
        if not self.start_browser():
            return False

        if not self.wait_for_login(timeout=120):
            self.stop_browser()
            return False

        # Neu co project URL cu, navigate ve do thay vi setup moi
        if saved_project_url and '/project/' in saved_project_url:
            self._log(f"Navigate ve project cu: {saved_project_url}", "info")
            self.driver.get(saved_project_url)
            time.sleep(5)  # Cho page load

            # Inject JS nhung KHONG goi VE3.setup()
            if not self._inject_js_without_setup():
                return False

            # Restore project URL
            self._project_url = saved_project_url
        else:
            # Inject JS va setup moi
            if not self._inject_js():
                return False

        return True

    def _inject_js_without_setup(self) -> bool:
        """Inject JS ma khong goi VE3.setup() - dung khi navigate ve project cu."""
        if self._js_injected:
            return True

        try:
            self._log("Inject JavaScript (khong setup)...")
            js_code = self._get_js_script()
            self.driver.execute_script(js_code)

            # Init VE3 voi project name
            self.driver.execute_script(f'VE3.init("{self.project_code}")')

            # Danh dau da setup (vi da co project)
            self.driver.execute_script("VE3.markSetupDone();")

            # Load media_names tu cache
            cached_media_names = self._load_media_cache()
            if cached_media_names:
                self._load_media_names_to_js(cached_media_names)

            self._js_injected = True
            self._log("Da san sang tao anh (project cu)!", "success")
            return True

        except Exception as e:
            self._log(f"Loi inject JS: {e}", "error")
            return False

    def generate_from_prompts(
        self,
        prompts: List[Dict],
        excel_path: Optional[Path] = None,
        max_setup_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Tao anh tu danh sach prompts da load san (tu smart_engine._load_prompts).
        Method nay nhan prompts truc tiep thay vi doc lai tu Excel.

        Features:
        - Neu prompt dau tien that bai (co the do setup loi), tu dong restart browser va thu lai (toi da 3 lan)
        - Theo doi cac prompt that bai va retry o cuoi
        - Timeout 2 phut cho moi anh

        Args:
            prompts: List cac dict co dang {'id': '1', 'prompt': '...', 'output_path': '...'}
            excel_path: Duong dan Excel (de cap nhat status)
            max_setup_retries: So lan retry toi da neu setup that bai (default: 3)

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("BROWSER FLOW GENERATOR - TAO ANH TU PROMPTS")
        self._log("=" * 60)

        if not prompts:
            return {"success": False, "error": "Khong co prompts"}

        self._log(f"Tong: {len(prompts)} prompts")
        self._log(f"Project: {self.project_code}")

        # Reset stats
        self.stats = {"total": len(prompts), "success": 0, "failed": 0, "skipped": 0, "low_quality": 0}

        # Load Excel workbook de cap nhat prompt_json
        workbook = None
        if excel_path and Path(excel_path).exists():
            try:
                workbook = PromptWorkbook(excel_path)
                workbook.load_or_create()
                self._log(f"[Excel] Loaded: {excel_path}")
            except Exception as e:
                self._log(f"[Excel] Warning: Khong load duoc Excel: {e}", "warn")

        # Khoi dong browser
        if not self.driver:
            if not self.start_browser():
                return {"success": False, "error": "Khong khoi dong duoc browser"}

            if not self.wait_for_login(timeout=120):
                self.stop_browser()
                return {"success": False, "error": "Chua dang nhap"}

        # Inject JS
        if not self._inject_js():
            return {"success": False, "error": "Khong inject duoc JS"}

        # Load media_names tu cache va set vao JS
        cached_media_names = self._load_media_cache()
        if cached_media_names:
            self._log(f"[CACHE] Loaded {len(cached_media_names)} media_names:")
            for key, val in cached_media_names.items():
                # Support ca format cu (string) va moi ({mediaName, seed})
                if isinstance(val, dict):
                    mn = val.get('mediaName', '')
                    seed = val.get('seed')
                    self._log(f"  {key} -> mediaName:{mn[:40] if mn else 'None'}..., seed:{seed}")
                else:
                    self._log(f"  {key} -> {val[:50] if val else 'None'}...")
            self._load_media_names_to_js(cached_media_names)
        else:
            self._log("[CACHE] ⚠️ EMPTY - Characters (nv/loc) chua duoc tao!", "warn")
            self._log("[CACHE] Hay chay tao anh nhan vat truoc de co media_names", "warn")

        self._log(f"\nBat dau tao {len(prompts)} anh...")

        # DEBUG: Hien thi prompt dau tien
        if prompts:
            p = prompts[0]
            self._log(f"[DEBUG] Prompt dau tien: id={p.get('id')}")
            self._log(f"[DEBUG] prompt = '{str(p.get('prompt', ''))[:100]}'")

        # Track failed prompts de retry sau
        failed_prompts = []  # List of (prompt_data, original_index)

        # =====================================================
        # HELPER: Pre-save prompt_json to Excel BEFORE API call
        # =====================================================
        def pre_save_prompt_json(prompt_data: Dict, workbook):
            """Tạo và lưu prompt_json vào Excel TRƯỚC khi gọi API."""
            pid = str(prompt_data.get('id', ''))
            prompt = prompt_data.get('prompt', '')
            if not prompt or not pid.isdigit():
                return

            # Parse reference_files
            reference_files = []
            ref_str = prompt_data.get('reference_files', '')
            if ref_str:
                try:
                    parsed = json.loads(ref_str) if isinstance(ref_str, str) else ref_str
                    reference_files = parsed if isinstance(parsed, list) else [parsed]
                except:
                    reference_files = [f.strip() for f in str(ref_str).split(',') if f.strip()]

            # Build prompt_json
            prompt_json = self._build_prompt_json(prompt, reference_files)
            prompt_data['prompt_json'] = prompt_json

            # Save to Excel BEFORE API call
            if workbook:
                try:
                    scene_id = int(pid)
                    workbook.update_scene(
                        scene_id,
                        prompt_json=prompt_json,
                        status_img="generating"  # Mark as generating
                    )
                    workbook.save()
                    self._log(f"[Excel] Pre-saved prompt_json for scene {scene_id}")
                except Exception as e:
                    self._log(f"[Excel] Pre-save warning: {e}", "warn")

        # === XU LY PROMPT DAU TIEN VOI SETUP RETRY ===
        first_prompt_success = False
        setup_attempts = 0

        while not first_prompt_success and setup_attempts < max_setup_retries:
            setup_attempts += 1

            if setup_attempts > 1:
                self._log(f"\n=== SETUP RETRY {setup_attempts}/{max_setup_retries} ===", "warn")
                if not self._restart_browser_and_setup():
                    self._log(f"Khong the khoi dong lai browser", "error")
                    continue

            # Pre-save prompt_json to Excel BEFORE calling API
            pre_save_prompt_json(prompts[0], workbook)

            # Thu prompt dau tien
            success, img_file, score, prompt_json = self._process_single_prompt(prompts[0], 0, len(prompts))

            if success:
                first_prompt_success = True
                self.stats["success"] += 1
                if score < 50.0:
                    self.stats["low_quality"] += 1
                # Cap nhat Excel (img_path, status) - prompt_json da luu truoc do
                if workbook:
                    try:
                        pid = prompts[0].get('id', '1')
                        if pid.isdigit():
                            scene_id = int(pid)
                            relative_path = f"img/{pid}.png" if img_file else ""
                            workbook.update_scene(
                                scene_id,
                                img_path=relative_path,
                                status_img="done" if score >= 50.0 else "low_quality"
                            )
                            workbook.save()
                            self._log(f"[Excel] Updated scene {scene_id}: status=done")
                    except Exception as e:
                        self._log(f"[Excel] Warning: {e}", "warn")
            else:
                self._log(f"Prompt dau tien that bai (lan {setup_attempts})", "error")

        if not first_prompt_success:
            # Da thu het so lan retry, ghi nhan that bai
            self._log(f"Prompt dau tien that bai sau {max_setup_retries} lan thu", "error")
            failed_prompts.append((prompts[0], 0))
            self.stats["failed"] += 1

        # === XU LY CAC PROMPT CON LAI ===
        for i, prompt_data in enumerate(prompts[1:], start=1):
            pid = str(prompt_data.get('id', i + 1))
            prompt = prompt_data.get('prompt', '')

            if not prompt:
                self._log(f"\n[{i+1}/{len(prompts)}] ID: {pid} - Skip (prompt rong)", "warn")
                self.stats["skipped"] += 1
                continue

            # Pre-save prompt_json to Excel BEFORE calling API
            pre_save_prompt_json(prompt_data, workbook)

            success, img_file, score, prompt_json = self._process_single_prompt(prompt_data, i, len(prompts))

            if success:
                self.stats["success"] += 1
                if score < 50.0:
                    self.stats["low_quality"] += 1
                # Cap nhat Excel (img_path, status) - prompt_json da luu truoc do
                if workbook:
                    try:
                        if pid.isdigit():
                            scene_id = int(pid)
                            relative_path = f"img/{pid}.png" if img_file else ""
                            workbook.update_scene(
                                scene_id,
                                img_path=relative_path,
                                status_img="done" if score >= 50.0 else "low_quality"
                            )
                            workbook.save()
                            self._log(f"[Excel] Updated scene {scene_id}: status=done")
                    except Exception as e:
                        self._log(f"[Excel] Warning: {e}", "warn")
            else:
                failed_prompts.append((prompt_data, i))
                self.stats["failed"] += 1
                # Update Excel status to error (prompt_json was already saved)
                if workbook and pid.isdigit():
                    try:
                        workbook.update_scene(int(pid), status_img="error")
                        workbook.save()
                    except:
                        pass

            # Delay giua cac prompt
            if i < len(prompts) - 1:
                time.sleep(2)

        # === RETRY FAILED PROMPTS ===
        if failed_prompts:
            self._log("\n" + "=" * 60)
            self._log(f"RETRY {len(failed_prompts)} ANH THAT BAI")
            self._log("=" * 60)

            retry_success = 0
            for prompt_data, original_index in failed_prompts:
                pid = str(prompt_data.get('id', original_index + 1))
                self._log(f"\nRetry ID: {pid}")

                # prompt_json already exists from pre-save, no need to create again
                success, img_file, score, prompt_json = self._process_single_prompt(
                    prompt_data, original_index, len(prompts)
                )

                if success:
                    retry_success += 1
                    self.stats["success"] += 1
                    self.stats["failed"] -= 1  # Giam failed vi da thanh cong
                    if score < 50.0:
                        self.stats["low_quality"] += 1
                    # Cap nhat Excel (img_path, status) - prompt_json da luu truoc do
                    if workbook:
                        try:
                            if pid.isdigit():
                                scene_id = int(pid)
                                relative_path = f"img/{pid}.png" if img_file else ""
                                workbook.update_scene(
                                    scene_id,
                                    img_path=relative_path,
                                    status_img="done" if score >= 50.0 else "low_quality"
                                )
                                workbook.save()
                                self._log(f"[Excel] Updated scene {scene_id}: status=done (retry)")
                        except Exception as e:
                            self._log(f"[Excel] Warning: {e}", "warn")

                # Delay
                time.sleep(2)

            self._log(f"\nRetry: {retry_success}/{len(failed_prompts)} thanh cong")

        # Luu media_names tu JS vao cache (cho cac lan chay sau)
        js_media_names = self._get_media_names_from_js()
        if js_media_names:
            # Merge voi cached (uu tien moi)
            all_media_names = {**cached_media_names, **js_media_names}
            self._save_media_cache(all_media_names)

        # Summary
        self._log("\n" + "=" * 60)
        self._log("HOAN THANH")
        self._log("=" * 60)
        self._log(f"Tong: {self.stats['total']}")
        self._log(f"Thanh cong: {self.stats['success']}")
        self._log(f"That bai: {self.stats['failed']}")
        self._log(f"Bo qua: {self.stats['skipped']}")
        if self.stats.get('low_quality', 0) > 0:
            self._log(f"Chat luong thap: {self.stats['low_quality']}")
        if js_media_names:
            self._log(f"Media names saved: {len(js_media_names)}")

        return {
            "success": True,
            "stats": self.stats.copy()
        }

    def generate_character_images(
        self,
        excel_path: Optional[Path] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Tao anh cho cac nhan vat trong Excel.

        Args:
            excel_path: Duong dan file Excel
            overwrite: Ghi de anh da co

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("TAO ANH NHAN VAT")
        self._log("=" * 60)

        # Tim file Excel
        if excel_path is None:
            excel_path = self._find_excel_file()

        if excel_path is None or not excel_path.exists():
            return {"success": False, "error": "Khong tim thay file Excel"}

        # Load Excel
        workbook = PromptWorkbook(excel_path)
        workbook.load_or_create()

        # Lay cac nhan vat can tao anh
        characters = workbook.get_characters()
        chars_to_process = []
        skipped_children = []

        for char in characters:
            if not char.english_prompt:
                continue

            if char.status == "done" and not overwrite:
                continue

            # Skip nhân vật trẻ em - không tạo ảnh tham chiếu
            # Thay vào đó, mô tả trẻ em trực tiếp trong scene prompt
            if _is_child_character(char.english_prompt):
                skipped_children.append(char.id)
                continue

            chars_to_process.append(char)

        if skipped_children:
            self._log(f"Skip {len(skipped_children)} nhan vat tre em: {', '.join(skipped_children)}", "warn")
            self._log("  (Tre em se duoc mo ta truc tiep trong scene prompt)")

        if not chars_to_process:
            self._log("Khong co nhan vat nao can tao anh", "warn")
            return {"success": True, "message": "No characters to process", "skipped_children": skipped_children}

        self._log(f"Se tao {len(chars_to_process)} anh nhan vat")

        # Khoi dong browser neu chua
        if not self.driver:
            if not self.start_browser():
                return {"success": False, "error": "Khong khoi dong duoc browser"}

            if not self.wait_for_login(timeout=120):
                self.stop_browser()
                return {"success": False, "error": "Chua dang nhap"}

        if not self._inject_js():
            return {"success": False, "error": "Khong inject duoc JS"}

        # Load media cache de co the reference characters da tao truoc do
        cached_media_names = self._load_media_cache()
        if cached_media_names:
            self._load_media_names_to_js(cached_media_names)

        success_count = 0
        failed_count = 0

        for i, char in enumerate(chars_to_process):
            char_id = char.id or f"char_{i+1}"
            prompt = char.english_prompt

            self._log(f"\n[{i+1}/{len(chars_to_process)}] Nhan vat: {char_id}")

            try:
                result = self.driver.execute_async_script(f"""
                    const callback = arguments[arguments.length - 1];
                    let resolved = false;

                    const timeoutId = setTimeout(() => {{
                        if (!resolved) {{
                            resolved = true;
                            callback({{ success: false, error: 'Timeout 120s' }});
                        }}
                    }}, 120000);

                    // ERROR DETECTION: Poll cho error toast
                    const errorCheckId = setInterval(() => {{
                        const toastDivs = document.querySelectorAll('div[class*="sc-f6076f05"]');
                        for (const div of toastDivs) {{
                            const buttons = div.querySelectorAll('button');
                            for (const btn of buttons) {{
                                const text = btn.textContent?.trim() || '';
                                if (text === 'Đóng' || text.includes('Đóng')) {{
                                    clearInterval(errorCheckId);
                                    clearTimeout(timeoutId);
                                    if (!resolved) {{
                                        resolved = true;
                                        callback({{ success: false, error: 'UI Error: Generation failed (toast)' }});
                                    }}
                                    return;
                                }}
                            }}
                        }}
                    }}, 1000);

                    VE3.run([{{
                        sceneId: "{char_id}",
                        prompt: `{self._escape_js_string(prompt)}`
                    }}]).then(r => {{
                        clearInterval(errorCheckId);
                        clearTimeout(timeoutId);
                        if (!resolved) {{
                            resolved = true;
                            callback({{ success: true, result: r }});
                        }}
                    }}).catch(e => {{
                        clearInterval(errorCheckId);
                        clearTimeout(timeoutId);
                        if (!resolved) {{
                            resolved = true;
                            callback({{ success: false, error: e.message }});
                        }}
                    }});
                """)

                if result and result.get("success"):
                    # Di chuyen file vao nv/
                    pattern = f"{self.project_code}_{char_id}*.png"
                    files = self._find_downloaded_files(pattern, wait_timeout=120)

                    if files:
                        dst_file = self.nv_path / f"{char_id}.png"
                        shutil.move(str(files[0]), str(dst_file))

                        workbook.update_character(char_id, status="done", image_file=f"{char_id}.png")
                        workbook.save()

                        self._log(f"Da luu: {dst_file}", "success")
                        success_count += 1
                    else:
                        workbook.update_character(char_id, status="error")
                        workbook.save()
                        failed_count += 1
                else:
                    failed_count += 1

                if i < len(chars_to_process) - 1:
                    time.sleep(2)

            except Exception as e:
                self._log(f"Loi: {e}", "error")
                failed_count += 1

        self._log(f"\nNhan vat: {success_count} thanh cong, {failed_count} that bai")

        # IMPORTANT: Luu mediaNames vao cache sau khi tao xong characters
        # De khi tao scenes co the reference den characters
        try:
            media_names = self._get_media_names_from_js()
            if media_names:
                self._save_media_cache(media_names)
                self._log(f"Da luu {len(media_names)} media_names cho reference", "success")
        except Exception as e:
            self._log(f"Loi luu media cache: {e}", "warn")

        return {
            "success": True,
            "characters_success": success_count,
            "characters_failed": failed_count
        }

    def _get_generation_mode(self) -> str:
        """
        Lay generation mode tu config: 'chrome' hoac 'api'.
        Mac dinh: 'chrome'.
        """
        return self.config.get('generation_mode', 'chrome')

    def generate_images_auto(
        self,
        excel_path: Optional[Path] = None,
        start_scene: int = 1,
        end_scene: Optional[int] = None,
        overwrite: bool = False,
        bearer_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tao anh tu dong - chon mode dua tren config.

        Mode duoc cau hinh trong settings.yaml (generation_mode: 'chrome' hoac 'api')

        Args:
            excel_path: Duong dan file Excel
            start_scene: Scene bat dau
            end_scene: Scene ket thuc
            overwrite: Ghi de anh da co
            bearer_token: Bearer token (chi can cho API mode)

        Returns:
            Dict voi ket qua
        """
        mode = self._get_generation_mode()
        self._log(f"[AUTO] Generation mode: {mode.upper()}")

        if mode == 'api':
            # API mode - goi truc tiep API
            return self.generate_scene_images_api(
                excel_path=excel_path,
                start_scene=start_scene,
                end_scene=end_scene,
                overwrite=overwrite,
                bearer_token=bearer_token
            )
        else:
            # Chrome mode (default) - browser automation
            return self.generate_scene_images(
                excel_path=excel_path,
                start_scene=start_scene,
                end_scene=end_scene,
                overwrite=overwrite
            )

    def generate_from_prompts_auto(
        self,
        prompts: List[Dict],
        excel_path: Optional[Path] = None,
        bearer_token: Optional[str] = None,
        max_setup_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Tao anh tu prompts - tu dong chon mode dua tren config.

        Args:
            prompts: List prompts [{'id': '1', 'prompt': '...'}]
            excel_path: Duong dan Excel
            bearer_token: Bearer token (chi can cho API mode)
            max_setup_retries: So lan retry setup (chi cho Chrome mode)

        Returns:
            Dict voi ket qua
        """
        mode = self._get_generation_mode()
        self._log(f"[AUTO] Generation mode: {mode.upper()}")

        if mode == 'api':
            return self.generate_from_prompts_api(
                prompts=prompts,
                excel_path=excel_path,
                bearer_token=bearer_token
            )
        else:
            return self.generate_from_prompts(
                prompts=prompts,
                excel_path=excel_path,
                max_setup_retries=max_setup_retries
            )

    def generate_all(
        self,
        characters: bool = True,
        scenes: bool = True,
        start_scene: int = 1,
        end_scene: Optional[int] = None,
        overwrite: bool = False,
        bearer_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tao tat ca anh (nhan vat + scenes).
        Tu dong chon mode dua tren config (generation_mode).

        Args:
            characters: Tao anh nhan vat
            scenes: Tao anh scenes
            start_scene: Scene bat dau
            end_scene: Scene ket thuc
            overwrite: Ghi de
            bearer_token: Bearer token (chi can cho API mode)

        Returns:
            Dict voi ket qua
        """
        results = {
            "characters": {},
            "scenes": {},
        }

        mode = self._get_generation_mode()
        self._log(f"[GENERATE_ALL] Mode: {mode.upper()}")

        try:
            # AUTO-UPDATE: Them filename annotations vao prompts (neu chua co)
            # Giup Flow match uploaded reference images voi prompt
            excel_path = self._find_excel_file()
            if scenes and excel_path and excel_path.exists():
                self._log("[AUTO] Kiem tra va cap nhat filename annotations trong prompts...", "info")
                try:
                    from modules.prompts_generator import PromptsGenerator
                    pg = PromptsGenerator()
                    updated = pg.update_excel_prompts_with_annotations(str(excel_path))
                    if updated:
                        self._log("[AUTO] Da cap nhat prompts voi filename annotations", "success")
                    else:
                        self._log("[AUTO] Khong can cap nhat annotations (da co san hoac khong co ref_files)", "info")
                except ImportError:
                    self._log("[AUTO] Khong the import PromptsGenerator, bo qua auto-update", "warn")
                except Exception as e:
                    self._log(f"[AUTO] Loi khi cap nhat annotations: {e}", "warn")

            if characters:
                # Characters luon dung Chrome mode (can UI de handle consent)
                results["characters"] = self.generate_character_images(overwrite=overwrite)

            if scenes:
                # Scenes su dung mode tu config
                results["scenes"] = self.generate_images_auto(
                    start_scene=start_scene,
                    end_scene=end_scene,
                    overwrite=overwrite,
                    bearer_token=bearer_token
                )
        finally:
            # Dong browser khi xong (chi can cho Chrome mode)
            if mode == 'chrome':
                self.stop_browser()

        return results

    def _escape_js_string(self, s: str) -> str:
        """Escape string cho JavaScript."""
        return (s
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t"))

    # =========================================================================
    # API MODE - Direct API call without browser
    # =========================================================================

    def generate_scene_images_api(
        self,
        excel_path: Optional[Path] = None,
        start_scene: int = 1,
        end_scene: Optional[int] = None,
        overwrite: bool = False,
        bearer_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tao anh bang API mode - goi truc tiep batchGenerateImages API.

        Uu diem:
        - Nhanh hon Chrome mode (khong can khoi dong browser)
        - On dinh hon (khong bi loi UI)

        Nhuoc diem:
        - Can bearer token (het han sau ~1h)
        - Khong tu dong xu ly consent dialogs

        Args:
            excel_path: Duong dan file Excel
            start_scene: Scene bat dau (1-indexed)
            end_scene: Scene ket thuc (None = tat ca)
            overwrite: Ghi de anh da co
            bearer_token: Bearer token (bat buoc)

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("API MODE - TAO ANH BANG DIRECT API CALL")
        self._log("=" * 60)

        # Import GoogleFlowAPI
        try:
            from modules.google_flow_api import GoogleFlowAPI, AspectRatio
        except ImportError as e:
            return {"success": False, "error": f"Khong import duoc GoogleFlowAPI: {e}"}

        # Check bearer token
        if not bearer_token:
            # Thu lay tu config
            bearer_token = self.config.get('flow_bearer_token', '')

        if not bearer_token:
            return {
                "success": False,
                "error": "Can bearer token cho API mode. Lay token tu Settings > Token"
            }

        # Tim file Excel
        if excel_path is None:
            excel_path = self._find_excel_file()

        if excel_path is None or not excel_path.exists():
            return {"success": False, "error": "Khong tim thay file Excel"}

        self._log(f"Excel: {excel_path}")
        self._log(f"Project: {self.project_code}")
        self._log(f"Token: {bearer_token[:20]}...{bearer_token[-10:]}")

        # Create API client
        api = GoogleFlowAPI(
            bearer_token=bearer_token,
            project_id=self.project_code,
            timeout=self.config.get('flow_timeout', 120),
            verbose=self.verbose
        )

        # Map aspect ratio
        ar_setting = self.config.get('flow_aspect_ratio', 'landscape')
        ar_map = {
            'landscape': AspectRatio.LANDSCAPE,
            'portrait': AspectRatio.PORTRAIT,
            'square': AspectRatio.SQUARE,
        }
        aspect_ratio = ar_map.get(ar_setting, AspectRatio.LANDSCAPE)

        # Load Excel
        workbook = PromptWorkbook(excel_path)
        workbook.load_or_create()

        # Lay cac scene can tao anh
        all_scenes = workbook.get_scenes()
        scenes_to_process = []

        for scene in all_scenes:
            if scene.scene_id < start_scene:
                continue
            if end_scene is not None and scene.scene_id > end_scene:
                break
            if not scene.img_prompt:
                continue
            if scene.status_img == "done" and not overwrite:
                self.stats["skipped"] += 1
                continue
            scenes_to_process.append(scene)

        if not scenes_to_process:
            self._log("Khong co scene nao can tao anh", "warn")
            return {"success": True, "message": "No scenes to process"}

        self._log(f"Se tao {len(scenes_to_process)} anh bang API")
        self.stats["total"] = len(scenes_to_process)

        # Load media cache cho reference
        cached_media_names = self._load_media_cache()
        if cached_media_names:
            self._log(f"Loaded {len(cached_media_names)} media references")

        # Process tung scene
        for i, scene in enumerate(scenes_to_process):
            scene_id = str(scene.scene_id)
            prompt = scene.img_prompt

            self._log(f"\n[{i+1}/{len(scenes_to_process)}] Scene {scene_id}")
            self._log(f"Prompt ({len(prompt)} chars): {prompt[:100]}...")

            try:
                # Build image inputs from references
                image_inputs = []
                ref_str = getattr(scene, 'reference_files', '') or ''
                if ref_str:
                    try:
                        ref_files = json.loads(ref_str) if ref_str.startswith('[') else [f.strip() for f in ref_str.split(',') if f.strip()]
                    except:
                        ref_files = [f.strip() for f in str(ref_str).split(',') if f.strip()]

                    for ref_file in ref_files:
                        ref_id = ref_file.replace('.png', '').replace('.jpg', '')
                        # Check cache for media_name
                        if ref_id in cached_media_names:
                            media_info = cached_media_names[ref_id]
                            media_name = media_info.get('mediaName') if isinstance(media_info, dict) else media_info
                            if media_name:
                                from modules.google_flow_api import ImageInput, ImageInputType
                                image_inputs.append(ImageInput(
                                    name=media_name,
                                    input_type=ImageInputType.REFERENCE
                                ))
                                self._log(f"[REF] Using cached media: {ref_id}")

                # Generate image
                success, images, error = api.generate_images(
                    prompt=prompt,
                    count=self.config.get('flow_image_count', 2),
                    aspect_ratio=aspect_ratio,
                    image_inputs=[inp.to_dict() for inp in image_inputs] if image_inputs else None
                )

                if success and images:
                    # Download best image
                    output_file = self.img_path / f"{scene_id}.png"

                    downloaded = api.download_image(
                        images[0],  # Take first image
                        self.img_path,
                        scene_id
                    )

                    if downloaded:
                        # Update Excel
                        relative_path = f"img/{scene_id}.png"
                        workbook.update_scene(
                            scene.scene_id,
                            img_path=relative_path,
                            status_img="done"
                        )
                        workbook.save()

                        # Save media_name to cache
                        if images[0].media_name:
                            cached_media_names[scene_id] = {
                                'mediaName': images[0].media_name,
                                'seed': images[0].seed
                            }

                        self._log(f"OK - Da tao va luu anh: {downloaded}", "success")
                        self.stats["success"] += 1
                    else:
                        self._log("Loi download anh", "error")
                        workbook.update_scene(scene.scene_id, status_img="error")
                        workbook.save()
                        self.stats["failed"] += 1
                else:
                    self._log(f"Loi: {error}", "error")
                    workbook.update_scene(scene.scene_id, status_img="error")
                    workbook.save()
                    self.stats["failed"] += 1

                # Delay giua cac prompt
                delay = self.config.get('flow_delay', 3.0)
                if i < len(scenes_to_process) - 1:
                    time.sleep(delay)

            except Exception as e:
                self._log(f"Exception: {e}", "error")
                import traceback
                traceback.print_exc()
                workbook.update_scene(scene.scene_id, status_img="error")
                workbook.save()
                self.stats["failed"] += 1

        # Save updated media cache
        if cached_media_names:
            self._save_media_cache(cached_media_names)

        # Summary
        self._log("\n" + "=" * 60)
        self._log("HOAN THANH (API MODE)")
        self._log("=" * 60)
        self._log(f"Tong: {self.stats['total']}")
        self._log(f"Thanh cong: {self.stats['success']}")
        self._log(f"That bai: {self.stats['failed']}")
        self._log(f"Bo qua: {self.stats['skipped']}")

        return {
            "success": True,
            "stats": self.stats.copy()
        }

    def generate_from_prompts_api(
        self,
        prompts: List[Dict],
        excel_path: Optional[Path] = None,
        bearer_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Tao anh tu danh sach prompts bang API mode.

        Args:
            prompts: List prompts [{'id': '1', 'prompt': '...'}]
            excel_path: Duong dan Excel (de cap nhat status)
            bearer_token: Bearer token (bat buoc)

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("API MODE - TAO ANH TU PROMPTS")
        self._log("=" * 60)

        try:
            from modules.google_flow_api import GoogleFlowAPI, AspectRatio
        except ImportError as e:
            return {"success": False, "error": f"Khong import duoc GoogleFlowAPI: {e}"}

        if not bearer_token:
            bearer_token = self.config.get('flow_bearer_token', '')

        if not bearer_token:
            return {"success": False, "error": "Can bearer token cho API mode"}

        if not prompts:
            return {"success": False, "error": "Khong co prompts"}

        self._log(f"Tong: {len(prompts)} prompts")
        self._log(f"Token: {bearer_token[:20]}...{bearer_token[-10:]}")

        # Create API client
        api = GoogleFlowAPI(
            bearer_token=bearer_token,
            project_id=self.project_code,
            timeout=self.config.get('flow_timeout', 120),
            verbose=self.verbose
        )

        # Map aspect ratio
        ar_setting = self.config.get('flow_aspect_ratio', 'landscape')
        ar_map = {
            'landscape': AspectRatio.LANDSCAPE,
            'portrait': AspectRatio.PORTRAIT,
            'square': AspectRatio.SQUARE,
        }
        aspect_ratio = ar_map.get(ar_setting, AspectRatio.LANDSCAPE)

        # Reset stats
        self.stats = {"total": len(prompts), "success": 0, "failed": 0, "skipped": 0}

        # Load Excel workbook
        workbook = None
        if excel_path and Path(excel_path).exists():
            try:
                workbook = PromptWorkbook(excel_path)
                workbook.load_or_create()
            except Exception as e:
                self._log(f"Warning: Khong load duoc Excel: {e}", "warn")

        # Load media cache
        cached_media_names = self._load_media_cache()

        for i, prompt_data in enumerate(prompts):
            pid = str(prompt_data.get('id', i + 1))
            prompt = prompt_data.get('prompt', '')

            if not prompt:
                self._log(f"[{i+1}/{len(prompts)}] ID: {pid} - Skip (prompt rong)", "warn")
                self.stats["skipped"] += 1
                continue

            self._log(f"\n[{i+1}/{len(prompts)}] ID: {pid}")
            self._log(f"Prompt ({len(prompt)} chars): {prompt[:100]}...")

            try:
                # Generate
                success, images, error = api.generate_images(
                    prompt=prompt,
                    count=self.config.get('flow_image_count', 2),
                    aspect_ratio=aspect_ratio
                )

                if success and images:
                    # Determine output dir
                    is_character = pid.startswith('nv') or pid.startswith('loc')
                    out_dir = self.nv_path if is_character else self.img_path

                    downloaded = api.download_image(images[0], out_dir, pid)

                    if downloaded:
                        # Update Excel
                        if workbook and pid.isdigit():
                            scene_id = int(pid)
                            relative_path = f"img/{pid}.png"
                            workbook.update_scene(scene_id, img_path=relative_path, status_img="done")
                            workbook.save()

                        # Save media cache
                        if images[0].media_name:
                            cached_media_names[pid] = {
                                'mediaName': images[0].media_name,
                                'seed': images[0].seed
                            }

                        self._log(f"OK - Da tao: {downloaded}", "success")
                        self.stats["success"] += 1
                    else:
                        self._log("Loi download", "error")
                        self.stats["failed"] += 1
                else:
                    self._log(f"Loi: {error}", "error")
                    self.stats["failed"] += 1

                # Delay
                delay = self.config.get('flow_delay', 3.0)
                if i < len(prompts) - 1:
                    time.sleep(delay)

            except Exception as e:
                self._log(f"Exception: {e}", "error")
                self.stats["failed"] += 1

        # Save media cache
        if cached_media_names:
            self._save_media_cache(cached_media_names)

        # Summary
        self._log("\n" + "=" * 60)
        self._log("HOAN THANH (API MODE)")
        self._log("=" * 60)
        self._log(f"Tong: {self.stats['total']}")
        self._log(f"Thanh cong: {self.stats['success']}")
        self._log(f"That bai: {self.stats['failed']}")
        self._log(f"Bo qua: {self.stats['skipped']}")

        return {
            "success": True,
            "stats": self.stats.copy()
        }

    def __enter__(self):
        """Context manager entry."""
        self.start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_browser()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_browser_flow_generator(
    project_path: str,
    profile_name: str = "main",
    headless: bool = False,
    verbose: bool = True
) -> BrowserFlowGenerator:
    """
    Factory function de tao BrowserFlowGenerator.

    Args:
        project_path: Duong dan project
        profile_name: Ten Chrome profile
        headless: Chay an
        verbose: In log

    Returns:
        BrowserFlowGenerator instance
    """
    return BrowserFlowGenerator(
        project_path=project_path,
        profile_name=profile_name,
        headless=headless,
        verbose=verbose
    )


def generate_images_from_excel(
    project_path: str,
    profile_name: str = "main",
    headless: bool = False,
    characters: bool = True,
    scenes: bool = True,
    start_scene: int = 1,
    end_scene: Optional[int] = None,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Ham tien ich de tao anh tu Excel.

    Args:
        project_path: Duong dan project (PROJECTS/KA1-0001)
        profile_name: Ten Chrome profile
        headless: Chay an
        characters: Tao anh nhan vat
        scenes: Tao anh scenes
        start_scene: Scene bat dau
        end_scene: Scene ket thuc
        overwrite: Ghi de anh cu

    Returns:
        Dict voi ket qua
    """
    generator = BrowserFlowGenerator(
        project_path=project_path,
        profile_name=profile_name,
        headless=headless,
        verbose=True
    )

    return generator.generate_all(
        characters=characters,
        scenes=scenes,
        start_scene=start_scene,
        end_scene=end_scene,
        overwrite=overwrite
    )


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    print("""
+============================================================+
|      BROWSER FLOW GENERATOR - VE3 TOOL                     |
+============================================================+
|  Tao anh tu Excel bang browser automation                  |
|                                                            |
|  Usage:                                                    |
|    python browser_flow_generator.py <project_path>         |
|                                                            |
|  Options:                                                  |
|    --profile <name>    Chrome profile name (default: main) |
|    --headless          Chay an (khong hien UI)             |
|    --characters        Chi tao anh nhan vat                |
|    --scenes            Chi tao anh scenes                  |
|    --start N           Bat dau tu scene N                  |
|    --end N             Ket thuc o scene N                  |
|    --overwrite         Ghi de anh da co                    |
+============================================================+
""")

    if not SELENIUM_AVAILABLE:
        print("Error: Selenium chua duoc cai dat")
        print("Chay: pip install selenium undetected-chromedriver")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Vui long cung cap duong dan project")
        print("Vi du: python browser_flow_generator.py ./PROJECTS/KA1-0001")
        sys.exit(1)

    project_path = sys.argv[1]

    # Parse options
    profile_name = "main"
    headless = "--headless" in sys.argv
    do_characters = "--characters" in sys.argv or "--scenes" not in sys.argv
    do_scenes = "--scenes" in sys.argv or "--characters" not in sys.argv
    overwrite = "--overwrite" in sys.argv
    start_scene = 1
    end_scene = None

    for i, arg in enumerate(sys.argv):
        if arg == "--profile" and i + 1 < len(sys.argv):
            profile_name = sys.argv[i + 1]
        if arg == "--start" and i + 1 < len(sys.argv):
            start_scene = int(sys.argv[i + 1])
        if arg == "--end" and i + 1 < len(sys.argv):
            end_scene = int(sys.argv[i + 1])

    # Run
    results = generate_images_from_excel(
        project_path=project_path,
        profile_name=profile_name,
        headless=headless,
        characters=do_characters,
        scenes=do_scenes,
        start_scene=start_scene,
        end_scene=end_scene,
        overwrite=overwrite
    )

    # Exit code
    scenes_failed = results.get("scenes", {}).get("stats", {}).get("failed", 0)
    chars_failed = results.get("characters", {}).get("characters_failed", 0)

    sys.exit(0 if (scenes_failed + chars_failed) == 0 else 1)
