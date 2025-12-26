#!/usr/bin/env python3
"""
Google Flow API - Batch Image Generator (VE3 Method)
=====================================================
Tự động tạo nhiều ảnh bằng DrissionPage + VE3 JavaScript.

Workflow:
1. Mở Chrome, đăng nhập Google
2. Inject VE3 JavaScript script
3. Gọi API.generateImages() qua JS (không cần UI)
4. Download và lưu ảnh

Cài đặt:
    pip install DrissionPage requests

Sử dụng:
    python batch_generator.py
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime
import random

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("Cần cài đặt: pip install DrissionPage requests")
    exit(1)

# Config
OUTPUT_DIR = Path("./batch_output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Path to VE3 JS script
VE3_JS_PATH = Path(__file__).parent / "scripts" / "ve3_browser_automation.js"

# Test prompts
DEFAULT_PROMPTS = [
    "a majestic lion in the savanna at sunset",
    "a cute kitten playing with yarn",
    "a futuristic city with flying cars",
    "a peaceful zen garden with cherry blossoms",
    "an astronaut riding a horse on mars",
    "a dragon breathing fire over a medieval castle",
    "a serene lake reflecting mountains at dawn",
    "a cozy coffee shop on a rainy day",
    "a magical forest with glowing mushrooms",
    "a vintage car on route 66 at sunset",
]

# Simple JS to call API directly (không cần full VE3 script)
JS_API_CALLER = '''
(function(){
    if(window.__batchApiReady) return 'ALREADY_READY';
    window.__batchApiReady = true;

    // Get project ID from URL
    window.__getProjectId = function() {
        const url = window.location.href;
        const match = url.match(/\\/project\\/([a-f0-9-]+)/i);
        return match ? match[1] : null;
    };

    // Generate session ID
    window.__genSessionId = function() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    };

    // Generate seed
    window.__genSeed = function() {
        return Math.floor(Math.random() * 999999) + 1;
    };

    // Build payload
    window.__buildPayload = function(prompt, projectId, count) {
        const sessionId = window.__genSessionId();
        const requests = [];
        for (let i = 0; i < count; i++) {
            requests.push({
                clientContext: {
                    sessionId: sessionId,
                    projectId: projectId,
                    tool: "IMAGE_FX"
                },
                seed: window.__genSeed(),
                imageModelName: "IMAGEN_3_1",
                imageAspectRatio: "IMAGE_ASPECT_RATIO_LANDSCAPE",
                prompt: prompt,
                imageInputs: []
            });
        }
        return { requests: requests };
    };

    // Call API and return result
    window.__generateImages = async function(prompt, count) {
        const projectId = window.__getProjectId();
        if (!projectId) {
            return { success: false, error: 'No projectId in URL' };
        }

        const url = 'https://aisandbox-pa.googleapis.com/v1/projects/' + projectId + '/flowMedia:batchGenerateImages';
        const payload = window.__buildPayload(prompt, projectId, count || 2);

        console.log('[BATCH] Calling API for:', prompt.slice(0, 50));

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errText = await response.text();
                return { success: false, error: 'API ' + response.status + ': ' + errText.slice(0, 200) };
            }

            const data = await response.json();

            // Extract image URLs
            const images = [];
            if (data.media) {
                for (const m of data.media) {
                    const imgUrl = m.image?.generatedImage?.fifeUrl;
                    if (imgUrl) {
                        images.push({
                            url: imgUrl,
                            seed: m.seed || 'unknown'
                        });
                    }
                }
            }

            return { success: true, images: images, count: images.length };

        } catch (e) {
            return { success: false, error: e.message };
        }
    };

    console.log('[BATCH] API Ready. ProjectId:', window.__getProjectId());
    return 'READY';
})();
'''


class BatchGenerator:
    def __init__(self):
        self.driver = None
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": []
        }

    def setup(self):
        """Setup browser."""
        print("=" * 60)
        print("  BATCH IMAGE GENERATOR (VE3 Method)")
        print("=" * 60)

        # Chrome
        print("\n[1] MỞ CHROME...")
        print("    1 = Mở Chrome mới")
        print("    2 = Kết nối Chrome đang chạy (port 9222)")
        choice = input("    Chọn (Enter=1): ").strip()

        options = ChromiumOptions()
        options.set_argument("--start-maximized")

        try:
            if choice == "2":
                options.set_local_port(9222)
                self.driver = ChromiumPage(addr_or_opts=options)
                print("    ✓ Kết nối Chrome port 9222")
            else:
                self.driver = ChromiumPage(options)
                print("    ✓ Chrome mới đã mở")
        except Exception as e:
            print(f"    ❌ Lỗi: {e}")
            return False

        # URL
        print("\n[2] URL")
        print(f"    URL hiện tại: {self.driver.url}")
        print("\n    Nhập URL project Flow (phải có /project/xxx):")
        print("    - Enter = giữ nguyên")
        print("    - Hoặc paste URL project")
        url_input = input("    URL: ").strip()

        if url_input:
            print(f"    → Đi tới: {url_input}")
            self.driver.get(url_input)
            print("    → Đang chờ trang load...")
            time.sleep(5)

        # Debug: show current URL
        print(f"    → URL hiện tại: {self.driver.url}")

        # Check project URL
        if "/project/" not in self.driver.url:
            print("    ⚠️ URL không có /project/xxx!")
            print("    Cần mở project Flow trước (vào labs.google → Flow → mở project)")
            return False

        # Check login
        if "accounts.google" in self.driver.url:
            print("    ⚠️ Cần đăng nhập Google!")
            input("    Đăng nhập xong nhấn Enter...")
            time.sleep(2)

        # Wait for user to confirm page is ready
        input("\n    Trang đã load xong? Nhấn Enter để tiếp tục...")

        # Inject API caller
        print("\n[3] INJECT API CALLER...")
        try:
            result = self.driver.run_js(JS_API_CALLER)
            print(f"    ✓ Result: {result}")

            # Test get project ID
            project_id = self.driver.run_js("return window.__getProjectId();")
            print(f"    ✓ Project ID: {project_id}")

            if not project_id:
                print("    ❌ Không lấy được Project ID!")
                return False

        except Exception as e:
            print(f"    ❌ JS error: {e}")
            return False

        return True

    def generate_one(self, prompt, idx):
        """Generate one image with given prompt."""
        print(f"\n[{idx+1}] {prompt[:50]}...")

        try:
            # Escape prompt for JS - replace backticks with single quotes
            safe_prompt = prompt.replace('`', "'").replace('"', '\\"')

            # Call JS API using string format (avoid f-string backslash issues)
            js_code = 'return await window.__generateImages("' + safe_prompt + '", 2);'

            result = self.driver.run_js(js_code)

            if not result:
                print("    ❌ No response from JS")
                return False, []

            if result.get("success"):
                images = result.get("images", [])
                print(f"    ✓ Got {len(images)} images")

                saved = []
                for i, img in enumerate(images):
                    url = img.get("url")
                    if url:
                        try:
                            resp = requests.get(url, timeout=60)
                            if resp.status_code == 200:
                                filename = f"batch_{idx:03d}_{i+1}.png"
                                (OUTPUT_DIR / filename).write_bytes(resp.content)
                                saved.append(filename)
                                print(f"      ✓ Saved: {filename}")
                        except Exception as e:
                            print(f"      ❌ Download error: {e}")

                return len(saved) > 0, saved
            else:
                error = result.get("error", "Unknown error")
                print(f"    ❌ API error: {error}")
                return False, []

        except Exception as e:
            print(f"    ❌ Exception: {e}")
            return False, []

    def run_batch(self, prompts):
        """Run batch generation."""
        print(f"\n{'=' * 60}")
        print(f"  BATCH GENERATION: {len(prompts)} prompts")
        print(f"{'=' * 60}")

        self.stats["total"] = len(prompts)

        for i, prompt in enumerate(prompts):
            try:
                success, saved = self.generate_one(prompt, i)

                if success:
                    self.stats["success"] += 1
                else:
                    self.stats["failed"] += 1
                    self.stats["errors"].append(f"Prompt {i+1}: Failed")

            except Exception as e:
                self.stats["failed"] += 1
                self.stats["errors"].append(f"Prompt {i+1}: {str(e)}")

            # Delay giữa các request để tránh rate limit
            if i < len(prompts) - 1:
                delay = random.uniform(3, 6)
                print(f"    ... chờ {delay:.1f}s")
                time.sleep(delay)

        # Print stats
        print(f"\n{'=' * 60}")
        print(f"  BATCH COMPLETE")
        print(f"{'=' * 60}")
        print(f"  Total: {self.stats['total']}")
        print(f"  Success: {self.stats['success']}")
        print(f"  Failed: {self.stats['failed']}")
        if self.stats['total'] > 0:
            print(f"  Success rate: {self.stats['success']/self.stats['total']*100:.1f}%")
        print(f"  Output: {OUTPUT_DIR.absolute()}")

        if self.stats["errors"]:
            print(f"\n  Errors:")
            for err in self.stats["errors"][:10]:
                print(f"    - {err}")

    def cleanup(self):
        if self.driver:
            self.driver.quit()


def main():
    gen = BatchGenerator()

    if not gen.setup():
        return

    # Menu
    print(f"\n{'=' * 60}")
    print("  OPTIONS:")
    print("    1. Test với 10 prompts mặc định")
    print("    2. Test với N prompts tùy chọn")
    print("    3. Load prompts từ file")
    print("    4. Nhập prompts thủ công")
    print(f"{'=' * 60}")

    choice = input("\nChọn (Enter=1): ").strip() or "1"

    prompts = []

    if choice == "1":
        prompts = DEFAULT_PROMPTS

    elif choice == "2":
        n = int(input("Số lượng prompts (1-100): ") or "10")
        n = min(max(1, n), 100)
        # Repeat default prompts
        prompts = (DEFAULT_PROMPTS * (n // len(DEFAULT_PROMPTS) + 1))[:n]

    elif choice == "3":
        file_path = input("Path to prompts file: ").strip()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                prompts = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"Error reading file: {e}")
            prompts = DEFAULT_PROMPTS

    elif choice == "4":
        print("Nhập prompts (mỗi dòng 1 prompt, dòng trống để kết thúc):")
        while True:
            p = input("> ").strip()
            if not p:
                break
            prompts.append(p)

    if not prompts:
        prompts = DEFAULT_PROMPTS

    print(f"\n→ Sẽ tạo {len(prompts)} ảnh")
    confirm = input("Tiếp tục? (Enter=yes, n=no): ").strip().lower()

    if confirm == 'n':
        print("Cancelled.")
        gen.cleanup()
        return

    try:
        gen.run_batch(prompts)
    except KeyboardInterrupt:
        print("\n\nInterrupted!")
    finally:
        input("\nNhấn Enter để đóng Chrome...")
        gen.cleanup()


if __name__ == "__main__":
    main()
