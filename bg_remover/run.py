#!/usr/bin/env python3
"""
BG Remover Pro - Launcher
=========================
Start the application with auto-reload support
"""

import os
import sys
import time
import webbrowser
import subprocess
import threading
from pathlib import Path

# Config
HOST = '127.0.0.1'
PORT = 5000
DEBUG = True
AUTO_OPEN_BROWSER = True

def check_dependencies():
    """Check and install required dependencies."""
    required = ['flask', 'flask_cors', 'flask_socketio', 'PIL', 'numpy']
    missing = []

    for pkg in required:
        try:
            if pkg == 'PIL':
                import PIL
            else:
                __import__(pkg.replace('-', '_'))
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Installing...")

        req_file = Path(__file__).parent / 'requirements.txt'
        if req_file.exists():
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(req_file)])
        else:
            for pkg in missing:
                if pkg == 'PIL':
                    pkg = 'pillow'
                subprocess.run([sys.executable, '-m', 'pip', 'install', pkg])

        print("Dependencies installed!")
        return True

    return False

def open_browser_delayed(url, delay=1.5):
    """Open browser after delay."""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()

def print_banner():
    """Print startup banner."""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║   ██████╗  ██████╗    ██████╗ ███████╗███╗   ███╗ ██████╗    ║
    ║   ██╔══██╗██╔════╝    ██╔══██╗██╔════╝████╗ ████║██╔═══██╗   ║
    ║   ██████╔╝██║  ███╗   ██████╔╝█████╗  ██╔████╔██║██║   ██║   ║
    ║   ██╔══██╗██║   ██║   ██╔══██╗██╔══╝  ██║╚██╔╝██║██║   ██║   ║
    ║   ██████╔╝╚██████╔╝   ██║  ██║███████╗██║ ╚═╝ ██║╚██████╔╝   ║
    ║   ╚═════╝  ╚═════╝    ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝    ║
    ║                                                              ║
    ║   🎨 AI-Powered Background Removal & 4K Upscaling            ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def main():
    """Main entry point."""
    print_banner()

    # Check dependencies
    if check_dependencies():
        print("\nRestarting with new dependencies...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    print(f"\n🚀 Starting BG Remover Pro...")
    print(f"📍 URL: http://{HOST}:{PORT}")
    print(f"🔄 Hot Reload: {'Enabled' if DEBUG else 'Disabled'}")
    print(f"\nPress Ctrl+C to stop\n")
    print("=" * 60)

    # Open browser
    if AUTO_OPEN_BROWSER:
        open_browser_delayed(f'http://{HOST}:{PORT}')

    # Start server
    try:
        from app import run_server
        run_server(host=HOST, port=PORT, debug=DEBUG)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTry running: pip install -r requirements.txt")

if __name__ == '__main__':
    main()
