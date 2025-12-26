#!/usr/bin/env python3
"""
VE3 Tool - Test với FULL headers như browser
"""

import json
import requests
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("  VE3 FULL HEADERS TEST")
print("=" * 60)

# Input
bearer = input("[1] Bearer: ").strip().replace("Bearer ", "").replace("bearer ", "")
x_browser = input("[2] x-browser-validation: ").strip()
x_client = input("[3] x-client-data (Enter to skip): ").strip()

file_input = input("[4] Payload path (Enter=Downloads): ").strip().strip('"').strip("'")

# Find payload
locations = [Path(file_input)] if file_input else []
locations.extend([
    Path.home() / "Downloads" / "payload.json",
    Path("C:/Users/admin/Downloads/payload.json"),
])

payload = None
for loc in locations:
    try:
        if loc.exists():
            payload = json.loads(loc.read_text(encoding='utf-8'))
            print(f"✓ Loaded: {loc}")
            break
    except:
        continue

if not payload:
    print("❌ Không tìm thấy payload!")
    exit(1)

# Parse
project_id = payload["requests"][0]["clientContext"]["projectId"]
recaptcha = payload["requests"][0]["clientContext"]["recaptchaToken"]
print(f"✓ Project: {project_id}")
print(f"✓ recaptcha: {recaptcha[:40]}...")

url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

# FULL headers như browser thực
headers = {
    "accept": "*/*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9,vi;q=0.8",
    "authorization": f"Bearer {bearer}",
    "content-type": "text/plain;charset=UTF-8",
    "origin": "https://labs.google",
    "referer": "https://labs.google/",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

if x_browser:
    headers["x-browser-validation"] = x_browser
    headers["x-browser-channel"] = "stable"
    headers["x-browser-copyright"] = "Copyright 2025 Google LLC. All Rights reserved."
    headers["x-browser-year"] = "2025"

if x_client:
    headers["x-client-data"] = x_client

print(f"\n⏳ Calling API with {len(headers)} headers...")

try:
    resp = requests.post(
        url,
        headers=headers,
        data=json.dumps(payload),
        timeout=120
    )

    print(f"\n[RESULT] Status: {resp.status_code}")

    if resp.status_code == 200:
        result = resp.json()
        if "media" in result:
            print(f"✅ SUCCESS! {len(result['media'])} images")
            Path("./test_output").mkdir(exist_ok=True)
            for i, m in enumerate(result["media"]):
                img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                if img_url:
                    img = requests.get(img_url).content
                    fname = f"full_{datetime.now().strftime('%H%M%S')}_{i+1}.png"
                    Path(f"./test_output/{fname}").write_bytes(img)
                    print(f"   ✓ Saved {fname}")
        else:
            print(f"Response: {json.dumps(result, indent=2)[:500]}")
    else:
        print(f"❌ Error: {resp.text[:500]}")

except Exception as e:
    print(f"❌ Exception: {e}")
