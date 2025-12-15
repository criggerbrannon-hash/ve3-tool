"""
Browser Video Generator
========================
Tạo video AI bằng browser automation với stealth mode.
Tương tự như tool kia - dùng headless browser thay vì direct API.

Yêu cầu:
    pip install playwright playwright-stealth
    playwright install chromium

Usage:
    from modules.browser_video import BrowserVideoGenerator

    gen = BrowserVideoGenerator(token, project_id)
    await gen.start()
    result = await gen.generate_video("path/to/image.png", "prompt")
    await gen.close()
"""

import asyncio
import json
import base64
import random
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

# Try to import playwright
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# Try to import stealth plugin
try:
    from playwright_stealth import stealth_async
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False


class BrowserVideoGenerator:
    """
    Generate video bằng browser automation với stealth mode.

    Giống cách tool kia làm:
    - Dùng headless browser
    - Stealth mode để tránh bot detection
    - Inject token + projectId vào browser context
    """

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"
    API_BASE = "https://aisandbox-pa.googleapis.com"

    def __init__(
        self,
        token: str,
        project_id: str,
        headless: bool = True,
        stealth_mode: bool = True,
        min_delay: int = 1000,
        max_delay: int = 3000,
        callback: Callable[[str], None] = None
    ):
        """
        Args:
            token: Bearer token (ya29.xxx)
            project_id: Project ID (uuid)
            headless: Chạy browser ẩn
            stealth_mode: Bật stealth để tránh detection
            min_delay: Delay tối thiểu giữa các action (ms)
            max_delay: Delay tối đa giữa các action (ms)
            callback: Log callback
        """
        self.token = token
        self.project_id = project_id
        self.headless = headless
        self.stealth_mode = stealth_mode
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.callback = callback

        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        self._started = False

    def log(self, msg: str):
        print(f"[BrowserVideo] {msg}")
        if self.callback:
            self.callback(msg)

    async def _random_delay(self, multiplier: float = 1.0):
        """Random delay để giống người thật."""
        delay = random.randint(self.min_delay, self.max_delay) * multiplier / 1000
        await asyncio.sleep(delay)

    async def start(self) -> bool:
        """Khởi động browser."""
        if not HAS_PLAYWRIGHT:
            self.log("❌ Cần cài: pip install playwright && playwright install chromium")
            return False

        try:
            self.log("Starting browser...")
            self.playwright = await async_playwright().start()

            # Launch browser với các options tương tự tool kia
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                ]
            )

            # Create context với fake user agent
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='vi-VN',
                timezone_id='Asia/Ho_Chi_Minh',
            )

            self.page = await self.context.new_page()

            # Apply stealth nếu có
            if self.stealth_mode and HAS_STEALTH:
                await stealth_async(self.page)
                self.log("✓ Stealth mode enabled")

            # Inject authorization header cho API calls
            await self._setup_api_intercept()

            self._started = True
            self.log("✓ Browser started")
            return True

        except Exception as e:
            self.log(f"❌ Start error: {e}")
            return False

    async def _setup_api_intercept(self):
        """Setup route intercept để inject auth headers."""

        async def handle_route(route):
            """Intercept API requests và thêm auth headers."""
            request = route.request
            url = request.url

            # Chỉ intercept requests tới aisandbox API
            if 'aisandbox-pa.googleapis.com' in url:
                headers = {
                    **request.headers,
                    'Authorization': f'Bearer {self.token}',
                }

                await route.continue_(headers=headers)
            else:
                await route.continue_()

        # Intercept all requests
        await self.page.route('**/*', handle_route)

    async def close(self):
        """Đóng browser."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self._started = False
        self.log("Browser closed")

    async def navigate_to_flow(self) -> bool:
        """Mở trang Flow."""
        try:
            self.log(f"Navigating to Flow...")
            await self.page.goto(self.FLOW_URL, wait_until='networkidle', timeout=60000)
            await self._random_delay(2)
            self.log("✓ Flow page loaded")
            return True
        except Exception as e:
            self.log(f"❌ Navigate error: {e}")
            return False

    async def upload_image_via_api(self, image_path: str) -> Optional[str]:
        """
        Upload ảnh sử dụng API call từ trong browser context.
        Cách này bypass bot detection vì request đi từ real browser.
        """
        self.log(f"Uploading: {Path(image_path).name}")

        path = Path(image_path)
        if not path.exists():
            self.log(f"❌ File not found: {image_path}")
            return None

        # Read và encode ảnh
        with open(image_path, 'rb') as f:
            raw_bytes = base64.b64encode(f.read()).decode('utf-8')

        mime_type = 'image/png' if image_path.lower().endswith('.png') else 'image/jpeg'

        # Gọi API từ trong browser context
        result = await self.page.evaluate(f'''
            async () => {{
                try {{
                    const response = await fetch(
                        'https://aisandbox-pa.googleapis.com/v1/projects/{self.project_id}/flowMedia:uploadImage',
                        {{
                            method: 'POST',
                            headers: {{
                                'Authorization': 'Bearer {self.token}',
                                'Content-Type': 'application/json',
                            }},
                            body: JSON.stringify({{
                                rawImageBytes: '{raw_bytes}',
                                mimeType: '{mime_type}'
                            }})
                        }}
                    );

                    if (response.ok) {{
                        const data = await response.json();
                        return {{
                            success: true,
                            data: data
                        }};
                    }} else {{
                        const text = await response.text();
                        return {{
                            success: false,
                            status: response.status,
                            error: text
                        }};
                    }}
                }} catch (e) {{
                    return {{
                        success: false,
                        error: e.message
                    }};
                }}
            }}
        ''')

        if result.get('success'):
            data = result.get('data', {})

            # Try extract mediaId from various response formats
            media_id = (
                data.get('mediaId') or
                data.get('mediaGenerationId', {}).get('mediaGenerationId') or
                data.get('id') or
                (data.get('name', '').split('/')[-1] if data.get('name') else None)
            )

            if media_id:
                self.log(f"✓ mediaId: {media_id[:40]}...")
                return media_id
            else:
                self.log(f"❌ No mediaId in response: {list(data.keys())}")
                return None
        else:
            self.log(f"❌ Upload failed: {result.get('status')} - {result.get('error', '')[:200]}")
            return None

    async def generate_video_via_api(self, media_id: str, prompt: str) -> Optional[Dict]:
        """
        Generate video sử dụng API call từ browser context.
        """
        self.log(f"Generating video: {prompt[:50]}...")

        seed = random.randint(1000, 99999)
        scene_id = str(uuid.uuid4())

        # Try multiple endpoints
        endpoints = [
            f'/v1/projects/{self.project_id}/flowMedia:batchGenerateVideos',
            f'/v1/projects/{self.project_id}/video:batchAsyncGenerateVideoReferenceImages',
            f'/v1/video:batchAsyncGenerateVideoReferenceImages',
        ]

        for endpoint in endpoints:
            # Different payload for different endpoints
            if 'flowMedia' in endpoint:
                payload = {
                    "requests": [{
                        "referenceImages": [{
                            "mediaId": media_id,
                            "imageUsageType": "IMAGE_USAGE_TYPE_ASSET"
                        }],
                        "textInput": {"prompt": prompt},
                        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                        "videoModelKey": "veo_3_0_r2v_fast_ultra",
                        "seed": seed,
                        "metadata": {"sceneId": scene_id}
                    }]
                }
            else:
                payload = {
                    "clientContext": {
                        "sessionId": f";{int(time.time() * 1000)}",
                        "projectId": self.project_id,
                        "tool": "PINHOLE",
                        "userPaygateTier": "PAYGATE_TIER_TWO"
                    },
                    "requests": [{
                        "aspectRatio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
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

            payload_json = json.dumps(payload).replace("'", "\\'")

            result = await self.page.evaluate(f'''
                async () => {{
                    try {{
                        const response = await fetch(
                            'https://aisandbox-pa.googleapis.com{endpoint}',
                            {{
                                method: 'POST',
                                headers: {{
                                    'Authorization': 'Bearer {self.token}',
                                    'Content-Type': 'application/json',
                                }},
                                body: '{payload_json}'
                            }}
                        );

                        if (response.ok) {{
                            const data = await response.json();
                            return {{
                                success: true,
                                data: data
                            }};
                        }} else {{
                            const text = await response.text();
                            return {{
                                success: false,
                                status: response.status,
                                error: text
                            }};
                        }}
                    }} catch (e) {{
                        return {{
                            success: false,
                            error: e.message
                        }};
                    }}
                }}
            ''')

            if result.get('success'):
                data = result.get('data', {})
                ops = data.get('operations') or data.get('results') or ([data] if data.get('name') else None)

                if ops:
                    self.log(f"✓ Got {len(ops)} operation(s)")
                    return {'operations': ops}

            self.log(f"  Endpoint {endpoint.split('/')[-1]} failed: {result.get('status', 'N/A')}")

        self.log("❌ All endpoints failed")
        return None

    async def check_video_status(self, operations: List[Dict]) -> Optional[Dict]:
        """Check status của video generation."""
        results = []

        for op in operations:
            name = op.get('name', '')

            if name:
                # Operation name format: projects/{projectId}/operations/{opId}
                result = await self.page.evaluate(f'''
                    async () => {{
                        try {{
                            const response = await fetch(
                                'https://aisandbox-pa.googleapis.com/v1/{name}',
                                {{
                                    method: 'GET',
                                    headers: {{
                                        'Authorization': 'Bearer {self.token}',
                                    }}
                                }}
                            );

                            if (response.ok) {{
                                return await response.json();
                            }}
                            return null;
                        }} catch (e) {{
                            return null;
                        }}
                    }}
                ''')

                if result:
                    results.append(result)
                else:
                    results.append(op)
            else:
                # Fallback: use batch check endpoint
                pass

        return {'operations': results} if results else None

    async def wait_for_video(self, operations: List[Dict], max_wait: int = 300) -> Optional[Dict]:
        """Đợi video hoàn thành."""
        self.log(f"Waiting for video (max {max_wait}s)...")

        start = time.time()
        current_ops = operations

        while time.time() - start < max_wait:
            result = await self.check_video_status(current_ops)

            if result:
                updated = result.get('operations', [])
                if updated:
                    current_ops = updated

                    all_done = True
                    for op in updated:
                        done = op.get('done', False)
                        status = str(op.get('metadata', {}).get('state', '')).upper()

                        if done or 'COMPLETED' in status or 'SUCCEEDED' in status:
                            continue
                        elif 'FAILED' in status or 'ERROR' in status or op.get('error'):
                            error = op.get('error', {}).get('message', 'Unknown error')
                            self.log(f"❌ FAILED: {error}")
                            return None
                        else:
                            all_done = False

                    if all_done:
                        self.log("✓ COMPLETED!")
                        return result

            elapsed = int(time.time() - start)
            self.log(f"  ... {elapsed}s")
            await asyncio.sleep(10)

        self.log("❌ Timeout")
        return None

    def _extract_video_url(self, op: Dict) -> Optional[str]:
        """Extract video URL from operation."""
        return (
            op.get('videoUrl') or
            op.get('response', {}).get('videoUrl') or
            op.get('response', {}).get('generatedVideo', {}).get('videoUrl') or
            op.get('response', {}).get('generatedVideo', {}).get('fifeUrl') or
            op.get('result', {}).get('videoUrl') or
            op.get('metadata', {}).get('videoUrl')
        )

    async def download_video(self, video_url: str, output_path: str) -> bool:
        """Download video."""
        try:
            # Download từ trong browser
            result = await self.page.evaluate(f'''
                async () => {{
                    try {{
                        const response = await fetch('{video_url}');
                        if (response.ok) {{
                            const blob = await response.blob();
                            const reader = new FileReader();
                            return new Promise((resolve) => {{
                                reader.onloadend = () => {{
                                    resolve({{
                                        success: true,
                                        data: reader.result.split(',')[1]
                                    }});
                                }};
                                reader.readAsDataURL(blob);
                            }});
                        }}
                        return {{ success: false }};
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }}
            ''')

            if result.get('success'):
                video_data = base64.b64decode(result['data'])
                with open(output_path, 'wb') as f:
                    f.write(video_data)
                self.log(f"✓ Saved: {output_path}")
                return True

            return False

        except Exception as e:
            self.log(f"❌ Download error: {e}")
            return False

    async def generate_video(
        self,
        image_path: str,
        prompt: str,
        output_dir: str = None
    ) -> Dict[str, Any]:
        """
        Full flow: upload → generate → wait → download.

        Args:
            image_path: Đường dẫn ảnh
            prompt: Prompt cho video
            output_dir: Thư mục output

        Returns:
            Dict với keys: success, output, video_url, error
        """
        result = {'image': image_path, 'success': False}

        if not self._started:
            if not await self.start():
                result['error'] = 'Failed to start browser'
                return result

        # 1. Upload
        media_id = await self.upload_image_via_api(image_path)
        if not media_id:
            result['error'] = 'Upload failed'
            return result

        await self._random_delay()

        # 2. Generate
        gen_result = await self.generate_video_via_api(media_id, prompt)
        if not gen_result:
            result['error'] = 'Generate failed'
            return result

        operations = gen_result.get('operations', [])

        # 3. Wait
        completed = await self.wait_for_video(operations)
        if not completed:
            result['error'] = 'Video generation failed or timeout'
            return result

        # 4. Download
        for op in completed.get('operations', []):
            video_url = self._extract_video_url(op)

            if video_url:
                if output_dir is None:
                    output_dir = str(Path(image_path).parent)

                Path(output_dir).mkdir(parents=True, exist_ok=True)
                filename = Path(image_path).stem + '_video.mp4'
                output_path = str(Path(output_dir) / filename)

                if await self.download_video(video_url, output_path):
                    result['success'] = True
                    result['output'] = output_path
                    result['video_url'] = video_url
                break

        return result


# ============================================================================
# SYNC WRAPPER
# ============================================================================

class BrowserVideoSync:
    """
    Sync wrapper cho BrowserVideoGenerator.
    Dễ dùng hơn trong code không async.
    """

    def __init__(self, token: str, project_id: str, **kwargs):
        self.token = token
        self.project_id = project_id
        self.kwargs = kwargs
        self._gen = None
        self._loop = None

    def _get_loop(self):
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def start(self) -> bool:
        self._gen = BrowserVideoGenerator(self.token, self.project_id, **self.kwargs)
        self._loop = self._get_loop()
        return self._loop.run_until_complete(self._gen.start())

    def generate_video(self, image_path: str, prompt: str, output_dir: str = None) -> Dict:
        if not self._gen:
            self.start()
        return self._loop.run_until_complete(
            self._gen.generate_video(image_path, prompt, output_dir)
        )

    def close(self):
        if self._gen and self._loop:
            self._loop.run_until_complete(self._gen.close())


# ============================================================================
# CLI
# ============================================================================

def main():
    import sys

    print("=" * 60)
    print("BROWSER VIDEO GENERATOR")
    print("=" * 60)

    if not HAS_PLAYWRIGHT:
        print("❌ Cần cài Playwright:")
        print("   pip install playwright playwright-stealth")
        print("   playwright install chromium")
        return

    # Get credentials
    token = input("Token (ya29.xxx): ").strip()
    if token.startswith("Bearer "):
        token = token[7:]

    project_id = input("ProjectID: ").strip()

    if not token or not project_id:
        print("❌ Cần cả token và projectId!")
        return

    # Get image
    image_path = input("Image path: ").strip()
    if not image_path or not Path(image_path).exists():
        print("❌ File không tồn tại!")
        return

    # Get prompt
    prompt = input("Prompt (Enter for default): ").strip()
    if not prompt:
        prompt = "Animate this image with smooth, natural motion"

    # Run
    print("\n" + "=" * 60)

    gen = BrowserVideoSync(token, project_id, headless=False)  # headless=False để debug

    try:
        if gen.start():
            result = gen.generate_video(image_path, prompt)

            if result.get('success'):
                print(f"\n✅ SUCCESS!")
                print(f"   Output: {result.get('output')}")
            else:
                print(f"\n❌ FAILED: {result.get('error')}")
    finally:
        gen.close()


if __name__ == "__main__":
    main()
