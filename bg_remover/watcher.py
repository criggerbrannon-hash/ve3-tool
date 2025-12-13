#!/usr/bin/env python3
"""
File Watcher - Auto Reload on Changes
=====================================
Watches for file changes and triggers reload
"""

import os
import sys
import time
import subprocess
import threading
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, PatternMatchingEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    print("Note: Install 'watchdog' for file watching: pip install watchdog")

class CodeChangeHandler(PatternMatchingEventHandler):
    """Handle file changes in the project."""

    patterns = ["*.py", "*.html", "*.css", "*.js"]
    ignore_directories = True
    ignore_patterns = ["*.pyc", "__pycache__/*", "*.log", "venv/*", ".git/*"]

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.last_modified = 0
        self.debounce_seconds = 1  # Prevent multiple reloads

    def on_modified(self, event):
        """Handle file modification."""
        current_time = time.time()
        if current_time - self.last_modified > self.debounce_seconds:
            self.last_modified = current_time
            print(f"\n🔄 File changed: {event.src_path}")
            self.callback()

    def on_created(self, event):
        """Handle file creation."""
        print(f"\n📄 File created: {event.src_path}")
        self.callback()


class ServerManager:
    """Manage the Flask server process."""

    def __init__(self, script_path):
        self.script_path = script_path
        self.process = None
        self.lock = threading.Lock()

    def start(self):
        """Start the server."""
        with self.lock:
            if self.process:
                self.stop()

            print("\n🚀 Starting server...")
            self.process = subprocess.Popen(
                [sys.executable, self.script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True
            )

            # Stream output in background
            def stream_output():
                try:
                    for line in self.process.stdout:
                        print(line, end='')
                except:
                    pass

            threading.Thread(target=stream_output, daemon=True).start()

    def stop(self):
        """Stop the server."""
        with self.lock:
            if self.process:
                print("\n⏹️  Stopping server...")
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                self.process = None

    def restart(self):
        """Restart the server."""
        print("\n♻️  Restarting server...")
        self.stop()
        time.sleep(0.5)
        self.start()


def run_watcher():
    """Run the file watcher."""
    if not HAS_WATCHDOG:
        print("Watchdog not installed. Running without file watching.")
        print("Install with: pip install watchdog")
        # Just run the app directly
        os.system(f"{sys.executable} app.py")
        return

    base_dir = Path(__file__).parent
    app_script = str(base_dir / "app.py")

    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║          BG REMOVER PRO - Development Mode                 ║
    ║                                                            ║
    ║    🔄 Auto-reload enabled                                  ║
    ║    👀 Watching for file changes...                         ║
    ║                                                            ║
    ║    Press Ctrl+C to stop                                    ║
    ╚════════════════════════════════════════════════════════════╝
    """)

    server = ServerManager(app_script)
    server.start()

    # Setup file watcher
    handler = CodeChangeHandler(callback=server.restart)
    observer = Observer()
    observer.schedule(handler, str(base_dir), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down watcher...")
        observer.stop()
        server.stop()

    observer.join()


if __name__ == '__main__':
    run_watcher()
