#!/usr/bin/env python3
"""
VE3 Image Editor - Simple HTTP Server
Run this script to start the image editor in your browser.
"""

import http.server
import socketserver
import webbrowser
import os
import sys
from functools import partial

PORT = 8080
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class CORSHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler with CORS headers."""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[Server] {args[0]}")


def main():
    global PORT

    # Check if port is specified as argument
    if len(sys.argv) > 1:
        try:
            PORT = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port number: {sys.argv[1]}")
            sys.exit(1)

    # Change to the script directory
    os.chdir(DIRECTORY)

    handler = partial(CORSHTTPRequestHandler, directory=DIRECTORY)

    # Try to find an available port
    for port in range(PORT, PORT + 100):
        try:
            with socketserver.TCPServer(("", port), handler) as httpd:
                PORT = port
                url = f"http://localhost:{PORT}"

                print("=" * 50)
                print("  VE3 Image Editor")
                print("=" * 50)
                print(f"\n  Server running at: {url}")
                print(f"  Directory: {DIRECTORY}")
                print("\n  Press Ctrl+C to stop the server\n")
                print("=" * 50)

                # Open browser
                try:
                    webbrowser.open(url)
                except Exception:
                    print(f"\n  Please open your browser and go to: {url}")

                # Start serving
                httpd.serve_forever()

        except OSError as e:
            if e.errno == 98 or e.errno == 48:  # Port already in use
                continue
            raise
    else:
        print(f"Error: Could not find an available port in range {PORT}-{PORT + 100}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
        sys.exit(0)
