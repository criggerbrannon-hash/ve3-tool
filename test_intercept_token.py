#!/usr/bin/env python3
"""
CÁCH DÙNG:
1. Mở Chrome bình thường, vào https://labs.google/fx/tools/flow
2. F12 → Console tab
3. Paste đoạn JS bên dưới vào Console, nhấn Enter
4. Tạo ảnh trong Flow
5. Copy dữ liệu từ alert/console
6. Chạy script này và paste vào
"""

import json
import requests
from pathlib import Path

print("""
==================================================
  BƯỚC 1: Paste đoạn JS này vào Chrome Console
==================================================

""")

JS_CODE = '''
(function(){
  const orig = fetch;
  window.fetch = async (url, opts) => {
    if (url.includes('batchGenerateImages')) {
      let h = {};
      if (opts.headers) {
        if (opts.headers.forEach) opts.headers.forEach((v,k) => h[k]=v);
        else h = opts.headers;
      }
      const data = btoa(unescape(encodeURIComponent(JSON.stringify({url, headers: h, body: opts.body}))));

      // Copy to clipboard
      navigator.clipboard.writeText(data).then(() => {
        alert("DA COPY VAO CLIPBOARD! Quay lai terminal paste.");
      });

      return new Response('{"blocked":true}');
    }
    return orig(url, opts);
  };
  alert("OK! Gio tao anh di.");
})();
'''

print(JS_CODE)

print("""
==================================================
  BƯỚC 2: Tạo ảnh trong Flow
  BƯỚC 3: Copy dữ liệu từ prompt/console
  BƯỚC 4: Paste vào đây
==================================================
""")

data = input("Paste data: ").strip()

if not data:
    print("Không có data!")
    exit()

# Decode
try:
    import base64
    decoded = json.loads(base64.b64decode(data).decode())
except:
    print("Data không hợp lệ!")
    exit()

url = decoded["url"]
headers = decoded["headers"]
body = json.loads(decoded["body"]) if isinstance(decoded["body"], str) else decoded["body"]

bearer = headers.get("authorization", "").replace("Bearer ", "")
print(f"\nBearer: {bearer[:30]}...{bearer[-10:]}")

# Đổi prompt
if "requests" in body:
    for r in body["requests"]:
        r["prompt"] = "A dragon flying over mountains"
        r["seed"] = 123456

# Gọi API
print("\nGọi API...")
resp = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
        "x-browser-validation": headers.get("x-browser-validation", ""),
    },
    data=json.dumps(body),
    timeout=120
)

print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    result = resp.json()
    if "media" in result:
        print(f"THÀNH CÔNG! {len(result['media'])} ảnh")
        Path("./test_output").mkdir(exist_ok=True)
        for i, m in enumerate(result["media"]):
            img_url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
            if img_url:
                Path(f"./test_output/img_{i+1}.png").write_bytes(requests.get(img_url).content)
                print(f"   Saved: ./test_output/img_{i+1}.png")
    else:
        print(f"Không có ảnh")
else:
    print(f"Lỗi: {resp.text[:300]}")
