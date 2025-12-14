"""
VE3 Tool - Prompts Generator Module
===================================
Sử dụng AI API để phân tích SRT và tạo prompts cho ảnh/video.
Hỗ trợ: DeepSeek (rẻ), Groq (free), Gemini
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
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
# MULTI AI CLIENT (DeepSeek + Groq + Gemini)
# ============================================================================

class MultiAIClient:
    """
    Client hỗ trợ nhiều AI providers.
    Ưu tiên: Gemini (chất lượng cao) > Groq (nhanh) > DeepSeek (rẻ, chậm) > Ollama (local)

    Tự động test và loại bỏ API keys không hoạt động khi khởi tạo.
    """

    DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
    OLLAMA_URL = "http://localhost:11434/api/generate"  # Local Ollama

    def __init__(self, config: dict, auto_filter: bool = True):
        """
        Config format:
        {
            "deepseek_api_keys": ["key1"],
            "groq_api_keys": ["key1", "key2"],
            "gemini_api_keys": ["key1"],
            "gemini_models": ["gemini-2.0-flash"],
            "ollama_model": "qwen2.5:7b",  # Optional: local model
        }

        auto_filter: Tự động test và loại bỏ API keys không hoạt động
        """
        self.config = config
        self.gemini_keys = [k for k in config.get("gemini_api_keys", []) if k and k.strip()]
        self.groq_keys = [k for k in config.get("groq_api_keys", []) if k and k.strip()]
        self.deepseek_keys = [k for k in config.get("deepseek_api_keys", []) if k and k.strip()]
        self.gemini_models = config.get("gemini_models", ["gemini-2.0-flash", "gemini-1.5-flash"])

        # Ollama local model
        self.ollama_model = config.get("ollama_model", "qwen2.5:7b")
        self.ollama_available = False

        self.deepseek_index = 0
        self.groq_index = 0
        self.gemini_key_index = 0
        self.gemini_model_index = 0

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
        print("\n[API Filter] Dang kiem tra API keys (parallel)...")

        results = {
            'gemini': [],
            'groq': [],
            'deepseek': [],
            'ollama': False
        }
        results_lock = threading.Lock()

        def test_gemini(key_info: Tuple[int, str]) -> Tuple[str, int, str, bool]:
            i, key = key_info
            result = self._test_gemini_key(key)
            return ('gemini', i, key, result)

        def test_groq(key_info: Tuple[int, str]) -> Tuple[str, int, str, bool]:
            i, key = key_info
            result = self._test_groq_key(key)
            return ('groq', i, key, result)

        def test_deepseek(key_info: Tuple[int, str]) -> Tuple[str, int, str, bool]:
            i, key = key_info
            result = self._test_deepseek_key(key)
            return ('deepseek', i, key, result)

        def test_ollama() -> Tuple[str, int, str, bool]:
            result = self._test_ollama()
            return ('ollama', 0, '', result)

        # Prepare all test tasks
        tasks = []
        tasks.extend([('gemini', i, key) for i, key in enumerate(self.gemini_keys)])
        tasks.extend([('groq', i, key) for i, key in enumerate(self.groq_keys)])
        tasks.extend([('deepseek', i, key) for i, key in enumerate(self.deepseek_keys)])

        # Use ThreadPoolExecutor for parallel API testing
        max_workers = min(len(tasks) + 1, 20)  # Max 20 parallel connections

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []

            # Submit all API tests
            for provider, i, key in tasks:
                if provider == 'gemini':
                    futures.append(executor.submit(test_gemini, (i, key)))
                elif provider == 'groq':
                    futures.append(executor.submit(test_groq, (i, key)))
                elif provider == 'deepseek':
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
        self.gemini_keys = results['gemini']
        self.groq_keys = results['groq']
        self.deepseek_keys = results['deepseek']
        self.ollama_available = results['ollama']

        total_working = len(self.gemini_keys) + len(self.groq_keys) + len(self.deepseek_keys)
        ollama_str = ", Ollama: OK" if self.ollama_available else ""
        print(f"[API Filter] Ket qua: {len(self.gemini_keys)} Gemini, {len(self.groq_keys)} Groq, {len(self.deepseek_keys)} DeepSeek{ollama_str}")

        if total_working == 0 and not self.ollama_available:
            print("[API Filter] CANH BAO: Khong co API nao hoat dong! Cai Ollama de dung offline.")
        else:
            # Show priority order
            if self.gemini_keys:
                print(f"[API Filter] Se dung: Gemini (uu tien)")
            elif self.groq_keys:
                print(f"[API Filter] Se dung: Groq (uu tien)")
            elif self.deepseek_keys:
                print(f"[API Filter] Se dung: DeepSeek")
            elif self.ollama_available:
                print(f"[API Filter] Se dung: Ollama (local)")

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

        # 4. Fallback to Ollama (local, free, offline)
        if self.ollama_available:
            for attempt in range(max_retries):
                try:
                    print(f"[Ollama] Dang goi local model ({self.ollama_model})...")
                    result = self._call_ollama(prompt, temperature)
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

    def _call_ollama(self, prompt: str, temperature: float) -> str:
        """Call Ollama local API."""
        data = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 8192,  # Max tokens
            }
        }

        self.logger.debug(f"Calling Ollama API: model={self.ollama_model}")
        print(f"[Ollama] Dang xu ly... (co the mat 1-5 phut tuy cau hinh may)")

        # Ollama can be slow, increase timeout
        resp = requests.post(self.OLLAMA_URL, json=data, timeout=600)

        if resp.status_code == 200:
            result = resp.json()
            return result.get("response", "")
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
            total_keys = len(self.gemini_keys) + len(self.groq_keys) + len(self.deepseek_keys)
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

        # Parallel processing settings
        self.parallel_enabled = settings.get("parallel_enabled", True)
        self.max_parallel_batches = settings.get("max_parallel_batches", 3)  # Parallel batch processing
        self.batch_size = settings.get("prompt_batch_size", 10)  # Scenes per batch

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

        # Step 1.5: Director's Treatment - Phân tích cấu trúc câu chuyện
        self.logger.info("=" * 50)
        self.logger.info("Step 1.5: Tạo DIRECTOR'S TREATMENT (Kịch bản đạo diễn)...")
        self.logger.info("=" * 50)
        directors_treatment = self._create_directors_treatment(full_story)
        if directors_treatment:
            self.logger.info(f"[Director's Treatment] Story parts: {len(directors_treatment.get('story_parts', []))}")

        # Step 2: Chia scene THÔNG MINH theo nội dung (dựa trên Director's Treatment)
        self.logger.info("Chia scene theo nội dung (AI Smart Division)...")
        scenes_data = self._smart_divide_scenes(srt_entries, characters, locations, directors_treatment)

        self.logger.info(f"Chia thành {len(scenes_data)} scenes")

        # Step 3: Tạo prompts cho từng batch scenes (PARALLEL)
        self.logger.info("=" * 50)
        self.logger.info("Step 3: Tạo IMG PROMPTS cho scenes...")
        self.logger.info("=" * 50)

        if not scenes_data:
            self.logger.error("KHÔNG CÓ SCENES DATA! Dừng.")
            return False

        # Chia scenes thành batches để tránh vượt quá context limit
        batch_size = self.batch_size
        batches = []
        for i in range(0, len(scenes_data), batch_size):
            batches.append(scenes_data[i:i + batch_size])

        total_batches = len(batches)
        self.logger.info(f"Chia thanh {total_batches} batches, moi batch {batch_size} scenes")

        all_scene_prompts = []

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

                # Thêm location đã dùng
                if location_used:
                    loc_file = f"{location_used}.png" if not location_used.endswith('.png') else location_used
                    if loc_file not in ref_files:
                        ref_files.append(loc_file)

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

            # Nếu không có nhân vật nào → thêm nvc làm mặc định
            if not has_character:
                if not ref_files:
                    ref_files = ["nvc.png"]
                else:
                    # Có loc nhưng không có nhân vật → thêm nvc vào đầu
                    ref_files.insert(0, "nvc.png")
                self.logger.warning(f"Scene {scene_data['scene_id']}: No character in refs, adding nvc.png → {ref_files}")

            chars_str = json.dumps(chars_used) if isinstance(chars_used, list) else str(chars_used)
            refs_str = json.dumps(ref_files) if isinstance(ref_files, list) else str(ref_files)

            # Lấy thời gian thực từ scene_data (đã được tính trong _validate_and_split_scenes)
            start_time = scene_data.get("start_time", "")
            end_time = scene_data.get("end_time", "")
            duration = scene_data.get("duration_seconds", 0)

            scene = Scene(
                scene_id=scene_data["scene_id"],
                start_time=start_time,          # Thời gian bắt đầu (HH:MM:SS,mmm)
                end_time=end_time,              # Thời gian kết thúc (HH:MM:SS,mmm)
                duration=round(duration, 2),    # Độ dài (giây)
                srt_start=scene_data["srt_start"],
                srt_end=scene_data["srt_end"],
                srt_text=scene_data["text"][:500],  # Truncate nếu quá dài
                img_prompt=prompts.get("img_prompt", ""),
                video_prompt=prompts.get("video_prompt", ""),
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
            response = self._generate_content(prompt, temperature=0.5)

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

                # For children (DO_NOT_GENERATE), use character_lock for both
                if portrait_prompt == "DO_NOT_GENERATE":
                    portrait_prompt = character_lock

                characters.append(Character(
                    id=char_data.get("id", ""),
                    role=char_data.get("role", "supporting"),
                    name=char_data.get("name", ""),
                    english_prompt=portrait_prompt,  # For reference image generation
                    character_lock=character_lock,    # For scene prompts (IMPORTANT!)
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

    def _smart_divide_scenes(self, srt_entries: List, characters: List = None, locations: List = None, directors_treatment: Dict = None) -> List[Dict[str, Any]]:
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
            return self._format_time_based_scenes(time_based_scenes)

        # Build full prompt với context + Director's Treatment
        try:
            prompt = prompt_template.format(
                srt_with_timestamps=scenes_for_ai,
                characters_info=chars_info,
                locations_info=locs_info,
                directors_treatment=treatment_info or "No director's treatment available - analyze story structure yourself"
            )
        except KeyError:
            # Fallback nếu template không có placeholder
            prompt = prompt_template.format(srt_with_timestamps=scenes_for_ai)
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
            response = self._generate_content(prompt, temperature=0.4, max_tokens=16000)
            json_data = self._extract_json(response)

            if not json_data or "scenes" not in json_data:
                self.logger.warning("[Smart Divide] AI không trả về scenes, dùng time-based")
                return self._format_time_based_scenes(time_based_scenes)

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

                final_scenes.append({
                    "scene_id": scene_id,
                    "scene_type": scene_type,  # NEW: Type of scene
                    "age_note": age_note,      # NEW: Age adjustment for flashbacks
                    "location_id": ai_data.get("location_id", "loc1"),
                    "characters_in_scene": chars_in_scene,
                    "story_beat": ai_data.get("story_beat", ""),
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration_seconds": duration,
                    "text": scene["text"],
                    "visual_moment": ai_data.get("visual_moment", scene["text"]),
                    "shot_type": ai_data.get("shot_type", "Medium shot"),
                    "srt_start": start_time,
                    "srt_end": end_time,
                })

            self.logger.info(f"Hoàn thành: {len(final_scenes)} scenes với visual_moment từ AI")
            return final_scenes

        except Exception as e:
            self.logger.error(f"AI analysis failed: {e}, returning time-based scenes")
            return self._format_time_based_scenes(time_based_scenes)

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

    def _format_time_based_scenes(self, time_based_scenes: List[Dict], default_char: str = "nvc") -> List[Dict[str, Any]]:
        """Format time-based scenes khi không có AI analysis."""
        formatted = []
        for i, scene in enumerate(time_based_scenes):
            start_time = format_srt_time(scene["start_time"]) if isinstance(scene["start_time"], timedelta) else scene.get("srt_start", "00:00:00,000")
            end_time = format_srt_time(scene["end_time"]) if isinstance(scene["end_time"], timedelta) else scene.get("srt_end", "00:00:08,000")
            duration = (scene["end_time"] - scene["start_time"]).total_seconds() if isinstance(scene["start_time"], timedelta) else 5

            formatted.append({
                "scene_id": i + 1,
                "location_id": "loc1",
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

        # Format thông tin scenes (include location_id, story_beat, shot_type and visual_moment)
        pacing_script = "\n".join([
            f"{s['scene_id']}. [{s.get('shot_type', 'Medium shot')}] \"{s['text']}\"\n"
            f"   Location: {s.get('location_id', 'N/A')}\n"
            f"   Story beat: {s.get('story_beat', 'N/A')}\n"
            f"   Visual: {s.get('visual_moment', s['text'])}"
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
                    # Scene không có prompt từ AI - tạo prompt đơn giản từ text
                    missing_scenes.append(scene_id)
                    scene_text = scene_data.get("text", "")
                    visual_moment = scene_data.get("visual_moment", scene_text)
                    shot_type = scene_data.get("shot_type", "Medium shot")

                    # Tạo prompt đơn giản từ nội dung scene
                    simple_prompt = f"{shot_type}, {visual_moment[:200]}, cinematic lighting, high quality"

                    result.append({
                        "img_prompt": simple_prompt,
                        "video_prompt": simple_prompt,
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

        # Build character description map
        char_desc = {}
        for c in characters:
            char_desc[c.id] = c.character_lock or c.vietnamese_prompt or f"{c.name}"

        # Build location description map
        loc_desc = {}
        for loc in locations:
            loc_desc[loc.id] = loc.location_lock or loc.name

        style_suffix = global_style or "Cinematic, 4K photorealistic, natural lighting"

        result = []
        for scene in scenes_data:
            # Get scene info
            # IMPORTANT: Ưu tiên visual_moment (đã được AI xử lý), KHÔNG dùng text (narration)!
            visual_moment = scene.get("visual_moment", "")
            scene_type = scene.get("scene_type", "FRAME_PRESENT")
            shot_type = scene.get("shot_type", "Medium shot")
            location_id = scene.get("location_id", "loc1")
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

            # Character description
            if char_parts:
                parts.append(", ".join(char_parts[:2]))  # Max 2 characters
            elif characters:
                # Default to main character if none specified
                parts.append(char_desc.get("nvc", characters[0].character_lock or characters[0].name))

            # Visual moment - ONLY if it's actually visual (not narration)
            # Check if visual_moment looks like narration (contains certain patterns)
            if visual_moment and not self._looks_like_narration(visual_moment):
                parts.append(visual_moment[:200])
            else:
                # Create generic visual based on scene_type
                if scene_type == "CHILDHOOD_FLASHBACK":
                    parts.append("in a warm nostalgic memory scene, soft warm lighting")
                elif scene_type == "ADULT_FLASHBACK":
                    parts.append("in a hopeful flashback scene, natural daylight")
                elif scene_type == "EMOTIONAL_BEAT":
                    parts.append("close-up shot, contemplative expression, emotional moment")
                else:  # FRAME_PRESENT or default
                    parts.append("in present day setting, natural lighting")

            # Location
            if loc_part:
                parts.append(loc_part)

            # Style
            parts.append(style_suffix)

            img_prompt = ". ".join([p for p in parts if p])

            result.append({
                "img_prompt": img_prompt,
                "video_prompt": img_prompt,
                "characters_used": chars_in_scene,
                "location_used": location_id,
                "reference_files": [f"{c}.png" for c in chars_in_scene] + ([f"{location_id}.png"] if location_id else [])
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
