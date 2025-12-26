#!/usr/bin/env python3
"""
VE3 Tool - Token Interceptor (No Selenium)
==========================================
Không cần Selenium, dùng Chrome DevTools Protocol trực tiếp.
"""

import sys
import json
import time
import requests as req
from pathlib import Path

try:
    import websocket
except ImportError:
    print("Cài websocket-client: pip install websocket-client")
    sys.exit(1)

OUTPUT_DIR = Path("./test_output")

INJECT_JS = """
(function() {
    if (window.__intercepted) return 'already';
    window.__intercepted = true;
    window.__captured = null;

    const orig = window.fetch;
    window.fetch = async function(url, opts) {
        if (url && url.includes('batchGenerateImages')) {
            window.__captured = {url, headers: opts?.headers || {}, body: opts?.body};
            alert('TOKEN CAPTURED! Quay lai terminal.');
            return new Response('{}', {status: 200});
        }
        return orig.apply(this, arguments);
    };
    return 'ok';
})();
"""


def main():
    print("=" * 50)
    print("  TOKEN INTERCEPTOR")
    print("=" * 50)

    print("""
BUOC 1: Dong TAT CA Chrome
BUOC 2: Mo CMD moi, paste lenh nay:

cd /d "C:\\Program Files\\Google\\Chrome\\Application" && chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\Users\\admin\\AppData\\Local\\Google\\Chrome\\User Data" --profile-directory="Profile 2" https://labs.google/fx/tools/flow

BUOC 3: Nhan Enter khi Chrome da mo...
""")
    input(">>> ")

    # Lấy websocket URL
    print("\nDang ket noi...")
    try:
        tabs = req.get("http://127.0.0.1:9222/json", timeout=5).json()
        ws_url = None
        for tab in tabs:
            if "labs.google" in tab.get("url", ""):
                ws_url = tab.get("webSocketDebuggerUrl")
                break
        if not ws_url:
            ws_url = tabs[0].get("webSocketDebuggerUrl") if tabs else None
    except Exception as e:
        print(f"KHONG KET NOI DUOC: {e}")
        print("\nKiem tra: Chrome da mo voi lenh tren chua?")
        return

    if not ws_url:
        print("Khong tim thay tab!")
        return

    print(f"OK! WebSocket: {ws_url[:50]}...")

    # Kết nối WebSocket
    ws = websocket.create_connection(ws_url)

    # Inject JS
    print("Inject interceptor...")
    ws.send(json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {"expression": INJECT_JS}
    }))
    result = json.loads(ws.recv())
    print(f"Inject: {result.get('result', {}).get('result', {}).get('value', 'error')}")

    print("""
BUOC 4: Tao anh trong Flow
   - Nhap prompt, nhan Generate
   - Se co alert 'TOKEN CAPTURED!'
""")
    print("Dang cho ban tao anh...")

    # Poll cho captured data
    while True:
        ws.send(json.dumps({
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {"expression": "JSON.stringify(window.__captured)"}
        }))
        resp = json.loads(ws.recv())
        val = resp.get("result", {}).get("result", {}).get("value")

        if val and val != "null":
            captured = json.loads(val)
            print(f"\nCAPTURED!")
            break
        time.sleep(1)

    ws.close()

    # Parse
    body = json.loads(captured["body"]) if isinstance(captured["body"], str) else captured["body"]
    headers = captured["headers"]

    bearer = headers.get("authorization", "").replace("Bearer ", "")
    x_val = headers.get("x-browser-validation", "")

    print(f"Bearer: {bearer[:30]}...{bearer[-10:]}")

    # Đổi prompt
    if "requests" in body:
        for r in body["requests"]:
            r["prompt"] = "A dragon flying over mountains"
            r["seed"] = int(time.time()) % 999999

    # Gọi API
    print("\nGoi API...")
    api_headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://labs.google",
        "Referer": "https://labs.google/",
    }
    if x_val:
        api_headers["x-browser-validation"] = x_val

    resp = req.post(captured["url"], headers=api_headers, data=json.dumps(body), timeout=120)
    print(f"Status: {resp.status_code}")

    if resp.status_code == 200:
        result = resp.json()
        if "media" in result:
            print(f"THANH CONG! {len(result['media'])} anh")
            OUTPUT_DIR.mkdir(exist_ok=True)
            for i, m in enumerate(result["media"]):
                url = m.get("image", {}).get("generatedImage", {}).get("fifeUrl")
                if url:
                    img = req.get(url).content
                    path = OUTPUT_DIR / f"dragon_{i+1}.png"
                    path.write_bytes(img)
                    print(f"   Saved: {path}")
        else:
            print(f"Khong co anh: {str(result)[:200]}")
    else:
        print(f"Loi: {resp.text[:300]}")


if __name__ == "__main__":
    main()
