"""
Test different request formats for Google's batchCheckAsyncVideoGenerationStatus endpoint.
This script tries multiple request body formats to find the one that works.

Usage:
    python test_google_poll_formats.py <operation_name>
"""
import json
import time
import sys
import requests
from pathlib import Path

# Load config
CONFIG_FILE = Path("config.json")
if not CONFIG_FILE.exists():
    print("❌ Need config.json with project_id, bearer_token, proxy_token")
    sys.exit(1)

config = json.loads(CONFIG_FILE.read_text())
PROJECT_ID = config.get("project_id", "")
BEARER_TOKEN = config.get("bearer_token", "")
PROXY_TOKEN = config.get("proxy_token", "")

GOOGLE_BASE = "https://aisandbox-pa.googleapis.com"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def create_session():
    """Create HTTP session with Google auth headers."""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
    })
    return session


def test_format(session, url, payload, format_name):
    """Test a specific request format."""
    log(f"\n{'='*60}")
    log(f"Testing format: {format_name}")
    log(f"URL: {url}")
    log(f"Payload: {json.dumps(payload)[:200]}")

    try:
        resp = session.post(url, json=payload, timeout=30)
        log(f"Status: {resp.status_code}")

        if resp.status_code == 200:
            result = resp.json()
            log(f"✅ SUCCESS!")
            log(f"Response: {json.dumps(result, indent=2)[:500]}")
            return True, result
        else:
            log(f"❌ Failed: {resp.text[:300]}")
            return False, None

    except Exception as e:
        log(f"❌ Exception: {e}")
        return False, None


def test_all_formats(operation_name):
    """Test all known request formats."""
    session = create_session()

    log(f"Testing operation name: {operation_name}")
    log(f"Project ID: {PROJECT_ID}")

    # URL variations
    urls = [
        f"{GOOGLE_BASE}/v1/video:batchCheckAsyncVideoGenerationStatus",
        f"{GOOGLE_BASE}/v1/operations/{operation_name}",
        f"{GOOGLE_BASE}/v1/projects/{PROJECT_ID}/operations/{operation_name}",
    ]

    # Payload variations for batch check endpoint
    batch_url = f"{GOOGLE_BASE}/v1/video:batchCheckAsyncVideoGenerationStatus"

    payloads = [
        # Format 1: operationNames array
        {"operationNames": [operation_name]},

        # Format 2: names array
        {"names": [operation_name]},

        # Format 3: operations array with name
        {"operations": [{"name": operation_name}]},

        # Format 4: operations array with string
        {"operations": [operation_name]},

        # Format 5: requests array with name
        {"requests": [{"name": operation_name}]},

        # Format 6: requests array with operationName
        {"requests": [{"operationName": operation_name}]},

        # Format 7: With clientContext
        {
            "clientContext": {
                "sessionId": f";{int(time.time()*1000)}",
                "projectId": PROJECT_ID,
                "tool": "PINHOLE"
            },
            "operationNames": [operation_name]
        },

        # Format 8: Full operation path format
        {"operationNames": [f"projects/{PROJECT_ID}/operations/{operation_name}"]},

        # Format 9: Video operations path
        {"operationNames": [f"video/operations/{operation_name}"]},

        # Format 10: With name field at root
        {"name": operation_name},
    ]

    # Test batch check endpoint with different payloads
    for i, payload in enumerate(payloads):
        success, result = test_format(session, batch_url, payload, f"Batch Format {i+1}")
        if success:
            log("\n" + "="*60)
            log("FOUND WORKING FORMAT!")
            log(f"Payload: {json.dumps(payload, indent=2)}")
            log("="*60)
            return result

    # Test GET operations endpoint
    log("\n" + "="*60)
    log("Testing GET operations endpoint...")
    for url in urls[1:]:  # Skip batch URL
        try:
            resp = session.get(url, timeout=30)
            log(f"GET {url}")
            log(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                result = resp.json()
                log(f"✅ SUCCESS!")
                log(f"Response: {json.dumps(result, indent=2)[:500]}")
                return result
            else:
                log(f"Response: {resp.text[:200]}")
        except Exception as e:
            log(f"Exception: {e}")

    log("\n❌ No working format found")
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_google_poll_formats.py <operation_name>")
        print("\nExample:")
        print("  python test_google_poll_formats.py 219f7e4c115a1ea38700b14104b0c4c6")
        return

    operation_name = sys.argv[1]

    print("="*60)
    print("GOOGLE API FORMAT TESTER")
    print("="*60)
    print(f"Operation: {operation_name}")
    print(f"Bearer token: {BEARER_TOKEN[:50]}...")
    print()

    result = test_all_formats(operation_name)

    if result:
        # Try to extract video URL
        print("\n" + "="*60)
        print("EXTRACTING VIDEO URL")
        print("="*60)

        video_url = None

        # Check operations array
        if "operations" in result:
            ops = result["operations"]
            if ops:
                op = ops[0]
                status = op.get("status", "")
                print(f"Status: {status}")

                if "SUCCEEDED" in status or "COMPLETE" in status:
                    # Try media array
                    media_list = op.get("media", [])
                    if media_list:
                        video_info = media_list[0].get("video", {})
                        video_url = video_info.get("url") or video_info.get("fifeUrl")

                    # Try metadata
                    if not video_url:
                        metadata = op.get("metadata", {})
                        video_info = metadata.get("video", {})
                        video_url = video_info.get("url") or video_info.get("fifeUrl")

        # Direct fields
        if not video_url:
            video_url = result.get("videoUrl") or result.get("url")

        if video_url:
            print(f"\n✅ Video URL: {video_url}")
        else:
            print("\n⚠️  No video URL found in response (video may still be processing)")


if __name__ == "__main__":
    main()
