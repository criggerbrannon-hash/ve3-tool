"""
VE3 Tool - Prompts Generator Module
===================================
Sử dụng AI API để phân tích SRT và tạo prompts cho ảnh/video.
Hỗ trợ: Groq (free, fast), Gemini, OpenRouter
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
    Scene
)
from modules.prompts_loader import (
    get_analyze_story_prompt,
    get_generate_scenes_prompt,
    get_global_style
)


# ============================================================================
# MULTI AI CLIENT (Groq + Gemini + OpenRouter)
# ============================================================================

class MultiAIClient:
    """
    Client hỗ trợ nhiều AI providers.
    Ưu tiên: Groq (free) > Gemini > OpenRouter
    """
    
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    def __init__(self, config: dict):
        """
        Config format:
        {
            "groq_api_keys": ["key1", "key2"],
            "gemini_api_keys": ["key1"],
            "gemini_models": ["gemini-2.0-flash"],
            "preferred_provider": "groq"
        }
        """
        self.config = config
        self.groq_keys = [k for k in config.get("groq_api_keys", []) if k and k.strip()]
        self.gemini_keys = [k for k in config.get("gemini_api_keys", []) if k and k.strip()]
        self.gemini_models = config.get("gemini_models", ["gemini-2.0-flash", "gemini-1.5-flash"])
        
        self.groq_index = 0
        self.gemini_key_index = 0
        self.gemini_model_index = 0
        
        self.logger = get_logger("multi_ai")
    
    def generate_content(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        max_retries: int = 5
    ) -> str:
        """Generate content using available AI providers."""
        
        last_error = None
        
        # Try Groq first (free and fast)
        if self.groq_keys:
            for attempt in range(max_retries):
                try:
                    result = self._call_groq(prompt, temperature, max_tokens)
                    if result:
                        return result
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    if "rate" in error_str or "429" in error_str:
                        self.logger.warning("Groq rate limit, trying next key...")
                        self.groq_index = (self.groq_index + 1) % len(self.groq_keys)
                        time.sleep(5)
                        continue
                    elif "invalid" in error_str or "unauthorized" in error_str:
                        self.logger.warning("Groq key invalid, trying next...")
                        self.groq_index = (self.groq_index + 1) % len(self.groq_keys)
                        continue
                    else:
                        self.logger.error(f"Groq error: {e}")
                        break
        
        # Fallback to Gemini
        if self.gemini_keys:
            for attempt in range(max_retries):
                try:
                    result = self._call_gemini(prompt, temperature, max_tokens)
                    if result:
                        return result
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    
                    if "leaked" in error_str:
                        self.logger.error("Gemini key leaked! Using next key...")
                        self.gemini_key_index = (self.gemini_key_index + 1) % len(self.gemini_keys)
                        continue
                    elif "429" in error_str or "quota" in error_str:
                        self.logger.warning("Gemini quota exceeded, trying next...")
                        self.gemini_key_index = (self.gemini_key_index + 1) % len(self.gemini_keys)
                        time.sleep(10)
                        continue
                    elif "404" in error_str:
                        self.logger.warning("Gemini model not found, trying next...")
                        self.gemini_model_index = (self.gemini_model_index + 1) % len(self.gemini_models)
                        continue
                    else:
                        self.logger.error(f"Gemini error: {e}")
                        break
        
        if last_error:
            raise last_error
        raise RuntimeError("No AI providers available")
    
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
        self.min_scene_duration = settings.get("min_scene_duration", 15)
        self.max_scene_duration = settings.get("max_scene_duration", 25)
    
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
        
        # Gom thành scenes
        scenes_data = group_srt_into_scenes(
            srt_entries,
            min_duration=self.min_scene_duration,
            max_duration=self.max_scene_duration
        )
        
        self.logger.info(f"Gom thành {len(scenes_data)} scenes")
        
        # Tạo full story text để phân tích nhân vật
        full_story = " ".join([e.text for e in srt_entries])
        
        # Step 1: Phân tích nhân vật
        self.logger.info("Phân tích nhân vật qua Gemini...")
        characters, context_lock = self._analyze_characters(full_story)

        if not characters:
            self.logger.error("Không thể phân tích nhân vật")
            return False

        self.logger.info(f"Context lock: {context_lock[:100]}..." if context_lock else "No context lock")
        
        # Lưu nhân vật vào Excel
        for char in characters:
            char.image_file = f"{char.id}.png"
            char.status = "pending"
            workbook.add_character(char)
        
        workbook.save()
        self.logger.info(f"Đã lưu {len(characters)} nhân vật")
        
        # Step 2: Tạo prompts cho từng batch scenes
        self.logger.info("Tạo prompts cho scenes...")
        
        # Chia scenes thành batches để tránh vượt quá context limit
        batch_size = 10
        all_scene_prompts = []
        
        for i in range(0, len(scenes_data), batch_size):
            batch = scenes_data[i:i + batch_size]
            self.logger.info(f"Xử lý batch {i // batch_size + 1}/{(len(scenes_data) - 1) // batch_size + 1}")
            
            scene_prompts = self._generate_scene_prompts(characters, batch, context_lock)
            all_scene_prompts.extend(scene_prompts)
            
            # Rate limiting
            if i + batch_size < len(scenes_data):
                time.sleep(2)  # Tránh rate limit
        
        # Lưu scenes vào Excel
        for scene_data, prompts in zip(scenes_data, all_scene_prompts):
            scene = Scene(
                scene_id=scene_data["scene_id"],
                srt_start=scene_data["srt_start"],
                srt_end=scene_data["srt_end"],
                srt_text=scene_data["text"][:500],  # Truncate nếu quá dài
                img_prompt=prompts.get("img_prompt", ""),
                video_prompt=prompts.get("video_prompt", ""),
                status_img="pending",
                status_vid="pending"
            )
            workbook.add_scene(scene)
        
        workbook.save()
        self.logger.info(f"Đã lưu {len(scenes_data)} scenes với prompts")
        
        return True
    
    def _analyze_characters(self, story_text: str) -> tuple:
        """
        Phân tích truyện và trích xuất nhân vật.

        Args:
            story_text: Toàn bộ nội dung truyện

        Returns:
            Tuple (List[Character], context_lock: str)
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
                return [], ""

            # Extract context_lock (new in v2.0)
            context_lock = json_data.get("context_lock", "")

            characters = []
            for char_data in json_data["characters"]:
                # Support both old format (english_prompt) and new format (portrait_prompt, character_lock)
                english_prompt = char_data.get("english_prompt", "")
                if not english_prompt:
                    # Try new format fields
                    english_prompt = char_data.get("portrait_prompt", "")
                    if english_prompt == "DO_NOT_GENERATE":
                        english_prompt = char_data.get("child_text_lock", "")

                characters.append(Character(
                    id=char_data.get("id", ""),
                    role=char_data.get("role", "supporting"),
                    name=char_data.get("name", ""),
                    english_prompt=english_prompt,
                    vietnamese_prompt=char_data.get("vietnamese_prompt", char_data.get("vietnamese_description", "")),
                ))

            return characters, context_lock

        except Exception as e:
            self.logger.error(f"Failed to analyze characters: {e}")
            return [], ""
    
    def _generate_scene_prompts(
        self,
        characters: List[Character],
        scenes_data: List[Dict[str, Any]],
        context_lock: str = ""
    ) -> List[Dict[str, str]]:
        """
        Tạo prompts cho một batch scenes.

        Args:
            characters: Danh sách nhân vật
            scenes_data: Danh sách scene data
            context_lock: Context lock string từ phân tích nhân vật

        Returns:
            List các dict chứa img_prompt và video_prompt
        """
        # Format thông tin nhân vật
        characters_info = "\n".join([
            f"- {char.id} ({char.role}): {char.name}\n  Appearance: {char.english_prompt}"
            for char in characters
        ])

        # Format thông tin scenes
        scenes_info = "\n".join([
            f"Scene {s['scene_id']} (SRT {s['srt_start']}-{s['srt_end']}):\n  \"{s['text'][:300]}...\""
            if len(s['text']) > 300 else
            f"Scene {s['scene_id']} (SRT {s['srt_start']}-{s['srt_end']}):\n  \"{s['text']}\""
            for s in scenes_data
        ])

        # Load global style từ config
        global_style = get_global_style()

        # Load prompt từ config/prompts.yaml
        prompt_template = get_generate_scenes_prompt()

        # Format locations info from characters (nếu có)
        locations_info = "Use locations appropriate for each scene context"

        # Try to format with all variables (v3.0 format)
        try:
            prompt = prompt_template.format(
                characters_info=characters_info,
                scenes_info=scenes_info,
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

Scenes:
{scenes_info}

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
                    result.append({
                        "img_prompt": prompts_map[scene_id].get("img_prompt", ""),
                        "video_prompt": prompts_map[scene_id].get("video_prompt", "")
                    })
                else:
                    result.append({"img_prompt": "", "video_prompt": ""})
            
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
