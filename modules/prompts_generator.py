"""
VE3 Tool - Prompts Generator Module
===================================
Sử dụng AI API để phân tích SRT và tạo prompts cho ảnh/video.
Hỗ trợ: DeepSeek (rẻ), Groq (free), Gemini
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests

from modules.utils import (
    get_logger,
    parse_srt_file,
    group_srt_into_scenes,
    format_srt_time
)
from modules.excel_manager import (
    PromptWorkbook,
    Character,
    Location,
    Scene
)
from modules.prompts_loader import (
    get_analyze_story_prompt,
    get_generate_scenes_prompt,
    get_smart_divide_scenes_prompt,
    get_global_style
)


# ============================================================================
# MULTI AI CLIENT (DeepSeek + Groq + Gemini)
# ============================================================================

class MultiAIClient:
    """
    Client hỗ trợ nhiều AI providers.
    Ưu tiên: Gemini (chất lượng cao) > Groq (nhanh) > DeepSeek (rẻ, chậm)

    Tự động test và loại bỏ API keys không hoạt động khi khởi tạo.
    """

    DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, config: dict, auto_filter: bool = True):
        """
        Config format:
        {
            "deepseek_api_keys": ["key1"],
            "groq_api_keys": ["key1", "key2"],
            "gemini_api_keys": ["key1"],
            "gemini_models": ["gemini-2.0-flash"],
        }

        auto_filter: Tự động test và loại bỏ API keys không hoạt động
        """
        self.config = config
        self.gemini_keys = [k for k in config.get("gemini_api_keys", []) if k and k.strip()]
        self.groq_keys = [k for k in config.get("groq_api_keys", []) if k and k.strip()]
        self.deepseek_keys = [k for k in config.get("deepseek_api_keys", []) if k and k.strip()]
        self.gemini_models = config.get("gemini_models", ["gemini-2.0-flash", "gemini-1.5-flash"])

        self.deepseek_index = 0
        self.groq_index = 0
        self.gemini_key_index = 0
        self.gemini_model_index = 0

        self.logger = get_logger("multi_ai")

        # Auto filter exhausted APIs at startup
        if auto_filter:
            self._filter_working_apis()

    def _filter_working_apis(self):
        """Test và loại bỏ API keys không hoạt động."""
        print("\n[API Filter] Dang kiem tra API keys...")

        # Test Gemini keys
        working_gemini = []
        for i, key in enumerate(self.gemini_keys):
            print(f"  Testing Gemini key #{i+1}...", end=" ")
            if self._test_gemini_key(key):
                print("OK")
                working_gemini.append(key)
            else:
                print("SKIP (quota/error)")

        # Test Groq keys
        working_groq = []
        for i, key in enumerate(self.groq_keys):
            print(f"  Testing Groq key #{i+1}...", end=" ")
            if self._test_groq_key(key):
                print("OK")
                working_groq.append(key)
            else:
                print("SKIP (rate limit/error)")

        # Test DeepSeek keys
        working_deepseek = []
        for i, key in enumerate(self.deepseek_keys):
            print(f"  Testing DeepSeek key #{i+1}...", end=" ")
            if self._test_deepseek_key(key):
                print("OK")
                working_deepseek.append(key)
            else:
                print("SKIP (error)")

        # Update with working keys only
        self.gemini_keys = working_gemini
        self.groq_keys = working_groq
        self.deepseek_keys = working_deepseek

        total_working = len(working_gemini) + len(working_groq) + len(working_deepseek)
        print(f"[API Filter] Ket qua: {len(working_gemini)} Gemini, {len(working_groq)} Groq, {len(working_deepseek)} DeepSeek")

        if total_working == 0:
            print("[API Filter] CANH BAO: Khong co API key nao hoat dong!")
        else:
            # Show priority order
            if working_gemini:
                print(f"[API Filter] Se dung: Gemini (uu tien)")
            elif working_groq:
                print(f"[API Filter] Se dung: Groq (uu tien)")
            elif working_deepseek:
                print(f"[API Filter] Se dung: DeepSeek")

    def _test_gemini_key(self, key: str) -> bool:
        """Test Gemini key với request nhỏ."""
        try:
            model = self.gemini_models[0] if self.gemini_models else "gemini-2.0-flash"
            url = f"{self.GEMINI_URL}/models/{model}:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": "Say OK"}]}],
                "generationConfig": {"maxOutputTokens": 5}
            }
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except:
            return False

    def _test_groq_key(self, key: str) -> bool:
        """Test Groq key với request nhỏ."""
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 5
            }
            resp = requests.post(self.GROQ_URL, headers=headers, json=data, timeout=10)
            return resp.status_code == 200
        except:
            return False

    def _test_deepseek_key(self, key: str) -> bool:
        """Test DeepSeek key với request nhỏ."""
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            data = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "Say OK"}],
                "max_tokens": 5
            }
            resp = requests.post(self.DEEPSEEK_URL, headers=headers, json=data, timeout=15)
            return resp.status_code == 200
        except:
            return False

    def generate_content(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        max_retries: int = 3
    ) -> str:
        """Generate content using available AI providers.
        Priority: Gemini (best quality) > Groq (fast) > DeepSeek (cheap, slow)

        Chi thu cac API da duoc filter la hoat dong.
        """

        last_error = None

        # 1. Try Gemini first (best quality, fastest)
        if self.gemini_keys:
            for attempt in range(max_retries):
                try:
                    print(f"[Gemini] Dang goi API (attempt {attempt + 1})...")
                    result = self._call_gemini(prompt, temperature, max_tokens)
                    if result:
                        print(f"[Gemini] Thanh cong!")
                        return result
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    if "leaked" in error_str:
                        self.logger.error("Gemini key leaked! Removing...")
                        if self.gemini_keys:
                            self.gemini_keys.pop(self.gemini_key_index)
                            if self.gemini_keys:
                                self.gemini_key_index = self.gemini_key_index % len(self.gemini_keys)
                        break  # Move to next provider
                    elif "429" in error_str or "quota" in error_str:
                        self.logger.warning("Gemini quota exceeded, removing key...")
                        if self.gemini_keys:
                            self.gemini_keys.pop(self.gemini_key_index)
                            if self.gemini_keys:
                                self.gemini_key_index = self.gemini_key_index % len(self.gemini_keys)
                            else:
                                break  # No more keys, move to next provider
                        continue
                    elif "404" in error_str:
                        self.gemini_model_index = (self.gemini_model_index + 1) % len(self.gemini_models)
                        continue
                    else:
                        self.logger.error(f"Gemini error: {e}")
                        break

        # 2. Fallback to Groq (fast, free but rate limited)
        if self.groq_keys:
            for attempt in range(max_retries):
                try:
                    print(f"[Groq] Dang goi API (attempt {attempt + 1})...")
                    result = self._call_groq(prompt, temperature, max_tokens)
                    if result:
                        print(f"[Groq] Thanh cong!")
                        return result
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    if "rate" in error_str or "429" in error_str:
                        self.logger.warning("Groq rate limit, trying next key...")
                        self.groq_index = (self.groq_index + 1) % len(self.groq_keys)
                        time.sleep(3)
                        continue
                    elif "invalid" in error_str or "unauthorized" in error_str:
                        self.logger.warning("Groq key invalid, removing...")
                        if self.groq_keys:
                            self.groq_keys.pop(self.groq_index)
                            if self.groq_keys:
                                self.groq_index = self.groq_index % len(self.groq_keys)
                            else:
                                break
                        continue
                    else:
                        self.logger.error(f"Groq error: {e}")
                        break

        # 3. Fallback to DeepSeek (cheap, stable but slow)
        if self.deepseek_keys:
            for attempt in range(max_retries):
                try:
                    result = self._call_deepseek(prompt, temperature, max_tokens)
                    if result:
                        return result
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()

                    if "rate" in error_str or "429" in error_str:
                        self.logger.warning("DeepSeek rate limit, trying next key...")
                        self.deepseek_index = (self.deepseek_index + 1) % len(self.deepseek_keys)
                        time.sleep(3)
                        continue
                    elif "invalid" in error_str or "unauthorized" in error_str:
                        self.logger.warning("DeepSeek key invalid, removing...")
                        if self.deepseek_keys:
                            self.deepseek_keys.pop(self.deepseek_index)
                            if self.deepseek_keys:
                                self.deepseek_index = self.deepseek_index % len(self.deepseek_keys)
                            else:
                                break
                        continue
                    else:
                        self.logger.error(f"DeepSeek error: {e}")
                        break

        if last_error:
            raise last_error
        raise RuntimeError("Khong co API provider nao hoat dong!")

    def _call_deepseek(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call DeepSeek API."""
        api_key = self.deepseek_keys[self.deepseek_index]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        print(f"[DeepSeek] Dang goi API... (prompt: {len(prompt)} ky tu, cho 60-120s)")

        resp = requests.post(self.DEEPSEEK_URL, headers=headers, json=data, timeout=180)

        if resp.status_code == 200:
            result = resp.json()
            print(f"[DeepSeek] Thanh cong!")
            return result["choices"][0]["message"]["content"]
        else:
            raise requests.RequestException(f"DeepSeek API error {resp.status_code}: {resp.text[:200]}")

    def _call_groq(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call Groq API."""
        api_key = self.groq_keys[self.groq_index]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        self.logger.debug(f"Calling Groq API (key #{self.groq_index + 1})...")

        resp = requests.post(self.GROQ_URL, headers=headers, json=data, timeout=120)

        if resp.status_code == 200:
            result = resp.json()
            return result["choices"][0]["message"]["content"]
        else:
            raise requests.RequestException(f"Groq API error {resp.status_code}: {resp.text[:200]}")
    
    def _call_gemini(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call Gemini API."""
        api_key = self.gemini_keys[self.gemini_key_index]
        model = self.gemini_models[self.gemini_model_index]
        
        url = f"{self.GEMINI_URL}/models/{model}:generateContent?key={api_key}"
        
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }
        
        self.logger.debug(f"Calling Gemini API: model={model}, key=#{self.gemini_key_index + 1}")
        
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        
        if resp.status_code == 200:
            result = resp.json()
            return result["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise requests.RequestException(f"Gemini API error {resp.status_code}: {resp.text[:300]}")


# ============================================================================
# LEGACY GEMINI CLIENT (for backwards compatibility)
# ============================================================================

class GeminiClient:
    """
    Client để gọi Gemini API (free tier).
    Hỗ trợ nhiều API keys và models - tự động chuyển khi gặp lỗi.
    """
    
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    def __init__(self, api_keys: list, models: list):
        """
        Khởi tạo Gemini client với nhiều API keys và models.
        
        Args:
            api_keys: List các API keys
            models: List các model names
        """
        if isinstance(api_keys, str):
            api_keys = [api_keys]
        if isinstance(models, str):
            models = [models]
            
        self.api_keys = api_keys
        self.models = models
        self.current_key_index = 0
        self.current_model_index = 0
        self.logger = get_logger("gemini_client")
    
    @property
    def current_api_key(self):
        return self.api_keys[self.current_key_index]
    
    @property
    def current_model(self):
        return self.models[self.current_model_index]
    
    def _next_key(self) -> bool:
        """Chuyển sang API key tiếp theo. Return False nếu hết keys."""
        self.current_key_index += 1
        if self.current_key_index >= len(self.api_keys):
            self.current_key_index = 0
            return False
        self.logger.info(f"Switching to API key #{self.current_key_index + 1}")
        return True
    
    def _next_model(self) -> bool:
        """Chuyển sang model tiếp theo. Return False nếu hết models."""
        self.current_model_index += 1
        if self.current_model_index >= len(self.models):
            self.current_model_index = 0
            return False
        self.logger.info(f"Switching to model: {self.current_model}")
        return True
    
    def generate_content(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        max_retries: int = None
    ) -> str:
        """
        Gọi Gemini API với tự động retry qua nhiều keys/models.
        """
        if max_retries is None:
            max_retries = len(self.api_keys) * len(self.models) * 2
        
        last_error = None
        attempts = 0
        
        while attempts < max_retries:
            attempts += 1
            
            try:
                result = self._call_api(prompt, temperature, max_tokens)
                return result
                
            except requests.RequestException as e:
                last_error = e
                error_str = str(e)
                
                # Lỗi 429 (quota exceeded) - thử key khác
                if "429" in error_str:
                    self.logger.warning(f"Quota exceeded, trying next key/model...")
                    if not self._next_key():
                        if not self._next_model():
                            # Đã thử hết tất cả, đợi và retry
                            self.logger.info("All keys/models tried. Waiting 15s...")
                            import time
                            time.sleep(15)
                    continue
                
                # Lỗi 404 (model not found) - thử model khác
                elif "404" in error_str:
                    self.logger.warning(f"Model {self.current_model} not found, trying next...")
                    if not self._next_model():
                        raise
                    continue
                
                # Lỗi khác
                else:
                    raise
        
        raise last_error or RuntimeError("Max retries exceeded")
    
    def _call_api(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int
    ) -> str:
        """Thực hiện gọi API một lần."""
        url = f"{self.BASE_URL}/models/{self.current_model}:generateContent"
        
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            }
        }
        
        params = {"key": self.current_api_key}
        
        self.logger.debug(f"Calling API: model={self.current_model}, key=#{self.current_key_index + 1}")
        
        response = requests.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            self.logger.error(f"API Error: {response.status_code}")
            raise requests.RequestException(
                f"Gemini API error: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text
        except (KeyError, IndexError) as e:
            raise ValueError(f"Invalid API response format: {e}")

# ============================================================================
# PROMPT TEMPLATES - Loaded from config/prompts.yaml
# ============================================================================
# Prompts are now loaded from external file for easy editing
# Edit config/prompts.yaml to customize prompts without changing code


# ============================================================================
# PROMPT GENERATOR CLASS
# ============================================================================

class PromptGenerator:
    """
    Class tạo prompts từ file SRT sử dụng Gemini API.
    
    Flow:
    1. Đọc SRT và gom thành scenes
    2. Gọi Gemini để phân tích nhân vật
    3. Gọi Gemini để tạo prompt cho từng scene
    4. Lưu vào Excel
    """
    
    def __init__(self, settings: Dict[str, Any]):
        """
        Khởi tạo PromptGenerator.
        
        Args:
            settings: Dictionary cấu hình từ settings.yaml
        """
        self.settings = settings
        self.logger = get_logger("prompt_generator")
        
        # Sử dụng MultiAIClient (hỗ trợ Groq + Gemini)
        self.ai_client = MultiAIClient(settings)
        
        # Legacy: Fallback to GeminiClient nếu cần
        api_keys = settings.get("gemini_api_keys") or [settings.get("gemini_api_key")]
        models = settings.get("gemini_models") or [settings.get("gemini_model", "gemini-2.0-flash")]
        self.gemini = GeminiClient(api_keys=api_keys, models=models)
        
        # Scene grouping settings
        self.min_scene_duration = settings.get("min_scene_duration", 3)  # Min 3s
        self.max_scene_duration = settings.get("max_scene_duration", 8)  # Max 8s per scene
    
    def _generate_content(self, prompt: str, temperature: float = 0.7, max_tokens: int = 8192) -> str:
        """Generate content using available AI providers."""
        # Try MultiAIClient first
        try:
            return self.ai_client.generate_content(prompt, temperature, max_tokens)
        except Exception as e:
            self.logger.warning(f"MultiAI failed: {e}, falling back to Gemini...")
            return self.gemini.generate_content(prompt, temperature, max_tokens)
    
    def generate_for_project(
        self,
        project_dir: Path,
        code: str,
        overwrite: bool = False
    ) -> bool:
        """
        Tạo prompts cho một project.
        
        Args:
            project_dir: Path đến thư mục project
            code: Mã project
            overwrite: Nếu True, ghi đè prompts đã có
            
        Returns:
            True nếu thành công
        """
        project_dir = Path(project_dir)
        
        # Paths
        srt_path = project_dir / "srt" / f"{code}.srt"
        excel_path = project_dir / "prompts" / f"{code}_prompts.xlsx"
        
        # Kiểm tra SRT file
        if not srt_path.exists():
            self.logger.error(f"SRT file không tồn tại: {srt_path}")
            return False
        
        # Load hoặc tạo Excel
        workbook = PromptWorkbook(excel_path).load_or_create()
        
        # Kiểm tra đã có prompts chưa
        if workbook.has_prompts() and not overwrite:
            self.logger.info("Prompts đã tồn tại, bỏ qua (dùng --overwrite-prompts để ghi đè)")
            return True
        
        # Clear dữ liệu cũ nếu overwrite
        if overwrite:
            self.logger.info("Xóa prompts cũ...")
            workbook.clear_characters()
            workbook.clear_scenes()
            workbook.save()
        
        # Đọc và parse SRT
        self.logger.info(f"Đọc SRT file: {srt_path}")
        srt_entries = parse_srt_file(srt_path)
        
        if not srt_entries:
            self.logger.error("Không tìm thấy entries trong SRT file")
            return False
        
        self.logger.info(f"Tìm thấy {len(srt_entries)} SRT entries")

        # Tạo full story text để phân tích
        full_story = " ".join([e.text for e in srt_entries])

        # Step 1: Phân tích nhân vật + bối cảnh TRƯỚC
        self.logger.info("Phân tích nhân vật và bối cảnh...")
        characters, locations, context_lock, global_style = self._analyze_characters(full_story)

        if not characters:
            self.logger.error("Không thể phân tích nhân vật")
            return False

        self.logger.info(f"Tìm thấy {len(characters)} nhân vật, {len(locations)} bối cảnh")

        # Lưu nhân vật vào Excel
        for char in characters:
            char.image_file = f"{char.id}.png"
            char.status = "pending"
            workbook.add_character(char)

        # Lưu locations
        for loc in locations:
            loc_char = Character(
                id=loc.id,
                role="location",
                name=loc.name,
                english_prompt=loc.english_prompt,
                vietnamese_prompt=loc.location_lock,
                image_file=f"{loc.id}.png",
                status="pending"
            )
            workbook.add_character(loc_char)

        workbook.save()
        self.logger.info(f"Đã lưu {len(characters)} nhân vật + {len(locations)} bối cảnh")

        # Step 2: Chia scene THÔNG MINH theo nội dung (không theo thời gian)
        self.logger.info("Chia scene theo nội dung (AI Smart Division)...")
        scenes_data = self._smart_divide_scenes(srt_entries)

        self.logger.info(f"Chia thành {len(scenes_data)} scenes")

        # Step 3: Tạo prompts cho từng batch scenes
        self.logger.info("Tạo prompts cho scenes...")

        # Chia scenes thành batches để tránh vượt quá context limit
        batch_size = 10
        all_scene_prompts = []

        for i in range(0, len(scenes_data), batch_size):
            batch = scenes_data[i:i + batch_size]
            self.logger.info(f"Xử lý batch {i // batch_size + 1}/{(len(scenes_data) - 1) // batch_size + 1}")

            scene_prompts = self._generate_scene_prompts(
                characters, batch, context_lock,
                locations=locations,
                global_style_override=global_style
            )
            all_scene_prompts.extend(scene_prompts)
            
            # Rate limiting
            if i + batch_size < len(scenes_data):
                time.sleep(2)  # Tránh rate limit
        
        # Lưu scenes vào Excel
        for scene_data, prompts in zip(scenes_data, all_scene_prompts):
            # Convert lists to JSON strings for storage
            chars_used = prompts.get("characters_used", [])
            ref_files = prompts.get("reference_files", [])
            chars_str = json.dumps(chars_used) if isinstance(chars_used, list) else str(chars_used)
            refs_str = json.dumps(ref_files) if isinstance(ref_files, list) else str(ref_files)

            scene = Scene(
                scene_id=scene_data["scene_id"],
                srt_start=scene_data["srt_start"],
                srt_end=scene_data["srt_end"],
                srt_text=scene_data["text"][:500],  # Truncate nếu quá dài
                img_prompt=prompts.get("img_prompt", ""),
                video_prompt=prompts.get("video_prompt", ""),
                status_img="pending",
                status_vid="pending",
                characters_used=chars_str,
                location_used=prompts.get("location_used", ""),
                reference_files=refs_str
            )
            workbook.add_scene(scene)
        
        workbook.save()
        self.logger.info(f"Đã lưu {len(scenes_data)} scenes với prompts")
        
        return True
    
    def _analyze_characters(self, story_text: str) -> tuple:
        """
        Phân tích truyện và trích xuất nhân vật + bối cảnh.

        Args:
            story_text: Toàn bộ nội dung truyện

        Returns:
            Tuple (List[Character], List[Location], context_lock: str, global_style: str)
        """
        # Load prompt từ config/prompts.yaml
        prompt_template = get_analyze_story_prompt()
        prompt = prompt_template.format(story_text=story_text[:8000])

        try:
            response = self._generate_content(prompt, temperature=0.5)

            # Parse JSON từ response
            json_data = self._extract_json(response)

            if not json_data or "characters" not in json_data:
                self.logger.error(f"Invalid characters response: {response[:500]}")
                return [], [], "", ""

            # Extract context_lock and global_style (v5.0 format)
            context_lock = json_data.get("context_lock", "")
            global_style = json_data.get("global_style", "")

            # Extract characters
            characters = []
            for char_data in json_data["characters"]:
                # Support both old format (english_prompt) and new format (portrait_prompt)
                english_prompt = char_data.get("english_prompt", "")
                if not english_prompt:
                    english_prompt = char_data.get("portrait_prompt", "")
                    if english_prompt == "DO_NOT_GENERATE":
                        # Tre em - dung character_lock thay vi portrait
                        english_prompt = char_data.get("character_lock", "")

                characters.append(Character(
                    id=char_data.get("id", ""),
                    role=char_data.get("role", "supporting"),
                    name=char_data.get("name", ""),
                    english_prompt=english_prompt,
                    vietnamese_prompt=char_data.get("vietnamese_prompt", char_data.get("vietnamese_description", "")),
                ))

            # Extract locations (v5.0 format)
            locations = []
            for loc_data in json_data.get("locations", []):
                english_prompt = loc_data.get("location_prompt", loc_data.get("english_prompt", ""))

                locations.append(Location(
                    id=loc_data.get("id", ""),
                    name=loc_data.get("name", ""),
                    english_prompt=english_prompt,
                    location_lock=loc_data.get("location_lock", ""),
                    lighting_default=loc_data.get("lighting_default", ""),
                    image_file=loc_data.get("filename", ""),
                ))

            self.logger.info(f"Extracted {len(characters)} characters, {len(locations)} locations")
            return characters, locations, context_lock, global_style

        except Exception as e:
            self.logger.error(f"Failed to analyze characters: {e}")
            return [], [], "", ""

    def _smart_divide_scenes(self, srt_entries: List) -> List[Dict[str, Any]]:
        """
        Chia scene thông minh theo nội dung thay vì theo thời gian.

        Args:
            srt_entries: List các SrtEntry từ file SRT

        Returns:
            List các scene data với: scene_id, start_time, end_time, text, srt_start, srt_end
        """
        # Format SRT entries với timestamps cho AI
        srt_with_timestamps = "\n".join([
            f"{e.index}. [{format_srt_time(e.start_time)} -> {format_srt_time(e.end_time)}] \"{e.text}\""
            for e in srt_entries
        ])

        # Load prompt từ config/prompts.yaml
        prompt_template = get_smart_divide_scenes_prompt()
        if not prompt_template:
            self.logger.warning("Smart divide prompt not found, falling back to time-based division")
            return self._fallback_time_based_division(srt_entries)

        prompt = prompt_template.format(srt_with_timestamps=srt_with_timestamps)

        try:
            self.logger.info("AI đang phân tích nội dung để chia scene...")
            response = self._generate_content(prompt, temperature=0.4, max_tokens=16000)

            # Parse JSON từ response
            json_data = self._extract_json(response)

            if not json_data or "scenes" not in json_data:
                self.logger.warning(f"Invalid smart divide response, falling back to time-based")
                return self._fallback_time_based_division(srt_entries)

            # Convert AI output to internal format
            scenes_data = []
            for scene in json_data["scenes"]:
                # Parse timestamps
                start_str = scene.get("start_time", "00:00:00")
                end_str = scene.get("end_time", "00:00:00")

                # Get SRT indices
                srt_indices = scene.get("srt_indices", [])
                srt_start = min(srt_indices) if srt_indices else 1
                srt_end = max(srt_indices) if srt_indices else 1

                scenes_data.append({
                    "scene_id": scene.get("scene_id", len(scenes_data) + 1),
                    "start_time": start_str,
                    "end_time": end_str,
                    "duration_seconds": scene.get("duration_seconds", 5),
                    "text": scene.get("text", ""),
                    "visual_moment": scene.get("visual_moment", ""),
                    "srt_start": srt_start,
                    "srt_end": srt_end,
                })

            self.logger.info(f"AI chia thành {len(scenes_data)} scenes theo nội dung")
            return scenes_data

        except Exception as e:
            self.logger.error(f"Smart divide failed: {e}, falling back to time-based")
            return self._fallback_time_based_division(srt_entries)

    def _fallback_time_based_division(self, srt_entries: List) -> List[Dict[str, Any]]:
        """Fallback: chia scene theo thời gian khi AI không hoạt động."""
        from modules.utils import group_srt_into_scenes
        return group_srt_into_scenes(
            srt_entries,
            min_duration=self.min_scene_duration,
            max_duration=self.max_scene_duration
        )

    def _generate_scene_prompts(
        self,
        characters: List[Character],
        scenes_data: List[Dict[str, Any]],
        context_lock: str = "",
        locations: List[Location] = None,
        global_style_override: str = ""
    ) -> List[Dict[str, str]]:
        """
        Tạo prompts cho một batch scenes.

        Args:
            characters: Danh sách nhân vật
            scenes_data: Danh sách scene data
            context_lock: Context lock string từ phân tích nhân vật
            locations: Danh sách locations
            global_style_override: Global style từ AI (nếu có)

        Returns:
            List các dict chứa img_prompt và video_prompt
        """
        locations = locations or []

        # Format thông tin nhân vật (v5.0 format) - include character_lock for AI to copy
        characters_info = "\n".join([
            f"- ID: {char.id}\n"
            f"  Name: {char.name} ({char.role})\n"
            f"  character_lock: \"{char.english_prompt}\"\n"
            f"  reference_file: {char.id}.png"
            for char in characters
        ])

        # Format thông tin locations (v5.0 format) - include location_lock for AI to copy
        if locations:
            locations_info = "\n".join([
                f"- ID: {loc.id}\n"
                f"  Name: {loc.name}\n"
                f"  location_lock: \"{loc.location_lock}\"\n"
                f"  lighting: {loc.lighting_default}\n"
                f"  reference_file: {loc.id}.png"
                for loc in locations
            ])
        else:
            locations_info = "(No location references - describe locations based on story context)"

        # Format thông tin scenes (pacing_script format)
        pacing_script = "\n".join([
            f"{s['scene_id']}. \"{s['text']}\""
            for s in scenes_data
        ])

        # Load global style - uu tien tu AI response
        global_style = global_style_override or get_global_style()

        # Load prompt từ config/prompts.yaml
        prompt_template = get_generate_scenes_prompt()

        # Try to format with all variables (v5.0 format)
        try:
            prompt = prompt_template.format(
                characters_info=characters_info,
                scenes_info=pacing_script,  # for backwards compat
                pacing_script=pacing_script,
                context_lock=context_lock or "Modern setting, natural lighting",
                global_style=global_style,
                locations_info=locations_info
            )
        except KeyError as e:
            # Fallback to simpler format
            self.logger.warning(f"Template format error: {e}, using simple format")
            prompt = f"""Create image prompts for these scenes:

Characters:
{characters_info}

Locations:
{locations_info}

Scenes:
{pacing_script}

Context: {context_lock or "Modern setting"}
Style: {global_style}

Return JSON: {{"scenes": [{{"scene_id": 1, "img_prompt": "...", "video_prompt": "..."}}]}}"""
        
        try:
            response = self._generate_content(prompt, temperature=0.6)
            
            # Parse JSON
            json_data = self._extract_json(response)
            
            if not json_data or "scenes" not in json_data:
                self.logger.warning(f"Invalid scene prompts response, using defaults")
                # Return default prompts
                return [{"img_prompt": "", "video_prompt": ""} for _ in scenes_data]
            
            # Match prompts với scenes
            prompts_map = {s["scene_id"]: s for s in json_data["scenes"]}

            result = []
            for scene_data in scenes_data:
                scene_id = scene_data["scene_id"]
                if scene_id in prompts_map:
                    scene_result = prompts_map[scene_id]
                    result.append({
                        "img_prompt": scene_result.get("img_prompt", ""),
                        "video_prompt": scene_result.get("video_prompt", ""),
                        "characters_used": scene_result.get("characters_used", []),
                        "location_used": scene_result.get("location_used", ""),
                        "reference_files": scene_result.get("reference_files", [])
                    })
                else:
                    result.append({
                        "img_prompt": "",
                        "video_prompt": "",
                        "characters_used": [],
                        "location_used": "",
                        "reference_files": []
                    })

            return result
            
        except Exception as e:
            self.logger.error(f"Failed to generate scene prompts: {e}")
            return [{"img_prompt": "", "video_prompt": ""} for _ in scenes_data]
    
    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        Trích xuất JSON từ response text.
        
        Gemini có thể trả về JSON trong markdown code block hoặc raw.
        """
        # Thử parse trực tiếp
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # Thử tìm JSON trong code block
        import re
        
        # Pattern cho ```json ... ```
        json_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if json_block:
            try:
                return json.loads(json_block.group(1))
            except json.JSONDecodeError:
                pass
        
        # Thử tìm JSON object bắt đầu bằng {
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
