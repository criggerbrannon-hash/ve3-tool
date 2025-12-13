"""
VE3 Tool - Smart Auto Engine
============================
1 NUT LAM TAT CA:
- Input: Voice file
- Output: Tat ca anh (KHONG THIEU)

Flow thong minh:
1. Kiem tra thieu gi -> bao
2. [Song song] Lay token + Lam SRT
3. Lam prompts (AI API)
4. [Song song] Tao anh voi nhieu accounts
5. Retry neu fail -> dam bao 100% output
"""

import os
import json
import time
import shutil
import threading
from pathlib import Path
from typing import List, Dict, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Resource:
    """Tai nguyen (profile hoac API key)."""
    type: str  # 'profile', 'groq', 'gemini'
    value: str  # path hoac key
    token: str = ""
    project_id: str = ""
    status: str = "ready"  # ready, busy, exhausted, error
    fail_count: int = 0
    last_used: float = 0
    token_time: float = 0  # Thoi gian lay token (de check het han)


class SmartEngine:
    """
    Engine thong minh - dam bao output 100%.
    """

    # Token het han sau 50 phut (thuc te la ~1h nhung de an toan)
    TOKEN_EXPIRY_SECONDS = 50 * 60

    def __init__(self, config_path: str = None):
        # Support VE3_CONFIG_DIR environment variable
        if config_path:
            self.config_path = Path(config_path)
        else:
            config_dir = os.environ.get('VE3_CONFIG_DIR', 'config')
            self.config_path = Path(config_dir) / "accounts.json"

        # Token cache file
        self.tokens_path = self.config_path.parent / "tokens.json"

        self.chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        # Resources
        self.profiles: List[Resource] = []
        self.headless_accounts: List[Resource] = []  # Headless accounts (Playwright)
        self.deepseek_keys: List[Resource] = []
        self.groq_keys: List[Resource] = []
        self.gemini_keys: List[Resource] = []

        # Settings - TOI UU TOC DO (PARALLEL OPTIMIZED)
        self.parallel = 20  # Tang len 20 - dung TAT CA tokens co san
        self.delay = 0.3    # Giam xuong 0.3s - may khoe chay nhanh
        self.max_retries = 3
        self.use_threadpool = True  # Dung ThreadPoolExecutor (hieu qua hon threading.Thread)
        self.images_per_worker = 5  # So anh moi worker xu ly truoc khi chuyen
        self.use_headless = True  # Uu tien headless mode (chay an)

        # State
        self.stop_flag = False
        self.callback = None
        self._lock = threading.Lock()

        # Cache media_name per profile: {profile_name: {image_id: media_name}}
        # QUAN TRONG: media_name chi valid cho token da tao ra no
        self.media_name_cache = {}

        self.load_config()
        self.load_cached_tokens()  # Load tokens da luu
        self.load_media_name_cache()  # Load media_name cache

    def log(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{ts}] [{level}] {msg}"
        if self.callback:
            self.callback(full_msg)
        else:
            # Fallback to print only when no GUI callback
            print(full_msg)

    def load_config(self):
        """Load config."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.chrome_path = data.get('chrome_path', self.chrome_path)

            # Load headless accounts (KHUYÊN DÙNG - chạy ẩn)
            for acc_id in data.get('headless_accounts', []):
                if acc_id and not acc_id.startswith('THAY_BANG'):
                    self.headless_accounts.append(Resource(
                        type='headless',
                        value=acc_id
                    ))

            # Load Chrome profiles (backup - khi headless không được)
            for i, p in enumerate(data.get('chrome_profiles', [])):
                path = p if isinstance(p, str) else p.get('path', '')
                # Skip placeholders
                if not path or path.startswith('THAY_BANG'):
                    continue
                if Path(path).exists():
                    self.profiles.append(Resource(
                        type='profile',
                        value=path
                    ))

            # Load API keys
            api = data.get('api_keys', {})

            # DeepSeek (uu tien cao nhat - re va on dinh)
            for k in api.get('deepseek', []):
                if k and not k.startswith('THAY_BANG') and not k.startswith('sk-YOUR'):
                    self.deepseek_keys.append(Resource(type='deepseek', value=k))

            for k in api.get('groq', []):
                if k and not k.startswith('THAY_BANG') and not k.startswith('gsk_YOUR'):
                    self.groq_keys.append(Resource(type='groq', value=k))

            for k in api.get('gemini', []):
                if k and not k.startswith('THAY_BANG') and not k.startswith('AIzaSy_YOUR'):
                    self.gemini_keys.append(Resource(type='gemini', value=k))

            # Settings
            settings = data.get('settings', {})
            self.parallel = settings.get('parallel', 2)
            self.delay = settings.get('delay_between_images', 2)
            self.use_headless = settings.get('use_headless', True)  # Mac dinh dung headless

        except Exception as e:
            self.log(f"Load config error: {e}", "ERROR")

    # ========== TOKEN CACHING ==========

    def load_cached_tokens(self):
        """Load tokens da luu tu file."""
        if not self.tokens_path.exists():
            return

        try:
            with open(self.tokens_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            now = time.time()
            loaded = 0
            expired = 0

            for profile in self.profiles:
                profile_name = Path(profile.value).name
                if profile_name in data:
                    token_data = data[profile_name]
                    token_time = token_data.get('time', 0)

                    # Check het han chua (50 phut)
                    if now - token_time < self.TOKEN_EXPIRY_SECONDS:
                        profile.token = token_data.get('token', '')
                        profile.project_id = token_data.get('project_id', '')
                        profile.token_time = token_time
                        loaded += 1
                    else:
                        expired += 1

            if loaded > 0:
                self.log(f"Loaded {loaded} cached tokens ({expired} expired)")

        except Exception as e:
            self.log(f"Load cached tokens error: {e}", "WARN")

    # ========== MEDIA NAME CACHING ==========
    # QUAN TRONG: media_name chi valid cho token da tao ra no
    # Khi generate anh nv/loc -> luu media_name
    # Khi generate scene -> dung media_name tu cung token

    def load_media_name_cache(self):
        """Load media_name cache tu file."""
        cache_path = self.config_path.parent / "media_names.json"
        if not cache_path.exists():
            return

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                self.media_name_cache = json.load(f)
            total = sum(len(v) for v in self.media_name_cache.values())
            if total > 0:
                self.log(f"Loaded {total} cached media_names")
        except Exception as e:
            self.log(f"Load media_name cache error: {e}", "WARN")

    def save_media_name_cache(self):
        """Luu media_name cache vao file."""
        try:
            cache_path = self.config_path.parent / "media_names.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(self.media_name_cache, f, indent=2)
        except Exception as e:
            self.log(f"Save media_name cache error: {e}", "WARN")

    def get_cached_media_name(self, profile: 'Resource', image_id: str) -> str:
        """Lay media_name tu cache cho profile + image_id."""
        profile_name = Path(profile.value).name
        return self.media_name_cache.get(profile_name, {}).get(image_id, "")

    def set_cached_media_name(self, profile: 'Resource', image_id: str, media_name: str):
        """Luu media_name vao cache."""
        profile_name = Path(profile.value).name
        if profile_name not in self.media_name_cache:
            self.media_name_cache[profile_name] = {}
        self.media_name_cache[profile_name][image_id] = media_name
        self.save_media_name_cache()

    def save_cached_tokens(self):
        """Luu tokens vao file de dung lai."""
        try:
            data = {}
            for profile in self.profiles:
                if profile.token:
                    profile_name = Path(profile.value).name
                    data[profile_name] = {
                        'token': profile.token,
                        'project_id': profile.project_id,
                        'time': profile.token_time or time.time()
                    }

            self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tokens_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            self.log(f"Saved {len(data)} tokens to cache")

        except Exception as e:
            self.log(f"Save tokens error: {e}", "WARN")

    def is_token_valid(self, profile: Resource) -> bool:
        """Check token con valid khong (chua het han + API hoat dong)."""
        if not profile.token:
            return False

        # Check het han chua
        if profile.token_time:
            age = time.time() - profile.token_time
            if age > self.TOKEN_EXPIRY_SECONDS:
                self.log(f"Token {Path(profile.value).name} het han ({int(age/60)} phut)")
                profile.token = ""
                return False

        # Quick API test (optional - co the bo qua de nhanh hon)
        # TODO: Them API test neu can

        return True

    def get_valid_token_count(self) -> int:
        """Dem so token con valid."""
        return sum(1 for p in self.profiles if self.is_token_valid(p))

    def check_requirements(self, has_voice: bool = True) -> Tuple[bool, List[str]]:
        """
        Kiem tra thieu gi.
        Return: (ok, list of missing items)
        """
        missing = []

        if not self.profiles:
            missing.append("Chrome profiles (sua config/accounts.json)")

        if has_voice and not self.deepseek_keys and not self.groq_keys and not self.gemini_keys:
            missing.append("AI API keys cho voice (DeepSeek RE: platform.deepseek.com/api_keys)")

        if not Path(self.chrome_path).exists():
            missing.append(f"Chrome: {self.chrome_path}")

        return len(missing) == 0, missing

    # ========== RESOURCE MANAGEMENT ==========

    def get_available_profile(self) -> Optional[Resource]:
        """Lay profile san sang."""
        with self._lock:
            for p in self.profiles:
                if p.status == 'ready' and p.token:
                    return p
            # Neu khong co token, tra ve profile dau tien de lay token
            for p in self.profiles:
                if p.status in ['ready', 'error'] and p.fail_count < self.max_retries:
                    return p
        return None

    def get_available_ai_key(self) -> Optional[Resource]:
        """Lay AI key san sang (uu tien DeepSeek vi re va on dinh)."""
        with self._lock:
            # Uu tien DeepSeek (re nhat, on dinh)
            for k in self.deepseek_keys:
                if k.status == 'ready' and k.fail_count < self.max_retries:
                    return k
            # Fallback Groq (free nhung hay rate limit)
            for k in self.groq_keys:
                if k.status == 'ready' and k.fail_count < self.max_retries:
                    return k
            # Fallback Gemini
            for k in self.gemini_keys:
                if k.status == 'ready' and k.fail_count < self.max_retries:
                    return k
        return None

    def mark_resource_used(self, res: Resource, success: bool):
        """Danh dau resource da dung."""
        with self._lock:
            res.last_used = time.time()
            if success:
                res.fail_count = 0
                res.status = 'ready'
            else:
                res.fail_count += 1
                if res.fail_count >= self.max_retries:
                    res.status = 'exhausted'
                    self.log(f"Resource exhausted: {res.type} - {res.value[:20]}...", "WARN")

    def reset_resources(self):
        """Reset tat ca resources."""
        with self._lock:
            for r in self.profiles + self.deepseek_keys + self.groq_keys + self.gemini_keys:
                r.status = 'ready'
                r.fail_count = 0

    # ========== TOKEN MANAGEMENT ==========

    def get_token_headless(self, account: Resource) -> bool:
        """
        Lay token bang HEADLESS mode (chay an).
        Khong mo browser window.
        """
        try:
            from modules.headless_token import HeadlessTokenExtractor
        except ImportError:
            self.log("Chua cai Playwright! Chay: pip install playwright && playwright install chromium", "ERROR")
            return False

        self.log(f"[Headless] Lay token: {account.value}...")

        try:
            extractor = HeadlessTokenExtractor(account.value)

            # Check co cookies chua
            if not extractor.has_valid_cookies():
                self.log(f"[Headless] {account.value} chua dang nhap!", "WARN")
                self.log(f"  -> Chay: python -m modules.headless_token login {account.value}", "WARN")
                return False

            # Lay token (headless)
            token, proj_id, error = extractor.extract_token(headless=True)

            if token:
                account.token = token
                account.project_id = proj_id or ""
                account.token_time = time.time()
                account.status = 'ready'
                self.log(f"[Headless] OK: {account.value} - Token OK!", "OK")
                self.save_cached_tokens()
                return True
            elif error == "need_login":
                self.log(f"[Headless] {account.value} can dang nhap lai!", "WARN")
                self.log(f"  -> Chay: python -m modules.headless_token login {account.value}", "WARN")
                return False
            else:
                account.fail_count += 1
                self.log(f"[Headless] FAIL: {account.value} - {error}", "ERROR")
                return False

        except Exception as e:
            account.fail_count += 1
            self.log(f"[Headless] ERROR: {e}", "ERROR")
            return False

    def get_token_for_profile(self, profile: Resource) -> bool:
        """Lay token cho 1 profile (Chrome visible)."""
        from modules.auto_token import ChromeAutoToken

        self.log(f"[Chrome] Lay token: {Path(profile.value).name}...")

        try:
            extractor = ChromeAutoToken(
                chrome_path=self.chrome_path,
                profile_path=profile.value,
                auto_close=True  # Tu dong dong Chrome sau khi lay token
            )

            token, proj_id, error = extractor.extract_token(callback=self.callback)

            if token:
                profile.token = token
                profile.project_id = proj_id or ""
                profile.token_time = time.time()  # Luu thoi gian lay token
                profile.status = 'ready'
                self.log(f"[Chrome] OK: {Path(profile.value).name} - Token OK!", "OK")
                self.save_cached_tokens()  # Luu ngay vao file
                return True
            else:
                profile.fail_count += 1
                self.log(f"[Chrome] FAIL: {Path(profile.value).name} - {error}", "ERROR")
                return False

        except Exception as e:
            profile.fail_count += 1
            self.log(f"[Chrome] ERROR: {e}", "ERROR")
            return False

    def get_all_tokens(self) -> int:
        """
        Lay token cho tat ca accounts.
        Uu tien: Headless (an) > Chrome profiles (visible)
        """
        success = 0
        total = len(self.headless_accounts) + len(self.profiles)

        if total == 0:
            self.log("Khong co account nao! Cau hinh config/accounts.json", "WARN")
            return 0

        # 1. HEADLESS ACCOUNTS (uu tien - chay AN)
        if self.use_headless and self.headless_accounts:
            self.log(f"=== LAY TOKEN HEADLESS ({len(self.headless_accounts)} accounts) ===")

            for i, account in enumerate(self.headless_accounts):
                if self.stop_flag:
                    break

                self.log(f"[{i+1}/{len(self.headless_accounts)}] {account.value}")

                if self.is_token_valid(account):
                    self.log(f"  -> Da co token valid, skip")
                    success += 1
                    continue

                if self.get_token_headless(account):
                    success += 1

                # Delay nho giua cac accounts
                if i < len(self.headless_accounts) - 1:
                    time.sleep(0.5)

        # 2. CHROME PROFILES (backup - khi headless khong du)
        if self.profiles and (not self.use_headless or success < len(self.headless_accounts)):
            self.log(f"=== LAY TOKEN CHROME ({len(self.profiles)} profiles) ===")

            for i, profile in enumerate(self.profiles):
                if self.stop_flag:
                    break

                self.log(f"[{i+1}/{len(self.profiles)}] {Path(profile.value).name}")

                if self.is_token_valid(profile):
                    self.log(f"  -> Da co token valid, skip")
                    success += 1
                    continue

                if profile.token:
                    self.log(f"  -> Token het han, lay moi...")

                if self.get_token_for_profile(profile):
                    success += 1

                if i < len(self.profiles) - 1:
                    time.sleep(1)

        self.log(f"=== XONG: {success}/{total} tokens ===")
        return success

    def refresh_token_if_needed(self, profile: Resource) -> bool:
        """Refresh token neu can - check expiry."""
        if not self.is_token_valid(profile):
            return self.get_token_for_profile(profile)
        return True

    def _get_other_valid_profile(self, exclude_profile: Resource) -> Optional[Resource]:
        """Tim profile khac co token con valid."""
        with self._lock:
            for p in self.profiles:
                if p != exclude_profile and p.token and self.is_token_valid(p):
                    return p
        return None

    def refresh_expired_tokens(self) -> int:
        """
        Kiem tra va refresh cac token da het han.
        Goi khi khoi dong tool.

        Returns:
            So token da refresh thanh cong
        """
        refreshed = 0
        expired_profiles = []

        # Tim cac profile co token het han
        for profile in self.profiles:
            if profile.token and not self.is_token_valid(profile):
                expired_profiles.append(profile)
                profile.token = ""  # Clear expired token

        if not expired_profiles:
            return 0

        self.log(f"Tim thay {len(expired_profiles)} token het han, dang refresh...")

        for profile in expired_profiles:
            if self.stop_flag:
                break
            if self.get_token_for_profile(profile):
                refreshed += 1

        self.log(f"Da refresh {refreshed}/{len(expired_profiles)} tokens")
        return refreshed

    # ========== SRT PROCESSING ==========

    def make_srt(self, voice_path: Path, srt_path: Path) -> bool:
        """Tao SRT tu voice."""
        if srt_path.exists():
            self.log(f"SRT da ton tai: {srt_path.name}")
            return True

        self.log("Transcribe voice -> SRT...")

        try:
            from modules.voice_to_srt import VoiceToSrt
            conv = VoiceToSrt(model_name="base", language="vi")
            conv.transcribe(voice_path, srt_path)
            self.log(f"OK: {srt_path.name}", "OK")
            return True
        except Exception as e:
            self.log(f"SRT error: {e}", "ERROR")
            return False

    # ========== PROMPT GENERATION ==========

    def make_prompts(self, proj_dir: Path, name: str, excel_path: Path) -> bool:
        """Tao prompts tu SRT. Retry voi cac AI keys khac neu fail."""
        if excel_path.exists():
            self.log(f"Prompts da ton tai: {excel_path.name}")
            return True

        self.log("Generate prompts...")

        # Load config
        import yaml
        cfg = {}
        cfg_file = Path("config/settings.yaml")
        if cfg_file.exists():
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}

        # Add API keys (thu tu uu tien: Gemini > Groq > DeepSeek)
        cfg['gemini_api_keys'] = [k.value for k in self.gemini_keys if k.status != 'exhausted']
        cfg['groq_api_keys'] = [k.value for k in self.groq_keys if k.status != 'exhausted']
        cfg['deepseek_api_keys'] = [k.value for k in self.deepseek_keys if k.status != 'exhausted']
        cfg['preferred_provider'] = 'gemini' if self.gemini_keys else ('groq' if self.groq_keys else 'deepseek')

        # Retry with different keys
        for attempt in range(self.max_retries):
            if self.stop_flag:
                return False

            ai_key = self.get_available_ai_key()
            if not ai_key:
                self.log("Het AI keys!", "ERROR")
                return False

            self.log(f"Thu AI key: {ai_key.type} (attempt {attempt+1})")

            try:
                from modules.prompts_generator import PromptGenerator
                gen = PromptGenerator(cfg)

                if gen.generate_for_project(proj_dir, name):
                    self.mark_resource_used(ai_key, True)
                    self.log(f"OK: {excel_path.name}", "OK")
                    return True
                else:
                    self.mark_resource_used(ai_key, False)

            except Exception as e:
                self.log(f"Prompt error: {e}", "ERROR")
                self.mark_resource_used(ai_key, False)

        return False

    # ========== IMAGE GENERATION ==========

    def generate_single_image(self, prompt_data: Dict, profile: Resource) -> tuple:
        """
        Tao 1 anh voi 1 profile, ho tro reference images.

        FLOW QUAN TRONG:
        1. Neu la nv*/loc* -> generate va LUU media_name vao cache
        2. Neu la scene -> dung media_name tu cache (cung profile/token)
           Neu khong co trong cache -> upload de lay media_name moi

        Returns:
            tuple: (success: bool, token_expired: bool)
        """
        from modules.google_flow_api import GoogleFlowAPI, AspectRatio, ImageInput

        pid = prompt_data.get('id', '')
        prompt = prompt_data.get('prompt', '')
        output = prompt_data.get('output_path', '')
        reference_files = prompt_data.get('reference_files', '')
        nv_path = prompt_data.get('nv_path', '')

        if not prompt or not output:
            return False, False

        # Skip if exists
        if Path(output).exists():
            return True, False

        is_reference_image = pid.startswith('nv') or pid.startswith('loc')

        try:
            # Bat verbose cho nv/loc de debug media_name
            api = GoogleFlowAPI(
                bearer_token=profile.token,
                project_id=profile.project_id,
                verbose=is_reference_image  # Verbose for reference images to debug
            )

            Path(output).parent.mkdir(parents=True, exist_ok=True)

            # === SCENE IMAGES: Su dung reference images ===
            image_inputs = []
            if nv_path and not is_reference_image:
                # Parse reference_files (JSON array or comma-separated)
                file_list = []
                if reference_files:
                    try:
                        parsed = json.loads(reference_files)
                        if isinstance(parsed, list):
                            file_list = parsed
                        elif isinstance(parsed, str):
                            file_list = [parsed]
                    except (json.JSONDecodeError, TypeError):
                        file_list = [f.strip() for f in str(reference_files).split(",") if f.strip()]

                # FALLBACK: Dam bao LUON co nhan vat trong reference
                has_character = any(f.lower().startswith('nv') for f in file_list)

                if not file_list:
                    # Khong co reference nao -> dung nvc
                    file_list = ["nvc.png"]
                    self.log(f"  -> No reference, using default nvc.png")
                elif not has_character:
                    # Chi co loc, khong co nhan vat -> them nvc vao dau
                    file_list.insert(0, "nvc.png")
                    self.log(f"  -> No character in refs, adding nvc.png → {file_list}")

                # Tim media_name cho moi reference image
                # LUU Y: API CHI CHAP NHAN media_name, KHONG chap nhan base64!
                skipped_refs = []
                for filename in file_list:
                    # Extract image_id tu filename (vd: "nv1.png" -> "nv1")
                    image_id = Path(filename).stem

                    # CHI dung cached media_name - base64 KHONG hoat dong
                    cached_media_name = self.get_cached_media_name(profile, image_id)

                    if cached_media_name:
                        # Co trong cache -> dung luon
                        image_inputs.append(ImageInput(name=cached_media_name))
                        self.log(f"  -> Ref OK: {image_id}")
                    else:
                        # Khong co media_name -> SKIP (khong the dung base64)
                        skipped_refs.append(image_id)

                if skipped_refs:
                    self.log(f"  -> SKIP refs (no media_name): {skipped_refs}", "WARN")
                    self.log(f"  -> Tao anh KHONG CO reference (chua co media_name)", "WARN")
                    # Clear image_inputs neu co bat ky ref nao thieu
                    # Vi API yeu cau TAT CA refs phai co media_name
                    image_inputs = []

                if image_inputs:
                    self.log(f"  -> Using {len(image_inputs)} reference images for {pid}")

            # === GENERATE IMAGE ===
            success, images, error = api.generate_images(
                prompt=prompt,
                count=1,
                aspect_ratio=AspectRatio.LANDSCAPE,
                image_inputs=image_inputs if image_inputs else None
            )

            if success and images:
                # === DEBUG: Xem API tra ve gi ===
                img = images[0]
                self.log(f"  -> DEBUG: media_name={img.media_name}, media_id={img.media_id}, workflow_id={img.workflow_id}")

                # === LUU MEDIA_NAME neu la nv/loc ===
                if is_reference_image:
                    # Thu lay media_name, fallback to workflow_id or media_id
                    ref_id = img.media_name or img.workflow_id or img.media_id
                    if ref_id:
                        self.set_cached_media_name(profile, pid, ref_id)
                        self.log(f"  -> Saved ref_id for {pid}: {ref_id[:40]}...")
                    else:
                        self.log(f"  -> WARNING: No identifier returned for {pid}!", "WARN")
                        self.log(f"  -> Available: media_name={img.media_name}, workflow_id={img.workflow_id}, media_id={img.media_id}", "DEBUG")

                # Download image
                downloaded = api.download_image(images[0], Path(output).parent, pid)
                if downloaded:
                    # Rename to correct filename if needed
                    if downloaded.exists() and str(downloaded) != output:
                        if Path(output).exists():
                            Path(output).unlink()
                        downloaded.rename(output)
                    return True, False
                else:
                    self.log(f"Download failed {pid}", "ERROR")
                    return False, False
            else:
                # Check if token expired
                error_str = str(error).lower()
                token_expired = 'expired' in error_str or 'unauthorized' in error_str or '401' in error_str or 'authentication' in error_str
                if token_expired:
                    self.log(f"Token het han cho {pid}, can refresh", "WARN")
                    profile.token = ""  # Clear expired token
                else:
                    self.log(f"Generate failed {pid}: {error}", "ERROR")
                return False, token_expired

        except Exception as e:
            error_str = str(e).lower()
            token_expired = 'expired' in error_str or 'unauthorized' in error_str or '401' in error_str or 'authentication' in error_str
            if token_expired:
                self.log(f"Token het han cho {pid}", "WARN")
                profile.token = ""
            else:
                self.log(f"Image error {pid}: {e}", "ERROR")
            return False, token_expired

    def generate_images_parallel(self, prompts: List[Dict]) -> Dict:
        """
        Tao anh - DUNG 1 PROFILE DUY NHAT.
        Dam bao media_name consistent (cung token tao ref va scene).

        DON GIAN & AN TOAN:
        - 1 voice = 1 profile
        - Tat ca anh (nv/loc + scenes) dung chung 1 profile
        - media_name luon valid vi cung token
        """
        self.log(f"=== TAO {len(prompts)} ANH (1 PROFILE) ===")

        # Sort: nv/loc truoc, scene sau (de co media_name khi tao scene)
        def sort_key(p):
            pid = p.get('id', '')
            if pid.startswith('nv'):
                return (0, pid)  # nv first
            elif pid.startswith('loc'):
                return (1, pid)  # loc second
            else:
                return (2, pid)  # scenes last

        sorted_prompts = sorted(prompts, key=sort_key)

        return self._generate_images_single_profile(sorted_prompts)

    def _generate_images_single_profile(self, prompts: List[Dict]) -> Dict:
        """
        Tao TAT CA images bang 1 PROFILE DUY NHAT.
        Don gian, an toan, media_name luon consistent.
        """
        results = {"success": 0, "failed": 0, "pending": list(prompts)}

        # Loop until all done or no resources left
        attempt = 0
        while results["pending"] and attempt < self.max_retries * 2:
            if self.stop_flag:
                break

            attempt += 1
            self.log(f"=== ROUND {attempt} - {len(results['pending'])} pending ===")

            # Get 1 profile with valid token
            all_accounts = self.headless_accounts + self.profiles
            active_profile = None
            for p in all_accounts:
                if p.token and p.status != 'exhausted':
                    active_profile = p
                    break

            if not active_profile:
                self.log("Khong co account nao co token!", "WARN")
                n = self.get_all_tokens()
                if n == 0:
                    break
                for p in all_accounts:
                    if p.token:
                        active_profile = p
                        break

            if not active_profile:
                break

            profile_name = Path(active_profile.value).name
            self.log(f"Dung profile: {profile_name}")

            # Process images sequentially with 1 profile
            pending = results["pending"]
            results["pending"] = []
            done_count = 0

            for prompt_data in pending:
                if self.stop_flag:
                    results["pending"].append(prompt_data)
                    continue

                pid = prompt_data.get('id', '')
                self.log(f"[{pid}] Dang tao...")

                # Check token still valid
                if not active_profile.token:
                    self.log(f"[{pid}] Token het han, dung lai!", "WARN")
                    results["pending"].append(prompt_data)
                    # Add remaining to pending
                    idx = pending.index(prompt_data)
                    results["pending"].extend(pending[idx+1:])
                    break

                success, token_expired = self.generate_single_image(prompt_data, active_profile)

                if token_expired:
                    active_profile.token = ""
                    self.log(f"[{pid}] Token het han!", "WARN")
                    results["pending"].append(prompt_data)
                    # Add remaining to pending
                    idx = pending.index(prompt_data)
                    results["pending"].extend(pending[idx+1:])
                    break

                if success:
                    self.log(f"[{pid}] OK!", "OK")
                    done_count += 1
                    results["success"] += 1
                else:
                    self.log(f"[{pid}] FAIL", "WARN")
                    results["pending"].append(prompt_data)

                # Small delay
                time.sleep(self.delay)

                # Progress log
                if done_count % 5 == 0:
                    self.log(f"[Progress] {done_count}/{len(pending)}")

            self.log(f"Round {attempt}: +{done_count} OK, {len(results['pending'])} pending")

            # If still have pending, wait a bit before retry
            if results["pending"]:
                time.sleep(1)

        results["failed"] = len(results["pending"])
        self.log(f"=== XONG: {results['success']} OK, {results['failed']} FAIL ===")

        return results

    # ========== MAIN PIPELINE ==========

    def run(
        self,
        input_path: str,
        output_dir: str = None,
        callback: Callable = None
    ) -> Dict:
        """
        PIPELINE LINH HOAT - bat dau ngay khi co 1 token.

        Flow moi:
        1. Check requirements
        2. SONG SONG: Lay 1 token + Lam SRT + Lam prompts
        3. Khi co 1 token + prompts -> BAT DAU TAO ANH NGAY
        4. SONG SONG: Tiep tuc lay them token + Tao anh
        5. Ket thuc khi het prompts

        Args:
            input_path: Voice file (.mp3, .wav) hoac Excel (.xlsx)
            output_dir: Thu muc output (optional)
            callback: Ham log callback

        Returns:
            Dict with success/failed counts
        """
        self.callback = callback
        self.stop_flag = False

        inp = Path(input_path)
        ext = inp.suffix.lower()
        name = inp.stem

        # Setup output dir
        if output_dir:
            proj_dir = Path(output_dir)
        else:
            proj_dir = Path("PROJECTS") / name

        proj_dir.mkdir(parents=True, exist_ok=True)
        for d in ["srt", "prompts", "nv", "img"]:
            (proj_dir / d).mkdir(exist_ok=True)

        excel_path = proj_dir / "prompts" / f"{name}_prompts.xlsx"
        srt_path = proj_dir / "srt" / f"{name}.srt"

        self.log("="*50)
        self.log(f"VE3 TOOL - FAST PIPELINE")
        self.log(f"INPUT: {inp}")
        self.log(f"OUTPUT: {proj_dir}")
        self.log("="*50)

        # === 1. CHECK REQUIREMENTS ===
        self.log("[STEP 1] Kiem tra yeu cau...")

        ok, missing = self.check_requirements(has_voice=(ext in ['.mp3', '.wav']))
        if not ok:
            self.log("THIEU:", "ERROR")
            for m in missing:
                self.log(f"  - {m}", "ERROR")
            return {"error": "missing_requirements", "missing": missing}

        valid_tokens = self.get_valid_token_count()
        self.log(f"  Profiles: {len(self.profiles)} ({valid_tokens} tokens da co)")
        self.log(f"  DeepSeek keys: {len(self.deepseek_keys)}")
        self.log(f"  Groq keys: {len(self.groq_keys)}")
        self.log(f"  Gemini keys: {len(self.gemini_keys)}")

        # Refresh expired tokens at startup
        self.refresh_expired_tokens()

        # === 2. SONG SONG: Token + SRT + Prompts ===
        self.log("[STEP 2] SONG SONG: Token + SRT + Prompts...")

        voice_path = None
        if ext in ['.mp3', '.wav']:
            voice_path = proj_dir / f"{name}{ext}"
            if inp != voice_path:
                shutil.copy2(inp, voice_path)

        # Results containers
        srt_done = [srt_path.exists()]
        prompts_done = [excel_path.exists()]
        tokens_done = [False]
        tokens_count = [0]

        # Thread 1: Lay TAT CA tokens (prefetch) - khong can cho SRT/Prompts
        # Lam song song vi lay token can mouse, SRT/Prompts khong can
        def prefetch_all_tokens():
            """Prefetch tat ca tokens truoc khi bat dau tao anh."""
            self.log("[PREFETCH] Bat dau lay tokens cho tat ca profiles...")
            count = 0

            for i, profile in enumerate(self.profiles):
                if self.stop_flag:
                    break

                # Skip neu token con valid
                if self.is_token_valid(profile):
                    self.log(f"[PREFETCH] Profile #{i+1}: Token valid, skip")
                    count += 1
                    continue

                self.log(f"[PREFETCH] Profile #{i+1}/{len(self.profiles)}: Dang lay token...")
                if self.get_token_for_profile(profile):
                    count += 1
                    self.log(f"[PREFETCH] Profile #{i+1}: OK!")
                else:
                    self.log(f"[PREFETCH] Profile #{i+1}: FAIL!", "WARN")

                # Delay ngan giua cac profiles
                if i < len(self.profiles) - 1:
                    time.sleep(0.5)

            tokens_count[0] = count
            tokens_done[0] = True
            self.log(f"[PREFETCH] XONG: {count}/{len(self.profiles)} tokens ready")

        # Thread 2: Lam SRT (khong can mouse)
        def do_srt():
            if voice_path and not srt_path.exists():
                srt_done[0] = self.make_srt(voice_path, srt_path)
            else:
                srt_done[0] = True

        # Thread 3: Lam Prompts (sau khi SRT xong, khong can mouse)
        def do_prompts():
            # Doi SRT
            while not srt_done[0] and not self.stop_flag:
                time.sleep(0.5)

            if ext == '.xlsx':
                if inp != excel_path:
                    shutil.copy2(inp, excel_path)
                prompts_done[0] = True
            elif srt_done[0] and not excel_path.exists():
                prompts_done[0] = self.make_prompts(proj_dir, name, excel_path)
            else:
                prompts_done[0] = excel_path.exists()

        # Start threads - TAT CA CHAY SONG SONG
        self.log("[STEP 2] SONG SONG: SRT + Prompts + Prefetch Tokens...")
        t1 = threading.Thread(target=prefetch_all_tokens, daemon=True)
        t2 = threading.Thread(target=do_srt, daemon=True)
        t3 = threading.Thread(target=do_prompts, daemon=True)

        t1.start()
        t2.start()
        t3.start()

        threads = [t1, t2, t3]

        # Doi ca 3 xong
        for t in threads:
            t.join()

        # Check results
        if not srt_done[0] and ext in ['.mp3', '.wav']:
            return {"error": "srt_failed"}

        if not prompts_done[0]:
            return {"error": "prompts_failed"}

        # Check tokens (da prefetch xong)
        has_token = any(p.token for p in self.profiles)
        if not has_token:
            self.log("Khong lay duoc token nao!", "ERROR")
            return {"error": "no_tokens"}

        self.log(f"[TOKENS] Da co {tokens_count[0]}/{len(self.profiles)} tokens san sang")

        # === 3. LOAD PROMPTS ===
        self.log("[STEP 3] Load prompts...")

        prompts = self._load_prompts(excel_path, proj_dir)

        if not prompts:
            return {"error": "no_prompts"}

        self.log(f"  Tong: {len(prompts)} prompts")

        # Filter existing
        prompts = [p for p in prompts if not Path(p['output_path']).exists()]
        self.log(f"  Can tao: {len(prompts)} anh")

        if not prompts:
            self.log("Tat ca anh da ton tai!", "OK")
            return {"success": 0, "failed": 0, "skipped": "all_exist"}

        # === 4. TAO ANH (Tokens da duoc prefetch) ===
        self.log("[STEP 4] Tao anh (tokens da san sang)...")

        # Tao anh - khong can lay token nua vi da prefetch o Step 2
        results = self.generate_images_parallel(prompts)

        # === 5. FINAL CHECK ===
        self.log("[STEP 5] Kiem tra ket qua...")

        if results["failed"] > 0:
            self.log(f"CON {results['failed']} ANH CHUA XONG!", "WARN")
        else:
            self.log("TAT CA ANH DA HOAN THANH!", "OK")

        # === 6. EXPORT TXT & SRT ===
        self.log("[STEP 6] Xuat TXT & SRT...")
        self._export_scenes(excel_path, proj_dir, name)

        return results

    def _export_scenes(self, excel_path: Path, proj_dir: Path, name: str) -> None:
        """Export scenes ra TXT va SRT de ho tro video editing."""
        try:
            from modules.excel_manager import PromptWorkbook

            wb = PromptWorkbook(excel_path)
            wb.load_or_create()

            # Export TXT - danh sach phan canh
            txt_path = proj_dir / f"{name}_scenes.txt"
            if wb.export_scenes_txt(txt_path):
                self.log(f"  -> TXT: {txt_path.name}", "OK")

            # Export SRT - thoi gian phan canh
            srt_output_path = proj_dir / f"{name}_scenes.srt"
            if wb.export_scenes_srt(srt_output_path):
                self.log(f"  -> SRT: {srt_output_path.name}", "OK")

        except Exception as e:
            self.log(f"  Export error: {e}", "WARN")

    def _load_prompts(self, excel_path: Path, proj_dir: Path) -> List[Dict]:
        """Load prompts tu Excel - doc TAT CA sheets."""
        import openpyxl

        prompts = []
        wb = openpyxl.load_workbook(excel_path)

        self.log(f"Excel co {len(wb.sheetnames)} sheets: {wb.sheetnames}")

        # Doc TAT CA sheets
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]

            # Get headers
            headers = []
            for cell in ws[1]:
                headers.append(cell.value)

            self.log(f"  Sheet '{sheet_name}' headers: {headers}")

            if not headers or all(h is None for h in headers):
                self.log(f"  -> Skip: no headers")
                continue

            # Tim cot ID, Prompt, va reference_files
            id_col = None
            prompt_col = None
            ref_col = None  # reference_files column

            for i, h in enumerate(headers):
                if h is None:
                    continue
                h_lower = str(h).lower().strip()

                # Tim cot ID
                if id_col is None:
                    if h_lower == 'id' or h_lower == 'scene_id' or h_lower == 'sceneid':
                        id_col = i
                    elif 'id' in h_lower and ('scene' in h_lower or 'nv' in h_lower or 'char' in h_lower):
                        id_col = i

                # Tim cot Prompt - uu tien english_prompt, sau do img_prompt
                if 'english' in h_lower and 'prompt' in h_lower:
                    prompt_col = i
                elif h_lower == 'img_prompt' and prompt_col is None:
                    prompt_col = i
                elif h_lower == 'image_prompt' and prompt_col is None:
                    prompt_col = i
                elif prompt_col is None and h_lower == 'prompt':
                    prompt_col = i
                elif prompt_col is None and 'prompt' in h_lower and 'video' not in h_lower and 'viet' not in h_lower:
                    prompt_col = i

                # Tim cot reference_files (cho scene images)
                if 'reference' in h_lower and 'file' in h_lower:
                    ref_col = i

            # Neu khong tim thay, thu cot dau = ID, tim cot co "prompt"
            if id_col is None and len(headers) > 0 and headers[0]:
                # Cot dau tien co the la ID
                first_col = str(headers[0]).lower()
                if 'id' in first_col or first_col in ['scene_id', 'nv_id', 'character_id']:
                    id_col = 0

            if id_col is None or prompt_col is None:
                self.log(f"  -> Skip: id_col={id_col}, prompt_col={prompt_col}")
                continue

            self.log(f"  -> Found: id_col={id_col} ({headers[id_col]}), prompt_col={prompt_col} ({headers[prompt_col]}), ref_col={ref_col}")

            count = 0
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row is None:
                    continue
                if id_col >= len(row) or prompt_col >= len(row):
                    continue

                pid = row[id_col]
                prompt = row[prompt_col]

                if not pid or not prompt:
                    continue

                pid_str = str(pid).strip()

                # Get reference_files if available
                reference_files = ""
                if ref_col is not None and ref_col < len(row):
                    reference_files = row[ref_col] or ""

                # Xac dinh output folder
                # Characters (nv*) and Locations (loc*) -> nv/ folder
                if pid_str.startswith('nv') or pid_str.startswith('loc'):
                    out_path = proj_dir / "nv" / f"{pid_str}.png"
                else:
                    out_path = proj_dir / "img" / f"{pid_str}.png"

                prompts.append({
                    'id': pid_str,
                    'prompt': str(prompt).strip(),
                    'output_path': str(out_path),
                    'sheet': sheet_name,
                    'reference_files': str(reference_files).strip() if reference_files else "",
                    'nv_path': str(proj_dir / "nv")  # Path to reference images folder
                })
                count += 1

            self.log(f"  -> Loaded {count} prompts from '{sheet_name}'")

        self.log(f"TONG CONG: {len(prompts)} prompts")
        return prompts

    def stop(self):
        """Dung."""
        self.stop_flag = True


# ============================================================================
# SIMPLE API
# ============================================================================

def run_auto(input_path: str, callback: Callable = None) -> Dict:
    """
    1 HAM DUY NHAT - Chay tat ca tu dong.

    Args:
        input_path: File voice (.mp3, .wav) hoac Excel (.xlsx)
        callback: Ham nhan log messages

    Returns:
        Dict: {"success": N, "failed": M}
    """
    engine = SmartEngine()
    return engine.run(input_path, callback=callback)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = run_auto(sys.argv[1], callback=print)
        print(f"\nResult: {result}")
    else:
        print("Usage: python smart_engine.py <voice.mp3>")
