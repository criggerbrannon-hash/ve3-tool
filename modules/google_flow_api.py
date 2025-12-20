"""
VE3 Tool - Google Flow API Module
=================================
Tích hợp trực tiếp với Google Flow API để tạo ảnh và video.

Sử dụng Bearer Token authentication.
API Endpoint: aisandbox-pa.googleapis.com
"""

import json
import time
import random
import base64
import uuid
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class AspectRatio(Enum):
    """Tỷ lệ khung hình cho ảnh."""
    LANDSCAPE = "IMAGE_ASPECT_RATIO_LANDSCAPE"    # 16:9
    PORTRAIT = "IMAGE_ASPECT_RATIO_PORTRAIT"      # 9:16
    SQUARE = "IMAGE_ASPECT_RATIO_SQUARE"          # 1:1


class ImageModel(Enum):
    """Model tạo ảnh."""
    GEM_PIX = "GEM_PIX"
    GEM_PIX_2 = "GEM_PIX_2"  # Default model - phiên bản mới hơn


class ImageInputType(Enum):
    """Loại input image cho reference."""
    REFERENCE = "IMAGE_INPUT_TYPE_REFERENCE"
    STYLE = "IMAGE_INPUT_TYPE_STYLE"
    SUBJECT = "IMAGE_INPUT_TYPE_SUBJECT"


@dataclass
class ImageInput:
    """Input image cho reference khi generate."""
    name: str = ""  # Media name từ response trước đó (preferred)
    input_type: ImageInputType = ImageInputType.REFERENCE
    base64_data: str = ""  # Base64 image data (fallback if no name)
    mime_type: str = "image/png"  # MIME type for base64

    def to_dict(self) -> Dict[str, Any]:
        """Convert sang dict format cho API."""
        result = {
            "imageInputType": self.input_type.value
        }
        if self.name:
            # Prefer media_name reference
            result["name"] = self.name
        elif self.base64_data:
            # Fallback: try inline base64 (may not work but worth trying)
            result["rawImageBytes"] = self.base64_data
            result["mimeType"] = self.mime_type
        return result

    @classmethod
    def from_file(cls, file_path: Path, input_type: ImageInputType = ImageInputType.REFERENCE) -> 'ImageInput':
        """Create ImageInput from local file with base64 data."""
        import base64
        with open(file_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')

        suffix = file_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp"
        }
        mime = mime_types.get(suffix, "image/png")

        return cls(name="", input_type=input_type, base64_data=data, mime_type=mime)


@dataclass
class GeneratedImage:
    """Kết quả ảnh được tạo."""
    url: Optional[str] = None
    base64_data: Optional[str] = None
    media_id: Optional[str] = None
    media_name: Optional[str] = None  # Name để dùng làm reference
    workflow_id: Optional[str] = None
    seed: Optional[int] = None
    prompt: str = ""
    aspect_ratio: str = ""
    local_path: Optional[Path] = None

    @property
    def has_data(self) -> bool:
        return bool(self.url or self.base64_data or self.media_id)

    def as_reference(self, input_type: ImageInputType = ImageInputType.REFERENCE) -> Optional[ImageInput]:
        """Chuyển thành ImageInput để dùng làm reference cho ảnh khác."""
        if self.media_name:
            return ImageInput(name=self.media_name, input_type=input_type)
        return None


class GoogleFlowAPI:
    """
    Client để tương tác với Google Flow API.

    Sử dụng Bearer Token authentication từ browser session.
    Hỗ trợ reCAPTCHA Enterprise qua các dịch vụ: 2Captcha, Anti-Captcha, CapSolver.
    """

    BASE_URL = "https://aisandbox-pa.googleapis.com"
    TOOL_NAME = "PINHOLE"  # Internal name for Flow
    RECAPTCHA_SITE_KEY = "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV"
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        bearer_token: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: int = 120,
        verbose: bool = False,
        captcha_api_key: Optional[str] = None,
        captcha_service: str = "2captcha"
    ):
        """
        Khởi tạo Google Flow API client.

        Args:
            bearer_token: OAuth Bearer token (bắt đầu bằng "ya29.")
            project_id: Project ID (nếu không có sẽ tự tạo UUID)
            session_id: Session ID (nếu không có sẽ tự tạo)
            timeout: Request timeout in seconds
            verbose: Print debug info
            captcha_api_key: API key cho dịch vụ CAPTCHA (2Captcha, Anti-Captcha, CapSolver)
            captcha_service: Tên dịch vụ CAPTCHA ("2captcha", "anticaptcha", "capsolver")
        """
        self.bearer_token = bearer_token.strip()
        self.project_id = project_id or str(uuid.uuid4())
        self.session_id = session_id or f";{int(time.time() * 1000)}"
        self.timeout = timeout
        self.verbose = verbose

        # CAPTCHA solver config
        self.captcha_api_key = captcha_api_key
        self.captcha_service = captcha_service
        self.recaptcha_token = None
        self._captcha_solver = None

        # Chrome headers config (for x-browser-validation)
        self.chrome_profile_path = None
        self._chrome_headers = None
        self._headers_extractor = None

        # Validate token format
        if not self.bearer_token.startswith("ya29."):
            print("⚠️  Warning: Bearer token should start with 'ya29.'")

        self.session = self._create_session()
    
    def _create_session(self) -> requests.Session:
        """Tạo HTTP session với headers chuẩn."""
        session = requests.Session()
        
        session.headers.update({
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        })
        
        return session
    
    def _log(self, message: str) -> None:
        """Print log message if verbose."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {message}")
    
    def _generate_seed(self) -> int:
        """Tạo random seed cho image generation."""
        return random.randint(1, 999999)

    # =========================================================================
    # reCAPTCHA ENTERPRISE
    # =========================================================================

    def _get_captcha_solver(self):
        """Lazy init CAPTCHA solver."""
        if self._captcha_solver is None and self.captcha_api_key:
            try:
                from .captcha_solver import CaptchaSolver, CaptchaService
                service_map = {
                    "2captcha": CaptchaService.TWOCAPTCHA,
                    "anticaptcha": CaptchaService.ANTICAPTCHA,
                    "capsolver": CaptchaService.CAPSOLVER
                }
                service = service_map.get(self.captcha_service.lower(), CaptchaService.TWOCAPTCHA)
                self._captcha_solver = CaptchaSolver(self.captcha_api_key, service)
            except ImportError:
                self._log("Warning: captcha_solver module not found")
        return self._captcha_solver

    def solve_recaptcha(self, action: str = "pageview") -> bool:
        """
        Giải reCAPTCHA Enterprise để lấy token.

        Args:
            action: Action name cho reCAPTCHA

        Returns:
            True nếu thành công và có token
        """
        solver = self._get_captcha_solver()
        if not solver:
            self._log("No CAPTCHA solver configured")
            return False

        self._log(f"Solving reCAPTCHA Enterprise (action={action})...")

        try:
            result = solver.solve_flow_recaptcha(action=action)
            if result.success and result.token:
                self.recaptcha_token = result.token
                self._log(f"Got reCAPTCHA token: {result.token[:50]}...")
                return True
            else:
                self._log(f"CAPTCHA solve failed: {result.error}")
                return False
        except Exception as e:
            self._log(f"CAPTCHA solve error: {e}")
            return False

    def get_captcha_balance(self) -> float:
        """Kiểm tra số dư tài khoản CAPTCHA service."""
        solver = self._get_captcha_solver()
        if solver:
            return solver.get_balance()
        return 0.0

    def set_recaptcha_token(self, token: str) -> None:
        """Set reCAPTCHA token thủ công (từ browser hoặc nguồn khác)."""
        self.recaptcha_token = token
        self._log(f"Set reCAPTCHA token: {token[:50]}...")

    def _add_recaptcha_header(self, headers: Dict[str, str] = None) -> Dict[str, str]:
        """Thêm reCAPTCHA token vào headers nếu có."""
        headers = headers or {}
        if self.recaptcha_token:
            headers["X-Recaptcha-Token"] = self.recaptcha_token
            headers["X-Recaptcha-Enterprise-Token"] = self.recaptcha_token
        return headers

    # =========================================================================
    # CHROME HEADERS (x-browser-validation)
    # =========================================================================

    def set_chrome_profile(self, profile_path: str) -> None:
        """Set Chrome profile path để extract headers."""
        self.chrome_profile_path = profile_path
        self._log(f"Set Chrome profile: {profile_path}")

    def extract_chrome_headers(self, force: bool = False) -> bool:
        """
        Extract headers từ Chrome (bao gồm x-browser-validation).

        Args:
            force: Force refresh headers

        Returns:
            True nếu thành công
        """
        if self._chrome_headers and not force:
            # Check if headers still valid (< 5 minutes old)
            age = self._chrome_headers.age_seconds() if hasattr(self._chrome_headers, 'age_seconds') else 999999
            if age < 300:
                self._log(f"Using cached Chrome headers (age: {age:.0f}s)")
                return True

        self._log("Extracting headers from Chrome...")

        try:
            from .chrome_headers_extractor import ChromeHeadersExtractor

            extractor = ChromeHeadersExtractor(
                chrome_profile_path=self.chrome_profile_path,
                headless=False,
                verbose=self.verbose
            )

            if not extractor.start_browser():
                self._log("Failed to start Chrome")
                return False

            if not extractor.navigate_to_flow():
                extractor.stop_browser()
                self._log("Failed to navigate to Flow")
                return False

            # Capture headers
            headers = extractor.capture_headers_from_network(timeout=30)
            extractor.stop_browser()

            if headers.is_valid():
                self._chrome_headers = headers
                self._update_session_with_chrome_headers()
                self._log("✅ Chrome headers extracted successfully!")
                return True
            else:
                self._log("❌ Failed to extract valid headers")
                return False

        except ImportError:
            self._log("chrome_headers_extractor module not found")
            return False
        except Exception as e:
            self._log(f"Error extracting headers: {e}")
            return False

    def _update_session_with_chrome_headers(self) -> None:
        """Update session với Chrome headers."""
        if not self._chrome_headers:
            return

        chrome_headers = self._chrome_headers.to_dict()
        self.session.headers.update(chrome_headers)
        self._log(f"Updated session with Chrome headers (x-browser-validation: {chrome_headers.get('x-browser-validation', '')[:30]}...)")

    def has_chrome_headers(self) -> bool:
        """Check if Chrome headers are available."""
        return self._chrome_headers is not None and self._chrome_headers.is_valid()

    # =========================================================================
    # IMAGE GENERATION
    # =========================================================================
    
    def generate_images(
        self,
        prompt: str,
        count: int = 2,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        model: ImageModel = ImageModel.GEM_PIX_2,
        image_inputs: Optional[List[ImageInput]] = None,
        reference_images: Optional[List[GeneratedImage]] = None
    ) -> Tuple[bool, List[GeneratedImage], str]:
        """
        Tạo ảnh từ prompt sử dụng Flow API.

        Args:
            prompt: Text prompt mô tả ảnh
            count: Số lượng ảnh cần tạo (1-4)
            aspect_ratio: Tỷ lệ khung hình
            model: Model tạo ảnh
            image_inputs: List ImageInput objects cho reference images
            reference_images: List GeneratedImage objects để dùng làm reference
                            (sẽ tự động convert sang ImageInput)

        Returns:
            Tuple[success, list_of_images, error_message]
        """
        self._log(f"Generating {count} images with prompt: {prompt[:50]}...")

        # Build imageInputs array từ ImageInput objects hoặc GeneratedImage
        image_inputs_data = []

        # Priority 1: ImageInput objects
        if image_inputs:
            for img_input in image_inputs:
                if isinstance(img_input, ImageInput):
                    image_inputs_data.append(img_input.to_dict())
                elif isinstance(img_input, dict):
                    # Support dict format directly
                    image_inputs_data.append(img_input)

        # Priority 2: Convert GeneratedImage objects to references
        if reference_images:
            for ref_img in reference_images:
                if isinstance(ref_img, GeneratedImage) and ref_img.media_name:
                    ref_input = ref_img.as_reference()
                    if ref_input:
                        image_inputs_data.append(ref_input.to_dict())

        if image_inputs_data:
            self._log(f"Using {len(image_inputs_data)} reference image(s)")
            # Debug: Show actual imageInputs being sent
            for i, inp in enumerate(image_inputs_data):
                name_preview = inp.get("name", "")[:60] if inp.get("name") else "None"
                inp_type = inp.get("imageInputType", "")
                has_b64 = "rawImageBytes" in inp
                self._log(f"  [{i}] name={name_preview} type={inp_type} has_base64={has_b64}")

        # Build requests array
        requests_data = []
        for _ in range(count):
            request_item = {
                "clientContext": {
                    "sessionId": self.session_id,
                    "projectId": self.project_id,
                    "tool": self.TOOL_NAME
                },
                "seed": self._generate_seed(),
                "imageModelName": model.value,
                "imageAspectRatio": aspect_ratio.value,
                "prompt": prompt,
                "imageInputs": image_inputs_data
            }
            requests_data.append(request_item)

        # Build payload với recaptchaToken nếu có
        payload = {
            "clientContext": {
                "sessionId": self.session_id,
                "projectId": self.project_id,
                "tool": self.TOOL_NAME
            },
            "sessionId": self.session_id,
            "requests": requests_data
        }

        # Thêm recaptchaToken nếu có (bắt buộc cho API)
        if hasattr(self, 'recaptcha_token') and self.recaptcha_token:
            payload["recaptchaToken"] = self.recaptcha_token
            self._log(f"Using captured recaptchaToken: {self.recaptcha_token[:50]}...")
        
        # Build URL
        url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"
        
        self._log(f"POST {url}")
        
        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=self.timeout
            )
            
            self._log(f"Response status: {response.status_code}")
            
            if response.status_code == 401:
                return False, [], "Authentication failed - Bearer token may be expired"
            
            if response.status_code == 403:
                self._log(f"403 Response: {response.text[:500]}")
                self._log(f"Request headers: x-browser-validation={self.session.headers.get('x-browser-validation', 'MISSING')[:50]}")
                return False, [], "Access forbidden - check permissions"
            
            if response.status_code != 200:
                return False, [], f"API error: {response.status_code} - {response.text[:200]}"
            
            # Parse response
            result = response.json()

            if self.verbose:
                self._log(f"Response: {json.dumps(result, indent=2)[:500]}")

            # === DEBUG: Log raw response structure ===
            self._log(f"=== RAW RESPONSE KEYS: {list(result.keys())}")
            if "media" in result and result["media"]:
                first_media = result["media"][0]
                self._log(f"=== MEDIA[0] KEYS: {list(first_media.keys())}")
                self._log(f"=== MEDIA[0].name: {first_media.get('name')}")
                self._log(f"=== MEDIA[0].workflowId: {first_media.get('workflowId')}")
                # Check nested structures
                if "image" in first_media:
                    img_wrapper = first_media["image"]
                    self._log(f"=== MEDIA[0].image KEYS: {list(img_wrapper.keys())}")
                    if "generatedImage" in img_wrapper:
                        gen_img = img_wrapper["generatedImage"]
                        self._log(f"=== generatedImage KEYS: {list(gen_img.keys())}")
                        # Check for any name-like fields
                        for k in gen_img.keys():
                            if 'name' in k.lower() or 'media' in k.lower() or 'id' in k.lower():
                                self._log(f"=== generatedImage.{k}: {gen_img.get(k)}")
            
            # Extract images from response
            images = self._parse_image_response(result, prompt, aspect_ratio.value)
            
            if images:
                self._log(f"✓ Generated {len(images)} images successfully")
                return True, images, ""
            else:
                # Check if we need to poll for results
                if self._needs_polling(result):
                    return self._poll_for_results(result, prompt, aspect_ratio.value)
                
                return False, [], "No images in response - check response format"
            
        except requests.exceptions.Timeout:
            return False, [], f"Request timeout after {self.timeout}s"
        except requests.exceptions.RequestException as e:
            return False, [], f"Network error: {str(e)}"
        except json.JSONDecodeError as e:
            return False, [], f"Invalid JSON response: {str(e)}"
        except Exception as e:
            return False, [], f"Unexpected error: {str(e)}"
    
    def _parse_image_response(
        self,
        response: Dict[str, Any],
        prompt: str,
        aspect_ratio: str
    ) -> List[GeneratedImage]:
        """
        Parse response từ API để lấy thông tin ảnh.
        
        Actual Flow API Response Format:
        {
          "media": [
            {
              "image": {
                "generatedImage": {
                  "aspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                  "encodedImage": "iVBORw0KGgo...",  // Base64 PNG
                  "fifeUrl": "https://storage.googleapis.com/...",
                  "mediaGenerationId": "...",
                  "seed": 634312,
                  "prompt": "cute princess pictures",
                  "modelNameType": "GEM_PIX"
                }
              },
              "name": "...",
              "workflowId": "..."
            }
          ],
          "workflows": [...]
        }
        """
        images = []
        
        # =====================================================================
        # PRIMARY FORMAT: Flow API "media" array (ACTUAL FORMAT)
        # =====================================================================
        if "media" in response:
            for media_item in response["media"]:
                # Navigate: media[].image.generatedImage
                image_wrapper = media_item.get("image", {})
                gen_image = image_wrapper.get("generatedImage", {})

                # Extract media name và workflow ID từ media_item level
                # Thu nhieu fields khac nhau vi API co the thay doi
                media_name = (
                    media_item.get("name") or  # Primary field - expected format
                    media_item.get("mediaName") or  # Alternative naming
                    media_item.get("resourceName") or  # GCP style
                    gen_image.get("name") or  # Inside generatedImage
                    gen_image.get("mediaName") or
                    gen_image.get("resourceName")
                )
                workflow_id = media_item.get("workflowId")
                media_generation_id = gen_image.get("mediaGenerationId")

                # Fallback: use workflowId or mediaGenerationId if no name
                if not media_name and workflow_id:
                    media_name = workflow_id
                    self._log(f"  -> Using workflowId as media_name: {workflow_id[:40]}...")
                elif not media_name and media_generation_id:
                    media_name = media_generation_id
                    self._log(f"  -> Using mediaGenerationId as media_name: {media_generation_id[:40]}...")

                if gen_image:
                    img = GeneratedImage(
                        url=gen_image.get("fifeUrl"),  # Direct download URL
                        base64_data=gen_image.get("encodedImage"),  # Base64 PNG
                        media_id=gen_image.get("mediaGenerationId"),
                        media_name=media_name,  # QUAN TRỌNG: name để dùng làm reference
                        workflow_id=workflow_id,
                        seed=gen_image.get("seed"),
                        prompt=gen_image.get("prompt", prompt),
                        aspect_ratio=gen_image.get("aspectRatio", aspect_ratio)
                    )
                    if img.has_data:
                        images.append(img)
                        self._log(f"  ✓ Parsed image: seed={img.seed}, has_url={bool(img.url)}, has_b64={bool(img.base64_data)}, media_name={bool(media_name)}")
        
        # =====================================================================
        # FALLBACK FORMATS (for compatibility)
        # =====================================================================
        
        # Format 2: Direct images array
        if not images and "images" in response:
            for img_data in response["images"]:
                img = GeneratedImage(
                    url=img_data.get("url") or img_data.get("imageUrl") or img_data.get("fifeUrl"),
                    base64_data=img_data.get("base64") or img_data.get("imageBytes") or img_data.get("encodedImage"),
                    media_id=img_data.get("mediaId") or img_data.get("id") or img_data.get("mediaGenerationId"),
                    seed=img_data.get("seed"),
                    prompt=prompt,
                    aspect_ratio=aspect_ratio
                )
                if img.has_data:
                    images.append(img)
        
        # Format 3: Nested in responses array
        if not images and "responses" in response:
            for resp in response["responses"]:
                img_data = resp.get("image", {}).get("generatedImage", resp.get("image", resp))
                img = GeneratedImage(
                    url=img_data.get("url") or img_data.get("fifeUrl"),
                    base64_data=img_data.get("base64") or img_data.get("encodedImage"),
                    media_id=img_data.get("mediaId") or img_data.get("mediaGenerationId"),
                    seed=img_data.get("seed") or resp.get("seed"),
                    prompt=prompt,
                    aspect_ratio=aspect_ratio
                )
                if img.has_data:
                    images.append(img)
        
        # Format 4: Media items (alternative naming)
        if not images and "mediaItems" in response:
            for item in response["mediaItems"]:
                gen_image = item.get("generatedImage", item)
                img = GeneratedImage(
                    url=gen_image.get("url") or gen_image.get("fifeUrl"),
                    base64_data=gen_image.get("base64") or gen_image.get("encodedImage"),
                    media_id=gen_image.get("id") or gen_image.get("mediaGenerationId"),
                    prompt=prompt,
                    aspect_ratio=aspect_ratio
                )
                if img.has_data:
                    images.append(img)
        
        return images
    
    def _needs_polling(self, response: Dict[str, Any]) -> bool:
        """Check if response indicates we need to poll for results."""
        # Common indicators for async processing
        indicators = [
            "operationId" in response,
            "taskId" in response,
            "jobId" in response,
            response.get("status") in ["PENDING", "PROCESSING", "IN_PROGRESS"],
            "done" in response and response["done"] == False,
        ]
        return any(indicators)
    
    def _poll_for_results(
        self,
        initial_response: Dict[str, Any],
        prompt: str,
        aspect_ratio: str,
        max_attempts: int = 30,
        poll_interval: float = 2.0
    ) -> Tuple[bool, List[GeneratedImage], str]:
        """
        Poll API để lấy kết quả khi generation là async.
        """
        self._log("Polling for results...")
        
        # Try to find operation/task ID
        operation_id = (
            initial_response.get("operationId") or
            initial_response.get("taskId") or
            initial_response.get("jobId") or
            initial_response.get("name")
        )
        
        if not operation_id:
            return False, [], "No operation ID found for polling"
        
        # Poll endpoint - adjust based on actual API
        poll_url = f"{self.BASE_URL}/v1/projects/{self.project_id}/media.fetchUserHistoryDirectly"
        
        for attempt in range(max_attempts):
            self._log(f"Poll attempt {attempt + 1}/{max_attempts}")
            time.sleep(poll_interval)
            
            try:
                response = self.session.get(poll_url, timeout=30)
                
                if response.status_code != 200:
                    continue
                
                result = response.json()
                
                # Check if complete
                if result.get("done") == True or result.get("status") == "COMPLETED":
                    images = self._parse_image_response(result, prompt, aspect_ratio)
                    if images:
                        return True, images, ""
                
            except Exception as e:
                self._log(f"Poll error: {e}")
                continue
        
        return False, [], f"Polling timeout after {max_attempts} attempts"
    
    # =========================================================================
    # IMAGE DOWNLOAD
    # =========================================================================
    
    def download_image(
        self,
        image: GeneratedImage,
        output_dir: Path,
        filename: Optional[str] = None
    ) -> Optional[Path]:
        """
        Download ảnh về local.
        
        Flow API cung cấp 2 cách lấy ảnh:
        1. fifeUrl: Direct signed URL từ Google Storage (ưu tiên)
        2. encodedImage: Base64 PNG data
        
        Args:
            image: GeneratedImage object
            output_dir: Thư mục lưu ảnh
            filename: Tên file (không có extension)
            
        Returns:
            Path đến file đã download
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            seed_str = f"_{image.seed}" if image.seed else ""
            filename = f"flow_{timestamp}{seed_str}"
        
        output_path = output_dir / f"{filename}.png"
        
        try:
            # Priority 1: Download from fifeUrl (signed Google Storage URL)
            if image.url:
                self._log(f"Downloading from fifeUrl...")
                
                # Use simple GET request (no auth needed - URL is signed)
                response = requests.get(image.url, timeout=60)
                
                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    image.local_path = output_path
                    self._log(f"✓ Saved to {output_path}")
                    return output_path
                else:
                    self._log(f"URL download failed ({response.status_code}), trying base64...")
            
            # Priority 2: Decode from encodedImage (base64)
            if image.base64_data:
                self._log("Decoding base64 encodedImage...")
                
                # Remove data URL prefix if present
                b64_data = image.base64_data
                if "," in b64_data:
                    b64_data = b64_data.split(",")[1]
                
                # Remove any whitespace/newlines
                b64_data = b64_data.strip().replace("\n", "").replace("\r", "")
                
                img_bytes = base64.b64decode(b64_data)
                
                with open(output_path, "wb") as f:
                    f.write(img_bytes)
                
                image.local_path = output_path
                self._log(f"✓ Saved to {output_path}")
                return output_path
            
            self._log("No URL or base64 data available")
            return None
                
        except Exception as e:
            self._log(f"Download error: {e}")
            return None
    
    def download_all_images(
        self,
        images: List[GeneratedImage],
        output_dir: Path,
        prefix: str = "flow"
    ) -> List[Path]:
        """
        Download tất cả ảnh về local.
        
        Args:
            images: List of GeneratedImage objects
            output_dir: Thư mục lưu ảnh
            prefix: Prefix cho tên file
            
        Returns:
            List of paths to downloaded files
        """
        downloaded = []
        
        for i, img in enumerate(images):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}_{i+1}"
            
            path = self.download_image(img, output_dir, filename)
            if path:
                downloaded.append(path)
        
        return downloaded
    
    # =========================================================================
    # IMAGE UPLOAD (Reference Images)
    # =========================================================================

    def upload_image(
        self,
        image_path: Path,
        image_type: ImageInputType = ImageInputType.REFERENCE,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    ) -> Tuple[bool, Optional[ImageInput], str]:
        """
        Upload ảnh local lên Flow để dùng làm reference.

        Args:
            image_path: Đường dẫn đến file ảnh local
            image_type: Loại input (REFERENCE, STYLE, SUBJECT)
            aspect_ratio: Tỷ lệ khung hình của ảnh

        Returns:
            Tuple[success, ImageInput object, error_message]
        """
        image_path = Path(image_path)

        if not image_path.exists():
            return False, None, f"File not found: {image_path}"

        self._log(f"Uploading image: {image_path.name}...")

        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            # Detect mime type
            suffix = image_path.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif"
            }
            mime_type = mime_types.get(suffix, "image/png")

            # Build upload request - sử dụng ASSET_MANAGER tool
            # Endpoint có thể là flowMedia:uploadImage hoặc media:upload
            url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:uploadImage"

            # Format đúng theo Flow API
            payload = {
                "clientContext": {
                    "sessionId": self.session_id,
                    "tool": "ASSET_MANAGER"  # Upload dùng ASSET_MANAGER, không phải PINHOLE
                },
                "imageInput": {
                    "aspectRatio": aspect_ratio.value,
                    "isUserUploaded": True,
                    "mimeType": mime_type,
                    "rawImageBytes": image_b64
                }
            }

            self._log(f"POST {url}")

            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=self.timeout
            )

            self._log(f"Response status: {response.status_code}")

            if response.status_code == 401:
                return False, None, "Authentication failed - Bearer token may be expired"

            if response.status_code == 403:
                return False, None, "Access forbidden - check permissions"

            if response.status_code not in [200, 201]:
                return False, None, f"Upload failed: {response.status_code} - {response.text[:200]}"

            # Parse response to get media name
            result = response.json()

            if self.verbose:
                self._log(f"Upload response: {json.dumps(result, indent=2)[:500]}")

            # Extract name from response - thử nhiều format khác nhau
            media_name = None

            # Format 1: Direct name field
            if "name" in result:
                media_name = result["name"]
            # Format 2: media array
            elif "media" in result:
                media = result["media"]
                if isinstance(media, list) and len(media) > 0:
                    media_name = media[0].get("name")
                elif isinstance(media, dict):
                    media_name = media.get("name")
            # Format 3: imageInput response
            elif "imageInput" in result:
                img_input = result["imageInput"]
                media_name = img_input.get("name") or img_input.get("mediaName")
            # Format 4: mediaName field
            elif "mediaName" in result:
                media_name = result["mediaName"]

            if media_name:
                self._log(f"✓ Upload successful, media_name: {media_name[:50]}...")
                return True, ImageInput(name=media_name, input_type=image_type), ""
            else:
                # Log full response for debugging
                self._log(f"Response without media_name: {json.dumps(result)[:300]}")
                return False, None, "Upload succeeded but no media name in response"

        except requests.exceptions.Timeout:
            return False, None, f"Upload timeout after {self.timeout}s"
        except requests.exceptions.RequestException as e:
            return False, None, f"Network error: {str(e)}"
        except Exception as e:
            return False, None, f"Upload error: {str(e)}"

    def upload_images(
        self,
        image_paths: List[Path],
        image_type: ImageInputType = ImageInputType.REFERENCE
    ) -> Tuple[List[ImageInput], List[str]]:
        """
        Upload nhiều ảnh cùng lúc.

        Args:
            image_paths: List đường dẫn ảnh
            image_type: Loại input

        Returns:
            Tuple[list of ImageInput, list of errors]
        """
        uploaded = []
        errors = []

        for path in image_paths:
            success, img_input, error = self.upload_image(path, image_type)
            if success and img_input:
                uploaded.append(img_input)
            else:
                errors.append(f"{path.name}: {error}")

        return uploaded, errors

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def generate_and_download(
        self,
        prompt: str,
        output_dir: Path,
        count: int = 2,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        prefix: str = "flow",
        reference_images: Optional[List[GeneratedImage]] = None,
        image_inputs: Optional[List[ImageInput]] = None
    ) -> Tuple[bool, List[Path], str]:
        """
        Tạo ảnh và download về local trong một lần gọi.

        Args:
            prompt: Text prompt
            output_dir: Thư mục lưu ảnh
            count: Số lượng ảnh
            aspect_ratio: Tỷ lệ khung hình
            prefix: Prefix cho tên file
            reference_images: List GeneratedImage objects để dùng làm reference
            image_inputs: List ImageInput objects cho reference (KHÔNG phải base64!)

        Returns:
            Tuple[success, list_of_paths, error_message]
        """
        # Generate with reference images
        success, images, error = self.generate_images(
            prompt=prompt,
            count=count,
            aspect_ratio=aspect_ratio,
            reference_images=reference_images,
            image_inputs=image_inputs
        )

        if not success:
            return False, [], error

        # Download
        paths = self.download_all_images(images, output_dir, prefix)

        if not paths:
            return False, [], "Generation succeeded but download failed"

        return True, paths, ""

    def generate_with_references(
        self,
        prompt: str,
        reference_image_paths: List[Path],
        output_dir: Path,
        count: int = 1,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        prefix: str = "flow"
    ) -> Tuple[bool, List[Path], str]:
        """
        Tạo ảnh với reference images từ file local.

        Workflow:
        1. Upload các ảnh reference
        2. Generate ảnh mới với references
        3. Download kết quả

        Args:
            prompt: Text prompt
            reference_image_paths: List đường dẫn ảnh reference
            output_dir: Thư mục lưu ảnh
            count: Số lượng ảnh
            aspect_ratio: Tỷ lệ khung hình
            prefix: Prefix cho tên file

        Returns:
            Tuple[success, list_of_paths, error_message]
        """
        self._log(f"Generate with {len(reference_image_paths)} reference images...")

        # Step 1: Upload reference images
        uploaded_refs, upload_errors = self.upload_images(reference_image_paths)

        if upload_errors:
            for err in upload_errors:
                self._log(f"Upload error: {err}")

        if not uploaded_refs:
            return False, [], "Failed to upload any reference images"

        self._log(f"Uploaded {len(uploaded_refs)} reference images")

        # Step 2: Generate with references
        return self.generate_and_download(
            prompt=prompt,
            output_dir=output_dir,
            count=count,
            aspect_ratio=aspect_ratio,
            prefix=prefix,
            image_inputs=uploaded_refs
        )
    
    # =========================================================================
    # TOKEN MANAGEMENT
    # =========================================================================
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test API connection với bearer token hiện tại.
        
        Returns:
            Tuple[success, message]
        """
        self._log("Testing API connection...")
        
        try:
            # Simple test: try to generate a minimal image
            success, images, error = self.generate_images(
                prompt="test",
                count=1,
                aspect_ratio=AspectRatio.SQUARE
            )
            
            if success:
                return True, "Connection successful - API is working"
            else:
                return False, f"Connection test failed: {error}"
                
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    def update_token(self, new_token: str) -> None:
        """
        Cập nhật Bearer token mới.
        
        Args:
            new_token: Bearer token mới
        """
        self.bearer_token = new_token.strip()
        self.session.headers["Authorization"] = f"Bearer {self.bearer_token}"
        self._log("Bearer token updated")
    
    @staticmethod
    def get_token_guide() -> str:
        """Hướng dẫn lấy Bearer Token."""
        return """
╔══════════════════════════════════════════════════════════════════════════════╗
║               HƯỚNG DẪN LẤY BEARER TOKEN TỪ GOOGLE FLOW                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. Mở trình duyệt (Chrome/Edge) và truy cập:                               ║
║     https://labs.google/fx/vi/tools/flow                                     ║
║                                                                              ║
║  2. Đăng nhập Google account nếu cần                                        ║
║                                                                              ║
║  3. Mở DevTools:                                                            ║
║     - Windows/Linux: F12 hoặc Ctrl + Shift + I                              ║
║     - Mac: Cmd + Option + I                                                  ║
║                                                                              ║
║  4. Chọn tab "Network"                                                      ║
║                                                                              ║
║  5. Thực hiện tạo một ảnh bất kỳ trên trang Flow                           ║
║                                                                              ║
║  6. Trong Network tab, tìm request "flowMedia:batchGenerateImages"         ║
║                                                                              ║
║  7. Click vào request đó, chọn tab "Headers"                                ║
║                                                                              ║
║  8. Tìm dòng "authorization" trong Request Headers                          ║
║     Giá trị sẽ có dạng: Bearer ya29.a0Aa7pCA_VG7SzW...                      ║
║                                                                              ║
║  9. Copy TOÀN BỘ giá trị sau "Bearer " (bắt đầu bằng "ya29.")               ║
║                                                                              ║
║  ⚠️  LƯU Ý QUAN TRỌNG:                                                      ║
║     - Token có thời hạn ngắn (~1 giờ), cần refresh thường xuyên            ║
║     - Mỗi lần refresh trang hoặc tạo ảnh mới sẽ có token mới               ║
║     - Không chia sẻ token với người khác                                    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_flow_client(
    token: str,
    project_id: Optional[str] = None,
    verbose: bool = False
) -> GoogleFlowAPI:
    """
    Factory function để tạo GoogleFlowAPI client.
    
    Args:
        token: Bearer token
        project_id: Project ID (optional)
        verbose: Enable verbose logging
        
    Returns:
        GoogleFlowAPI instance
    """
    return GoogleFlowAPI(
        bearer_token=token,
        project_id=project_id,
        verbose=verbose
    )


def quick_generate(
    prompt: str,
    token: str,
    output_dir: str = "./output",
    count: int = 2,
    aspect_ratio: str = "landscape"
) -> List[str]:
    """
    Quick function để tạo ảnh với minimal setup.
    
    Args:
        prompt: Text prompt
        token: Bearer token
        output_dir: Output directory
        count: Number of images
        aspect_ratio: "landscape", "portrait", or "square"
        
    Returns:
        List of output file paths
    """
    # Map aspect ratio string
    ar_map = {
        "landscape": AspectRatio.LANDSCAPE,
        "portrait": AspectRatio.PORTRAIT,
        "square": AspectRatio.SQUARE,
        "16:9": AspectRatio.LANDSCAPE,
        "9:16": AspectRatio.PORTRAIT,
        "1:1": AspectRatio.SQUARE,
    }
    ar = ar_map.get(aspect_ratio.lower(), AspectRatio.LANDSCAPE)
    
    client = GoogleFlowAPI(bearer_token=token, verbose=True)
    success, paths, error = client.generate_and_download(
        prompt=prompt,
        output_dir=Path(output_dir),
        count=count,
        aspect_ratio=ar
    )
    
    if success:
        return [str(p) for p in paths]
    else:
        print(f"❌ Error: {error}")
        return []


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys
    
    print(GoogleFlowAPI.get_token_guide())
    
    if len(sys.argv) < 3:
        print("\nUsage: python google_flow_api.py <token> <prompt>")
        print("Example: python google_flow_api.py 'ya29.xxx' 'a cute cat'")
        sys.exit(1)
    
    token = sys.argv[1]
    prompt = sys.argv[2]
    
    print(f"\n🎨 Generating images for: {prompt}")
    paths = quick_generate(prompt, token)
    
    if paths:
        print(f"\n✅ Generated {len(paths)} images:")
        for p in paths:
            print(f"   📁 {p}")
    else:
        print("\n❌ Generation failed")
