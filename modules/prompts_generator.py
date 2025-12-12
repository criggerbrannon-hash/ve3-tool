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

        # Step 2: Chia scene THÔNG MINH theo nội dung (không theo thời gian)
        self.logger.info("Chia scene theo nội dung (AI Smart Division)...")
        scenes_data = self._smart_divide_scenes(srt_entries)

        self.logger.info(f"Chia thành {len(scenes_data)} scenes")

        # Step 3: Tạo prompts cho từng batch scenes (PARALLEL)
        self.logger.info("Tạo prompts cho scenes...")

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
        
        # Lưu scenes vào Excel
        for scene_data, prompts in zip(scenes_data, all_scene_prompts):
            # Convert lists to JSON strings for storage
            chars_used = prompts.get("characters_used", [])
            location_used = prompts.get("location_used", "")
            ref_files = prompts.get("reference_files", [])

            # === AUTO-GENERATE reference_files nếu AI không điền ===
            if not ref_files:
                ref_files = []
                # Thêm tất cả nhân vật đã dùng
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
                # Thêm location đã dùng
                if location_used:
                    loc_file = f"{location_used}.png" if not location_used.endswith('.png') else location_used
                    if loc_file not in ref_files:
                        ref_files.append(loc_file)

                if ref_files:
                    self.logger.debug(f"Scene {scene_data['scene_id']}: Auto-generated reference_files: {ref_files}")

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
                    "story_beat": scene.get("story_beat", ""),  # Nhịp kể chuyện
                    "start_time": start_str,
                    "end_time": end_str,
                    "duration_seconds": scene.get("duration_seconds", 5),
                    "text": scene.get("text", ""),
                    "visual_moment": scene.get("visual_moment", ""),
                    "shot_type": scene.get("shot_type", "Medium shot"),
                    "srt_start": srt_start,
                    "srt_end": srt_end,
                })

            self.logger.info(f"AI chia thành {len(scenes_data)} scenes theo nội dung")

            # POST-VALIDATION: Chia lại những scene vượt quá max_duration (8s)
            validated_scenes = self._validate_and_split_scenes(scenes_data, srt_entries)
            if len(validated_scenes) != len(scenes_data):
                self.logger.info(f"Post-validation: {len(scenes_data)} -> {len(validated_scenes)} scenes (split long scenes)")

            return validated_scenes

        except Exception as e:
            self.logger.error(f"Smart divide failed: {e}, falling back to time-based")
            return self._fallback_time_based_division(srt_entries)

    def _validate_and_split_scenes(self, scenes_data: List[Dict], srt_entries: List) -> List[Dict[str, Any]]:
        """
        Validate và chia lại những scene vượt quá max_duration.

        Args:
            scenes_data: List scenes từ AI
            srt_entries: List SrtEntry gốc

        Returns:
            List scenes đã được validate và split nếu cần
        """
        # Build lookup table: srt_index -> SrtEntry
        srt_lookup = {e.index: e for e in srt_entries}

        validated = []
        scene_counter = 1

        for scene in scenes_data:
            # Tính duration thực tế từ srt_start và srt_end
            srt_start = scene.get("srt_start", 1)
            srt_end = scene.get("srt_end", srt_start)

            # Lấy các SRT entries trong range này
            scene_entries = [srt_lookup[i] for i in range(srt_start, srt_end + 1) if i in srt_lookup]

            if not scene_entries:
                # Không tìm thấy entries, giữ nguyên
                scene["scene_id"] = scene_counter
                validated.append(scene)
                scene_counter += 1
                continue

            # Tính duration thực tế
            actual_start = scene_entries[0].start_time
            actual_end = scene_entries[-1].end_time
            actual_duration = (actual_end - actual_start).total_seconds()

            if actual_duration <= self.max_scene_duration:
                # Duration OK, giữ nguyên
                scene["scene_id"] = scene_counter
                scene["start_time"] = format_srt_time(actual_start)
                scene["end_time"] = format_srt_time(actual_end)
                scene["duration_seconds"] = actual_duration
                validated.append(scene)
                scene_counter += 1
            else:
                # Duration vượt quá max, cần chia nhỏ
                self.logger.warning(f"Scene {scene.get('scene_id')} duration={actual_duration:.1f}s > {self.max_scene_duration}s, splitting...")

                # Sử dụng group_srt_into_scenes để chia theo thời gian
                sub_scenes = group_srt_into_scenes(
                    scene_entries,
                    min_duration=self.min_scene_duration,
                    max_duration=self.max_scene_duration
                )

                for sub in sub_scenes:
                    validated.append({
                        "scene_id": scene_counter,
                        "story_beat": scene.get("story_beat", ""),
                        "start_time": format_srt_time(sub["start_time"]) if isinstance(sub["start_time"], timedelta) else sub["start_time"],
                        "end_time": format_srt_time(sub["end_time"]) if isinstance(sub["end_time"], timedelta) else sub["end_time"],
                        "duration_seconds": (sub["end_time"] - sub["start_time"]).total_seconds() if isinstance(sub["start_time"], timedelta) else 5,
                        "text": sub["text"],
                        "visual_moment": scene.get("visual_moment", sub["text"]),
                        "shot_type": scene.get("shot_type", "Medium shot"),
                        "srt_start": sub["srt_start"],
                        "srt_end": sub["srt_end"],
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

        # Format thông tin scenes (include story_beat, shot_type and visual_moment)
        pacing_script = "\n".join([
            f"{s['scene_id']}. [{s.get('shot_type', 'Medium shot')}] \"{s['text']}\"\n"
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
