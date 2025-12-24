"""
VE3 Tool - Prompts Generator Module
===================================
Sử dụng AI API để phân tích SRT và tạo prompts cho ảnh/video.
Hỗ trợ: DeepSeek (primary), Ollama (local fallback)
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
import threading

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
# MULTI AI CLIENT (DeepSeek + Ollama)
# ============================================================================

class MultiAIClient:
    """
    Client hỗ trợ AI providers.
    Ưu tiên: DeepSeek (primary) > Ollama (local fallback)

    Tự động test và loại bỏ API keys không hoạt động khi khởi tạo.
    """

    DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
    OLLAMA_URL = "http://localhost:11434/api/generate"  # Local Ollama

    def __init__(self, config: dict, auto_filter: bool = True):
        """
        Config format:
        {
            "deepseek_api_keys": ["key1"],
            "ollama_model": "qwen2.5:7b",  # Optional: local model fallback
        }

        auto_filter: Tự động test và loại bỏ API keys không hoạt động
        """
        self.config = config
        self.deepseek_keys = [k for k in config.get("deepseek_api_keys", []) if k and k.strip()]

        # Ollama model (fallback)
        self.ollama_model = config.get("ollama_model", "qwen2.5:7b")
        self.ollama_endpoint = config.get("ollama_endpoint", "http://localhost:11434")
        self.OLLAMA_URL = f"{self.ollama_endpoint}/api/generate"
        self.ollama_available = False

        self.deepseek_index = 0

        # Parallel processing settings
        self.max_parallel_requests = config.get("max_parallel_requests", 5)
        self.parallel_enabled = config.get("parallel_enabled", True)
        self._request_lock = threading.Lock()

        self.logger = get_logger("multi_ai")

        # Auto filter exhausted APIs at startup
        if auto_filter:
            self._filter_working_apis()

    def _filter_working_apis(self):
        """Test và loại bỏ API keys không hoạt động - PARALLEL VERSION."""
        print("\n[API Filter] Dang kiem tra API keys...")

        results = {
            'deepseek': [],
            'ollama': False
        }
        results_lock = threading.Lock()

        def test_deepseek(key_info: Tuple[int, str]) -> Tuple[str, int, str, bool]:
            i, key = key_info
            result = self._test_deepseek_key(key)
            return ('deepseek', i, key, result)

        def test_ollama() -> Tuple[str, int, str, bool]:
            result = self._test_ollama()
            return ('ollama', 0, '', result)

        # Prepare all test tasks
        tasks = []
        tasks.extend([('deepseek', i, key) for i, key in enumerate(self.deepseek_keys)])

        # Use ThreadPoolExecutor for parallel API testing
        max_workers = min(len(tasks) + 1, 10)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            # Submit all API tests
            for provider, i, key in tasks:
                if provider == 'deepseek':
                    futures.append(executor.submit(test_deepseek, (i, key)))

            # Submit Ollama test
            futures.append(executor.submit(test_ollama))

            # Process results as they complete
            for future in as_completed(futures):
                try:
                    provider, idx, key, success = future.result()
                    status = "OK" if success else "SKIP"

                    if provider == 'ollama':
                        results['ollama'] = success
                        print(f"  Ollama ({self.ollama_model}): {'OK (local)' if success else 'NOT AVAILABLE'}")
                    else:
                        print(f"  {provider.capitalize()} key #{idx+1}: {status}")
                        if success:
                            with results_lock:
                                results[provider].append(key)
                except Exception as e:
                    self.logger.error(f"API test error: {e}")

        # Update with working keys only
        self.deepseek_keys = results['deepseek']
        self.ollama_available = results['ollama']

        ollama_str = ", Ollama: OK" if self.ollama_available else ""
        print(f"[API Filter] Ket qua: {len(self.deepseek_keys)} DeepSeek{ollama_str}")

        if len(self.deepseek_keys) == 0 and not self.ollama_available:
            print("[API Filter] CANH BAO: Khong co API nao hoat dong! Cai Ollama de dung offline.")
        else:
            # Show priority order
            if self.deepseek_keys:
                print(f"[API Filter] Se dung: DeepSeek (uu tien)")
            elif self.ollama_available:
                print(f"[API Filter] Se dung: Ollama (local fallback)")

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

    def _test_ollama(self) -> bool:
        """Test Ollama local server."""
        try:
            data = {
                "model": self.ollama_model,
                "prompt": "Say OK",
                "stream": False
            }
            resp = requests.post(self.OLLAMA_URL, json=data, timeout=30)
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
        Priority: DeepSeek (primary) > Ollama (local fallback)

        Chi thu cac API da duoc filter la hoat dong.
        """

        last_error = None

        # 1. Try DeepSeek first (primary)
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

        # 2. Fallback to Ollama (local, free, offline)
        if self.ollama_available:
            for attempt in range(max_retries):
                try:
                    print(f"[Ollama] Dang goi local model ({self.ollama_model})...")
                    result = self._call_ollama(prompt, temperature, max_tokens)
                    if result:
                        print(f"[Ollama] Thanh cong!")
                        return result
                except Exception as e:
                    last_error = e
                    self.logger.error(f"Ollama error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    continue

        if last_error:
            raise last_error
        raise RuntimeError("Khong co API provider nao hoat dong! Cai Ollama: ollama pull qwen2.5:7b")

    def _call_deepseek(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call DeepSeek API."""
        api_key = self.deepseek_keys[self.deepseek_index]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Determine if prompt expects JSON response
        expects_json = any(kw in prompt.lower() for kw in ['json', 'output format', '{"', "{'"])

        # DeepSeek max_tokens limit is 8192
        deepseek_max_tokens = min(max_tokens, 8192)

        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. When asked to output JSON, respond ONLY with valid JSON, no markdown code blocks, no explanations before or after the JSON."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": deepseek_max_tokens
        }

        # Force JSON mode if prompt expects JSON
        if expects_json:
            data["response_format"] = {"type": "json_object"}

        print(f"[DeepSeek] Dang goi API... (prompt: {len(prompt)} ky tu, json_mode={expects_json}, max_tokens={deepseek_max_tokens}, cho 60-180s)")

        resp = requests.post(self.DEEPSEEK_URL, headers=headers, json=data, timeout=180)

        if resp.status_code == 200:
            result = resp.json()
            content = result["choices"][0]["message"]["content"]
            print(f"[DeepSeek] Thanh cong! Response: {len(content)} ky tu")

            # Log preview for debugging
            if content:
                preview = content[:300].replace('\n', ' ')
                print(f"[DeepSeek] Preview: {preview}...")

            return content
        else:
            error_text = resp.text[:500]
            print(f"[DeepSeek] Error {resp.status_code}: {error_text}")
            raise requests.RequestException(f"DeepSeek API error {resp.status_code}: {error_text}")

    def _call_ollama(self, prompt: str, temperature: float, max_tokens: int = 16000) -> str:
        """Call Ollama local API.

        Args:
            prompt: The prompt to send
            temperature: Temperature for generation
            max_tokens: Max output tokens (default 16000 for large responses like Director's Shooting Plan)
        """
        data = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,  # Higher for Director's Shooting Plan
                "num_ctx": 32768,  # Context window - qwen2.5:7b supports up to 128k
            }
        }

        self.logger.debug(f"Calling Ollama API: model={self.ollama_model}, max_tokens={max_tokens}")
        print(f"[Ollama] Dang xu ly voi {self.ollama_model}... (co the mat 2-5 phut)")

        # Ollama can be slow, increase timeout
        resp = requests.post(self.OLLAMA_URL, json=data, timeout=600)

        if resp.status_code == 200:
            result = resp.json()
            response_text = result.get("response", "")
            if not response_text or not response_text.strip():
                self.logger.warning(f"[Ollama] Returned empty response. Full result: {result}")
                raise ValueError("Ollama returned empty response")
            return response_text
        else:
            raise requests.RequestException(f"Ollama API error {resp.status_code}: {resp.text[:200]}")

    def generate_batch_parallel(
        self,
        prompts: List[str],
        temperature: float = 0.7,
        max_tokens: int = 8192,
        max_workers: int = None
    ) -> List[str]:
        """
        Generate content for multiple prompts in parallel.

        Args:
            prompts: List of prompts to process
            temperature: Temperature for generation
            max_tokens: Max tokens per response
            max_workers: Max parallel workers (None = auto)

        Returns:
            List of responses in same order as prompts
        """
        if not prompts:
            return []

        # Single prompt - no parallelization needed
        if len(prompts) == 1:
            return [self.generate_content(prompts[0], temperature, max_tokens)]

        # Determine worker count
        if max_workers is None:
            # Use total available API keys as max workers
            total_keys = len(self.deepseek_keys)
            if self.ollama_available:
                total_keys += 1  # Ollama can handle 1 at a time
            max_workers = min(self.max_parallel_requests, max(1, total_keys))

        print(f"[Parallel] Xu ly {len(prompts)} prompts voi {max_workers} workers...")

        # Results placeholder (preserve order)
        results = [None] * len(prompts)
        errors = []

        def process_prompt(idx_prompt: Tuple[int, str]) -> Tuple[int, str, Exception]:
            """Process single prompt and return (index, result, error)."""
            idx, prompt = idx_prompt
            try:
                # Thread-safe API selection
                with self._request_lock:
                    pass  # Lock just to serialize index updates

                result = self.generate_content(prompt, temperature, max_tokens)
                return (idx, result, None)
            except Exception as e:
                return (idx, "", e)

        # Execute in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(process_prompt, (i, p))
                for i, p in enumerate(prompts)
            ]

            # Process as completed with progress
            completed = 0
            for future in as_completed(futures):
                idx, result, error = future.result()
                completed += 1

                if error:
                    errors.append((idx, error))
                    self.logger.warning(f"Prompt {idx+1} failed: {error}")
                    results[idx] = ""  # Empty result for failed
                else:
                    results[idx] = result

                print(f"[Parallel] Hoan thanh {completed}/{len(prompts)}...", end="\r")

        print(f"[Parallel] Hoan thanh {len(prompts)} prompts, {len(errors)} loi")

        # Retry failed prompts sequentially
        if errors:
            print(f"[Parallel] Retry {len(errors)} prompts that bi loi...")
            for idx, _ in errors:
                try:
                    results[idx] = self.generate_content(prompts[idx], temperature, max_tokens)
                except Exception as e:
                    self.logger.error(f"Retry failed for prompt {idx+1}: {e}")
                    results[idx] = ""

        return results


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
    Class tạo prompts từ file SRT sử dụng AI API (DeepSeek + Ollama).

    Flow:
    1. Đọc SRT và gom thành scenes
    2. Gọi AI để phân tích nhân vật
    3. Gọi AI để tạo prompt cho từng scene
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

        # Sử dụng MultiAIClient (DeepSeek + Ollama)
        self.ai_client = MultiAIClient(settings)

        # Scene grouping settings
        self.min_scene_duration = settings.get("min_scene_duration", 3)  # Min 3s
        self.max_scene_duration = settings.get("max_scene_duration", 8)  # Max 8s per scene

        # Parallel processing settings
        self.parallel_enabled = settings.get("parallel_enabled", True)
        self.max_parallel_batches = settings.get("max_parallel_batches", 3)  # Parallel batch processing
        self.batch_size = settings.get("prompt_batch_size", 10)  # Scenes per batch

    def _is_child_character(self, char_id: str) -> bool:
        """
        Check if a character ID represents a child (cannot use reference image).
        Children cause API policy violations when used as reference images.

        Child patterns:
        - nvc1: narrator as child
        - IDs ending with numbers that indicate child versions
        - Or any ID marked with is_child=true in analyze_story
        """
        if not char_id:
            return False

        # Remove .png extension if present
        char_id_clean = char_id.replace('.png', '').lower()

        # Known child character patterns
        child_patterns = ['nvc1', 'nv1c', 'child']

        for pattern in child_patterns:
            if pattern in char_id_clean:
                return True

        return False

    def _filter_children_from_refs(self, ref_files: list, return_filtered: bool = False) -> list:
        """
        Filter out child characters from reference_files list.
        Children should be described inline in img_prompt, not referenced.

        Args:
            ref_files: List of reference file names (e.g., ["nvc.png", "nvc1.png", "loc.png"])
            return_filtered: If True, return tuple (filtered_refs, filtered_children)

        Returns:
            Filtered list without child characters, or tuple if return_filtered=True
        """
        if not ref_files:
            return ([], []) if return_filtered else []

        filtered = []
        children = []
        for ref in ref_files:
            if self._is_child_character(ref):
                self.logger.info(f"  -> Filtered out child character from references: {ref}")
                children.append(ref)
                continue
            filtered.append(ref)

        if return_filtered:
            return filtered, children
        return filtered

    def _get_child_inline_description(self, child_ref: str, characters: list) -> str:
        """
        Get inline description for a child character using their character_lock.

        Args:
            child_ref: Child reference file name (e.g., "nvc1.png")
            characters: List of Character objects

        Returns:
            Inline description like "(Child: 8-year-old boy, messy brown hair...)"
        """
        if not characters:
            return ""

        # Extract character ID from filename (remove .png extension)
        char_id = child_ref.replace(".png", "")

        # Find matching character
        for char in characters:
            if char.id == char_id:
                # Use character_lock for inline description
                char_lock = getattr(char, 'character_lock', '')
                if char_lock:
                    return f"(Child: {char_lock})"
        return ""

    def _add_children_inline_to_prompt(
        self,
        img_prompt: str,
        filtered_children: list,
        characters: list
    ) -> str:
        """
        Add inline descriptions for filtered children to the img_prompt.

        Args:
            img_prompt: Original prompt
            filtered_children: List of child reference files that were filtered
            characters: List of Character objects

        Returns:
            Updated prompt with inline child descriptions
        """
        if not img_prompt or not filtered_children or not characters:
            return img_prompt

        # Collect inline descriptions
        inline_descs = []
        for child_ref in filtered_children:
            desc = self._get_child_inline_description(child_ref, characters)
            if desc:
                inline_descs.append(desc)
                self.logger.info(f"  -> Added inline description for {child_ref}: {desc[:50]}...")

        if inline_descs:
            # Add at the beginning or end of prompt
            inline_text = ", ".join(inline_descs)
            # Add to prompt - prepend to make children visible in the scene
            img_prompt = f"{inline_text} - {img_prompt}"

        return img_prompt

    def _add_filename_annotations_to_prompt(
        self,
        img_prompt: str,
        reference_files: list,
        characters: list = None,
        locations: list = None
    ) -> str:
        """
        Add filename annotations to img_prompt for Flow to match uploaded reference images.

        Args:
            img_prompt: Original prompt
            reference_files: List of reference files (e.g., ["nvc.png", "nv1.png", "loc_apartment.png"])
            characters: List of Character objects (optional, for better matching)
            locations: List of Location objects (optional, for better matching)

        Returns:
            Updated prompt with filename annotations

        Example:
            Input:  "A 30-year-old man walking in the living room"
            Output: "A 30-year-old man (nvc.png) walking in the living room (loc_apartment.png)"
        """
        if not img_prompt or not reference_files:
            return img_prompt

        result = img_prompt
        annotations_added = []

        # Build lookup maps
        char_map = {}  # id -> character_lock
        loc_map = {}   # id -> location_lock

        if characters:
            for c in characters:
                char_map[c.id] = c.character_lock or c.vietnamese_prompt or c.name

        if locations:
            for loc in locations:
                loc_map[loc.id] = loc.location_lock or loc.name

        # Add annotations for each reference file
        for ref_file in reference_files:
            # Ensure filename has extension
            if not any(ref_file.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                ref_file = f"{ref_file}.png"

            ref_id = ref_file.replace('.png', '').replace('.jpg', '').replace('.jpeg', '').replace('.webp', '')
            annotation = f"({ref_file})"

            # Check if annotation already exists
            if annotation in result:
                annotations_added.append(ref_file)
                continue

            # Try to find where to insert annotation
            inserted = False

            # Method 1: Match character_lock/location_lock in prompt
            if ref_id in char_map and char_map[ref_id]:
                desc = char_map[ref_id]
                # Try to find description in prompt and add annotation after
                match_len = min(30, len(desc))
                if match_len > 5 and desc[:match_len] in result:
                    # Find end of description (next comma, period, or clause)
                    idx = result.find(desc[:match_len])
                    if idx >= 0:
                        # Find the end of this character description
                        end_idx = idx + match_len
                        for end_char in [',', '.', ' in ', ' at ', ' with ', ' and ']:
                            pos = result.find(end_char, end_idx)
                            if pos > 0 and pos < end_idx + 100:
                                end_idx = pos
                                break
                        # Insert annotation
                        result = result[:end_idx] + f" {annotation}" + result[end_idx:]
                        inserted = True
                        annotations_added.append(ref_file)

            if not inserted and ref_id in loc_map and loc_map[ref_id]:
                desc = loc_map[ref_id]
                match_len = min(20, len(desc))
                if match_len > 5 and desc[:match_len] in result:
                    idx = result.find(desc[:match_len])
                    if idx >= 0:
                        end_idx = idx + match_len
                        for end_char in [',', '.', ' with ', ' and ']:
                            pos = result.find(end_char, end_idx)
                            if pos > 0 and pos < end_idx + 80:
                                end_idx = pos
                                break
                        result = result[:end_idx] + f" {annotation}" + result[end_idx:]
                        inserted = True
                        annotations_added.append(ref_file)

            # Method 2: If not inserted, will be added at the end as consolidated annotation
            if not inserted:
                annotations_added.append(ref_file)

        # Method 3: Add consolidated reference annotation at the end
        # This ensures ALL reference files are mentioned even if not inserted inline
        missing_annotations = [f for f in reference_files if f"({f}" not in result and f not in [a for a in annotations_added if f"({a})" in result]]

        # Ensure all refs have .png extension for checking
        all_refs_normalized = []
        for ref in reference_files:
            if not any(ref.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                ref = f"{ref}.png"
            all_refs_normalized.append(ref)

        # Check which refs are NOT yet in the result
        refs_not_in_result = [ref for ref in all_refs_normalized if f"({ref})" not in result]

        if refs_not_in_result:
            # Add as consolidated annotation at end
            refs_str = ", ".join(refs_not_in_result)
            # Clean up ending
            result = result.rstrip('. ')
            result = f"{result} (reference: {refs_str})."

        return result

    def _generate_content(self, prompt: str, temperature: float = 0.7, max_tokens: int = 8192) -> str:
        """Generate content using available AI providers (DeepSeek + Ollama)."""
        return self.ai_client.generate_content(prompt, temperature, max_tokens)

    def _generate_content_large(self, prompt: str, temperature: float = 0.7, max_tokens: int = 16000) -> str:
        """
        Generate content với ưu tiên DeepSeek (primary) > Ollama (fallback).

        DeepSeek có giới hạn max_tokens=8192, có thể bị truncate với Director's Shooting Plan.
        Ollama không có giới hạn tokens nhưng có thể chậm hoặc timeout.

        Priority (theo yêu cầu user):
        1. DeepSeek - Primary, nhanh và ổn định
        2. Ollama - Fallback nếu DeepSeek thất bại
        """
        # Thử DeepSeek trước (primary)
        print("[Director] Dùng DeepSeek (primary, nhanh, giới hạn 8192 tokens)")
        try:
            result = self.ai_client.generate_content(prompt, temperature, min(max_tokens, 8192))
            if result:
                print(f"[Director] DeepSeek trả về {len(result)} ký tự")
                # Check if response might be truncated
                if len(result) > 30000:
                    print("[Director] Response dài, có thể bị truncate...")
                return result
        except Exception as e:
            self.logger.warning(f"[Director] DeepSeek failed: {e}, falling back to Ollama...")
            print(f"[Director] DeepSeek thất bại: {e}, chuyển sang Ollama...")

        # Fallback: dùng Ollama (không giới hạn tokens nhưng có thể chậm)
        if hasattr(self.ai_client, 'ollama_available') and self.ai_client.ollama_available:
            print(f"[Director] Dùng Ollama {self.ai_client.ollama_model} (fallback, không giới hạn tokens)")
            try:
                result = self.ai_client._call_ollama(prompt, temperature, max_tokens)
                if result:
                    print(f"[Director] Ollama trả về {len(result)} ký tự")
                    return result
            except Exception as e:
                self.logger.warning(f"[Director] Ollama also failed: {e}")
                print(f"[Director] Ollama cũng thất bại: {e}")

        return ""

    def generate_for_project(
        self,
        project_dir: Path,
        code: str,
        overwrite: bool = False,
        on_characters_ready: Callable = None
    ) -> bool:
        """
        Tạo prompts cho một project.

        Args:
            project_dir: Path đến thư mục project
            code: Mã project
            overwrite: Nếu True, ghi đè prompts đã có
            on_characters_ready: Callback được gọi ngay khi characters được save
                                 Signature: on_characters_ready(excel_path, proj_dir)
                                 Cho phép caller bắt đầu tạo ảnh nhân vật song song

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

        # Lưu nhân vật vào Excel (skip children - họ sẽ được mô tả inline trong scene)
        children_skipped = 0
        for char in characters:
            # Children don't need reference images - they will be described inline in scene prompts
            if char.is_child or char.english_prompt == "DO_NOT_GENERATE":
                char.image_file = "NONE"
                char.status = "skip"  # Skip image generation
                children_skipped += 1
                self.logger.info(f"  -> Skipping child character: {char.id} (will use inline description)")
            else:
                char.image_file = f"{char.id}.png"
                char.status = "pending"
            workbook.add_character(char)

        if children_skipped > 0:
            self.logger.info(f"  -> {children_skipped} child characters skipped for image generation")

        # Lưu locations (as Character with role="location")
        for loc in locations:
            loc_char = Character(
                id=loc.id,
                role="location",
                name=loc.name,
                english_prompt=loc.english_prompt,  # location_prompt - for generating reference image
                character_lock=loc.location_lock,   # location_lock - for scene prompts (IMPORTANT!)
                vietnamese_prompt=loc.location_lock,  # Keep for backwards compat
                image_file=f"{loc.id}.png",
                status="pending"
            )
            workbook.add_character(loc_char)

        workbook.save()
        self.logger.info(f"Đã lưu {len(characters)} nhân vật + {len(locations)} bối cảnh")

        # === PARALLEL OPTIMIZATION ===
        # Gọi callback để caller có thể bắt đầu tạo ảnh nhân vật SONG SONG
        # trong khi vẫn tiếp tục tạo scene prompts
        if on_characters_ready:
            self.logger.info("[PARALLEL] Characters ready! Triggering character image generation...")
            try:
                on_characters_ready(excel_path, project_dir)
            except Exception as e:
                self.logger.warning(f"[PARALLEL] Callback error (non-fatal): {e}")

        # Step 1.5: Director's Treatment - Phân tích cấu trúc câu chuyện
        self.logger.info("=" * 50)
        self.logger.info("Step 1.5: Tạo DIRECTOR'S TREATMENT (Kịch bản đạo diễn)...")
        self.logger.info("=" * 50)
        directors_treatment = self._create_directors_treatment(full_story)
        if directors_treatment:
            self.logger.info(f"[Director's Treatment] Story parts: {len(directors_treatment.get('story_parts', []))}")

        # Step 2: DIRECTOR'S SHOOTING PLAN - Đạo diễn lên kế hoạch quay
        self.logger.info("=" * 50)
        self.logger.info("Step 2: DIRECTOR'S SHOOTING PLAN - Đạo diễn quyết định ảnh!")
        self.logger.info("=" * 50)

        directors_shooting = self._create_directors_shooting_plan(
            full_story, srt_entries, characters, locations, global_style
        )

        using_director_prompts = False  # Flag để biết có dùng prompts từ đạo diễn không

        if directors_shooting and directors_shooting.get("shooting_plan"):
            # Dùng kế hoạch quay từ đạo diễn
            scenes_data = self._convert_shooting_plan_to_scenes(directors_shooting["shooting_plan"])
            using_director_prompts = True
            self.logger.info(f"[Director] ✓ Sử dụng {len(scenes_data)} shots từ đạo diễn")
        else:
            # Fallback: Dùng smart_divide_scenes cũ
            self.logger.warning("[Director] Không có kế hoạch quay, sử dụng smart_divide_scenes...")
            scenes_data = self._smart_divide_scenes(srt_entries, characters, locations, directors_treatment, global_style)
            using_director_prompts = False

        self.logger.info(f"Tổng cộng {len(scenes_data)} scenes")

        # Step 3: Tạo prompts cho từng batch scenes (PARALLEL)
        self.logger.info("=" * 50)
        self.logger.info("Step 3: Tạo IMG PROMPTS cho scenes...")
        self.logger.info("=" * 50)

        if not scenes_data:
            self.logger.error("KHÔNG CÓ SCENES DATA! Dừng.")
            return False

        all_scene_prompts = []

        # === NẾU ĐẠO DIỄN ĐÃ TẠO PROMPTS → DÙ LUÔN, KHÔNG CẦN GỌI AI NỮA ===
        if using_director_prompts:
            self.logger.info("[Director Flow] Đạo diễn đã tạo prompts! Sử dụng trực tiếp...")
            for scene in scenes_data:
                # Lấy prompts từ scene (đạo diễn đã điền)
                # Ưu tiên characters_used/location_used đã được set trong _convert_shooting_plan_to_scenes
                chars_used = scene.get("characters_used", scene.get("characters_in_scene", []))
                loc_used = scene.get("location_used", scene.get("location_id", ""))

                all_scene_prompts.append({
                    "img_prompt": scene.get("img_prompt", ""),
                    "video_prompt": scene.get("img_prompt", ""),  # Dùng chung img_prompt cho video
                    "characters_used": chars_used,
                    "location_used": loc_used,
                    "reference_files": scene.get("reference_files", []),
                    "shot_type": scene.get("shot_type", ""),
                    "camera_angle": scene.get("camera_angle", ""),
                })
            self.logger.info(f"[Director Flow] ✓ Lấy {len(all_scene_prompts)} prompts từ đạo diễn")
        else:
            # === FLOW CŨ: Gọi AI tạo prompts ===
            self.logger.info("[Legacy Flow] Tạo prompts bằng AI...")

            # Chia scenes thành batches để tránh vượt quá context limit
            batch_size = self.batch_size
            batches = []
            for i in range(0, len(scenes_data), batch_size):
                batches.append(scenes_data[i:i + batch_size])

            total_batches = len(batches)
            self.logger.info(f"Chia thanh {total_batches} batches, moi batch {batch_size} scenes")

            if self.parallel_enabled and total_batches > 1:
                # PARALLEL PROCESSING: Process multiple batches concurrently
                self.logger.info(f"[Parallel] Xu ly {total_batches} batches song song (max {self.max_parallel_batches} workers)...")

                def process_batch(batch_info: Tuple[int, List]) -> Tuple[int, List]:
                    """Process single batch and return (batch_idx, prompts)."""
                    batch_idx, batch = batch_info
                    prompts = self._generate_scene_prompts(
                        characters, batch, context_lock,
                        locations=locations,
                        global_style_override=global_style
                    )
                    return (batch_idx, prompts)

                # Results placeholder (preserve order)
                batch_results = [None] * total_batches

                with ThreadPoolExecutor(max_workers=self.max_parallel_batches) as executor:
                    futures = [
                        executor.submit(process_batch, (i, batch))
                        for i, batch in enumerate(batches)
                    ]

                    # Process as completed with progress
                    completed = 0
                    for future in as_completed(futures):
                        try:
                            batch_idx, prompts = future.result()
                            batch_results[batch_idx] = prompts
                            completed += 1
                            print(f"[Parallel] Batch {completed}/{total_batches} hoan thanh")
                        except Exception as e:
                            self.logger.error(f"Batch failed: {e}")

                # Flatten results in order
                for prompts in batch_results:
                    if prompts:
                        all_scene_prompts.extend(prompts)
                    else:
                        # Batch failed, add empty prompts
                        self.logger.warning("Some batch failed, using empty prompts")

                print(f"[Parallel] Hoan thanh {len(all_scene_prompts)} scene prompts")
            else:
                # SEQUENTIAL PROCESSING (fallback)
                for i, batch in enumerate(batches):
                    self.logger.info(f"Xu ly batch {i + 1}/{total_batches}")

                    scene_prompts = self._generate_scene_prompts(
                        characters, batch, context_lock,
                        locations=locations,
                        global_style_override=global_style
                    )
                    all_scene_prompts.extend(scene_prompts)

                    # Rate limiting
                    if i + 1 < total_batches:
                        time.sleep(2)  # Tránh rate limit

        # === VALIDATE: Đảm bảo all_scene_prompts có đủ số lượng như scenes_data ===
        self.logger.info(f"Scenes: {len(scenes_data)}, Prompts: {len(all_scene_prompts)}")
        if len(all_scene_prompts) < len(scenes_data):
            self.logger.warning(f"THIẾU {len(scenes_data) - len(all_scene_prompts)} prompts! Tạo fallback...")
            while len(all_scene_prompts) < len(scenes_data):
                idx = len(all_scene_prompts)
                scene = scenes_data[idx]
                # Tạo prompt từ visual_moment hoặc text
                visual = scene.get("visual_moment", scene.get("text", ""))
                fallback_prompt = f"{scene.get('shot_type', 'Medium shot')}, {visual[:300]}, cinematic lighting, 4K photorealistic"
                all_scene_prompts.append({
                    "img_prompt": fallback_prompt,
                    "video_prompt": fallback_prompt,
                    "characters_used": scene.get("characters_in_scene", []),
                    "location_used": scene.get("location_id", ""),
                    "reference_files": []
                })
                self.logger.info(f"Created fallback prompt for scene {idx + 1}")

        # Lưu scenes vào Excel
        for scene_data, prompts in zip(scenes_data, all_scene_prompts):
            # Convert lists to JSON strings for storage
            chars_used = prompts.get("characters_used", [])

            # === LOCATION: Ưu tiên từ AI, fallback từ scene_data (Director Flow) ===
            location_used = prompts.get("location_used", "")
            if not location_used:
                # Fallback: dùng location_id từ bước chia scene (smart_divide_scenes)
                location_used = scene_data.get("location_id", "")
                if location_used:
                    self.logger.debug(f"Scene {scene_data['scene_id']}: Using location_id from scene division: {location_used}")

            ref_files = prompts.get("reference_files", [])

            # === AUTO-GENERATE reference_files nếu AI không điền ===
            if not ref_files:
                ref_files = []

                # Ưu tiên 1: Lấy từ prompts (characters_used)
                if chars_used:
                    if isinstance(chars_used, str):
                        try:
                            chars_used = json.loads(chars_used)
                        except:
                            chars_used = [chars_used]
                    for char_id in chars_used:
                        if char_id and not char_id.endswith('.png'):
                            ref_files.append(f"{char_id}.png")
                        elif char_id:
                            ref_files.append(char_id)

                # Ưu tiên 2: Fallback từ scene_data (characters_in_scene từ smart_divide)
                if not ref_files:
                    chars_in_scene = scene_data.get("characters_in_scene", [])
                    if chars_in_scene:
                        if isinstance(chars_in_scene, str):
                            try:
                                chars_in_scene = json.loads(chars_in_scene)
                            except:
                                chars_in_scene = [chars_in_scene]
                        for char_id in chars_in_scene:
                            if char_id and not char_id.endswith('.png'):
                                ref_files.append(f"{char_id}.png")
                            elif char_id:
                                ref_files.append(char_id)
                        self.logger.debug(f"Scene {scene_data['scene_id']}: Using characters_in_scene: {chars_in_scene}")

                # Thêm location đã dùng - MAP sang actual location ID
                if location_used:
                    # Tìm actual location ID từ locations list
                    actual_loc_id = None

                    # Nếu location_used đã là ID thực (có file tương ứng trong locations)
                    for loc in locations:
                        if loc.id == location_used:
                            actual_loc_id = location_used
                            break

                    # Nếu không tìm thấy, location_used có thể là generic (loc1, loc2...)
                    # Thử match theo index hoặc dùng location đầu tiên
                    if not actual_loc_id and locations:
                        # Nếu là loc1, loc2... thử parse index
                        import re
                        match = re.match(r'loc(\d+)', location_used)
                        if match:
                            idx = int(match.group(1)) - 1  # loc1 -> index 0
                            if 0 <= idx < len(locations):
                                actual_loc_id = locations[idx].id
                                self.logger.debug(f"Scene: Mapped '{location_used}' to '{actual_loc_id}'")

                        # Fallback: dùng location đầu tiên
                        if not actual_loc_id:
                            actual_loc_id = locations[0].id
                            self.logger.debug(f"Scene: Fallback '{location_used}' to '{actual_loc_id}'")

                    # Thêm vào ref_files nếu tìm được
                    if actual_loc_id:
                        loc_file = f"{actual_loc_id}.png" if not actual_loc_id.endswith('.png') else actual_loc_id
                        if loc_file not in ref_files:
                            ref_files.append(loc_file)
                        # Cập nhật location_used thành actual ID
                        location_used = actual_loc_id

                if ref_files:
                    self.logger.debug(f"Scene {scene_data['scene_id']}: Auto-generated reference_files: {ref_files}")

            # === QUAN TRỌNG: Đảm bảo LUÔN có nhân vật trong reference ===
            # Kiểm tra xem có nhân vật nào trong ref_files không
            has_character = False
            if ref_files:
                for ref in ref_files:
                    ref_lower = str(ref).lower()
                    # nvc, nv1, nv2... là nhân vật (không phải loc)
                    if ref_lower.startswith('nv'):
                        has_character = True
                        break

            # Nếu không có nhân vật nào → chọn nhân vật PHÙ HỢP dựa trên scene_type
            if not has_character:
                scene_type = scene_data.get("scene_type", "FRAME_PRESENT")

                # Chọn nhân vật dựa trên loại scene
                if scene_type == "CHILDHOOD_FLASHBACK":
                    # Flashback tuổi thơ: CHỈ dùng mẹ trẻ (KHÔNG dùng child reference - API policy!)
                    # Child sẽ được mô tả chi tiết trong img_prompt thay vì dùng reference
                    default_chars = ["nv1_young.png"]
                    self.logger.info(f"Scene {scene_data['scene_id']}: CHILDHOOD_FLASHBACK → using young mother only (child described in prompt)")
                elif scene_type == "ADULT_FLASHBACK":
                    # Flashback trưởng thành: narrator trẻ
                    default_chars = ["nvc_young.png"]
                    self.logger.info(f"Scene {scene_data['scene_id']}: ADULT_FLASHBACK → using young narrator")
                elif scene_type == "EMOTIONAL_BEAT":
                    # Cảm xúc: narrator hiện tại (close-up)
                    default_chars = ["nvc.png"]
                    self.logger.info(f"Scene {scene_data['scene_id']}: EMOTIONAL_BEAT → using narrator close-up")
                else:  # FRAME_PRESENT, YOUTUBE_CTA, default
                    # Hiện tại: narrator hiện tại
                    default_chars = ["nvc.png"]
                    self.logger.info(f"Scene {scene_data['scene_id']}: {scene_type} → using current narrator")

                # Thêm vào ref_files
                if not ref_files:
                    ref_files = default_chars.copy()
                else:
                    # Có loc nhưng không có nhân vật → thêm nhân vật vào đầu
                    for char in reversed(default_chars):
                        ref_files.insert(0, char)

            # === QUAN TRỌNG: Filter children từ reference_files (API policy violation) ===
            # Children phải được mô tả trong img_prompt, không dùng reference image
            ref_files, filtered_children = self._filter_children_from_refs(ref_files, return_filtered=True)

            chars_str = json.dumps(chars_used) if isinstance(chars_used, list) else str(chars_used)
            refs_str = json.dumps(ref_files) if isinstance(ref_files, list) else str(ref_files)

            # Lấy thời gian thực từ scene_data (đã được tính trong _validate_and_split_scenes)
            start_time = scene_data.get("start_time", "")
            end_time = scene_data.get("end_time", "")
            duration = scene_data.get("duration_seconds", 0)

            # === QUAN TRỌNG: Thêm filename annotations vào prompt ===
            # Format: "A 30-year-old man (nvc.png) walking in the park (loc_park.png)"
            # Giúp Flow match uploaded images với prompt
            img_prompt = prompts.get("img_prompt", "")
            video_prompt = prompts.get("video_prompt", "")

            # === ADD INLINE CHILD DESCRIPTIONS ===
            # Children must be described inline since they can't use reference images
            if filtered_children:
                img_prompt = self._add_children_inline_to_prompt(img_prompt, filtered_children, characters)
                video_prompt = self._add_children_inline_to_prompt(video_prompt, filtered_children, characters)

            if ref_files:
                img_prompt = self._add_filename_annotations_to_prompt(
                    img_prompt, ref_files, characters, locations
                )
                video_prompt = self._add_filename_annotations_to_prompt(
                    video_prompt, ref_files, characters, locations
                )

            # QUAN TRONG: srt_start/srt_end la timestamps chinh
            # Fallback sang start_time/end_time neu khong co
            srt_start_val = scene_data.get("srt_start") or start_time or "00:00:00,000"
            srt_end_val = scene_data.get("srt_end") or end_time or "00:00:05,000"

            # Tinh duration neu chua co
            if not duration and srt_start_val and srt_end_val:
                try:
                    duration = parse_time_to_seconds(srt_end_val) - parse_time_to_seconds(srt_start_val)
                except:
                    duration = 5.0  # Default 5s

            # planned_duration: thoi luong dao dien len ke hoach (mac dinh = duration)
            # Nguoi dung co the thay doi trong Excel sau
            planned_duration = scene_data.get("planned_duration", duration)

            scene = Scene(
                scene_id=scene_data["scene_id"],
                srt_start=srt_start_val,              # Timestamp bat dau (HH:MM:SS,mmm)
                srt_end=srt_end_val,                  # Timestamp ket thuc (HH:MM:SS,mmm)
                duration=round(duration, 2),          # Do dai tu SRT (giay)
                planned_duration=round(planned_duration, 2),  # Thoi luong dao dien ke hoach
                srt_text=scene_data.get("text", "")[:500],  # Truncate nếu quá dài
                img_prompt=img_prompt,
                video_prompt=video_prompt,
                status_img="pending",
                status_vid="pending",
                characters_used=chars_str,
                location_used=location_used,
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
            # Dùng _generate_content_large để ưu tiên Ollama (không giới hạn tokens)
            # DeepSeek chỉ có 8192 tokens output, không đủ cho analyze_story phức tạp
            response = self._generate_content_large(prompt, temperature=0.5, max_tokens=16000)

            # Parse JSON từ response
            json_data = self._extract_json(response)

            if not json_data or "characters" not in json_data:
                self.logger.error(f"Invalid characters response: {response[:500]}")
                return [], [], "", ""

            # Extract context_lock and global_style (v5.0 format)
            context_lock = json_data.get("context_lock", "")
            global_style = json_data.get("global_style", "")

            # Extract world_setting (v6.0 - Director's Vision)
            world_setting = json_data.get("world_setting", {})
            if world_setting:
                self.logger.info(f"[Director's Vision] Era: {world_setting.get('era', 'N/A')}, Setting: {world_setting.get('setting', 'N/A')}")
                # Nếu không có context_lock, tạo từ world_setting
                if not context_lock:
                    context_lock = f"{world_setting.get('era', '')}, {world_setting.get('setting', '')}, {world_setting.get('visual_style', '')}"
                    self.logger.info(f"[Director's Vision] Generated context_lock: {context_lock[:100]}...")

            # Extract characters
            characters = []
            for char_data in json_data["characters"]:
                # portrait_prompt = full prompt for generating reference image (white background)
                # character_lock = short description for scene prompts (IMPORTANT!)
                portrait_prompt = char_data.get("portrait_prompt", char_data.get("english_prompt", ""))
                character_lock = char_data.get("character_lock", "")

                # Check if this is a child character
                is_child = char_data.get("is_child", False)

                # If portrait_prompt is DO_NOT_GENERATE, this is a child (no reference image)
                if portrait_prompt == "DO_NOT_GENERATE":
                    is_child = True
                    # Keep DO_NOT_GENERATE as marker - don't replace with character_lock
                    self.logger.info(f"  -> Child character detected: {char_data.get('id', '')} - will use inline description")

                characters.append(Character(
                    id=char_data.get("id", ""),
                    role=char_data.get("role", "supporting"),
                    name=char_data.get("name", ""),
                    english_prompt=portrait_prompt,  # Keep DO_NOT_GENERATE for children
                    character_lock=character_lock,    # For scene prompts (IMPORTANT!)
                    vietnamese_prompt=char_data.get("vietnamese_prompt", char_data.get("vietnamese_description", "")),
                    is_child=is_child,
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

    def _create_directors_treatment(self, story_text: str) -> Optional[Dict]:
        """
        Tạo Director's Treatment - Kịch bản đạo diễn phân tích cấu trúc câu chuyện.

        Args:
            story_text: Toàn bộ nội dung câu chuyện

        Returns:
            Dict với story_parts, visual_guidelines, scene_mapping_guide
        """
        try:
            # Load prompt từ config/prompts.yaml
            prompt_template = self._load_prompt_template("directors_treatment")
            if not prompt_template:
                self.logger.warning("[Director's Treatment] Không tìm thấy prompt template, bỏ qua")
                return None

            prompt = prompt_template.format(story_text=story_text[:12000])

            self.logger.info("[Director's Treatment] Đang phân tích cấu trúc câu chuyện...")
            response = self._generate_content(prompt, temperature=0.3, max_tokens=8000)
            json_data = self._extract_json(response)

            if not json_data or "story_parts" not in json_data:
                self.logger.warning("[Director's Treatment] AI không trả về story_parts")
                return None

            # Log story analysis
            story_analysis = json_data.get("story_analysis", {})
            self.logger.info(f"[Director's Treatment] Title: {story_analysis.get('title', 'N/A')}")
            self.logger.info(f"[Director's Treatment] Theme: {story_analysis.get('main_theme', 'N/A')}")

            # Log story parts
            for part in json_data.get("story_parts", []):
                self.logger.info(f"  Part {part.get('part_number')}: {part.get('part_name')} ({part.get('time_range', 'N/A')})")
                self.logger.info(f"    Tone: {part.get('emotional_tone', 'N/A')}")
                self.logger.info(f"    Strategy: {part.get('visual_strategy', 'N/A')[:80]}...")

            return json_data

        except Exception as e:
            self.logger.error(f"[Director's Treatment] Failed: {e}")
            return None

    def _create_directors_shooting_plan(
        self,
        story_text: str,
        srt_entries: List,
        characters: List,
        locations: List,
        global_style: str
    ) -> Optional[Dict]:
        """
        Tạo Director's Shooting Plan - Kế hoạch quay phim chi tiết.
        ĐÂY LÀ BƯỚC QUAN TRỌNG NHẤT - Đạo diễn quyết định tạo bao nhiêu ảnh và ảnh gì!

        Args:
            story_text: Toàn bộ nội dung câu chuyện
            srt_entries: List các SrtEntry với timestamps
            characters: List các Character đã phân tích
            locations: List các Location đã phân tích
            global_style: Global style string

        Returns:
            Dict với shooting_plan chứa tất cả shots đã lên kế hoạch
        """
        try:
            # Load prompt template
            prompt_template = self._load_prompt_template("directors_shooting_plan")
            if not prompt_template:
                self.logger.warning("[Director's Shooting Plan] Không tìm thấy prompt template")
                return None

            # Format SRT segments với timestamps
            srt_segments = "\n".join([
                f"[{self._format_timedelta(e.start_time)} - {self._format_timedelta(e.end_time)}] \"{e.text[:200]}\""
                for e in srt_entries
            ])

            # Format characters info
            chars_info = "NHÂN VẬT:\n" + "\n".join([
                f"- {c.id}: {c.name} - {c.character_lock or ''}"
                for c in characters
            ]) if characters else "Không có thông tin nhân vật"

            # Format locations info
            locs_info = "BỐI CẢNH:\n" + "\n".join([
                f"- {loc.id}: {loc.name} - {loc.location_lock or ''}"
                for loc in locations
            ]) if locations else "Không có thông tin bối cảnh"

            # Build prompt
            prompt = prompt_template.format(
                story_text=story_text[:10000],
                srt_segments=srt_segments[:15000],
                characters_info=chars_info,
                locations_info=locs_info,
                global_style=global_style or get_global_style()
            )

            self.logger.info("=" * 50)
            self.logger.info("[Director's Shooting Plan] Đạo diễn đang lên kế hoạch quay...")
            self.logger.info("=" * 50)

            # Director's Shooting Plan cần response rất dài (nhiều scenes)
            # DeepSeek bị giới hạn 8192 tokens nên ưu tiên Ollama nếu có
            response = self._generate_content_large(prompt, temperature=0.4, max_tokens=16000)

            # DEBUG: Log response để xem AI trả về gì
            self.logger.info(f"[Director's Shooting Plan] Response length: {len(response) if response else 0}")
            if response:
                self.logger.info(f"[Director's Shooting Plan] Response preview: {response[:500]}...")

            json_data = self._extract_json(response)

            # DEBUG: Log json_data
            if json_data:
                self.logger.info(f"[Director's Shooting Plan] JSON keys: {list(json_data.keys())}")
            else:
                self.logger.warning(f"[Director's Shooting Plan] Failed to extract JSON from response")

            if not json_data or "shooting_plan" not in json_data:
                self.logger.warning("[Director's Shooting Plan] AI không trả về shooting_plan")
                if json_data:
                    self.logger.warning(f"[Director's Shooting Plan] Available keys: {list(json_data.keys())}")
                return None

            shooting_plan = json_data["shooting_plan"]

            # Log summary
            self.logger.info(f"[Director's Shooting Plan] Tổng thời lượng: {shooting_plan.get('total_duration', 'N/A')}")
            self.logger.info(f"[Director's Shooting Plan] Tổng số ảnh: {shooting_plan.get('total_images', 0)}")

            total_shots = 0
            for part in shooting_plan.get("story_parts", []):
                shots_count = len(part.get("shots", []))
                total_shots += shots_count
                self.logger.info(f"  Part {part.get('part_number')}: {part.get('part_name')} - {shots_count} shots")

            self.logger.info(f"[Director's Shooting Plan] Tổng shots thực tế: {total_shots}")

            return json_data

        except Exception as e:
            self.logger.error(f"[Director's Shooting Plan] Failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _format_timedelta(self, td) -> str:
        """Format timedelta thành HH:MM:SS"""
        if hasattr(td, 'total_seconds'):
            total_seconds = int(td.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return str(td)

    def _convert_shooting_plan_to_scenes(self, shooting_plan: Dict) -> List[Dict[str, Any]]:
        """
        Chuyển đổi shooting_plan từ đạo diễn thành scenes data.

        Args:
            shooting_plan: Output từ directors_shooting_plan

        Returns:
            List scenes với format tương thích với hệ thống hiện tại
        """
        scenes = []
        scene_id = 1

        def normalize_timestamp(ts: str) -> str:
            """
            Chuẩn hóa timestamp về format SRT: HH:MM:SS,mmm
            Input có thể là: "00:00", "00:00:00", "00:00:00,000", "0:00", etc.
            """
            ts = ts.strip()
            if not ts:
                return "00:00:00,000"

            # Nếu có dấu phẩy (milliseconds)
            if "," in ts:
                main_part, ms = ts.rsplit(",", 1)
            else:
                main_part = ts
                ms = "000"

            # Đảm bảo ms là 3 chữ số
            ms = ms.ljust(3, "0")[:3]

            # Parse main part
            parts = main_part.split(":")
            if len(parts) == 2:
                # MM:SS -> HH:MM:SS
                mm, ss = parts
                hh = "00"
            elif len(parts) == 3:
                hh, mm, ss = parts
            else:
                return "00:00:00,000"

            # Pad với 0
            hh = hh.zfill(2)
            mm = mm.zfill(2)
            ss = ss.zfill(2)

            return f"{hh}:{mm}:{ss},{ms}"

        for part in shooting_plan.get("story_parts", []):
            for shot in part.get("shots", []):
                # Parse srt_range để lấy timestamps
                srt_range = shot.get("srt_range", "00:00 - 00:08")
                times = srt_range.split(" - ")
                start_time = normalize_timestamp(times[0]) if len(times) > 0 else "00:00:00,000"
                end_time = normalize_timestamp(times[1]) if len(times) > 1 else "00:00:08,000"

                # === Extract characters_used và location_used từ reference_files ===
                ref_files = shot.get("reference_files", [])
                chars_in_shot = shot.get("characters_in_shot", [])

                # Location: ưu tiên từ reference_files (loc_xxx.png), fallback từ part.location
                location_from_refs = ""
                chars_from_refs = []
                for ref in ref_files:
                    ref_name = ref.replace(".png", "").strip()
                    if ref_name.startswith("loc_"):
                        location_from_refs = ref_name  # e.g., "loc_courthouse"
                    else:
                        chars_from_refs.append(ref_name)  # e.g., "nvc"

                # Fallback location từ part level
                location_id = location_from_refs or (
                    part.get("location", "").split(",")[0].strip() if part.get("location") else ""
                )

                # Characters: ưu tiên characters_in_shot, fallback từ reference_files
                characters_used = chars_in_shot if chars_in_shot else chars_from_refs

                scene = {
                    "scene_id": scene_id,
                    "srt_start": start_time,
                    "srt_end": end_time,
                    "start_time": start_time,
                    "end_time": end_time,
                    "text": shot.get("srt_text", ""),
                    "scene_type": part.get("part_name", "SCENE"),
                    "location_id": location_id,
                    "characters_in_scene": characters_used,
                    "characters_used": characters_used,  # Thêm trực tiếp cho Excel
                    "location_used": location_id,  # Thêm trực tiếp cho Excel
                    "reference_files": ref_files,
                    "img_prompt": shot.get("img_prompt", ""),
                    "shot_type": shot.get("shot_type", ""),
                    "camera_angle": shot.get("camera_angle", ""),
                    "visual_description": shot.get("visual_description", ""),
                    # Đánh dấu đã có prompt từ đạo diễn
                    "from_director": True
                }

                # Filter children from reference_files
                scene["reference_files"] = self._filter_children_from_refs(scene["reference_files"])

                # VALIDATE & FIX: Check if action matches location in img_prompt
                srt_text = shot.get("srt_text", "")
                fixed_prompt = self._validate_and_fix_location(scene["img_prompt"], srt_text)
                if fixed_prompt != scene["img_prompt"]:
                    self.logger.warning(f"[Validation] Fixed location mismatch in scene {scene_id}")
                    scene["img_prompt"] = fixed_prompt

                scenes.append(scene)
                scene_id += 1

        self.logger.info(f"[Director] Đã chuyển đổi {len(scenes)} shots thành scenes")
        return scenes

    def _validate_and_fix_location(self, img_prompt: str, srt_text: str) -> str:
        """
        Validate và fix location mismatch trong img_prompt.

        Ví dụ lỗi: "LYING IN BED... hotel hallway" → Sửa thành "LYING IN BED... bedroom"

        Args:
            img_prompt: Prompt từ AI
            srt_text: Text gốc từ SRT (để xác định location đúng)

        Returns:
            Fixed img_prompt
        """
        if not img_prompt:
            return img_prompt

        import re
        prompt_lower = img_prompt.lower()
        srt_lower = srt_text.lower() if srt_text else ""

        # Định nghĩa các action → location mappings
        action_location_rules = [
            # BED actions → must be bedroom
            {
                "actions": ["lying in bed", "on the bed", "in bed", "bedroom", "on bed", "fell off the bed", "jumped up from bed"],
                "wrong_locations": ["hallway", "corridor", "street", "outdoor", "kitchen", "office", "restaurant"],
                "correct_location": "master bedroom, king-sized bed with silk sheets, elegant furniture, soft ambient lighting"
            },
            # KITCHEN actions → must be kitchen
            {
                "actions": ["cooking", "in the kitchen", "at the stove", "preparing food"],
                "wrong_locations": ["bedroom", "hallway", "office", "outdoor", "street"],
                "correct_location": "modern kitchen interior, stove, countertops, cooking utensils, warm lighting"
            },
            # BATHROOM actions
            {
                "actions": ["shower", "bathtub", "bathroom", "brushing teeth", "mirror"],
                "wrong_locations": ["bedroom", "kitchen", "office", "outdoor", "hallway"],
                "correct_location": "elegant bathroom, marble tiles, mirror, soft lighting"
            },
            # OUTDOOR actions
            {
                "actions": ["walking on street", "driving", "in the car", "outdoor", "park", "garden"],
                "wrong_locations": ["bedroom", "kitchen", "bathroom", "office interior"],
                "correct_location": "outdoor scene, natural daylight"
            },
            # RESTAURANT actions
            {
                "actions": ["dining", "at restaurant", "eating dinner", "at the table"],
                "wrong_locations": ["bedroom", "bathroom", "street", "office"],
                "correct_location": "elegant restaurant interior, dining tables, ambient lighting"
            },
        ]

        # Check SRT text for location hints
        srt_location_hints = {
            "bed": "bedroom",
            "bedroom": "bedroom",
            "master bedroom": "master bedroom",
            "kitchen": "kitchen",
            "bathroom": "bathroom",
            "restaurant": "restaurant",
            "office": "office",
            "car": "car interior",
            "street": "street",
            "courthouse": "courthouse",
            "hospital": "hospital",
        }

        # Find if SRT mentions a specific location
        srt_location = None
        for hint, loc in srt_location_hints.items():
            if hint in srt_lower:
                srt_location = loc
                break

        # Check each rule
        for rule in action_location_rules:
            # Check if any action is in the prompt
            action_found = any(action in prompt_lower for action in rule["actions"])

            if action_found:
                # Check if wrong location is in the prompt
                for wrong_loc in rule["wrong_locations"]:
                    if wrong_loc in prompt_lower:
                        self.logger.warning(f"[Validation] Action/Location mismatch: action implies {rule['actions'][0]} but found '{wrong_loc}'")

                        # Use SRT location if available, otherwise use rule's correct location
                        correct_loc = rule["correct_location"]
                        if srt_location:
                            if srt_location == "bedroom" or srt_location == "master bedroom":
                                correct_loc = "master bedroom, king-sized bed with silk sheets, elegant nightstands, soft warm lighting"
                            elif srt_location == "kitchen":
                                correct_loc = "modern kitchen, marble countertops, stainless steel appliances, warm lighting"

                        # Replace the wrong location with correct one
                        # Find the sentence containing the wrong location and replace
                        pattern = re.compile(r'[^.]*' + re.escape(wrong_loc) + r'[^.]*\.?', re.IGNORECASE)
                        fixed = pattern.sub(correct_loc + '. ', img_prompt)

                        # Clean up double spaces/periods
                        fixed = re.sub(r'\s+', ' ', fixed)
                        fixed = re.sub(r'\.\.+', '.', fixed)

                        return fixed.strip()

        return img_prompt

    def _load_prompt_template(self, prompt_name: str) -> Optional[str]:
        """Load a specific prompt template from prompts.yaml"""
        try:
            import yaml
            prompts_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts = yaml.safe_load(f)
            return prompts.get(prompt_name, None)
        except Exception as e:
            self.logger.error(f"Failed to load prompt {prompt_name}: {e}")
            return None

    def _smart_divide_scenes(self, srt_entries: List, characters: List = None, locations: List = None, directors_treatment: Dict = None, global_style: str = "") -> List[Dict[str, Any]]:
        """
        Chia scene theo hướng: TIME-BASED trước (max 8s), rồi AI phân tích nội dung.
        Sử dụng Director's Treatment để hướng dẫn visual strategy.

        Flow mới:
        1. Chia SRT thành các nhóm <= 8s (time-based, đảm bảo chính xác)
        2. AI phân tích nội dung mỗi nhóm → xác định location + visual_moment (dựa trên Director's Treatment)
        3. Sử dụng thông tin characters/locations đã phân tích để tạo visual chính xác

        Args:
            srt_entries: List các SrtEntry từ file SRT
            characters: List các Character đã phân tích
            locations: List các Location đã phân tích
            global_style: Global style string for consistent image styling

        Returns:
            List các scene data với: scene_id, start_time, end_time, text, srt_start, srt_end
        """
        characters = characters or []
        locations = locations or []

        # BƯỚC 1: Chia theo thời gian trước (max 8s/scene) - CHÍNH XÁC
        self.logger.info("Bước 1: Chia SRT theo thời gian (max 8s/scene)...")
        time_based_scenes = group_srt_into_scenes(
            srt_entries,
            min_duration=self.min_scene_duration,
            max_duration=self.max_scene_duration
        )
        self.logger.info(f"Đã chia thành {len(time_based_scenes)} scenes (max 8s/scene)")

        # DEBUG: Log từng scene để kiểm tra
        for i, s in enumerate(time_based_scenes):
            duration = 0
            if isinstance(s.get("start_time"), timedelta) and isinstance(s.get("end_time"), timedelta):
                duration = (s["end_time"] - s["start_time"]).total_seconds()
            self.logger.info(f"  Scene {i+1}: {s.get('srt_start', '')} -> {s.get('srt_end', '')} ({duration:.1f}s)")

        # VALIDATE: Nếu có scene nào > max_duration, chia lại
        needs_resplit = False
        for s in time_based_scenes:
            if isinstance(s.get("start_time"), timedelta) and isinstance(s.get("end_time"), timedelta):
                duration = (s["end_time"] - s["start_time"]).total_seconds()
                if duration > self.max_scene_duration + 0.5:  # +0.5 tolerance
                    self.logger.warning(f"Scene {s.get('scene_id')} duration={duration:.1f}s > {self.max_scene_duration}s!")
                    needs_resplit = True
                    break

        if needs_resplit:
            self.logger.warning("Re-splitting scenes to enforce max duration...")
            time_based_scenes = self._force_split_scenes(time_based_scenes, srt_entries)

        # BƯỚC 2: AI phân tích nội dung để tạo visual_moment và xác định location
        self.logger.info("Bước 2: AI phân tích nội dung để tạo visual_moment...")

        # Format thông tin characters cho AI
        chars_info = ""
        if characters:
            chars_info = "NHÂN VẬT ĐÃ XÁC ĐỊNH:\n" + "\n".join([
                f"- {c.id}: {c.name} ({c.role}) - {c.character_lock or c.vietnamese_prompt or ''}"
                for c in characters
            ])

        # Format thông tin locations cho AI
        locs_info = ""
        if locations:
            locs_info = "BỐI CẢNH ĐÃ XÁC ĐỊNH:\n" + "\n".join([
                f"- {loc.id}: {loc.name} - {loc.location_lock or ''}"
                for loc in locations
            ])

        # Format scenes cho AI
        scenes_for_ai = "\n".join([
            f"{i+1}. [{s.get('srt_start', '')} -> {s.get('srt_end', '')}] \"{s['text'][:300]}\""
            for i, s in enumerate(time_based_scenes)
        ])

        # Format Director's Treatment cho AI (nếu có)
        treatment_info = ""
        if directors_treatment:
            import json
            treatment_info = json.dumps(directors_treatment, indent=2, ensure_ascii=False)
            self.logger.info(f"[Smart Divide] Using Director's Treatment with {len(directors_treatment.get('story_parts', []))} story parts")

        # Load prompt
        prompt_template = get_smart_divide_scenes_prompt()
        if not prompt_template:
            self.logger.warning("Smart divide prompt not found, returning time-based scenes")
            return self._format_time_based_scenes(time_based_scenes, locations=locations)

        # Get default global style if not provided
        if not global_style:
            global_style = get_global_style()

        # Build full prompt với context + Director's Treatment
        try:
            prompt = prompt_template.format(
                srt_with_timestamps=scenes_for_ai,
                characters_info=chars_info,
                locations_info=locs_info,
                directors_treatment=treatment_info or "No director's treatment available - analyze story structure yourself",
                global_style=global_style
            )
        except KeyError:
            # Fallback nếu template không có placeholder
            prompt = prompt_template.format(srt_with_timestamps=scenes_for_ai, global_style=global_style)
            # Prepend context
            context_parts = []
            if treatment_info:
                context_parts.append(f"DIRECTOR'S TREATMENT:\n{treatment_info}")
            if chars_info:
                context_parts.append(chars_info)
            if locs_info:
                context_parts.append(locs_info)
            if context_parts:
                prompt = "\n\n".join(context_parts) + "\n\n" + prompt

        try:
            response = self._generate_content(prompt, temperature=0.4, max_tokens=8000)
            json_data = self._extract_json(response)

            if not json_data or "scenes" not in json_data:
                self.logger.warning("[Smart Divide] AI không trả về scenes, dùng time-based")
                return self._format_time_based_scenes(time_based_scenes, locations=locations)

            self.logger.info(f"[Smart Divide] AI trả về {len(json_data['scenes'])} scene analyses")

            # Extract NEW locations từ AI (locations chưa có trong danh sách ban đầu)
            new_locations = json_data.get("new_locations", [])
            if new_locations:
                self.logger.info(f"[Smart Divide] AI created {len(new_locations)} NEW locations:")
                for loc in new_locations:
                    self.logger.info(f"  - {loc.get('id')}: {loc.get('name')} - {loc.get('location_lock', '')[:50]}...")
                    # Add to locations list for reference
                    locations.append(Location(
                        id=loc.get("id", ""),
                        name=loc.get("name", ""),
                        english_prompt=loc.get("location_prompt", ""),
                        location_lock=loc.get("location_lock", ""),
                        lighting_default=loc.get("lighting_default", ""),
                        image_file=f"{loc.get('id', 'loc')}.png"
                    ))

            # Merge AI analysis vào time-based scenes
            ai_scenes_map = {s.get("scene_id", i+1): s for i, s in enumerate(json_data["scenes"])}

            final_scenes = []
            for i, scene in enumerate(time_based_scenes):
                scene_id = i + 1
                ai_data = ai_scenes_map.get(scene_id, {})

                # Format timestamps
                start_time = scene.get("srt_start", format_srt_time(scene["start_time"]) if isinstance(scene["start_time"], timedelta) else scene["start_time"])
                end_time = scene.get("srt_end", format_srt_time(scene["end_time"]) if isinstance(scene["end_time"], timedelta) else scene["end_time"])
                duration = scene.get("duration", (scene["end_time"] - scene["start_time"]).total_seconds() if isinstance(scene["start_time"], timedelta) else 5)

                # Lấy characters từ AI analysis
                chars_in_scene = ai_data.get("characters_in_scene", [])
                if not chars_in_scene and characters:
                    # Fallback: dùng nhân vật chính nếu AI không chỉ định
                    chars_in_scene = [characters[0].id] if characters else []

                # Scene type (PRESENT_ACTION, FLASHBACK, NARRATION, YOUTUBE_CTA)
                scene_type = ai_data.get("scene_type", "PRESENT_ACTION")
                age_note = ai_data.get("age_note", "")

                # Ưu tiên img_prompt từ AI, sau đó visual_moment, KHÔNG dùng scene text làm fallback!
                ai_img_prompt = ai_data.get("img_prompt", "")
                ai_visual_moment = ai_data.get("visual_moment", "")

                # KHÔNG DÙNG scene["text"] làm fallback - sẽ gây narration trong prompt!
                final_visual = ai_img_prompt or ai_visual_moment or ""

                # Map AI's location_id to actual location ID
                ai_location = ai_data.get("location_id", "")
                actual_location_id = ""
                if ai_location:
                    # Kiểm tra nếu ai_location là ID thực tế trong locations list
                    for loc in locations:
                        if loc.id == ai_location:
                            actual_location_id = ai_location
                            break
                    # Nếu không tìm thấy, có thể AI trả về generic (loc1, loc2...)
                    if not actual_location_id and locations:
                        import re
                        match = re.match(r'loc(\d+)', ai_location)
                        if match:
                            idx = int(match.group(1)) - 1  # loc1 -> index 0
                            if 0 <= idx < len(locations):
                                actual_location_id = locations[idx].id
                        # Fallback: dùng location đầu tiên
                        if not actual_location_id:
                            actual_location_id = locations[0].id
                elif locations:
                    # AI không trả về location, dùng location đầu tiên
                    actual_location_id = locations[0].id

                final_scenes.append({
                    "scene_id": scene_id,
                    "scene_type": scene_type,  # NEW: Type of scene
                    "age_note": age_note,      # NEW: Age adjustment for flashbacks
                    "location_id": actual_location_id,
                    "characters_in_scene": chars_in_scene,
                    "story_beat": ai_data.get("story_beat", ""),
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration,
                    "text": scene["text"],  # Keep for subtitle reference
                    "visual_moment": final_visual,  # Use AI visual, NOT narration!
                    "img_prompt": ai_img_prompt,  # NEW: Direct img_prompt from AI
                    "shot_type": ai_data.get("shot_type", "Medium shot"),
                    "srt_start": start_time,
                    "srt_end": end_time,
                })

            self.logger.info(f"Hoàn thành: {len(final_scenes)} scenes với visual_moment từ AI")
            return final_scenes

        except Exception as e:
            self.logger.error(f"AI analysis failed: {e}, returning time-based scenes")
            return self._format_time_based_scenes(time_based_scenes, locations=locations)

    def _force_split_scenes(self, scenes: List[Dict], srt_entries: List) -> List[Dict]:
        """Force split scenes that exceed max_duration."""
        result = []
        scene_counter = 1

        for scene in scenes:
            if not isinstance(scene.get("start_time"), timedelta):
                scene["scene_id"] = scene_counter
                result.append(scene)
                scene_counter += 1
                continue

            duration = (scene["end_time"] - scene["start_time"]).total_seconds()

            if duration <= self.max_scene_duration + 0.5:
                scene["scene_id"] = scene_counter
                result.append(scene)
                scene_counter += 1
            else:
                # Scene quá dài, cần chia nhỏ
                srt_indices = scene.get("srt_indices", [])
                if srt_indices:
                    # Tìm SRT entries cho scene này
                    scene_entries = [e for e in srt_entries if e.index in srt_indices]
                    if scene_entries:
                        # Chia lại với max_duration nhỏ hơn
                        sub_scenes = group_srt_into_scenes(
                            scene_entries,
                            min_duration=1,  # Bỏ qua min để đảm bảo max
                            max_duration=self.max_scene_duration
                        )
                        for sub in sub_scenes:
                            sub["scene_id"] = scene_counter
                            result.append(sub)
                            scene_counter += 1
                        continue

                # Fallback: chia đều theo thời gian
                num_parts = int(duration / self.max_scene_duration) + 1
                part_duration = duration / num_parts
                start_sec = scene["start_time"].total_seconds()

                for i in range(num_parts):
                    part_start = timedelta(seconds=start_sec + i * part_duration)
                    part_end = timedelta(seconds=min(start_sec + (i + 1) * part_duration, scene["end_time"].total_seconds()))

                    result.append({
                        "scene_id": scene_counter,
                        "start_time": part_start,
                        "end_time": part_end,
                        "text": scene["text"],
                        "srt_start": format_srt_time(part_start),
                        "srt_end": format_srt_time(part_end),
                        "srt_indices": scene.get("srt_indices", []),
                    })
                    scene_counter += 1

        return result

    def _format_time_based_scenes(self, time_based_scenes: List[Dict], default_char: str = "nvc", locations: List = None) -> List[Dict[str, Any]]:
        """Format time-based scenes khi không có AI analysis."""
        # Lấy actual location ID từ locations list, không dùng generic loc1
        actual_location_id = ""
        if locations and len(locations) > 0:
            actual_location_id = locations[0].id

        formatted = []
        for i, scene in enumerate(time_based_scenes):
            start_time = format_srt_time(scene["start_time"]) if isinstance(scene["start_time"], timedelta) else scene.get("srt_start", "00:00:00,000")
            end_time = format_srt_time(scene["end_time"]) if isinstance(scene["end_time"], timedelta) else scene.get("srt_end", "00:00:08,000")
            duration = (scene["end_time"] - scene["start_time"]).total_seconds() if isinstance(scene["start_time"], timedelta) else 5

            formatted.append({
                "scene_id": i + 1,
                "location_id": actual_location_id,
                "characters_in_scene": [default_char],  # Default: nhân vật chính
                "story_beat": "",
                "start_time": start_time,
                "end_time": end_time,
                "duration_seconds": duration,
                "text": scene["text"],
                "visual_moment": scene["text"],
                "shot_type": "Medium shot",
                "srt_start": start_time,
                "srt_end": end_time,
            })
        return formatted

    def _validate_and_split_scenes(self, scenes_data: List[Dict], srt_entries: List) -> List[Dict[str, Any]]:
        """
        Validate và chia lại những scene vượt quá max_duration.
        LUÔN check duration từ timestamps, không phụ thuộc srt_indices.

        Args:
            scenes_data: List scenes từ AI
            srt_entries: List SrtEntry gốc

        Returns:
            List scenes đã được validate và split nếu cần
        """
        def parse_time_to_seconds(ts: str) -> float:
            """Convert timestamp string "HH:MM:SS,mmm" hoặc "HH:MM:SS" to seconds."""
            if not ts:
                return 0
            ts = ts.replace(",", ".")
            parts = ts.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            return 0

        # Build lookup table: srt_index -> SrtEntry
        srt_lookup = {e.index: e for e in srt_entries}

        validated = []
        scene_counter = 1

        for scene in scenes_data:
            # LUÔN tính duration từ timestamps
            start_str = scene.get("start_time", "00:00:00")
            end_str = scene.get("end_time", "00:00:00")
            duration_from_ts = parse_time_to_seconds(end_str) - parse_time_to_seconds(start_str)

            # Lấy duration_seconds từ AI (fallback)
            duration = scene.get("duration_seconds", duration_from_ts) or duration_from_ts

            self.logger.debug(f"Scene {scene.get('scene_id')}: {start_str} -> {end_str} = {duration:.1f}s")

            if duration <= self.max_scene_duration:
                # Duration OK, giữ nguyên
                scene["scene_id"] = scene_counter
                scene["duration_seconds"] = duration
                scene["srt_start"] = start_str if "," in start_str else f"{start_str},000"
                scene["srt_end"] = end_str if "," in end_str else f"{end_str},000"
                validated.append(scene)
                scene_counter += 1
            else:
                # Duration > max, cần chia nhỏ
                self.logger.warning(f"Scene {scene.get('scene_id')} duration={duration:.1f}s > {self.max_scene_duration}s, SPLITTING!")

                # Tìm SRT entries trong khoảng thời gian này
                start_sec = parse_time_to_seconds(start_str)
                end_sec = parse_time_to_seconds(end_str)

                scene_entries = []
                for entry in srt_entries:
                    entry_start = entry.start_time.total_seconds()
                    entry_end = entry.end_time.total_seconds()
                    # Entry nằm trong khoảng scene
                    if entry_start >= start_sec - 0.5 and entry_end <= end_sec + 0.5:
                        scene_entries.append(entry)

                if scene_entries:
                    # Có SRT entries → chia theo entries
                    sub_scenes = group_srt_into_scenes(
                        scene_entries,
                        min_duration=self.min_scene_duration,
                        max_duration=self.max_scene_duration
                    )

                    for sub in sub_scenes:
                        sub_start = format_srt_time(sub["start_time"]) if isinstance(sub["start_time"], timedelta) else sub["start_time"]
                        sub_end = format_srt_time(sub["end_time"]) if isinstance(sub["end_time"], timedelta) else sub["end_time"]
                        sub_duration = (sub["end_time"] - sub["start_time"]).total_seconds() if isinstance(sub["start_time"], timedelta) else 5

                        validated.append({
                            "scene_id": scene_counter,
                            "location_id": scene.get("location_id", ""),
                            "story_beat": scene.get("story_beat", ""),
                            "start_time": sub_start,
                            "end_time": sub_end,
                            "duration_seconds": sub_duration,
                            "text": sub["text"],
                            "visual_moment": scene.get("visual_moment", sub["text"]),
                            "shot_type": scene.get("shot_type", "Medium shot"),
                            "srt_start": sub_start,
                            "srt_end": sub_end,
                        })
                        scene_counter += 1
                else:
                    # Không tìm được entries → chia đều theo thời gian
                    self.logger.warning(f"No SRT entries found for scene, splitting evenly by time")
                    num_parts = int(duration / self.max_scene_duration) + 1
                    part_duration = duration / num_parts
                    original_text = scene.get("text", "")

                    for i in range(num_parts):
                        part_start_sec = start_sec + (i * part_duration)
                        part_end_sec = min(start_sec + ((i + 1) * part_duration), end_sec)

                        # Convert to timestamp string
                        def sec_to_ts(sec):
                            h = int(sec // 3600)
                            m = int((sec % 3600) // 60)
                            s = sec % 60
                            return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

                        validated.append({
                            "scene_id": scene_counter,
                            "location_id": scene.get("location_id", ""),
                            "story_beat": scene.get("story_beat", ""),
                            "start_time": sec_to_ts(part_start_sec),
                            "end_time": sec_to_ts(part_end_sec),
                            "duration_seconds": part_end_sec - part_start_sec,
                            "text": original_text,
                            "visual_moment": scene.get("visual_moment", original_text),
                            "shot_type": scene.get("shot_type", "Medium shot"),
                            "srt_start": sec_to_ts(part_start_sec),
                            "srt_end": sec_to_ts(part_end_sec),
                        })
                        scene_counter += 1

        return validated

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

        # Format thông tin nhân vật (v5.0 format) - use character_lock for scene prompts
        # IMPORTANT: character_lock is the short description for scenes, NOT english_prompt (portrait_prompt)
        # NEVER use portrait_prompt (english_prompt) for scenes - it has "white studio background"!
        def get_char_lock(char):
            """Get character_lock, extract from english_prompt if needed (remove white background)."""
            if char.character_lock and char.character_lock.strip():
                return char.character_lock
            # Fallback: extract basic description from english_prompt (remove studio/background refs)
            if char.english_prompt:
                prompt = char.english_prompt
                # Remove studio background references
                for phrase in ["Pure white studio background", "white studio background",
                               "Bright, even studio lighting", "studio lighting",
                               "Looking directly at camera", "neutral expression",
                               "8K, sharp focus", "high fidelity portraiture"]:
                    prompt = prompt.replace(phrase, "").replace(phrase.lower(), "")
                # Clean up
                prompt = " ".join(prompt.split())  # Remove extra spaces
                if len(prompt) > 20:  # Only use if meaningful
                    return prompt
            return f"{char.name} ({char.role})"  # Ultimate fallback

        characters_info = "\n".join([
            f"- ID: {char.id}\n"
            f"  Name: {char.name} ({char.role})\n"
            f"  character_lock: \"{get_char_lock(char)}\"\n"
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

        # Kiểm tra xem có scenes nào đã có img_prompt từ smart_divide_scenes không
        scenes_with_prompts = [s for s in scenes_data if s.get("img_prompt")]
        if scenes_with_prompts and len(scenes_with_prompts) == len(scenes_data):
            # TẤT CẢ scenes đã có img_prompt từ smart_divide_scenes - dùng trực tiếp!
            self.logger.info(f"[Scene Prompts] All {len(scenes_data)} scenes already have img_prompt from smart_divide_scenes - using directly!")
            result = []
            for s in scenes_data:
                result.append({
                    "img_prompt": s.get("img_prompt", ""),
                    "video_prompt": s.get("img_prompt", ""),
                    "characters_used": s.get("characters_in_scene", []),
                    "location_used": s.get("location_id", ""),
                    "reference_files": []  # Will be populated later
                })
            return result

        # Format thông tin scenes (include location_id, story_beat, shot_type and visual_moment)
        # KHÔNG dùng s['text'] làm fallback cho visual_moment!
        pacing_script = "\n".join([
            f"{s['scene_id']}. [{s.get('shot_type', 'Medium shot')}] \"{s['text']}\"\n"
            f"   Scene Type: {s.get('scene_type', 'FRAME_PRESENT')}\n"
            f"   Location: {s.get('location_id', 'N/A')}\n"
            f"   Characters: {s.get('characters_in_scene', [])}\n"
            f"   Story beat: {s.get('story_beat', 'N/A')}\n"
            f"   Visual hint: {s.get('visual_moment', '') or '(Create visual based on narration meaning)'}"
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
            self.logger.info(f"[Scene Prompts] Generating for {len(scenes_data)} scenes...")
            response = self._generate_content(prompt, temperature=0.6)

            # Parse JSON
            json_data = self._extract_json(response)

            if not json_data or "scenes" not in json_data:
                self.logger.warning(f"[Scene Prompts] Invalid response - no 'scenes' key in JSON")
                self.logger.warning(f"[Scene Prompts] Raw response (first 500 chars): {str(response)[:500]}")
                # Return FALLBACK prompts (không để trống!)
                return self._create_fallback_prompts(scenes_data, characters, locations, global_style)

            self.logger.info(f"[Scene Prompts] Got {len(json_data['scenes'])} scene prompts from AI (need {len(scenes_data)})")

            # Kiểm tra nếu AI trả về thiếu prompts
            if len(json_data['scenes']) < len(scenes_data):
                self.logger.warning(f"[Scene Prompts] AI THIẾU {len(scenes_data) - len(json_data['scenes'])} prompts!")

            # Match prompts với scenes
            prompts_map = {s["scene_id"]: s for s in json_data["scenes"]}

            result = []
            missing_scenes = []
            for scene_data in scenes_data:
                scene_id = scene_data["scene_id"]
                if scene_id in prompts_map:
                    scene_result = prompts_map[scene_id]

                    # POST-PROCESS: Clean any narration text from img_prompt
                    img_prompt = scene_result.get("img_prompt", "")
                    scene_text = scene_data.get("text", "")[:100]  # First 100 chars of narration
                    img_prompt = self._clean_narration_from_prompt(img_prompt, scene_text)

                    result.append({
                        "img_prompt": img_prompt,
                        "video_prompt": scene_result.get("video_prompt", ""),
                        "characters_used": scene_result.get("characters_used", []),
                        "location_used": scene_result.get("location_used", ""),
                        "reference_files": scene_result.get("reference_files", [])
                    })
                else:
                    # Scene không có prompt từ AI - dùng fallback THÔNG MINH
                    missing_scenes.append(scene_id)
                    # GỌI FALLBACK METHOD thay vì dùng scene_text trực tiếp!
                    # Fallback sẽ tạo prompt dựa trên scene_type, KHÔNG dùng narration text
                    fallback_prompts = self._create_fallback_prompts(
                        [scene_data], characters, locations, global_style_override
                    )
                    if fallback_prompts:
                        result.append(fallback_prompts[0])
                    else:
                        # Ultimate fallback - generic nhưng KHÔNG có narration text
                        result.append({
                            "img_prompt": f"Medium shot, cinematic scene, natural lighting, 4K photorealistic",
                            "video_prompt": f"Medium shot, cinematic scene",
                            "characters_used": [],
                            "location_used": "",
                            "reference_files": []
                        })

            if missing_scenes:
                self.logger.warning(f"[Scene Prompts] Đã tạo prompt đơn giản cho {len(missing_scenes)} scenes thiếu: {missing_scenes}")

            return result
            
        except Exception as e:
            self.logger.error(f"Failed to generate scene prompts: {e}")
            # Return FALLBACK prompts (không để trống!)
            return self._create_fallback_prompts(scenes_data, characters, locations, global_style)

    def _create_fallback_prompts(
        self,
        scenes_data: List[Dict],
        characters: List = None,
        locations: List = None,
        global_style: str = ""
    ) -> List[Dict[str, str]]:
        """Tạo fallback prompts khi AI không trả về đúng.

        IMPORTANT: KHÔNG đưa narration/dialogue text vào img_prompt!
        img_prompt chỉ chứa mô tả hình ảnh (visual description).
        """
        self.logger.info(f"[Fallback] Tạo {len(scenes_data)} fallback prompts...")
        characters = characters or []
        locations = locations or []

        # Build character description map - THEM FILENAME ANNOTATION de Flow match anh reference
        char_desc = {}
        for c in characters:
            desc = c.character_lock or c.vietnamese_prompt or f"{c.name}"
            # Them annotation filename: "A 30-year-old man (nvc.png)"
            char_desc[c.id] = f"{desc} ({c.id}.png)"

        # Build location description map - THEM FILENAME ANNOTATION
        loc_desc = {}
        for loc in locations:
            desc = loc.location_lock or loc.name
            # Them annotation filename: "Modern apartment living room (loc_apartment.png)"
            loc_desc[loc.id] = f"{desc} ({loc.id}.png)"

        style_suffix = global_style or "Cinematic, 4K photorealistic, natural lighting"

        # Shot type rotation for variety (HOOK + variety pattern)
        shot_types_hook = ["WIDE LOW ANGLE", "EXTREME CLOSE-UP", "EXTREME CLOSE-UP"]  # First 3 scenes
        shot_types_cycle = ["WIDE", "CLOSE-UP", "MEDIUM", "EXTREME CLOSE-UP", "LOW ANGLE", "TWO-SHOT"]

        result = []
        for idx, scene in enumerate(scenes_data):
            # Get scene info
            # IMPORTANT: Ưu tiên visual_moment (đã được AI xử lý), KHÔNG dùng text (narration)!
            visual_moment = scene.get("visual_moment", "")
            scene_type = scene.get("scene_type", "FRAME_PRESENT")

            # SHOT TYPE VARIETY - Critical for cinematic feel!
            if scene.get("shot_type") and scene.get("shot_type") != "Medium shot":
                shot_type = scene.get("shot_type")
            elif idx < 3:
                # HOOK scenes (1-3) - must be dramatic!
                shot_type = shot_types_hook[idx]
            else:
                # Cycle through variety for remaining scenes
                shot_type = shot_types_cycle[(idx - 3) % len(shot_types_cycle)]

            # Map location_id to actual location ID, không dùng generic loc1
            raw_location = scene.get("location_id", "")
            location_id = ""
            if raw_location:
                # Kiểm tra nếu raw_location là ID thực tế trong locations list
                for loc in locations:
                    if loc.id == raw_location:
                        location_id = raw_location
                        break
                # Nếu không tìm thấy, có thể là generic (loc1, loc2...)
                if not location_id and locations:
                    import re
                    match = re.match(r'loc(\d+)', raw_location)
                    if match:
                        idx_loc = int(match.group(1)) - 1  # loc1 -> index 0
                        if 0 <= idx_loc < len(locations):
                            location_id = locations[idx_loc].id
                    # Fallback: dùng location đầu tiên
                    if not location_id:
                        location_id = locations[0].id
            elif locations:
                # Không có location trong scene data, dùng location đầu tiên
                location_id = locations[0].id

            chars_in_scene = scene.get("characters_in_scene", [])

            # Build character part
            char_parts = []
            for char_id in chars_in_scene:
                if char_id in char_desc:
                    char_parts.append(char_desc[char_id])

            # Build location part
            loc_part = loc_desc.get(location_id, "")

            # Build prompt - ONLY VISUAL DESCRIPTION, NO NARRATION TEXT!
            parts = [shot_type]

            # Character description - chọn đúng nhân vật theo scene_type!
            if char_parts:
                parts.append(", ".join(char_parts[:2]))  # Max 2 characters
            elif characters:
                # Chọn nhân vật PHÙ HỢP dựa trên scene_type
                if scene_type == "CHILDHOOD_FLASHBACK":
                    # Mẹ trẻ + con nhỏ
                    young_mother = char_desc.get("nv1_young", char_desc.get("nv1", "32-year-old mother"))
                    child = char_desc.get("nvc1", "8-year-old boy")
                    parts.append(f"{young_mother}, with {child}")
                elif scene_type == "ADULT_FLASHBACK":
                    # Narrator trẻ (25-28 tuổi)
                    young_narrator = char_desc.get("nvc_young", char_desc.get("nvc", "25-year-old man"))
                    parts.append(young_narrator)
                else:
                    # FRAME_PRESENT, EMOTIONAL_BEAT - narrator hiện tại
                    parts.append(char_desc.get("nvc", characters[0].character_lock or characters[0].name))

            # Visual moment - ONLY if it's actually visual (not narration)
            # Check if visual_moment looks like narration (contains certain patterns)
            if visual_moment and not self._looks_like_narration(visual_moment):
                parts.append(visual_moment[:200])
            else:
                # Create STORY-AWARE visual based on scene_type and scene text
                scene_text = scene.get("text", "").lower()

                # 🔥 HOOK SCENES (1-3) - CRITICAL FOR VIEWER RETENTION!
                # These scenes need EXTRA dramatic visuals to hook viewers immediately
                if idx < 3:
                    hook_visual = self._create_hook_visual(idx, scene_text, char_parts, loc_part)
                    if hook_visual:
                        parts.append(hook_visual)
                        # Skip normal processing for HOOK scenes
                        # Location and style will be added below
                        if loc_part:
                            parts.append(loc_part)
                        parts.append(style_suffix)
                        img_prompt = ". ".join([p for p in parts if p])

                        # Build reference_files với actual location ID
                        hook_actual_loc = None
                        if location_id:
                            if location_id in loc_desc:
                                hook_actual_loc = location_id
                            elif locations:
                                hook_actual_loc = locations[0].id

                        all_refs = [f"{c}.png" for c in chars_in_scene]
                        if hook_actual_loc:
                            all_refs.append(f"{hook_actual_loc}.png")

                        filtered_refs, filtered_children = self._filter_children_from_refs(all_refs, return_filtered=True)
                        # Add inline child descriptions
                        if filtered_children:
                            img_prompt = self._add_children_inline_to_prompt(img_prompt, filtered_children, characters)

                        result.append({
                            "img_prompt": img_prompt,
                            "video_prompt": img_prompt,
                            "characters_used": chars_in_scene,
                            "location_used": hook_actual_loc or location_id,
                            "reference_files": filtered_refs
                        })
                        continue  # Skip to next scene

                if scene_type == "CHILDHOOD_FLASHBACK":
                    # Analyze scene text for specific childhood visuals
                    if "work" in scene_text or "job" in scene_text:
                        parts.append("exhausted young mother in work uniform, late evening, warm nostalgic lighting")
                    elif "home" in scene_text or "door" in scene_text:
                        parts.append("tired mother entering small apartment, child waiting, warm embrace, soft tungsten lighting")
                    elif "bed" in scene_text or "sleep" in scene_text:
                        parts.append("mother tucking child into bed, small shared bedroom, dim warm bedside lamp")
                    else:
                        parts.append("warm childhood memory scene, mother and child together, soft nostalgic golden lighting")

                elif scene_type == "ADULT_FLASHBACK":
                    # Analyze scene text for specific adult flashback visuals
                    if "build" in scene_text or "hammer" in scene_text or "nail" in scene_text:
                        parts.append("man hammering wooden beam on house frame, sawdust on face, determined expression, sunny day")
                    elif "land" in scene_text or "buy" in scene_text or "save" in scene_text:
                        parts.append("proud man standing on empty lot holding property deed, hopeful smile, golden sunset")
                    elif "finish" in scene_text or "complete" in scene_text or "done" in scene_text:
                        parts.append("man standing proudly in front of finished house, arms crossed, sense of accomplishment")
                    else:
                        parts.append("young adult working hard toward his dream, hopeful determined expression, natural daylight")

                elif scene_type == "EMOTIONAL_BEAT":
                    # Analyze scene text for emotional context
                    if "believe" in scene_text or "trust" in scene_text:
                        parts.append("extreme close-up of eyes glistening with emotion, distant gaze, painful memory")
                    elif "betray" in scene_text or "court" in scene_text:
                        parts.append("close-up of face showing shock and disbelief, trembling lip, fighting back tears")
                    else:
                        parts.append("close-up contemplative expression, eyes reflecting deep thought, emotional weight visible")

                else:  # FRAME_PRESENT or default
                    # Analyze scene text for present-day context
                    if "court" in scene_text or "legal" in scene_text:
                        parts.append("sitting on courthouse steps, holding legal documents, worried expression, morning light")
                    elif "house" in scene_text or "home" in scene_text:
                        parts.append("standing outside house, conflicted expression, life's work at stake")
                    else:
                        parts.append("present day, contemplative moment, natural lighting, weight of situation visible")

            # Location
            if loc_part:
                parts.append(loc_part)

            # Style
            parts.append(style_suffix)

            img_prompt = ". ".join([p for p in parts if p])

            # Build reference_files, filtering out children (API policy)
            # QUAN TRONG: Dùng location ID thực tế từ locations list, không dùng generic loc1/loc2
            actual_location_id = None
            if location_id:
                # Kiểm tra nếu location_id đã là ID thực (có trong loc_desc)
                if location_id in loc_desc:
                    actual_location_id = location_id
                else:
                    # location_id là generic (loc1, loc2...), tìm location phù hợp từ list
                    # Ưu tiên: dùng location đầu tiên trong list nếu có
                    if locations:
                        actual_location_id = locations[0].id
                        self.logger.debug(f"Scene {idx+1}: Mapped '{location_id}' to '{actual_location_id}'")

            all_refs = [f"{c}.png" for c in chars_in_scene]
            if actual_location_id:
                all_refs.append(f"{actual_location_id}.png")

            filtered_refs, filtered_children = self._filter_children_from_refs(all_refs, return_filtered=True)
            # Add inline child descriptions
            if filtered_children:
                img_prompt = self._add_children_inline_to_prompt(img_prompt, filtered_children, characters)

            result.append({
                "img_prompt": img_prompt,
                "video_prompt": img_prompt,
                "characters_used": chars_in_scene,
                "location_used": actual_location_id or location_id,
                "reference_files": filtered_refs
            })

        self.logger.info(f"[Fallback] Đã tạo {len(result)} fallback prompts")
        return result

    def _looks_like_narration(self, text: str) -> bool:
        """Check if text looks like narration/dialogue rather than visual description.

        Narration patterns:
        - Contains quotes or spoken text
        - Starts with "I ", "My ", "We ", "She ", "He "
        - Contains past tense narrative phrases
        """
        if not text:
            return True

        text_lower = text.lower().strip()

        # Narration indicators
        narration_patterns = [
            # First person narrative
            text_lower.startswith("i "),
            text_lower.startswith("i'"),
            text_lower.startswith("my "),
            text_lower.startswith("we "),
            # Third person narrative
            text_lower.startswith("she "),
            text_lower.startswith("he "),
            text_lower.startswith("they "),
            # Contains dialogue markers
            '"' in text,
            "said" in text_lower,
            "told" in text_lower,
            "asked" in text_lower,
            # Past tense narrative
            "i was" in text_lower,
            "i had" in text_lower,
            "i remember" in text_lower,
            "by the time" in text_lower,
            "years old" in text_lower,
            # YouTube CTA
            "subscribe" in text_lower,
            "like button" in text_lower,
            "comment" in text_lower,
        ]

        return any(narration_patterns)

    def _create_hook_visual(self, scene_idx: int, scene_text: str, char_parts: List[str], loc_part: str) -> str:
        """Create dramatic HOOK visual for scenes 1-3 (idx 0-2).

        HOOK scenes are CRITICAL for viewer retention. They must be:
        - Scene 1 (idx=0): WIDE LOW ANGLE - character DEVASTATED, ISOLATED, overwhelming environment
        - Scene 2 (idx=1): EXTREME CLOSE-UP - face with RAW emotion, tears, pain
        - Scene 3 (idx=2): EXTREME CLOSE-UP - meaningful detail (trembling hands, documents, etc.)

        These visuals MUST include CHARACTER - never empty locations!
        """
        if scene_idx == 0:
            # SCENE 1: THE GRABBER - Tiny figure in overwhelming environment
            # MUST show character in state of devastation/isolation

            # Analyze scene_text for context clues
            if any(w in scene_text for w in ["court", "legal", "lawsuit", "judge"]):
                return "TINY figure hunched ALONE on MASSIVE courthouse steps, head in hands, DEVASTATED posture, dwarfed by towering columns, morning fog, dramatic low angle emphasizing isolation"
            elif any(w in scene_text for w in ["hospital", "doctor", "sick", "ill"]):
                return "TINY figure sitting ALONE in vast hospital corridor, hunched over in despair, fluorescent lights stretching endlessly, dramatic low angle emphasizing vulnerability"
            elif any(w in scene_text for w in ["house", "home", "evict", "lost"]):
                return "TINY figure standing ALONE before house, shoulders slumped in defeat, belongings scattered, dramatic low angle, overwhelming sky"
            elif any(w in scene_text for w in ["grave", "funeral", "death", "die"]):
                return "TINY figure kneeling ALONE at gravestone, hunched in grief, cemetery stretching endlessly, dramatic low angle, overcast sky"
            elif any(w in scene_text for w in ["mother", "mom", "parent"]):
                return "TINY figure sitting ALONE, head bowed in sorrow, clutching photograph of mother, DEVASTATING isolation visible, dramatic low angle"
            else:
                # Default dramatic opening
                return "TINY figure hunched ALONE in vast empty space, ISOLATED and OVERWHELMED, head bowed in despair, dramatic low angle emphasizing human fragility against overwhelming circumstances"

        elif scene_idx == 1:
            # SCENE 2: EMOTIONAL IMPACT - Face with raw emotion
            # MUST show extreme close-up of face with visible emotion

            if any(w in scene_text for w in ["betray", "trust", "lie", "deceive"]):
                return "EXTREME CLOSE-UP of face, eyes glistening with TEARS of betrayal, jaw clenched fighting back sobs, single tear rolling down cheek, raw disbelief visible"
            elif any(w in scene_text for w in ["remember", "memory", "past"]):
                return "EXTREME CLOSE-UP of face, eyes distant and glistening with painful memories, nostalgic ache visible, bittersweet pain etched in expression"
            elif any(w in scene_text for w in ["lost", "gone", "never"]):
                return "EXTREME CLOSE-UP of face, eyes red and swollen, DEVASTATED expression, lips trembling, the weight of loss carved into every feature"
            elif any(w in scene_text for w in ["mother", "mom"]):
                return "EXTREME CLOSE-UP of face, eyes filling with tears thinking of mother, profound grief and longing visible, chin trembling with emotion"
            else:
                # Default emotional close-up
                return "EXTREME CLOSE-UP of face showing RAW EMOTION, eyes glistening with unshed tears, profound pain visible in every feature, intimate and vulnerable moment"

        elif scene_idx == 2:
            # SCENE 3: DETAIL SHOT - Meaningful object or body part
            # Close-up on detail that tells the story

            if any(w in scene_text for w in ["court", "legal", "document", "paper"]):
                return "EXTREME CLOSE-UP of trembling hands clutching crumpled legal documents, knuckles white with tension, papers slightly shaking, desperation visible"
            elif any(w in scene_text for w in ["ring", "wedding", "marriage"]):
                return "EXTREME CLOSE-UP of trembling finger touching wedding ring, the weight of broken vows visible, intimate painful detail"
            elif any(w in scene_text for w in ["photo", "picture", "memory"]):
                return "EXTREME CLOSE-UP of weathered hands holding faded photograph, edges worn from years of touching, precious memory captured"
            elif any(w in scene_text for w in ["mother", "mom"]):
                return "EXTREME CLOSE-UP of hands clutching mother's keepsake, fingers tracing familiar pattern, tears visible on skin, profound connection"
            elif any(w in scene_text for w in ["key", "house", "home"]):
                return "EXTREME CLOSE-UP of trembling hands gripping house keys, knuckles white, the weight of losing everything visible in the tension"
            else:
                # Default detail shot
                return "EXTREME CLOSE-UP of trembling hands, knuckles white with tension, the weight of the moment visible in every crease and tremor, intimate emotional detail"

        return ""  # Should not reach here

    def _clean_narration_from_prompt(self, img_prompt: str, scene_text: str) -> str:
        """Remove any narration/dialogue text that might have been included in img_prompt.

        AI sometimes includes the scene text directly in the prompt, which causes
        image generators to render text as subtitles on the image.

        Args:
            img_prompt: The image prompt from AI
            scene_text: The narration/dialogue text from SRT (first ~100 chars)

        Returns:
            Cleaned img_prompt without narration text
        """
        if not img_prompt or not scene_text:
            return img_prompt

        import re

        # 1. Remove exact match of scene_text (or significant portion)
        # Try to match phrases that are clearly from the narration
        words = scene_text.split()
        if len(words) >= 5:
            # Try to match 5+ consecutive words from narration
            for i in range(len(words) - 4):
                phrase = " ".join(words[i:i+5])
                if phrase.lower() in img_prompt.lower():
                    # Found narration in prompt - try to remove it
                    # Find and remove the sentence containing this phrase
                    pattern = re.compile(r'[^.]*' + re.escape(phrase) + r'[^.]*\.?', re.IGNORECASE)
                    img_prompt = pattern.sub('', img_prompt)
                    self.logger.debug(f"[Clean] Removed narration phrase: '{phrase[:30]}...'")

        # 2. Remove common narration patterns
        narration_patterns = [
            r'By the time I was \d+ years old[^.]*\.?',
            r'I had saved[^.]*\.?',
            r'I decided to[^.]*\.?',
            r'It cost me[^.]*\.?',
            r'I remember[^.]*\.?',
            r'She (told|said|asked)[^.]*\.?',
            r'He (told|said|asked)[^.]*\.?',
            r'"[^"]*"',  # Remove quoted dialogue
        ]

        for pattern in narration_patterns:
            if re.search(pattern, img_prompt, re.IGNORECASE):
                img_prompt = re.sub(pattern, '', img_prompt, flags=re.IGNORECASE)
                self.logger.debug(f"[Clean] Removed pattern: {pattern[:30]}...")

        # 3. Clean up: remove double periods, extra spaces
        img_prompt = re.sub(r'\.\.+', '.', img_prompt)
        img_prompt = re.sub(r'\s+', ' ', img_prompt)
        img_prompt = img_prompt.strip()
        img_prompt = img_prompt.strip('.')

        # 4. If prompt is now too short, return original (something went wrong)
        if len(img_prompt) < 30:
            self.logger.warning(f"[Clean] Prompt too short after cleaning, may need manual review")

        return img_prompt

    def _extract_json(self, text: str) -> Optional[Dict]:
        """
        Trích xuất JSON từ response text.

        Hỗ trợ nhiều format: raw JSON, markdown code block, DeepSeek <think> tags.
        Cũng xử lý JSON bị truncated (chưa đóng đủ braces).
        """
        if not text:
            self.logger.warning("[_extract_json] Empty text received")
            return None

        if not text.strip():
            self.logger.warning("[_extract_json] Text is only whitespace")
            return None

        import re

        # Bước 1: Loại bỏ DeepSeek <think>...</think> tags
        clean_text = re.sub(r'<think>[\s\S]*?</think>', '', text).strip()

        # Kiểm tra sau khi loại bỏ <think> tags
        if not clean_text:
            self.logger.warning("[_extract_json] Text empty after removing <think> tags")
            self.logger.debug(f"[_extract_json] Original text (first 300 chars): {text[:300]}")
            return None

        # Bước 2: Thử parse trực tiếp
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            self.logger.warning(f"[_extract_json] Direct parse failed at position {e.pos}: {e.msg}")

        # Bước 3: Thử tìm JSON trong code block ```json ... ```
        # Improved: xử lý cả trường hợp không có closing ```
        json_block = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', clean_text)
        if json_block:
            block_content = json_block.group(1).strip()
            # Nếu có ``` thừa ở cuối, cắt bỏ
            if block_content.endswith('```'):
                block_content = block_content[:-3].strip()
            try:
                return json.loads(block_content)
            except json.JSONDecodeError as e:
                self.logger.debug(f"[_extract_json] Code block parse failed: {e}")
                # Thử repair JSON trong code block nếu bị truncated
                if block_content.startswith('{'):
                    self.logger.info("[_extract_json] Attempting to repair JSON from code block...")
                    clean_text = block_content  # Dùng nội dung code block cho bước 4
        else:
            # Không tìm thấy code block đóng - thử tìm code block mở không đóng
            json_block_open = re.search(r'```(?:json)?\s*\n?([\s\S]*)', clean_text)
            if json_block_open:
                block_content = json_block_open.group(1).strip()
                # Loại bỏ trailing ``` nếu có
                block_content = re.sub(r'```\s*$', '', block_content).strip()
                self.logger.info(f"[_extract_json] Found unclosed code block, extracted {len(block_content)} chars")
                if block_content.startswith('{'):
                    clean_text = block_content  # Dùng cho bước 4

        # Bước 4: Tìm JSON object bắt đầu bằng { và kết thúc bằng }
        start_idx = clean_text.find('{')
        if start_idx != -1:
            # Đếm balanced braces và brackets
            brace_count = 0
            bracket_count = 0
            end_idx = -1
            last_brace_idx = start_idx

            for i, char in enumerate(clean_text[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                    last_brace_idx = i
                elif char == '}':
                    brace_count -= 1
                    last_brace_idx = i
                    if brace_count == 0:
                        end_idx = i
                        break
                elif char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1

            # Nếu tìm được JSON balanced
            if end_idx > start_idx:
                json_str = clean_text[start_idx:end_idx + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    self.logger.debug(f"[_extract_json] Balanced parse failed: {e}")
                    # Thử fix trailing commas
                    fixed_json = re.sub(r',(\s*[}\]])', r'\1', json_str)
                    try:
                        return json.loads(fixed_json)
                    except json.JSONDecodeError:
                        pass

            # Bước 4b: JSON bị truncated - thử repair bằng cách đóng braces
            elif brace_count > 0:
                self.logger.warning(f"[_extract_json] JSON truncated! Unclosed braces: {brace_count}, brackets: {bracket_count}")
                # Lấy text từ { đến hết
                json_str = clean_text[start_idx:]

                # Chiến lược repair mạnh mẽ hơn
                repair_attempts = [
                    # Attempt 1: Find last complete scene object and close there
                    lambda s: self._truncate_at_last_complete_scene(s, brace_count, bracket_count),
                    # Attempt 2: Find last complete string value and close
                    lambda s: self._truncate_at_last_complete_value(s, brace_count, bracket_count),
                    # Attempt 3: Simple close with ]} pattern
                    lambda s: self._simple_json_close(s, brace_count, bracket_count),
                ]

                for attempt, repair_fn in enumerate(repair_attempts):
                    try:
                        repaired = repair_fn(json_str)
                        if repaired:
                            result = json.loads(repaired)
                            self.logger.info(f"[_extract_json] Successfully repaired truncated JSON (strategy {attempt + 1})")
                            return result
                    except json.JSONDecodeError as e:
                        self.logger.debug(f"[_extract_json] Repair strategy {attempt + 1} failed: {e.msg}")
                        continue
                    except Exception as e:
                        self.logger.debug(f"[_extract_json] Repair strategy {attempt + 1} error: {e}")
                        continue

                self.logger.warning(f"[_extract_json] Could not repair truncated JSON")

        # Bước 5: Fallback - regex greedy
        json_match = re.search(r'\{[\s\S]*\}', clean_text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        self.logger.warning(f"[_extract_json] Could not extract JSON. Response length: {len(text)}")
        self.logger.warning(f"[_extract_json] Response starts with: {text[:200] if text else 'EMPTY'}")
        return None

    def _truncate_at_last_complete_scene(self, json_str: str, brace_count: int, bracket_count: int) -> Optional[str]:
        """
        Tìm scene cuối cùng hoàn chỉnh (có đầy đủ img_prompt) và truncate tại đó.
        Director's Shooting Plan trả về array of scenes, mỗi scene có img_prompt.
        """
        import re

        # Tìm tất cả các scene objects hoàn chỉnh (có cả img_prompt với closing quote)
        # Pattern: { ... "img_prompt": "..." ... }
        scene_pattern = r'\{\s*"scene_id"[^}]*"img_prompt"\s*:\s*"[^"]*"[^}]*\}'

        matches = list(re.finditer(scene_pattern, json_str, re.DOTALL))

        if matches:
            # Lấy vị trí kết thúc của scene cuối cùng hoàn chỉnh
            last_match = matches[-1]
            truncated = json_str[:last_match.end()]

            # Đếm lại braces/brackets trong phần truncated
            new_brace_count = truncated.count('{') - truncated.count('}')
            new_bracket_count = truncated.count('[') - truncated.count(']')

            # Đóng JSON
            suffix = ']' * max(0, new_bracket_count) + '}' * max(0, new_brace_count)
            return truncated + suffix

        return None

    def _truncate_at_last_complete_value(self, json_str: str, brace_count: int, bracket_count: int) -> Optional[str]:
        """
        Tìm vị trí cuối cùng có value hoàn chỉnh (string đóng đúng, number, boolean).
        """
        import re

        # Tìm pattern cuối cùng là một value hoàn chỉnh
        # Pattern: "key": "value" hoặc "key": number hoặc "key": true/false/null
        complete_value_patterns = [
            # String value với closing quote, có thể theo sau bởi , hoặc }
            r'"[^"]+"\s*:\s*"[^"]*"(?=\s*[,}\]])',
            # Number value
            r'"[^"]+"\s*:\s*-?\d+\.?\d*(?=\s*[,}\]])',
            # Boolean/null
            r'"[^"]+"\s*:\s*(?:true|false|null)(?=\s*[,}\]])',
            # Array/Object close
            r'[\]}](?=\s*[,}\]])',
        ]

        last_pos = 0
        for pattern in complete_value_patterns:
            for match in re.finditer(pattern, json_str):
                if match.end() > last_pos:
                    last_pos = match.end()

        if last_pos > 0:
            # Truncate tại vị trí này
            truncated = json_str[:last_pos]

            # Xử lý trailing comma
            truncated = re.sub(r',\s*$', '', truncated)

            # Đếm lại braces/brackets
            new_brace_count = truncated.count('{') - truncated.count('}')
            new_bracket_count = truncated.count('[') - truncated.count(']')

            # Đóng JSON
            suffix = ']' * max(0, new_bracket_count) + '}' * max(0, new_brace_count)
            return truncated + suffix

        return None

    def _simple_json_close(self, json_str: str, brace_count: int, bracket_count: int) -> Optional[str]:
        """
        Phương pháp đơn giản: tìm điểm an toàn cuối cùng và đóng.
        """
        import re

        # Tìm vị trí của closing quote cuối cùng (kết thúc một string value)
        # Sau đó truncate tại đó
        last_quote_pos = json_str.rfind('"')

        if last_quote_pos > 0:
            # Kiểm tra xem quote này có phải là closing quote không
            # (không phải escaped và số lượng quotes trước đó là lẻ)
            substr = json_str[:last_quote_pos + 1]

            # Đếm quotes không escaped
            quote_count = len(re.findall(r'(?<!\\)"', substr))

            if quote_count % 2 == 0:
                # Đây là closing quote của một string
                truncated = substr

                # Tìm và xóa incomplete key-value sau string này
                # Pattern: , "incomplete_key  hoặc , incomplete_value
                truncated = re.sub(r',\s*"[^"]*$', '', truncated)
                truncated = re.sub(r',\s*$', '', truncated)

                # Đếm lại braces/brackets
                new_brace_count = truncated.count('{') - truncated.count('}')
                new_bracket_count = truncated.count('[') - truncated.count(']')

                # Đóng JSON
                suffix = ']' * max(0, new_bracket_count) + '}' * max(0, new_brace_count)
                return truncated + suffix

        # Fallback: đơn giản thêm closing braces
        # Loại bỏ phần cuối có thể không hoàn chỉnh
        truncated = re.sub(r',\s*"[^"]*$', '', json_str)  # Incomplete key
        truncated = re.sub(r':\s*"[^"]*$', '""', truncated)  # Incomplete string value -> empty string
        truncated = re.sub(r',\s*$', '', truncated)

        new_brace_count = truncated.count('{') - truncated.count('}')
        new_bracket_count = truncated.count('[') - truncated.count(']')

        suffix = ']' * max(0, new_bracket_count) + '}' * max(0, new_brace_count)
        return truncated + suffix

    def update_excel_prompts_with_annotations(self, excel_path: str) -> bool:
        """
        Update existing Excel prompts with filename annotations.
        Use this to add annotations to prompts that were generated before this feature.

        Args:
            excel_path: Path to Excel file

        Returns:
            True if successful
        """
        from modules.excel_manager import PromptWorkbook

        try:
            excel_path = Path(excel_path)
            if not excel_path.exists():
                self.logger.error(f"Excel file not found: {excel_path}")
                return False

            workbook = PromptWorkbook(excel_path).load_or_create()

            # Load characters and locations
            characters = workbook.get_characters()
            locations = [c for c in characters if c.role == "location"]
            characters = [c for c in characters if c.role != "location"]

            # Update scenes
            scenes = workbook.get_scenes()
            updated_count = 0

            for scene in scenes:
                # Get reference_files
                ref_files = []
                if scene.reference_files:
                    try:
                        ref_files = json.loads(scene.reference_files) if scene.reference_files.startswith('[') else [scene.reference_files]
                    except:
                        ref_files = [f.strip() for f in scene.reference_files.split(',') if f.strip()]

                if not ref_files:
                    continue

                # Update img_prompt
                new_img_prompt = self._add_filename_annotations_to_prompt(
                    scene.img_prompt or "", ref_files, characters, locations
                )
                new_video_prompt = self._add_filename_annotations_to_prompt(
                    scene.video_prompt or "", ref_files, characters, locations
                )

                # Check if changed
                if new_img_prompt != scene.img_prompt or new_video_prompt != scene.video_prompt:
                    workbook.update_scene(
                        scene.scene_id,
                        img_prompt=new_img_prompt,
                        video_prompt=new_video_prompt
                    )
                    updated_count += 1
                    self.logger.info(f"Updated scene {scene.scene_id} with filename annotations")

            workbook.save()
            self.logger.info(f"Updated {updated_count} scenes with filename annotations")
            return True

        except Exception as e:
            self.logger.error(f"Error updating Excel prompts: {e}")
            return False
