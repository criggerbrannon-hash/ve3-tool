"""
VE3 Tool - Google Video API Module
==================================
Tạo video từ ảnh + prompt sử dụng Google Labs Video API.

API Endpoint: aisandbox-pa.googleapis.com
Flow:
1. Upload ảnh hoặc dùng ảnh đã có
2. Gửi prompt + ảnh để tạo video
3. Poll status cho đến khi hoàn thành
4. Download video
"""

import json
import time
import base64
import uuid
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class VideoAspectRatio(Enum):
    """Tỷ lệ khung hình cho video."""
    LANDSCAPE = "VIDEO_ASPECT_RATIO_LANDSCAPE"    # 16:9
    PORTRAIT = "VIDEO_ASPECT_RATIO_PORTRAIT"      # 9:16
    SQUARE = "VIDEO_ASPECT_RATIO_SQUARE"          # 1:1


class VideoDuration(Enum):
    """Thời lượng video."""
    SHORT = "VIDEO_DURATION_SHORT"    # ~4 giây
    LONG = "VIDEO_DURATION_LONG"      # ~8 giây


@dataclass
class GeneratedVideo:
    """Kết quả video được tạo."""
    video_id: Optional[str] = None
    url: Optional[str] = None
    base64_data: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, failed
    prompt: str = ""
    source_image: str = ""
    local_path: Optional[Path] = None
    error: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        return self.status == "completed" and (self.url or self.base64_data)


class GoogleVideoAPI:
    """
    Client để tương tác với Google Video API (Labs).

    Sử dụng Bearer Token authentication từ browser session.
    """

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(
        self,
        bearer_token: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout: int = 120,
        verbose: bool = True
    ):
        """
        Khởi tạo Google Video API client.

        Args:
            bearer_token: OAuth Bearer token (bắt đầu bằng "ya29.")
            project_id: Project ID (nếu không có sẽ tự tạo UUID)
            session_id: Session ID (nếu không có sẽ tự tạo)
            timeout: Request timeout in seconds
            verbose: Print debug info
        """
        self.bearer_token = bearer_token.strip()
        self.project_id = project_id or str(uuid.uuid4())
        self.session_id = session_id or f";{int(time.time() * 1000)}"
        self.timeout = timeout
        self.verbose = verbose

        # Validate token format
        if not self.bearer_token.startswith("ya29."):
            self._log("⚠️  Warning: Bearer token should start with 'ya29.'")

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
            print(f"[{timestamp}] [VideoAPI] {message}")

    # =========================================================================
    # IMAGE UPLOAD
    # =========================================================================

    def upload_image(self, image_path: Path) -> Tuple[bool, Optional[str], str]:
        """
        Upload ảnh lên Google để dùng làm source cho video.

        Args:
            image_path: Path đến file ảnh

        Returns:
            Tuple[success, media_id, error_message]
        """
        if not image_path.exists():
            return False, None, f"Image not found: {image_path}"

        self._log(f"Uploading image: {image_path.name}...")

        try:
            # Đọc và encode ảnh
            with open(image_path, "rb") as f:
                image_data = f.read()

            base64_image = base64.b64encode(image_data).decode("utf-8")

            # Xác định mime type
            suffix = image_path.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp"
            }
            mime_type = mime_types.get(suffix, "image/png")

            # Build payload
            payload = {
                "image": {
                    "imageBytes": base64_image,
                    "mimeType": mime_type
                },
                "clientContext": {
                    "sessionId": self.session_id,
                    "projectId": self.project_id,
                    "tool": "FLOW"
                }
            }

            # Upload endpoint (có thể cần điều chỉnh)
            url = f"{self.BASE_URL}/v1/projects/{self.project_id}/media:upload"

            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                media_id = result.get("mediaId") or result.get("id")
                if media_id:
                    self._log(f"✓ Image uploaded: {media_id}")
                    return True, media_id, ""
                return False, None, "No media ID in response"
            else:
                return False, None, f"Upload failed: {response.status_code}"

        except Exception as e:
            return False, None, f"Upload error: {str(e)}"

    def image_to_base64(self, image_path: Path) -> Optional[str]:
        """Convert ảnh sang base64."""
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            self._log(f"Error reading image: {e}")
            return None

    # =========================================================================
    # VIDEO GENERATION
    # =========================================================================

    def generate_video(
        self,
        prompt: str,
        image_path: Optional[Path] = None,
        image_base64: Optional[str] = None,
        aspect_ratio: VideoAspectRatio = VideoAspectRatio.LANDSCAPE,
        duration: VideoDuration = VideoDuration.SHORT
    ) -> Tuple[bool, Optional[str], str]:
        """
        Bắt đầu tạo video từ prompt và ảnh.

        Args:
            prompt: Text prompt mô tả chuyển động video
            image_path: Path đến ảnh nguồn
            image_base64: Base64 encoded image (nếu không có image_path)
            aspect_ratio: Tỷ lệ khung hình
            duration: Thời lượng video

        Returns:
            Tuple[success, operation_id, error_message]
        """
        self._log(f"Generating video with prompt: {prompt[:50]}...")

        # Prepare image
        if image_path:
            image_b64 = self.image_to_base64(image_path)
            if not image_b64:
                return False, None, "Cannot read image"
        elif image_base64:
            image_b64 = image_base64
        else:
            return False, None, "No image provided"

        # Build request payload
        # Note: Cấu trúc này có thể cần điều chỉnh theo API thực tế
        payload = {
            "requests": [{
                "clientContext": {
                    "sessionId": self.session_id,
                    "projectId": self.project_id,
                    "tool": "FLOW"
                },
                "prompt": prompt,
                "imageInputs": [{
                    "encodedImage": image_b64
                }],
                "videoAspectRatio": aspect_ratio.value,
                "videoDuration": duration.value
            }]
        }

        # Generate endpoint
        url = f"{self.BASE_URL}/v1/projects/{self.project_id}/flowMedia:batchGenerateVideos"

        self._log(f"POST {url}")

        try:
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

            if response.status_code not in [200, 202]:
                return False, None, f"API error: {response.status_code} - {response.text[:200]}"

            result = response.json()

            if self.verbose:
                self._log(f"Response: {json.dumps(result, indent=2)[:500]}")

            # Extract operation ID for polling
            operation_id = (
                result.get("operationId") or
                result.get("name") or
                result.get("taskId") or
                result.get("jobId")
            )

            if operation_id:
                self._log(f"✓ Video generation started: {operation_id}")
                return True, operation_id, ""

            # Có thể video đã sẵn sàng ngay
            if "media" in result or "videos" in result:
                return True, "immediate", ""

            return False, None, "No operation ID in response"

        except requests.exceptions.Timeout:
            return False, None, f"Request timeout after {self.timeout}s"
        except requests.exceptions.RequestException as e:
            return False, None, f"Network error: {str(e)}"
        except Exception as e:
            return False, None, f"Unexpected error: {str(e)}"

    # =========================================================================
    # STATUS POLLING
    # =========================================================================

    def check_video_status(
        self,
        operation_id: str
    ) -> Tuple[str, Optional[GeneratedVideo], str]:
        """
        Kiểm tra trạng thái video generation.

        Args:
            operation_id: ID từ generate_video

        Returns:
            Tuple[status, video_result, error_message]
            status: "pending", "processing", "completed", "failed"
        """
        # Endpoint để check status
        url = f"{self.BASE_URL}/v1/video:batchCheckAsyncVideoGenerationStatus"

        payload = {
            "operationIds": [operation_id],
            "clientContext": {
                "sessionId": self.session_id,
                "projectId": self.project_id
            }
        }

        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=60
            )

            if response.status_code != 200:
                return "failed", None, f"Status check failed: {response.status_code}"

            result = response.json()

            # Parse status từ response
            # Cấu trúc có thể khác - cần điều chỉnh
            status = result.get("status", "").lower()

            if status in ["completed", "done", "success"]:
                video = self._parse_video_result(result)
                if video:
                    return "completed", video, ""
                return "completed", None, "Video ready but cannot parse"

            elif status in ["pending", "queued"]:
                return "pending", None, ""

            elif status in ["processing", "running", "in_progress"]:
                return "processing", None, ""

            elif status in ["failed", "error"]:
                error_msg = result.get("error", {}).get("message", "Unknown error")
                return "failed", None, error_msg

            # Check for results directly
            if "videos" in result or "media" in result:
                video = self._parse_video_result(result)
                if video:
                    return "completed", video, ""

            return "processing", None, ""

        except Exception as e:
            return "failed", None, f"Status check error: {str(e)}"

    def _parse_video_result(self, response: Dict[str, Any]) -> Optional[GeneratedVideo]:
        """Parse video từ API response."""
        try:
            # Try different response formats
            video_data = None

            # Format 1: media array
            if "media" in response:
                for media in response["media"]:
                    if "video" in media:
                        video_data = media["video"]
                        break

            # Format 2: videos array
            elif "videos" in response:
                if response["videos"]:
                    video_data = response["videos"][0]

            # Format 3: direct video object
            elif "video" in response:
                video_data = response["video"]

            if not video_data:
                return None

            return GeneratedVideo(
                video_id=video_data.get("id") or video_data.get("mediaId"),
                url=video_data.get("url") or video_data.get("videoUrl") or video_data.get("fifeUrl"),
                base64_data=video_data.get("encodedVideo") or video_data.get("videoBytes"),
                status="completed"
            )

        except Exception as e:
            self._log(f"Parse error: {e}")
            return None

    # =========================================================================
    # WAIT FOR COMPLETION
    # =========================================================================

    def wait_for_video(
        self,
        operation_id: str,
        max_wait: int = 300,  # 5 phút
        poll_interval: float = 5.0
    ) -> Tuple[bool, Optional[GeneratedVideo], str]:
        """
        Chờ video hoàn thành.

        Args:
            operation_id: ID từ generate_video
            max_wait: Thời gian chờ tối đa (giây)
            poll_interval: Khoảng cách giữa các lần check (giây)

        Returns:
            Tuple[success, video, error_message]
        """
        self._log(f"Waiting for video (max {max_wait}s)...")

        start_time = time.time()
        last_status = ""

        while time.time() - start_time < max_wait:
            status, video, error = self.check_video_status(operation_id)

            if status != last_status:
                self._log(f"Status: {status}")
                last_status = status

            if status == "completed":
                if video:
                    self._log("✓ Video generation completed!")
                    return True, video, ""
                else:
                    return False, None, "Completed but no video data"

            elif status == "failed":
                return False, None, error or "Video generation failed"

            time.sleep(poll_interval)

        return False, None, f"Timeout after {max_wait}s"

    # =========================================================================
    # VIDEO DOWNLOAD
    # =========================================================================

    def download_video(
        self,
        video: GeneratedVideo,
        output_dir: Path,
        filename: Optional[str] = None
    ) -> Optional[Path]:
        """
        Download video về local.

        Args:
            video: GeneratedVideo object
            output_dir: Thư mục lưu video
            filename: Tên file (không có extension)

        Returns:
            Path đến file đã download
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"video_{timestamp}"

        output_path = output_dir / f"{filename}.mp4"

        try:
            # Priority 1: Download from URL
            if video.url:
                self._log(f"Downloading from URL...")
                response = requests.get(video.url, timeout=120)

                if response.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(response.content)
                    video.local_path = output_path
                    self._log(f"✓ Saved to {output_path}")
                    return output_path

            # Priority 2: Decode from base64
            if video.base64_data:
                self._log("Decoding base64 video...")
                video_bytes = base64.b64decode(video.base64_data)

                with open(output_path, "wb") as f:
                    f.write(video_bytes)

                video.local_path = output_path
                self._log(f"✓ Saved to {output_path}")
                return output_path

            self._log("No URL or base64 data available")
            return None

        except Exception as e:
            self._log(f"Download error: {e}")
            return None

    # =========================================================================
    # CONVENIENCE METHOD
    # =========================================================================

    def generate_and_download(
        self,
        prompt: str,
        image_path: Path,
        output_dir: Path,
        filename: Optional[str] = None,
        aspect_ratio: VideoAspectRatio = VideoAspectRatio.LANDSCAPE,
        duration: VideoDuration = VideoDuration.SHORT,
        max_wait: int = 300
    ) -> Tuple[bool, Optional[Path], str]:
        """
        Tạo video và download trong một lần gọi.

        Args:
            prompt: Text prompt
            image_path: Path đến ảnh nguồn
            output_dir: Thư mục lưu video
            filename: Tên file output
            aspect_ratio: Tỷ lệ khung hình
            duration: Thời lượng
            max_wait: Thời gian chờ tối đa

        Returns:
            Tuple[success, video_path, error_message]
        """
        # Step 1: Generate
        success, operation_id, error = self.generate_video(
            prompt=prompt,
            image_path=image_path,
            aspect_ratio=aspect_ratio,
            duration=duration
        )

        if not success:
            return False, None, error

        # Step 2: Wait
        success, video, error = self.wait_for_video(
            operation_id=operation_id,
            max_wait=max_wait
        )

        if not success:
            return False, None, error

        # Step 3: Download
        video_path = self.download_video(video, output_dir, filename)

        if video_path:
            return True, video_path, ""
        else:
            return False, None, "Download failed"

    # =========================================================================
    # TOKEN MANAGEMENT
    # =========================================================================

    def test_connection(self) -> Tuple[bool, str]:
        """Test API connection."""
        self._log("Testing API connection...")

        try:
            # Simple status check
            url = f"{self.BASE_URL}/v1/video:batchCheckAsyncVideoGenerationStatus"
            payload = {
                "operationIds": ["test"],
                "clientContext": {
                    "sessionId": self.session_id,
                    "projectId": self.project_id
                }
            }

            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=30
            )

            # 401 = token invalid, 404/400 = endpoint ok but no operation
            if response.status_code == 401:
                return False, "Authentication failed - token expired"
            elif response.status_code in [200, 400, 404]:
                return True, "Connection OK - API is accessible"
            else:
                return False, f"Unexpected status: {response.status_code}"

        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def update_token(self, new_token: str) -> None:
        """Cập nhật Bearer token mới."""
        self.bearer_token = new_token.strip()
        self.session.headers["Authorization"] = f"Bearer {self.bearer_token}"
        self._log("Bearer token updated")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_video_client(
    token: str,
    project_id: Optional[str] = None,
    verbose: bool = True
) -> GoogleVideoAPI:
    """Factory function để tạo GoogleVideoAPI client."""
    return GoogleVideoAPI(
        bearer_token=token,
        project_id=project_id,
        verbose=verbose
    )


def quick_generate_video(
    prompt: str,
    image_path: str,
    token: str,
    output_dir: str = "./output"
) -> Optional[str]:
    """
    Quick function để tạo video với minimal setup.

    Args:
        prompt: Text prompt
        image_path: Path đến ảnh nguồn
        token: Bearer token
        output_dir: Output directory

    Returns:
        Path đến video hoặc None
    """
    client = GoogleVideoAPI(bearer_token=token, verbose=True)

    success, video_path, error = client.generate_and_download(
        prompt=prompt,
        image_path=Path(image_path),
        output_dir=Path(output_dir)
    )

    if success:
        return str(video_path)
    else:
        print(f"❌ Error: {error}")
        return None


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║               GOOGLE VIDEO API - TEST TOOL                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Usage:                                                                      ║
║    python google_video_api.py <token> <image_path> <prompt>                  ║
║                                                                              ║
║  Example:                                                                    ║
║    python google_video_api.py 'ya29.xxx' './nv/nvc.png' 'gentle wind blow'   ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    if len(sys.argv) < 4:
        print("Missing arguments!")
        print("Usage: python google_video_api.py <token> <image_path> <prompt>")
        sys.exit(1)

    token = sys.argv[1]
    image_path = sys.argv[2]
    prompt = sys.argv[3]

    print(f"\n🎬 Generating video...")
    print(f"   Image: {image_path}")
    print(f"   Prompt: {prompt}")

    result = quick_generate_video(
        prompt=prompt,
        image_path=image_path,
        token=token,
        output_dir="./output"
    )

    if result:
        print(f"\n✅ Video saved: {result}")
    else:
        print("\n❌ Video generation failed")
