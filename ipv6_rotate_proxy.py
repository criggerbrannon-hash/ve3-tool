#!/usr/bin/env python3
"""
IPv6 Rotating Proxy Server
==========================
Tạo SOCKS5 proxy server xoay qua danh sách IPv6 của bạn.
Chrome kết nối qua proxy này sẽ dùng IPv6 khác nhau mỗi request.
"""

import socket
import threading
import struct
import random
import time
from typing import List

# Danh sách IPv6 của bạn
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
]

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 1080

class IPv6Rotator:
    def __init__(self, ipv6_list: List[str]):
        self.ipv6_list = ipv6_list
        self.index = 0
        self.lock = threading.Lock()
        self.usage_count = {ip: 0 for ip in ipv6_list}

    def get_next(self) -> str:
        with self.lock:
            ip = self.ipv6_list[self.index]
            self.usage_count[ip] += 1
            self.index = (self.index + 1) % len(self.ipv6_list)
            return ip

    def get_random(self) -> str:
        with self.lock:
            ip = random.choice(self.ipv6_list)
            self.usage_count[ip] += 1
            return ip

    def stats(self):
        return dict(self.usage_count)


class SOCKS5Handler(threading.Thread):
    """Handle SOCKS5 connection with IPv6 source binding"""

    def __init__(self, client_socket, client_addr, rotator: IPv6Rotator):
        super().__init__()
        self.client = client_socket
        self.client_addr = client_addr
        self.rotator = rotator
        self.daemon = True

    def run(self):
        try:
            self.handle_socks5()
        except Exception as e:
            pass
        finally:
            try:
                self.client.close()
            except:
                pass

    def handle_socks5(self):
        # SOCKS5 greeting
        data = self.client.recv(262)
        if len(data) < 2 or data[0] != 0x05:
            return

        # No auth required
        self.client.send(b'\x05\x00')

        # SOCKS5 request
        data = self.client.recv(4)
        if len(data) < 4:
            return

        ver, cmd, _, atyp = data[0], data[1], data[2], data[3]

        if ver != 0x05 or cmd != 0x01:  # Only CONNECT supported
            self.client.send(b'\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00')
            return

        # Parse destination address
        if atyp == 0x01:  # IPv4
            addr_data = self.client.recv(4)
            dest_addr = socket.inet_ntoa(addr_data)
        elif atyp == 0x03:  # Domain name
            length = self.client.recv(1)[0]
            dest_addr = self.client.recv(length).decode('utf-8')
        elif atyp == 0x04:  # IPv6
            addr_data = self.client.recv(16)
            dest_addr = socket.inet_ntop(socket.AF_INET6, addr_data)
        else:
            self.client.send(b'\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00')
            return

        # Port
        port_data = self.client.recv(2)
        dest_port = struct.unpack('!H', port_data)[0]

        # Get rotating IPv6
        source_ipv6 = self.rotator.get_next()

        # Connect to destination
        try:
            # Try IPv6 first, fallback to IPv4
            try:
                remote = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                remote.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # Bind to our IPv6
                remote.bind((source_ipv6, 0))
                remote.settimeout(30)
                # For IPv4 destinations, use IPv4-mapped IPv6 address
                if atyp == 0x01:  # IPv4 destination
                    remote.close()
                    raise socket.error("Use IPv4")
                remote.connect((dest_addr, dest_port))
            except:
                # Fallback: try direct connection (for IPv4 destinations)
                remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                remote.settimeout(30)
                # Resolve domain if needed
                if atyp == 0x03:
                    dest_addr = socket.gethostbyname(dest_addr)
                remote.connect((dest_addr, dest_port))

            print(f"[PROXY] {source_ipv6} → {dest_addr}:{dest_port}")

            # Success response
            self.client.send(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')

            # Relay data
            self.relay(self.client, remote)

        except Exception as e:
            print(f"[ERROR] Connect failed: {e}")
            self.client.send(b'\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00')

    def relay(self, client, remote):
        """Relay data between client and remote"""
        client.setblocking(False)
        remote.setblocking(False)

        while True:
            try:
                # Client -> Remote
                try:
                    data = client.recv(65536)
                    if data:
                        remote.sendall(data)
                    elif data == b'':
                        break
                except BlockingIOError:
                    pass
                except:
                    break

                # Remote -> Client
                try:
                    data = remote.recv(65536)
                    if data:
                        client.sendall(data)
                    elif data == b'':
                        break
                except BlockingIOError:
                    pass
                except:
                    break

                time.sleep(0.001)

            except:
                break

        try:
            remote.close()
        except:
            pass


def main():
    print("=" * 60)
    print("  IPv6 ROTATING PROXY SERVER")
    print("=" * 60)
    print(f"\n[INFO] Loaded {len(IPV6_LIST)} IPv6 addresses")
    print(f"[INFO] Starting SOCKS5 proxy on {PROXY_HOST}:{PROXY_PORT}")
    print(f"\n[USAGE] Khởi động Chrome với proxy:")
    print(f'  chrome.exe --proxy-server="socks5://127.0.0.1:1080" --remote-debugging-port=9222')
    print("\n" + "=" * 60)

    rotator = IPv6Rotator(IPV6_LIST)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((PROXY_HOST, PROXY_PORT))
    server.listen(100)

    print(f"\n[OK] Proxy server đang chạy... (Ctrl+C để dừng)\n")

    try:
        while True:
            client, addr = server.accept()
            handler = SOCKS5Handler(client, addr, rotator)
            handler.start()
    except KeyboardInterrupt:
        print("\n\n[INFO] Đang dừng...")
        print("\n[STATS] Thống kê sử dụng IPv6:")
        for ip, count in rotator.stats().items():
            if count > 0:
                print(f"  {ip}: {count} requests")
    finally:
        server.close()


if __name__ == "__main__":
    main()
