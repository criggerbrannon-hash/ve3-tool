#!/usr/bin/env python3
"""
Kết hợp: JS chặn request + copy Authorization header thủ công
"""

import json
import requests
from pathlib import Path

print("""
==================================================
  BƯỚC 1: Lấy Authorization header TRƯỚC
==================================================
  - F12 → Network → tạo 1 ảnh bất kỳ
  - Copy "authorization: Bearer ya29.xxx..."
==================================================
""")

bearer = input("Paste Authorization: ").strip()
if bearer.startswith("Bearer "):
    bearer = bearer[7:]
if not bearer.startswith("ya29."):
    print("Sai! Phải là ya29.xxx")
    exit()

print(f"✓ Bearer OK")

print("""
==================================================
  BƯỚC 2: Paste JS vào Console (F12 → Console)
==================================================
""")

print('''(function(){
  window.fetch = async (url, opts) => {
    if (url.includes('batchGenerateImages')) {
      navigator.clipboard.writeText(opts.body);
      alert("PAYLOAD DA COPY! Paste vao terminal.");
      return new Response('{}');
    }
    return window.__origFetch(url, opts);
  };
  window.__origFetch = window.__origFetch || fetch;
  alert("OK! Tao anh di.");
})();''')

print("""
==================================================
  BƯỚC 3: Tạo ảnh → Alert "PAYLOAD DA COPY"
  BƯỚC 4: Paste payload vào đây (Ctrl+V, Enter)
==================================================
""")

payload_str = input("Payload: ").strip()
if not payload_str:
    print("Không có payload!")
    exit()

try:
    payload = json.loads(payload_str)
except:
    print("JSON không hợp lệ!")
    exit()

project_id = payload.get("requests", [{}])[0].get("clientContext", {}).get("projectId", "")
url = f"https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"

print(f"✓ Project: {project_id}")

# Đổi prompt
for r in payload.get("requests", []):
    r["prompt"] = "A majestic dragon over mountains, 4k"
    r["seed"] = 888888

print("✓ Prompt: dragon")
print("\n⏳ Gọi API...")

resp = requests.post(url, headers={
    "Authorization": f"Bearer {bearer}",
    "Content-Type": "text/plain;charset=UTF-8",
    "Origin": "https://labs.google",
    "Referer": "https://labs.google/",
}, data=json.dumps(payload), timeout=120)

print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    result = resp.json()
    if "media" in result:
        print(f"✅ THÀNH CÔNG! {len(result['media'])} ảnh")
        Path("./test_output").mkdir(exist_ok=True)
        for i, m in enumerate(result["media"]):
            u = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
            if u:
                Path(f"./test_output/dragon_{i+1}.png").write_bytes(requests.get(u).content)
                print(f"   💾 dragon_{i+1}.png")
elif resp.status_code == 403:
    print("❌ 403 - Token hết hạn hoặc đã dùng")
    print(resp.text[:200])
else:
    print(f"❌ {resp.text[:200]}")
