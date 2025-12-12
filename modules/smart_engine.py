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


class SmartEngine:
    """
    Engine thong minh - dam bao output 100%.
    """
    
    def __init__(self, config_path: str = None):
        # Support VE3_CONFIG_DIR environment variable
        if config_path:
            self.config_path = Path(config_path)
        else:
            config_dir = os.environ.get('VE3_CONFIG_DIR', 'config')
            self.config_path = Path(config_dir) / "accounts.json"
        
        self.chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        
        # Resources
        self.profiles: List[Resource] = []
        self.groq_keys: List[Resource] = []
        self.gemini_keys: List[Resource] = []
        
        # Settings
        self.parallel = 2
        self.delay = 2
        self.max_retries = 3
        
        # State
        self.stop_flag = False
        self.callback = None
        self._lock = threading.Lock()
        
        self.load_config()
    
    def log(self, msg: str, level: str = "INFO"):
        ts = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{ts}] [{level}] {msg}"
        print(full_msg)
        if self.callback:
            self.callback(full_msg)
    
    def load_config(self):
        """Load config."""
        if not self.config_path.exists():
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.chrome_path = data.get('chrome_path', self.chrome_path)
            
            # Load profiles
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
            
        except Exception as e:
            self.log(f"Load config error: {e}", "ERROR")
    
    def check_requirements(self, has_voice: bool = True) -> Tuple[bool, List[str]]:
        """
        Kiem tra thieu gi.
        Return: (ok, list of missing items)
        """
        missing = []
        
        if not self.profiles:
            missing.append("Chrome profiles (sua config/accounts.json)")
        
        if has_voice and not self.groq_keys and not self.gemini_keys:
            missing.append("AI API keys cho voice (Groq FREE: console.groq.com/keys)")
        
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
        """Lay AI key san sang (uu tien Groq vi free)."""
        with self._lock:
            # Uu tien Groq
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
            for r in self.profiles + self.groq_keys + self.gemini_keys:
                r.status = 'ready'
                r.fail_count = 0
    
    # ========== TOKEN MANAGEMENT ==========
    
    def get_token_for_profile(self, profile: Resource) -> bool:
        """Lay token cho 1 profile."""
        from modules.auto_token import ChromeAutoToken
        
        self.log(f"Lay token: {Path(profile.value).name}...")
        
        try:
            extractor = ChromeAutoToken(
                chrome_path=self.chrome_path,
                profile_path=profile.value
            )
            
            token, proj_id, error = extractor.extract_token(callback=self.callback)
            
            if token:
                profile.token = token
                profile.project_id = proj_id or ""
                profile.status = 'ready'
                self.log(f"OK: {Path(profile.value).name} - Token OK!", "OK")
                return True
            else:
                profile.fail_count += 1
                self.log(f"FAIL: {Path(profile.value).name} - {error}", "ERROR")
                return False
                
        except Exception as e:
            profile.fail_count += 1
            self.log(f"ERROR: {e}", "ERROR")
            return False
    
    def get_all_tokens(self) -> int:
        """Lay token cho tat ca profiles (tuan tu vi can GUI)."""
        success = 0
        
        self.log(f"=== LAY TOKEN CHO {len(self.profiles)} PROFILES ===")
        
        for i, profile in enumerate(self.profiles):
            if self.stop_flag:
                break
            
            self.log(f"[{i+1}/{len(self.profiles)}] {Path(profile.value).name}")
            
            if profile.token:
                self.log(f"  -> Da co token, skip")
                success += 1
                continue
            
            if self.get_token_for_profile(profile):
                success += 1
            
            # Doi giua cac profiles
            if i < len(self.profiles) - 1:
                time.sleep(3)
        
        self.log(f"=== XONG: {success}/{len(self.profiles)} tokens ===")
        return success
    
    def refresh_token_if_needed(self, profile: Resource) -> bool:
        """Refresh token neu can."""
        # TODO: Check token expiry
        if not profile.token:
            return self.get_token_for_profile(profile)
        return True
    
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
        
        # Add API keys
        cfg['groq_api_keys'] = [k.value for k in self.groq_keys if k.status != 'exhausted']
        cfg['gemini_api_keys'] = [k.value for k in self.gemini_keys if k.status != 'exhausted']
        cfg['preferred_provider'] = 'groq'
        
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

    def generate_single_image(self, prompt_data: Dict, profile: Resource) -> bool:
        """Tao 1 anh voi 1 profile, ho tro reference images."""
        from modules.google_flow_api import GoogleFlowAPI, AspectRatio
        import json

        pid = prompt_data.get('id', '')
        prompt = prompt_data.get('prompt', '')
        output = prompt_data.get('output_path', '')
        reference_files = prompt_data.get('reference_files', '')
        nv_path = prompt_data.get('nv_path', '')

        if not prompt or not output:
            return False

        # Skip if exists
        if Path(output).exists():
            return True

        try:
            api = GoogleFlowAPI(
                bearer_token=profile.token,
                project_id=profile.project_id,
                verbose=False
            )

            Path(output).parent.mkdir(parents=True, exist_ok=True)

            # Upload reference images to get media_name (NOT base64!)
            image_inputs = []
            if reference_files and nv_path and not pid.startswith('nv') and not pid.startswith('loc'):
                # Parse reference_files (JSON array or comma-separated)
                file_list = []
                try:
                    parsed = json.loads(reference_files)
                    if isinstance(parsed, list):
                        file_list = parsed
                    elif isinstance(parsed, str):
                        file_list = [parsed]
                except (json.JSONDecodeError, TypeError):
                    file_list = [f.strip() for f in str(reference_files).split(",") if f.strip()]

                # Upload each reference image to get media_name
                for filename in file_list:
                    img_path = Path(nv_path) / filename
                    if img_path.exists():
                        try:
                            # Upload để lấy media_name (KHÔNG gửi base64 trực tiếp!)
                            success_upload, img_input, error_upload = api.upload_image(img_path)
                            if success_upload and img_input:
                                image_inputs.append(img_input)  # ImageInput object với media_name
                                self.log(f"  -> Uploaded: {filename} -> {img_input.name[:40]}...")
                            else:
                                self.log(f"  -> Upload failed {filename}: {error_upload}", "WARN")
                        except Exception as e:
                            self.log(f"  -> Upload error {filename}: {e}", "WARN")
                    else:
                        self.log(f"  -> Reference not found: {img_path}", "WARN")

                if image_inputs:
                    self.log(f"  -> Using {len(image_inputs)} reference images for {pid}")

            # generate_and_download returns (success, paths, error)
            success, paths, error = api.generate_and_download(
                prompt=prompt,
                output_dir=Path(output).parent,
                count=1,
                aspect_ratio=AspectRatio.LANDSCAPE,
                prefix=pid,
                image_inputs=image_inputs if image_inputs else None
            )

            if success and paths:
                # Rename first image to correct filename
                src = paths[0]
                if src.exists() and str(src) != output:
                    if Path(output).exists():
                        Path(output).unlink()
                    src.rename(output)
                return True
            else:
                self.log(f"Generate failed {pid}: {error}", "ERROR")
                return False

        except Exception as e:
            self.log(f"Image error {pid}: {e}", "ERROR")
            if 'unauthorized' in str(e).lower() or '401' in str(e):
                profile.token = ""
            return False
    
    def generate_images_parallel(self, prompts: List[Dict]) -> Dict:
        """
        Tao anh SONG SONG.
        Dam bao tat ca prompts deu duoc tao - retry neu fail.
        """
        self.log(f"=== TAO {len(prompts)} ANH SONG SONG ===")
        
        results = {"success": 0, "failed": 0, "pending": list(prompts)}
        
        # Loop until all done or no resources left
        attempt = 0
        while results["pending"] and attempt < self.max_retries * 2:
            if self.stop_flag:
                break
            
            attempt += 1
            self.log(f"=== ROUND {attempt} - {len(results['pending'])} pending ===")
            
            # Get profiles with tokens
            active_profiles = [p for p in self.profiles if p.token and p.status != 'exhausted']
            
            if not active_profiles:
                self.log("Khong co profile nao co token!", "WARN")
                # Try to get more tokens
                n = self.get_all_tokens()
                if n == 0:
                    break
                active_profiles = [p for p in self.profiles if p.token]
            
            if not active_profiles:
                break
            
            n_workers = min(len(active_profiles), self.parallel, len(results["pending"]))
            
            # Distribute prompts
            pending = results["pending"]
            results["pending"] = []
            
            chunks = [[] for _ in range(n_workers)]
            for i, p in enumerate(pending):
                chunks[i % n_workers].append(p)
            
            # Run workers
            done_in_round = []
            failed_in_round = []
            lock = threading.Lock()
            
            def worker(worker_id: int, profile: Resource, prompt_list: List[Dict]):
                for pd in prompt_list:
                    if self.stop_flag:
                        break
                    
                    pid = pd.get('id', '')
                    self.log(f"[W{worker_id}] {pid}...")
                    
                    # Refresh token if needed
                    if not profile.token:
                        if not self.refresh_token_if_needed(profile):
                            with lock:
                                failed_in_round.append(pd)
                            continue
                    
                    success = self.generate_single_image(pd, profile)
                    
                    with lock:
                        if success:
                            done_in_round.append(pd)
                            self.log(f"[W{worker_id}] {pid}: OK!", "OK")
                        else:
                            failed_in_round.append(pd)
                            self.log(f"[W{worker_id}] {pid}: FAIL", "WARN")
                    
                    time.sleep(self.delay)
            
            # Start threads
            threads = []
            for i in range(n_workers):
                if chunks[i]:
                    t = threading.Thread(
                        target=worker,
                        args=(i+1, active_profiles[i], chunks[i]),
                        daemon=True
                    )
                    t.start()
                    threads.append(t)
            
            # Wait
            for t in threads:
                t.join()
            
            # Update results
            results["success"] += len(done_in_round)
            results["pending"] = failed_in_round
            
            self.log(f"Round {attempt}: +{len(done_in_round)} OK, {len(failed_in_round)} pending")
            
            # If still have pending, wait a bit
            if results["pending"]:
                time.sleep(5)
        
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
        CHAY TAT CA - 1 ham duy nhat.
        
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
        
        self.log("="*50)
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
        
        self.log(f"  Profiles: {len(self.profiles)}")
        self.log(f"  Groq keys: {len(self.groq_keys)}")
        self.log(f"  Gemini keys: {len(self.gemini_keys)}")
        
        # === 2. PARALLEL: GET TOKENS + MAKE SRT ===
        self.log("[STEP 2] Lay tokens + Tao SRT (song song)...")
        
        srt_path = proj_dir / "srt" / f"{name}.srt"
        voice_path = None
        
        if ext in ['.mp3', '.wav']:
            voice_path = proj_dir / f"{name}{ext}"
            if inp != voice_path:
                shutil.copy2(inp, voice_path)
        
        # Start SRT in background if voice
        srt_thread = None
        srt_result = [False]
        
        if voice_path and not srt_path.exists():
            def srt_worker():
                srt_result[0] = self.make_srt(voice_path, srt_path)
            srt_thread = threading.Thread(target=srt_worker, daemon=True)
            srt_thread.start()
        else:
            srt_result[0] = True
        
        # Get tokens (main thread - needs Chrome GUI)
        n_tokens = self.get_all_tokens()
        
        # Wait for SRT
        if srt_thread:
            srt_thread.join()
        
        if not srt_result[0] and ext in ['.mp3', '.wav']:
            return {"error": "srt_failed"}
        
        if n_tokens == 0:
            return {"error": "no_tokens"}
        
        # === 3. MAKE PROMPTS ===
        self.log("[STEP 3] Tao prompts...")
        
        if ext == '.xlsx':
            # Input is Excel
            if inp != excel_path:
                shutil.copy2(inp, excel_path)
        else:
            # Generate from SRT
            if not self.make_prompts(proj_dir, name, excel_path):
                return {"error": "prompts_failed"}
        
        # === 4. LOAD PROMPTS ===
        self.log("[STEP 4] Load prompts...")
        
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
        
        # === 5. GENERATE IMAGES ===
        self.log("[STEP 5] Tao anh song song...")
        
        results = self.generate_images_parallel(prompts)
        
        # === 6. FINAL CHECK ===
        self.log("[STEP 6] Kiem tra ket qua...")
        
        if results["failed"] > 0:
            self.log(f"CON {results['failed']} ANH CHUA XONG!", "WARN")
            # TODO: Could try alternative methods here
        else:
            self.log("TAT CA ANH DA HOAN THANH!", "OK")
        
        return results
    
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
