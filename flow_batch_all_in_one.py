#!/usr/bin/env python3
"""
Google Flow - All-in-One Batch Image Generator
===============================================
Tích hợp: IPv6 Rotating Proxy + Chrome + Batch Generator
Chỉ cần chạy 1 file này!
"""

import socket
import threading
import struct
import select
import time
import json
import subprocess
import requests
from pathlib import Path
from typing import List, Optional
import sys
import os

# ============== CẤU HÌNH ==============

# Danh sách 100 IPv6 của bạn
IPV6_LIST = [
    "2001:ee0:b004:1f00::2",
    "2001:ee0:b004:1f01::2",
    "2001:ee0:b004:1f02::3",
    "2001:ee0:b004:1f03::4",
    "2001:ee0:b004:1f04::5",
    "2001:ee0:b004:1f05::6",
    "2001:ee0:b004:1f06::7",
    "2001:ee0:b004:1f07::8",
    "2001:ee0:b004:1f08::9",
    "2001:ee0:b004:1f09::10",
    "2001:ee0:b004:1f0A::11",
    "2001:ee0:b004:1f0B::12",
    "2001:ee0:b004:1f0C::13",
    "2001:ee0:b004:1f0D::14",
    "2001:ee0:b004:1f0E::15",
    "2001:ee0:b004:1f10::16",
    "2001:ee0:b004:1f11::17",
    "2001:ee0:b004:1f12::18",
    "2001:ee0:b004:1f13::19",
    "2001:ee0:b004:1f14::20",
    "2001:ee0:b004:1f15::21",
    "2001:ee0:b004:1f16::22",
    "2001:ee0:b004:1f17::23",
    "2001:ee0:b004:1f18::24",
    "2001:ee0:b004:1f19::25",
    "2001:ee0:b004:1f1A::26",
    "2001:ee0:b004:1f1B::27",
    "2001:ee0:b004:1f1C::28",
    "2001:ee0:b004:1f1D::29",
    "2001:ee0:b004:1f1E::30",
    "2001:ee0:b004:1f1F::31",
    "2001:ee0:b004:1f20::32",
    "2001:ee0:b004:1f21::33",
    "2001:ee0:b004:1f22::34",
    "2001:ee0:b004:1f23::35",
    "2001:ee0:b004:1f24::36",
    "2001:ee0:b004:1f25::37",
    "2001:ee0:b004:1f26::38",
    "2001:ee0:b004:1f27::39",
    "2001:ee0:b004:1f28::40",
    "2001:ee0:b004:1f29::41",
    "2001:ee0:b004:1f2A::42",
    "2001:ee0:b004:1f2B::43",
    "2001:ee0:b004:1f2C::44",
    "2001:ee0:b004:1f2D::45",
    "2001:ee0:b004:1f2E::46",
    "2001:ee0:b004:1f2F::47",
    "2001:ee0:b004:1f30::48",
    "2001:ee0:b004:1f31::49",
    "2001:ee0:b004:1f32::50",
    "2001:ee0:b004:1f33::51",
    "2001:ee0:b004:1f34::52",
    "2001:ee0:b004:1f35::53",
    "2001:ee0:b004:1f36::54",
    "2001:ee0:b004:1f37::55",
    "2001:ee0:b004:1f38::56",
    "2001:ee0:b004:1f39::57",
    "2001:ee0:b004:1f3A::58",
    "2001:ee0:b004:1f3B::59",
    "2001:ee0:b004:1f3C::60",
    "2001:ee0:b004:1f3D::61",
    "2001:ee0:b004:1f3E::62",
    "2001:ee0:b004:1f3F::63",
    "2001:ee0:b004:1f40::64",
    "2001:ee0:b004:1f41::65",
    "2001:ee0:b004:1f42::66",
    "2001:ee0:b004:1f43::67",
    "2001:ee0:b004:1f44::68",
    "2001:ee0:b004:1f45::69",
    "2001:ee0:b004:1f46::70",
    "2001:ee0:b004:1f47::71",
    "2001:ee0:b004:1f48::72",
    "2001:ee0:b004:1f49::73",
    "2001:ee0:b004:1f4A::74",
    "2001:ee0:b004:1f4B::75",
    "2001:ee0:b004:1f4C::76",
    "2001:ee0:b004:1f4D::77",
    "2001:ee0:b004:1f4E::78",
    "2001:ee0:b004:1f4F::79",
    "2001:ee0:b004:1f50::80",
    "2001:ee0:b004:1f51::81",
    "2001:ee0:b004:1f52::82",
    "2001:ee0:b004:1f53::83",
    "2001:ee0:b004:1f54::84",
    "2001:ee0:b004:1f55::85",
    "2001:ee0:b004:1f56::86",
    "2001:ee0:b004:1f57::87",
    "2001:ee0:b004:1f58::88",
    "2001:ee0:b004:1f59::89",
    "2001:ee0:b004:1f5A::90",
    "2001:ee0:b004:1f5B::91",
    "2001:ee0:b004:1f5C::92",
    "2001:ee0:b004:1f5D::93",
    "2001:ee0:b004:1f5E::94",
    "2001:ee0:b004:1f5F::95",
    "2001:ee0:b004:1f60::96",
    "2001:ee0:b004:1f61::97",
    "2001:ee0:b004:1f62::98",
    "2001:ee0:b004:1f63::99",
    "2001:ee0:b004:1f64::100",
]

PROXY_PORT = 1080
CHROME_DEBUG_PORT = 9222
OUTPUT_DIR = Path("./batch_output")

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

# ============== IPv6 PROXY SERVER ==============

def test_ipv6_bindable(ipv6_addr: str) -> bool:
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.bind((ipv6_addr, 0))
        sock.close()
        return True
    except:
        return False


class IPv6Rotator:
    def __init__(self, ipv6_list: List[str]):
        print("[PROXY] Testing IPv6 addresses...")
        self.ipv6_list = []
        self.failed_ips = set()

        for ip in ipv6_list:
            if test_ipv6_bindable(ip):
                self.ipv6_list.append(ip)

        if not self.ipv6_list:
            raise Exception("No bindable IPv6 addresses!")

        print(f"[PROXY] {len(self.ipv6_list)} IPv6 available")
        self.index = 0
        self.lock = threading.Lock()

    def get_next(self) -> str:
        with self.lock:
            # Skip failed IPs
            attempts = 0
            while attempts < len(self.ipv6_list):
                ip = self.ipv6_list[self.index]
                self.index = (self.index + 1) % len(self.ipv6_list)
                if ip not in self.failed_ips:
                    return ip
                attempts += 1
            # All failed, reset and try again
            self.failed_ips.clear()
            return self.ipv6_list[0]

    def mark_failed(self, ip: str):
        with self.lock:
            self.failed_ips.add(ip)
            print(f"[PROXY] Marked {ip} as failed, {len(self.ipv6_list) - len(self.failed_ips)} remaining")


class SOCKS5Handler(threading.Thread):
    def __init__(self, client_socket, rotator: IPv6Rotator):
        super().__init__()
        self.client = client_socket
        self.rotator = rotator
        self.daemon = True

    def run(self):
        try:
            self.handle_socks5()
        except:
            pass
        finally:
            try:
                self.client.close()
            except:
                pass

    def handle_socks5(self):
        self.client.settimeout(30)
        data = self.client.recv(262)
        if len(data) < 2 or data[0] != 0x05:
            return

        self.client.send(b'\x05\x00')

        data = self.client.recv(4)
        if len(data) < 4:
            return

        ver, cmd, _, atyp = data[0], data[1], data[2], data[3]

        if ver != 0x05 or cmd != 0x01:
            self.client.send(b'\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00')
            return

        if atyp == 0x01:
            addr_data = self.client.recv(4)
            dest_addr = socket.inet_ntoa(addr_data)
            is_ipv4 = True
        elif atyp == 0x03:
            length = self.client.recv(1)[0]
            dest_addr = self.client.recv(length).decode('utf-8')
            is_ipv4 = None
        elif atyp == 0x04:
            addr_data = self.client.recv(16)
            dest_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
            is_ipv4 = False
        else:
            self.client.send(b'\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00')
            return

        port_data = self.client.recv(2)
        dest_port = struct.unpack('!H', port_data)[0]

        source_ipv6 = self.rotator.get_next()

        try:
            remote = None

            if is_ipv4 is None:
                try:
                    infos = socket.getaddrinfo(dest_addr, dest_port, socket.AF_INET6, socket.SOCK_STREAM)
                    if infos:
                        dest_addr = infos[0][4][0]
                        is_ipv4 = False
                except:
                    try:
                        dest_addr = socket.gethostbyname(dest_addr)
                        is_ipv4 = True
                    except:
                        self.client.send(b'\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00')
                        return

            if is_ipv4:
                remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote.settimeout(30)
                remote.connect((dest_addr, dest_port))
            else:
                remote = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                remote.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                remote.bind((source_ipv6, 0))
                remote.settimeout(30)
                remote.connect((dest_addr, dest_port))
                # Only log Google API calls
                if 'google' in dest_addr.lower():
                    print(f"[PROXY] {source_ipv6[-15:]} → {dest_addr[:30]}")

            self.client.send(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
            self.relay(self.client, remote)

        except Exception as e:
            if source_ipv6 and 'google' in str(dest_addr).lower():
                self.rotator.mark_failed(source_ipv6)
            self.client.send(b'\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00')
        finally:
            if remote:
                try:
                    remote.close()
                except:
                    pass

    def relay(self, client, remote):
        sockets = [client, remote]
        while True:
            try:
                readable, _, exceptional = select.select(sockets, [], sockets, 60)
                if exceptional or not readable:
                    break
                for sock in readable:
                    other = remote if sock is client else client
                    try:
                        data = sock.recv(65536)
                        if data:
                            other.sendall(data)
                        else:
                            return
                    except:
                        return
            except:
                break


class ProxyServer(threading.Thread):
    def __init__(self, rotator: IPv6Rotator):
        super().__init__()
        self.rotator = rotator
        self.daemon = True
        self.server = None

    def run(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", PROXY_PORT))
        self.server.listen(100)
        print(f"[PROXY] Running on 127.0.0.1:{PROXY_PORT}")

        while True:
            try:
                client, _ = self.server.accept()
                handler = SOCKS5Handler(client, self.rotator)
                handler.start()
            except:
                break

    def stop(self):
        if self.server:
            self.server.close()


# ============== CHROME LAUNCHER ==============

def find_chrome():
    """Find Chrome executable"""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "chrome.exe"


def launch_chrome():
    """Launch Chrome with proxy and debug port"""
    chrome_path = find_chrome()
    cmd = [
        chrome_path,
        f"--proxy-server=socks5://127.0.0.1:{PROXY_PORT}",
        f"--remote-debugging-port={CHROME_DEBUG_PORT}",
        "--no-first-run",
        "--disable-default-apps",
    ]
    print(f"[CHROME] Launching with proxy...")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)


# ============== BATCH GENERATOR ==============

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    HAS_DRISSION = True
except ImportError:
    HAS_DRISSION = False

JS_INTERCEPTOR = '''
(function(){
    if(window.__batchReady) return 'READY';
    window.__batchReady = true;
    window.__images = [];
    window.__imageTime = 0;
    window.__lastError = null;

    const origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        const response = await origFetch.apply(this, arguments);
        const urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('batchGenerateImages')) {
            try {
                const clone = response.clone();
                const data = await clone.json();

                if (response.status !== 200) {
                    window.__lastError = data.error?.message || 'API Error ' + response.status;
                    console.log('[BATCH] Error:', window.__lastError);
                } else if (data.media && data.media.length > 0) {
                    window.__images = [];
                    window.__lastError = null;
                    for (const m of data.media) {
                        const imgUrl = m.image?.generatedImage?.fifeUrl;
                        if (imgUrl) window.__images.push(imgUrl);
                    }
                    window.__imageTime = Date.now();
                    console.log('[BATCH] Got', window.__images.length, 'images');
                }
            } catch(e) {
                window.__lastError = e.message;
            }
        }
        return response;
    };
    return 'READY';
})();
'''


class BatchGenerator:
    def __init__(self):
        self.driver = None
        self.stats = {"total": 0, "success": 0, "failed": 0}

    def connect_chrome(self):
        if not HAS_DRISSION:
            print("[ERROR] Install DrissionPage: pip install DrissionPage")
            return False

        print("[CHROME] Connecting to debug port...")
        options = ChromiumOptions()
        try:
            options.set_local_port(CHROME_DEBUG_PORT)
            self.driver = ChromiumPage(addr_or_opts=options)
            print(f"[CHROME] Connected: {self.driver.url[:50]}...")
            return True
        except Exception as e:
            print(f"[ERROR] {e}")
            return False

    def setup_interceptor(self):
        print("[BATCH] Setting up interceptor...")
        result = self.driver.run_js(JS_INTERCEPTOR)
        return result == 'READY'

    def find_textarea(self):
        for sel in ["tag:textarea", "css:textarea"]:
            try:
                el = self.driver.ele(sel, timeout=2)
                if el:
                    return el
            except:
                pass
        return None

    def wait_for_images(self, timeout=120):
        start = time.time()
        last_time = self.driver.run_js("return window.__imageTime || 0;")

        while time.time() - start < timeout:
            # Check for errors
            error = self.driver.run_js("return window.__lastError;")
            if error:
                self.driver.run_js("window.__lastError = null;")
                return None, error

            current = self.driver.run_js("return window.__imageTime || 0;")
            if current > last_time:
                images = self.driver.run_js("return window.__images || [];")
                self.driver.run_js("window.__images = []; window.__imageTime = 0;")
                return images, None
            time.sleep(0.5)

        return [], "Timeout"

    def download_images(self, urls, idx):
        saved = []
        for i, url in enumerate(urls):
            try:
                resp = requests.get(url, timeout=60)
                if resp.status_code == 200:
                    filename = f"batch_{idx:03d}_{i+1}.png"
                    (OUTPUT_DIR / filename).write_bytes(resp.content)
                    saved.append(filename)
            except:
                pass
        return saved

    def run_batch(self, prompts):
        OUTPUT_DIR.mkdir(exist_ok=True)

        print("\n" + "=" * 50)
        print("  BATCH IMAGE GENERATION")
        print("  Script nhập prompt, BẠN CLICK Generate")
        print("=" * 50)

        for idx, prompt in enumerate(prompts, 1):
            self.stats["total"] += 1
            short = prompt[:40] + "..." if len(prompt) > 40 else prompt
            print(f"\n[{idx}/{len(prompts)}] {short}")

            # Find and fill textarea
            textarea = self.find_textarea()
            if not textarea:
                print("    ✗ Không tìm thấy textarea")
                self.stats["failed"] += 1
                continue

            textarea.clear()
            textarea.input(prompt)
            print("    ✓ Đã nhập prompt")

            print("    → CLICK 'Generate' TRONG CHROME...")

            # Wait for response
            images, error = self.wait_for_images(timeout=120)

            if error:
                print(f"    ✗ Lỗi: {error}")
                self.stats["failed"] += 1

                # If IP blocked, wait a bit
                if "403" in str(error) or "blocked" in str(error).lower():
                    print("    → IP bị block, đợi 5s rồi thử lại...")
                    time.sleep(5)
                continue

            if not images:
                print("    ✗ Không có ảnh")
                self.stats["failed"] += 1
                continue

            # Download images
            saved = self.download_images(images, idx)
            if saved:
                print(f"    ✓ Đã lưu {len(saved)} ảnh: {', '.join(saved)}")
                self.stats["success"] += 1
            else:
                print("    ✗ Lỗi download")
                self.stats["failed"] += 1

            time.sleep(1)

        # Summary
        print("\n" + "=" * 50)
        print("  KẾT QUẢ")
        print("=" * 50)
        print(f"  Tổng: {self.stats['total']}")
        print(f"  Thành công: {self.stats['success']}")
        print(f"  Thất bại: {self.stats['failed']}")
        print(f"  Ảnh lưu tại: {OUTPUT_DIR.absolute()}")


# ============== MAIN ==============

def main():
    print("=" * 60)
    print("  GOOGLE FLOW - ALL-IN-ONE BATCH GENERATOR")
    print("  IPv6 Rotating Proxy + Chrome + Batch Generator")
    print("=" * 60)
    print()

    # Step 1: Start proxy
    try:
        rotator = IPv6Rotator(IPV6_LIST)
    except Exception as e:
        print(f"[ERROR] {e}")
        print("\n[TIP] Run as Admin:")
        print("  powershell -ExecutionPolicy Bypass -File add_ipv6_windows.ps1")
        return

    proxy = ProxyServer(rotator)
    proxy.start()
    time.sleep(1)

    # Step 2: Check if Chrome already running on debug port
    already_running = False
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{CHROME_DEBUG_PORT}/json", timeout=2)
        already_running = True
        print("[CHROME] Already running with debug port")
    except:
        pass

    if not already_running:
        launch_chrome()

    # Step 3: Connect and run batch
    generator = BatchGenerator()

    print("\n[INFO] Hãy mở Google Flow trong Chrome và đăng nhập")
    print("[INFO] Sau đó nhấn ENTER để tiếp tục...")
    input()

    if not generator.connect_chrome():
        return

    if "/project/" not in generator.driver.url:
        print("[WARN] Hãy mở một project trong Flow trước!")
        print("[INFO] Nhấn ENTER khi đã sẵn sàng...")
        input()

    if not generator.setup_interceptor():
        print("[ERROR] Không thể setup interceptor")
        return

    # Run batch
    generator.run_batch(DEFAULT_PROMPTS)

    print("\n[INFO] Hoàn tất! Nhấn Ctrl+C để thoát.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
