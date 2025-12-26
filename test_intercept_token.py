#!/usr/bin/env python3
"""
Lấy token thủ công từ Chrome DevTools
"""

import json
import requests
from pathlib import Path

print("""
==================================================
  BƯỚC 1: Mở Chrome → Flow → F12 → Network tab
  BƯỚC 2: Tạo ảnh trong Flow
  BƯỚC 3: Tìm request "batchGenerateImages"
  BƯỚC 4: Click vào → Headers tab
  BƯỚC 5: Copy "authorization" header (Bearer ya29.xxx...)
==================================================
""")

bearer = input("Paste Authorization header: ").strip()
if bearer.startswith("Bearer "):
    bearer = bearer[7:]

if not bearer or not bearer.startswith("ya29."):
    print("Token không hợp lệ! Phải bắt đầu bằng ya29.")
    exit()

print(f"\n✓ Token: {bearer[:30]}...{bearer[-10:]}")

print("""
==================================================
  BƯỚC 6: Click Payload tab
  BƯỚC 7: Right-click → Copy value (hoặc copy thủ công)
==================================================
""")

print("Paste request payload (JSON):")
lines = []
while True:
    line = input()
    if line.strip() == "":
        break
    lines.append(line)

payload_str = "".join(lines)

try:
    payload = json.loads(payload_str)
except:
    print("Payload không hợp lệ!")
    exit()

# Lấy URL từ payload
project_id = payload.get("requests", [{}])[0].get("clientContext", {}).get("projectId", "")
url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

print(f"\n✓ Project: {project_id}")

# Đổi prompt
for r in payload.get("requests", []):
    r["prompt"] = "A dragon flying over mountains, fantasy art, 4k"
    r["seed"] = 999999

print("✓ Prompt: A dragon flying over mountains")

# Gọi API
print("\n⏳ Gọi API...")

resp = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
    },
    data=json.dumps(payload),
    timeout=120
)

print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    result = resp.json()
    if "media" in result:
        print(f"\n✅ THÀNH CÔNG! {len(result['media'])} ảnh")
        Path("./test_output").mkdir(exist_ok=True)
        for i, m in enumerate(result["media"]):
            img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
            if img_url:
                Path(f"./test_output/dragon_{i+1}.png").write_bytes(requests.get(img_url).content)
                print(f"   💾 ./test_output/dragon_{i+1}.png")
    else:
        print(f"Không có ảnh: {str(result)[:200]}")
else:
    print(f"❌ Lỗi: {resp.text[:300]}")
