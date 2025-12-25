"""
VE3 Tool - Image to Video Converter
====================================
Chuyển đổi ảnh sang video sử dụng Google Veo 3 API.

Flow:
1. Đọc ảnh từ thư mục img/
2. Upload ảnh lên Google Flow để lấy mediaId
3. Tạo video từ ảnh (I2V) qua API
4. Download video và thay thế ảnh gốc
"""

import os
import time
import json
import shutil
import requests
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass
import base64


@dataclass
class VideoConversionResult:
    """Kết quả chuyển đổi ảnh sang video."""
    image_path: Path
    video_path: Optional[Path] = None
    video_url: Optional[str] = None
    media_id: Optional[str] = None
    status: str = "pending"  # pending, uploading, generating, downloading, completed, failed
    error: Optional[str] = None
    prompt: str = ""

    @property
    def is_completed(self) -> bool:
        return self.status == "completed" and self.video_path and self.video_path.exists()

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"


class ImageToVideoConverter:
    """
    Chuyển đổi ảnh sang video sử dụng Google Veo 3 API.

    Hỗ trợ:
    - Direct API (cần bearer token)
    - Proxy API (nanoai.pics - bypass captcha)
    """

    GOOGLE_BASE = "https://aisandbox-pa.googleapis.com"
    PROXY_BASE = "https://flow-api.nanoai.pics/api/fix"

    # Video models
    I2V_MODEL_FAST = "veo_3_0_r2v_fast_ultra"
    I2V_MODEL_QUALITY = "veo_3_0_r2v"

    def __init__(
        self,
        project_path: str,
        bearer_token: str,
        project_id: str,
        proxy_token: Optional[str] = None,
        use_proxy: bool = True,
        video_model: str = None,
        log_callback: Optional[Callable] = None
    ):
        """
        Khởi tạo converter.

        Args:
            project_path: Đường dẫn thư mục project
            bearer_token: Google Flow bearer token (ya29.xxx)
            project_id: Google Flow project ID
            proxy_token: Token cho proxy API (nanoai.pics)
            use_proxy: Sử dụng proxy để bypass captcha
            video_model: Model video (fast/quality)
            log_callback: Function để log
        """
        self.project_path = Path(project_path)
        self.bearer_token = bearer_token
        self.project_id = project_id
        self.proxy_token = proxy_token
        self.use_proxy = use_proxy and bool(proxy_token)
        self.video_model = video_model or self.I2V_MODEL_FAST
        self.log_callback = log_callback

        # Thư mục
        self.img_dir = self.project_path / "img"
        self.video_dir = self.project_path / "video"
        self.backup_dir = self.project_path / "img_backup"

    def _log(self, message: str, level: str = "info"):
        """Log message."""
        if self.log_callback:
            self.log_callback(message, level)
        else:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [{level.upper()}] {message}")

    def _google_headers(self) -> Dict[str, str]:
        """Headers cho Google API."""
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json"
        }

    def _proxy_headers(self) -> Dict[str, str]:
        """Headers cho Proxy API."""
        return {
            "Authorization": f"Bearer {self.proxy_token}",
            "Content-Type": "application/json"
        }

    def get_images_to_convert(self, count: int = None, full: bool = False) -> List[Path]:
        """
        Lấy danh sách ảnh cần chuyển sang video.

        Args:
            count: Số lượng ảnh (None = tất cả)
            full: True = tất cả ảnh

        Returns:
            Danh sách đường dẫn ảnh
        """
        if not self.img_dir.exists():
            self._log(f"Thư mục img không tồn tại: {self.img_dir}", "error")
            return []

        # Lấy tất cả ảnh (png, jpg, jpeg, webp)
        images = []
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
            images.extend(self.img_dir.glob(ext))

        # Sắp xếp theo tên (scene_1, scene_2, ...)
        images = sorted(images, key=lambda p: p.stem)

        if full or count is None:
            return images

        return images[:count]

    def upload_image_for_media_id(self, image_path: Path) -> Optional[str]:
        """
        Upload ảnh lên Google Flow để lấy mediaId.

        Args:
            image_path: Đường dẫn ảnh

        Returns:
            mediaId hoặc None nếu lỗi
        """
        self._log(f"Uploading image: {image_path.name}")

        # Đọc ảnh và encode base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        # Xác định mime type
        ext = image_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp"
        }
        mime_type = mime_types.get(ext, "image/png")

        session_id = f";{int(time.time() * 1000)}"

        # Tạo request để upload ảnh
        body_json = {
            "clientContext": {
                "sessionId": session_id,
                "projectId": self.project_id,
                "tool": "PINHOLE"
            },
            "requests": [{
                "clientContext": {
                    "sessionId": session_id,
                    "projectId": self.project_id,
                    "tool": "PINHOLE"
                },
                "seed": int(time.time()) % 100000,
                "imageModelName": "GEM_PIX_2",
                "imageAspectRatio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "prompt": f"Reference image from {image_path.name}",
                "imageInputs": [{
                    "inputType": "IMAGE_INPUT_TYPE_REFERENCE",
                    "image": {
                        "bytesBase64Encoded": image_data,
                        "mimeType": mime_type
                    }
                }]
            }]
        }

        try:
            if self.use_proxy:
                return self._upload_via_proxy(body_json)
            else:
                return self._upload_direct(body_json)
        except Exception as e:
            self._log(f"Upload error: {e}", "error")
            return None

    def _upload_direct(self, body_json: Dict) -> Optional[str]:
        """Upload trực tiếp qua Google API."""
        url = f"{self.GOOGLE_BASE}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"

        response = requests.post(
            url,
            headers=self._google_headers(),
            json=body_json,
            timeout=60
        )

        if response.status_code != 200:
            self._log(f"Upload failed: {response.status_code} - {response.text[:200]}", "error")
            return None

        result = response.json()
        media = result.get("media", [])
        if media:
            return media[0].get("name")

        return None

    def _upload_via_proxy(self, body_json: Dict) -> Optional[str]:
        """Upload qua proxy API."""
        payload = {
            "body_json": body_json,
            "flow_auth_token": self.bearer_token,
            "flow_url": f"{self.GOOGLE_BASE}/v1/projects/{self.project_id}/flowMedia:batchGenerateImages"
        }

        response = requests.post(
            f"{self.PROXY_BASE}/create-image-veo3",
            headers=self._proxy_headers(),
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            self._log(f"Proxy upload failed: {response.status_code}", "error")
            return None

        task_id = response.json().get("taskId")
        if not task_id:
            return None

        # Poll for result
        for _ in range(60):
            status_resp = requests.get(
                f"{self.PROXY_BASE}/task-status?taskId={task_id}",
                headers=self._proxy_headers(),
                timeout=30
            )

            if status_resp.status_code == 200:
                result = status_resp.json().get("result", {})
                media = result.get("media", [])
                if media:
                    return media[0].get("name")

            time.sleep(2)

        return None

    def create_video_from_image(
        self,
        media_id: str,
        prompt: str = "",
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    ) -> Tuple[Optional[str], Optional[List[Dict]]]:
        """
        Tạo video từ ảnh đã upload.

        Args:
            media_id: Media ID của ảnh
            prompt: Prompt mô tả chuyển động
            aspect_ratio: Tỷ lệ video

        Returns:
            Tuple[video_url, operations] hoặc (None, None) nếu lỗi
        """
        self._log(f"Creating video from media: {media_id[:50]}...")

        session_id = f";{int(time.time() * 1000)}"
        scene_id = f"scene-{int(time.time())}"

        # Default prompt nếu không có
        if not prompt:
            prompt = "Subtle motion, cinematic, slow movement"

        body_json = {
            "clientContext": {
                "projectId": self.project_id,
                "recaptchaToken": "",
                "sessionId": session_id,
                "tool": "PINHOLE",
                "userPaygateTier": "PAYGATE_TIER_TWO"
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "metadata": {"sceneId": scene_id},
                "referenceImages": [{
                    "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                    "mediaId": media_id
                }],
                "seed": int(time.time()) % 100000,
                "textInput": {"prompt": prompt},
                "videoModelKey": self.video_model
            }]
        }

        try:
            if self.use_proxy:
                return self._create_video_via_proxy(body_json)
            else:
                return self._create_video_direct(body_json)
        except Exception as e:
            self._log(f"Create video error: {e}", "error")
            return None, None

    def _create_video_direct(self, body_json: Dict) -> Tuple[Optional[str], Optional[List[Dict]]]:
        """Tạo video trực tiếp qua Google API."""
        url = f"{self.GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"

        response = requests.post(
            url,
            headers=self._google_headers(),
            json=body_json,
            timeout=60
        )

        if response.status_code != 200:
            self._log(f"Create video failed: {response.status_code}", "error")
            return None, None

        result = response.json()
        operations = result.get("operations", [])

        if operations:
            return None, operations  # Cần poll để lấy video URL

        return None, None

    def _create_video_via_proxy(self, body_json: Dict) -> Tuple[Optional[str], Optional[List[Dict]]]:
        """Tạo video qua proxy API."""
        payload = {
            "body_json": body_json,
            "flow_auth_token": self.bearer_token,
            "flow_url": f"{self.GOOGLE_BASE}/v1/video:batchAsyncGenerateVideoReferenceImages"
        }

        response = requests.post(
            f"{self.PROXY_BASE}/create-video-veo3",
            headers=self._proxy_headers(),
            json=payload,
            timeout=60
        )

        if response.status_code != 200:
            self._log(f"Proxy create video failed: {response.status_code}", "error")
            return None, None

        task_id = response.json().get("taskId")
        if not task_id:
            return None, None

        # Poll proxy để lấy operations
        for _ in range(30):
            status_resp = requests.get(
                f"{self.PROXY_BASE}/task-status?taskId={task_id}",
                headers=self._proxy_headers(),
                timeout=30
            )

            if status_resp.status_code == 200:
                result = status_resp.json().get("result", {})
                operations = result.get("operations", [])
                if operations:
                    return None, operations

            time.sleep(3)

        return None, None

    def poll_video_status(self, operations: List[Dict], timeout: int = 180) -> Optional[str]:
        """
        Poll Google API để lấy video URL.

        Args:
            operations: Operations array từ create video
            timeout: Timeout (giây)

        Returns:
            Video URL hoặc None
        """
        self._log("Polling video status...")

        url = f"{self.GOOGLE_BASE}/v1/video:batchCheckAsyncVideoGenerationStatus"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = requests.post(
                    url,
                    headers=self._google_headers(),
                    json={"operations": operations},
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    ops = result.get("operations", [])

                    if ops:
                        op = ops[0]
                        status = op.get("status", "")

                        if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                            video_url = op.get("operation", {}).get("metadata", {}).get("video", {}).get("fifeUrl")
                            if video_url:
                                self._log("Video generation completed!")
                                return video_url

                        elif "ERROR" in status or "FAILED" in status:
                            self._log(f"Video generation failed: {status}", "error")
                            return None

                        else:
                            # Still processing
                            elapsed = int(time.time() - start_time)
                            self._log(f"Video generating... ({elapsed}s)")

                elif response.status_code == 401:
                    self._log("Token expired!", "error")
                    return None

            except Exception as e:
                self._log(f"Poll error: {e}", "warn")

            time.sleep(5)

        self._log("Video generation timeout!", "error")
        return None

    def download_video(self, video_url: str, output_path: Path) -> bool:
        """
        Download video từ URL.

        Args:
            video_url: URL video
            output_path: Đường dẫn lưu

        Returns:
            True nếu thành công
        """
        self._log(f"Downloading video to: {output_path.name}")

        try:
            response = requests.get(video_url, stream=True, timeout=120)

            if response.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                self._log(f"Downloaded: {output_path.name}")
                return True
            else:
                self._log(f"Download failed: {response.status_code}", "error")
                return False

        except Exception as e:
            self._log(f"Download error: {e}", "error")
            return False

    def convert_image_to_video(
        self,
        image_path: Path,
        prompt: str = "",
        replace_image: bool = True,
        cached_media_name: str = ""
    ) -> VideoConversionResult:
        """
        Chuyển đổi một ảnh sang video.

        Args:
            image_path: Đường dẫn ảnh
            prompt: Prompt mô tả chuyển động
            replace_image: Thay thế ảnh bằng video
            cached_media_name: Media name đã cache từ lúc tạo ảnh (bỏ qua upload)

        Returns:
            VideoConversionResult
        """
        result = VideoConversionResult(image_path=image_path, prompt=prompt)

        try:
            # Step 1: Get media_id - dùng cached nếu có, không thì upload
            if cached_media_name:
                # Dùng media_name đã cache từ lúc tạo ảnh - KHÔNG CẦN UPLOAD LẠI
                self._log(f"Sử dụng cached media_name: {cached_media_name[:50]}...")
                result.status = "cached"
                media_id = cached_media_name
            else:
                # Không có cache - phải upload ảnh để lấy media_id mới
                result.status = "uploading"
                media_id = self.upload_image_for_media_id(image_path)

                if not media_id:
                    result.status = "failed"
                    result.error = "Failed to upload image"
                    return result

            result.media_id = media_id

            # Step 2: Create video
            result.status = "generating"
            video_url, operations = self.create_video_from_image(media_id, prompt)

            if not operations:
                result.status = "failed"
                result.error = "Failed to start video generation"
                return result

            # Step 3: Poll for completion
            video_url = self.poll_video_status(operations)

            if not video_url:
                result.status = "failed"
                result.error = "Video generation failed or timeout"
                return result

            result.video_url = video_url

            # Step 4: Download video
            result.status = "downloading"
            video_filename = image_path.stem + ".mp4"
            video_path = self.video_dir / video_filename

            if not self.download_video(video_url, video_path):
                result.status = "failed"
                result.error = "Failed to download video"
                return result

            result.video_path = video_path

            # Step 5: Replace image with video (optional)
            if replace_image:
                # Backup ảnh gốc
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = self.backup_dir / image_path.name
                shutil.copy2(image_path, backup_path)

                # Xóa ảnh gốc
                image_path.unlink()

                # Copy video vào thư mục img (với tên giống ảnh nhưng .mp4)
                img_video_path = self.img_dir / video_filename
                shutil.copy2(video_path, img_video_path)

                self._log(f"Replaced {image_path.name} with {video_filename}")

            result.status = "completed"
            return result

        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            self._log(f"Conversion error: {e}", "error")
            return result

    def convert_batch(
        self,
        count: int = None,
        full: bool = False,
        prompt: str = "",
        replace_images: bool = True,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Chuyển đổi nhiều ảnh sang video.

        Args:
            count: Số lượng ảnh (None = tất cả)
            full: True = tất cả ảnh
            prompt: Prompt chung cho tất cả
            replace_images: Thay thế ảnh bằng video
            progress_callback: Callback(current, total, result)

        Returns:
            Dict với thống kê
        """
        images = self.get_images_to_convert(count, full)

        if not images:
            self._log("Không có ảnh để chuyển đổi!", "warn")
            return {"success": 0, "failed": 0, "total": 0}

        self._log(f"Bắt đầu chuyển {len(images)} ảnh sang video...")

        # Tạo thư mục video
        self.video_dir.mkdir(parents=True, exist_ok=True)

        results = []
        success_count = 0
        failed_count = 0

        for i, image_path in enumerate(images):
            self._log(f"[{i+1}/{len(images)}] Processing: {image_path.name}")

            result = self.convert_image_to_video(
                image_path,
                prompt=prompt,
                replace_image=replace_images
            )

            results.append(result)

            if result.is_completed:
                success_count += 1
            else:
                failed_count += 1

            if progress_callback:
                progress_callback(i + 1, len(images), result)

            # Delay giữa các request
            if i < len(images) - 1:
                time.sleep(2)

        self._log(f"Hoàn thành: {success_count} thành công, {failed_count} thất bại")

        return {
            "success": success_count,
            "failed": failed_count,
            "total": len(images),
            "results": results
        }


def create_video_converter(
    project_path: str,
    config: Dict[str, Any],
    log_callback: Optional[Callable] = None
) -> Optional[ImageToVideoConverter]:
    """
    Factory function để tạo converter từ config.

    Args:
        project_path: Đường dẫn project
        config: Config dict (từ settings.yaml)
        log_callback: Log callback

    Returns:
        ImageToVideoConverter hoặc None
    """
    bearer_token = config.get("flow_bearer_token", "")
    project_id = config.get("flow_project_id", "")
    proxy_token = config.get("proxy_api_token", "")

    if not bearer_token:
        if log_callback:
            log_callback("Thiếu flow_bearer_token!", "error")
        return None

    if not project_id:
        # Tạo project ID mới
        import uuid
        project_id = str(uuid.uuid4())

    video_model = config.get("video_model", "fast")
    model_map = {
        "fast": ImageToVideoConverter.I2V_MODEL_FAST,
        "quality": ImageToVideoConverter.I2V_MODEL_QUALITY
    }

    return ImageToVideoConverter(
        project_path=project_path,
        bearer_token=bearer_token,
        project_id=project_id,
        proxy_token=proxy_token,
        use_proxy=bool(proxy_token),
        video_model=model_map.get(video_model, ImageToVideoConverter.I2V_MODEL_FAST),
        log_callback=log_callback
    )
