#!/usr/bin/env python3
"""
Google Flow API - Interceptor Solution
=======================================
This is the WORKING solution to call Google Flow API directly without proxy.

How it works:
1. Inject JS interceptor into browser Console
2. User clicks Generate button in UI (real user action generates valid token)
3. JS captures payload.json and saves it to Downloads
4. This Python script sends the request with captured payload immediately
5. API returns 200 with image URLs

Why this approach?
- Google reCAPTCHA Enterprise requires REAL user interaction
- Tokens generated programmatically (via grecaptcha.enterprise.execute()) fail with 403
- Only tokens from actual user clicks pass reCAPTCHA validation

JS Interceptor Code (paste in Console):
---------------------------------------
(function(){
    if(!window.__origFetch) window.__origFetch = window.fetch;
    window.fetch = async (url, opts) => {
        if (url.includes('batchGenerateImages')) {
            const blob = new Blob([opts.body], {type:'application/json'});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'payload_' + Date.now() + '.json';
            a.click();
            console.log('[INTERCEPTOR] Payload captured! Run Python script NOW!');
            alert('CAPTURED! Run Python script immediately!');
            return new Response('{"blocked":"interceptor"}');
        }
        return window.__origFetch(url, opts);
    };
    console.log('[INTERCEPTOR] Ready! Click Generate button.');
    alert('READY! Now click Generate button.');
})();
---------------------------------------

Usage:
  python google_flow_interceptor.py
"""

import json
import requests
from pathlib import Path
from datetime import datetime
import time
import sys

# Output directory for generated images
OUTPUT_DIR = Path("./generated_images")
OUTPUT_DIR.mkdir(exist_ok=True)

# Where to look for payload files
DOWNLOADS_DIR = Path.home() / "Downloads"

# JS code for reference
JS_INTERCEPTOR = '''
(function(){
    if(!window.__origFetch) window.__origFetch = window.fetch;
    window.fetch = async (url, opts) => {
        if (url.includes('batchGenerateImages')) {
            const blob = new Blob([opts.body], {type:'application/json'});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'payload_' + Date.now() + '.json';
            a.click();
            console.log('[INTERCEPTOR] Payload captured! Run Python script NOW!');
            alert('CAPTURED! Run Python script immediately!');
            return new Response('{"blocked":"interceptor"}');
        }
        return window.__origFetch(url, opts);
    };
    console.log('[INTERCEPTOR] Ready! Click Generate button.');
    alert('READY! Now click Generate button.');
})();
'''


def find_latest_payload():
    """Find the most recent payload file in Downloads."""
    patterns = ["payload_*.json", "payload.json"]
    files = []

    for pattern in patterns:
        files.extend(DOWNLOADS_DIR.glob(pattern))

    if not files:
        return None

    # Return most recently modified file
    return max(files, key=lambda f: f.stat().st_mtime)


def call_api(payload_path: Path, bearer: str, x_browser: str = None) -> bool:
    """Call Google Flow API with the captured payload."""

    # Load payload
    try:
        payload = json.loads(payload_path.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"    Error reading payload: {e}")
        return False

    # Extract info from payload
    requests_list = payload.get("requests", [])
    if not requests_list:
        print("    Error: Payload has no 'requests' field!")
        return False

    first_req = requests_list[0]
    client_ctx = first_req.get("clientContext", {})
    project_id = client_ctx.get("projectId", "")
    prompt = first_req.get("prompt", "")

    print(f"    Project: {project_id}")
    print(f"    Prompt: {prompt[:50]}...")

    # Build request
    url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    if x_browser:
        headers["x-browser-validation"] = x_browser
        headers["x-browser-channel"] = "stable"
        headers["x-browser-year"] = "2025"

    print("    Calling API...")

    try:
        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=120
        )

        print(f"    Status: {resp.status_code}")

        if resp.status_code == 200:
            result = resp.json()

            if "media" in result and result["media"]:
                print(f"    SUCCESS! {len(result['media'])} images generated")

                for i, media in enumerate(result["media"]):
                    img_url = media.get("image", {}).get("generatedImage", {}).get("fifeUrl")

                    if img_url:
                        try:
                            img_resp = requests.get(img_url, timeout=60)
                            if img_resp.status_code == 200:
                                filename = f"flow_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i+1}.png"
                                (OUTPUT_DIR / filename).write_bytes(img_resp.content)
                                print(f"       Saved: {filename}")
                        except Exception as e:
                            print(f"       Download error: {e}")

                return True
            else:
                print("    Warning: Response has no images")
                print(json.dumps(result, indent=2)[:300])
                return False

        elif resp.status_code == 401:
            print("    Error 401: Bearer token expired!")
            print("    Get a new Bearer token from Network tab")
            return False

        elif resp.status_code == 403:
            if "recaptcha" in resp.text.lower():
                print("    Error 403: reCAPTCHA token expired or already used!")
                print("    Generate a NEW image in Chrome to get fresh payload")
            else:
                print("    Error 403: Permission denied")
            return False

        else:
            print(f"    Error {resp.status_code}: {resp.text[:200]}")
            return False

    except requests.exceptions.Timeout:
        print("    Error: Request timeout (>120s)")
        return False
    except Exception as e:
        print(f"    Exception: {e}")
        return False


def main():
    print("=" * 60)
    print("  GOOGLE FLOW API - INTERCEPTOR")
    print("=" * 60)

    # Step 1: Get Bearer token
    print("\n[1] BEARER TOKEN")
    print("    Copy from Chrome -> F12 -> Network -> any request -> Headers -> authorization")
    bearer = input("    Paste: ").strip()
    if bearer.lower().startswith("bearer "):
        bearer = bearer[7:]

    if not bearer or len(bearer) < 100:
        print("    Error: Invalid Bearer token!")
        return

    print(f"    OK ({len(bearer)} chars)")

    # Step 2: x-browser-validation (optional)
    print("\n[2] X-BROWSER-VALIDATION (optional)")
    print("    Copy from Headers -> x-browser-validation")
    x_browser = input("    Paste (Enter to skip): ").strip()

    # Step 3: Show JS code
    print("\n[3] INJECT JS INTERCEPTOR")
    print("    Copy this code and paste in Chrome Console (F12 -> Console):")
    print("-" * 60)
    print(JS_INTERCEPTOR)
    print("-" * 60)

    input("\n    Press Enter when you've injected the JS...")

    # Step 4: Wait for payload
    print("\n[4] WAITING FOR PAYLOAD...")
    print("    Now click the Generate button in Chrome.")
    print("    The JS will capture the payload and save to Downloads.")
    print("    Press Ctrl+C to stop.\n")

    last_payload = find_latest_payload()
    last_mtime = last_payload.stat().st_mtime if last_payload else 0

    try:
        while True:
            sys.stdout.write(f"\r[{datetime.now().strftime('%H:%M:%S')}] Waiting for new payload...")
            sys.stdout.flush()

            current = find_latest_payload()

            if current:
                current_mtime = current.stat().st_mtime

                # Check if it's a new or updated file
                if current_mtime > last_mtime:
                    # Wait a moment for file to be fully written
                    time.sleep(0.5)

                    print(f"\n\n{'=' * 40}")
                    print(f"PAYLOAD DETECTED: {current.name}")
                    print(f"Time: {datetime.fromtimestamp(current_mtime)}")
                    print(f"{'=' * 40}")

                    success = call_api(current, bearer, x_browser)

                    if success:
                        print(f"\n    Images saved to: {OUTPUT_DIR.absolute()}")

                    print(f"{'=' * 40}\n")

                    last_mtime = current_mtime

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\nStopped.")


if __name__ == "__main__":
    main()
