"""
Video Generator from Images
============================
Flow:
1. Upload image → mediaId
2. Generate video với mediaId + recaptchaToken
3. Poll status
4. Download video

Cần capture từ Chrome:
- token (Authorization Bearer)
- projectId (từ URL)
- recaptchaToken (từ request generate)
- x-browser headers
"""

import sys
import time
import json
import base64
import uuid
import random
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List


class VideoGenerator:
    """Generate video từ ảnh local."""

    BASE_URL = "https://aisandbox-pa.googleapis.com"

    def __init__(
        self,
        token: str,
        project_id: str,
        recaptcha_token: str = None,
        x_browser_validation: str = None,
        x_client_data: str = None
    ):
        self.token = token
        self.project_id = project_id
        self.recaptcha_token = recaptcha_token
        self.x_browser_validation = x_browser_validation
        self.x_client_data = x_client_data
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "text/plain;charset=UTF-8",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "x-browser-channel": "stable",
            "x-browser-copyright": "Copyright 2025 Google LLC. All Rights reserved.",
            "x-browser-year": "2025",
        }

        if self.x_browser_validation:
            headers["x-browser-validation"] = self.x_browser_validation
        if self.x_client_data:
            headers["x-client-data"] = self.x_client_data

        session.headers.update(headers)
        return session

    def log(self, msg: str):
        print(f"[VideoGen] {msg}")

    def upload_image(self, image_path: str) -> Optional[str]:
        """
        Upload ảnh local lên Google và nhận mediaId.

        Args:
            image_path: Đường dẫn đến file ảnh (jpg, png)

        Returns:
            mediaId nếu thành công, None nếu thất bại
        """
        self.log(f"Uploading: {image_path}")

        path = Path(image_path)
        if not path.exists():
            self.log(f"File không tồn tại: {image_path}")
            return None

        # Đọc và encode base64
        with open(path, "rb") as f:
            image_bytes = f.read()

        # Encode base64 (không có prefix data:image/...)
        raw_bytes = base64.b64encode(image_bytes).decode("utf-8")

        url = f"{self.BASE_URL}/v1:uploadUserImage"
        payload = {
            "imageInput": {
                "rawImageBytes": raw_bytes
            }
        }

        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=120
            )

            self.log(f"Upload status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                media_id = data.get("mediaGenerationId", {}).get("mediaGenerationId")
                if media_id:
                    self.log(f"✓ mediaId: {media_id[:50]}...")
                    return media_id
                else:
                    self.log(f"✗ Không tìm thấy mediaId trong response: {data}")
                    return None
            else:
                self.log(f"✗ Upload failed: {response.text[:500]}")
                return None

        except Exception as e:
            self.log(f"✗ Upload error: {e}")
            return None

    def generate_video(
        self,
        media_id: str,
        prompt: str,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    ) -> Optional[Dict]:
        """
        Tạo video từ mediaId.

        Args:
            media_id: ID của ảnh đã upload
            prompt: Mô tả video
            aspect_ratio: Tỷ lệ video

        Returns:
            operations data nếu thành công
        """
        self.log(f"Generating video...")
        self.log(f"Prompt: {prompt}")

        url = f"{self.BASE_URL}/v1/video:batchAsyncGenerateVideoReferenceImages"

        scene_id = str(uuid.uuid4())
        seed = random.randint(1000, 99999)

        payload = {
            "clientContext": {
                "sessionId": f";{int(time.time() * 1000)}",
                "projectId": self.project_id,
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
                "seed": seed,
                "textInput": {"prompt": prompt},
                "videoModelKey": "veo_3_0_r2v_fast_ultra"
            }]
        }

        # Thêm recaptchaToken nếu có
        if self.recaptcha_token:
            payload["clientContext"]["recaptchaToken"] = self.recaptcha_token

        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=120
            )

            self.log(f"Generate status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                operations = data.get("operations", [])
                if operations:
                    self.log(f"✓ Got {len(operations)} operation(s)")
                    return data
                else:
                    self.log(f"✗ No operations in response: {data}")
                    return None
            else:
                self.log(f"✗ Generate failed: {response.text[:500]}")
                return None

        except Exception as e:
            self.log(f"✗ Generate error: {e}")
            return None

    def check_status(self, operations: List[Dict]) -> Optional[Dict]:
        """
        Kiểm tra status của video.

        Args:
            operations: Mảng operations từ generate response

        Returns:
            Updated operations data
        """
        url = f"{self.BASE_URL}/v1/video:batchCheckAsyncVideoGenerationStatus"

        # Payload giống hệt response từ generate
        payload = {"operations": operations}

        try:
            response = self.session.post(
                url,
                data=json.dumps(payload),
                timeout=60
            )

            if response.status_code == 200:
                return response.json()
            else:
                self.log(f"Status check failed: {response.status_code}")
                self.log(f"Response: {response.text[:300]}")
                return None

        except Exception as e:
            self.log(f"Status check error: {e}")
            return None

    def wait_for_completion(
        self,
        operations: List[Dict],
        max_wait: int = 300,
        poll_interval: int = 10
    ) -> Optional[Dict]:
        """
        Đợi video hoàn thành.

        Args:
            operations: Mảng operations từ generate
            max_wait: Thời gian tối đa (giây)
            poll_interval: Khoảng cách giữa các lần check

        Returns:
            Completed operations data
        """
        self.log(f"Waiting for video (max {max_wait}s)...")

        start_time = time.time()
        current_ops = operations
        attempt = 0

        while time.time() - start_time < max_wait:
            attempt += 1
            elapsed = int(time.time() - start_time)

            result = self.check_status(current_ops)

            if not result:
                self.log(f"Check #{attempt} ({elapsed}s): Failed to get status")
                time.sleep(poll_interval)
                continue

            updated_ops = result.get("operations", [])

            if updated_ops:
                # Update current_ops với status mới
                current_ops = updated_ops

                # Check từng operation
                all_done = True
                for op in updated_ops:
                    status = op.get("status", "UNKNOWN")
                    op_name = op.get("operation", {}).get("name", "?")[:8]

                    if status == "MEDIA_GENERATION_STATUS_COMPLETED":
                        self.log(f"Check #{attempt} ({elapsed}s): {op_name}... COMPLETED ✓")
                    elif status == "MEDIA_GENERATION_STATUS_FAILED":
                        self.log(f"Check #{attempt} ({elapsed}s): {op_name}... FAILED ✗")
                        return None
                    else:
                        self.log(f"Check #{attempt} ({elapsed}s): {op_name}... {status}")
                        all_done = False

                if all_done:
                    self.log("✓ All videos completed!")
                    return result

            time.sleep(poll_interval)

        self.log(f"✗ Timeout after {max_wait}s")
        return None

    def download_video(self, video_url: str, output_path: str) -> bool:
        """Download video từ URL."""
        self.log(f"Downloading to: {output_path}")

        try:
            response = requests.get(video_url, timeout=120)

            if response.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                self.log(f"✓ Downloaded: {len(response.content)} bytes")
                return True
            else:
                self.log(f"✗ Download failed: {response.status_code}")
                return False

        except Exception as e:
            self.log(f"✗ Download error: {e}")
            return False

    def process_image(
        self,
        image_path: str,
        prompt: str,
        output_path: str = None
    ) -> Dict[str, Any]:
        """
        Full flow: Upload → Generate → Wait → Download

        Args:
            image_path: Đường dẫn ảnh
            prompt: Mô tả video
            output_path: Đường dẫn lưu video (optional)

        Returns:
            Result dict
        """
        self.log("=" * 50)
        self.log("PROCESSING IMAGE → VIDEO")
        self.log("=" * 50)

        # Step 1: Upload
        self.log("\n[STEP 1] Upload image")
        media_id = self.upload_image(image_path)
        if not media_id:
            return {"success": False, "error": "Upload failed"}

        # Step 2: Generate
        self.log("\n[STEP 2] Generate video")
        gen_result = self.generate_video(media_id, prompt)
        if not gen_result:
            return {"success": False, "error": "Generate failed", "media_id": media_id}

        operations = gen_result.get("operations", [])

        # Step 3: Wait for completion
        self.log("\n[STEP 3] Wait for completion")
        completed = self.wait_for_completion(operations)
        if not completed:
            return {
                "success": False,
                "error": "Video generation failed or timeout",
                "media_id": media_id,
                "operations": operations
            }

        # Step 4: Extract video URL and download
        self.log("\n[STEP 4] Download video")

        results = []
        completed_ops = completed.get("operations", [])

        for i, op in enumerate(completed_ops):
            # Try different fields for video URL
            video_url = (
                op.get("videoUrl") or
                op.get("generatedVideo", {}).get("videoUrl") or
                op.get("generatedVideo", {}).get("fifeUrl") or
                op.get("mediaUrl")
            )

            if video_url:
                if output_path:
                    # Generate unique filename for multiple videos
                    if len(completed_ops) > 1:
                        base, ext = output_path.rsplit(".", 1) if "." in output_path else (output_path, "mp4")
                        save_path = f"{base}_{i+1}.{ext}"
                    else:
                        save_path = output_path

                    self.download_video(video_url, save_path)
                    results.append({
                        "video_url": video_url,
                        "saved_to": save_path
                    })
                else:
                    results.append({"video_url": video_url})
            else:
                self.log(f"⚠️ Could not find video URL for operation {i+1}")
                self.log(f"Operation data: {json.dumps(op, indent=2)[:500]}")

        return {
            "success": True,
            "media_id": media_id,
            "videos": results,
            "completed_operations": completed_ops
        }


def load_credentials(file_path: str = "video_credentials.json") -> Dict:
    """Load credentials từ file."""
    path = Path(file_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_credentials(data: Dict, file_path: str = "video_credentials.json"):
    """Save credentials ra file."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved to {file_path}")


def main():
    """Main function với interactive mode."""
    print("=" * 60)
    print("VIDEO GENERATOR FROM IMAGES")
    print("=" * 60)

    # Load saved credentials
    creds = load_credentials()

    # Get credentials
    token = creds.get("token") or input("Enter Bearer token: ").strip()
    project_id = creds.get("project_id") or input("Enter project_id: ").strip()
    recaptcha_token = creds.get("recaptcha_token") or input("Enter recaptchaToken (or press Enter to skip): ").strip()
    x_browser_validation = creds.get("x_browser_validation") or input("Enter x-browser-validation (or Enter to skip): ").strip()

    if not token or not project_id:
        print("✗ Cần token và project_id!")
        return

    # Save for next time
    save_credentials({
        "token": token,
        "project_id": project_id,
        "recaptcha_token": recaptcha_token,
        "x_browser_validation": x_browser_validation
    })

    # Create generator
    generator = VideoGenerator(
        token=token,
        project_id=project_id,
        recaptcha_token=recaptcha_token or None,
        x_browser_validation=x_browser_validation or None
    )

    # Get image path
    image_path = input("\nEnter image path: ").strip()
    if not image_path:
        image_path = r"D:\AUTO\ve3-tool\1.png"

    # Get prompt
    prompt = input("Enter prompt (or press Enter for default): ").strip()
    if not prompt:
        prompt = "Animate this image with smooth motion"

    # Output path
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = str(output_dir / f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4")

    # Process
    result = generator.process_image(image_path, prompt, output_path)

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False)[:2000])

    return result.get("success", False)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
