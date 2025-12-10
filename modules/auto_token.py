"""
VE3 Tool - Auto Token v15
=========================
Flow:
1. Mo Chrome (minimized)
2. DevTools -> Inject capture -> DONG DevTools
3. PyAutoGUI: Click dropdown -> Click "Tao hinh anh" -> Click textarea -> Paste -> Enter
4. Doi
5. DevTools -> Lay token -> Dong
6. TAT Chrome

Updates v15:
- Auto close Chrome sau khi lay token
- Chay minimized mac dinh, chi restore khi can tuong tac
- Giam thoi gian doi
"""

import sys
import time
import subprocess
import os
from pathlib import Path
from typing import Optional, Tuple, Callable

# Windows-specific imports for window management
try:
    import ctypes
    from ctypes import wintypes
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False

try:
    import pyautogui as pag
    pag.FAILSAFE = True
    pag.PAUSE = 0.1
except ImportError:
    pag = None

try:
    import pyperclip
except ImportError:
    pyperclip = None


class ChromeAutoToken:
    """Auto lay token voi Chrome minimized."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        headless: bool = False,
        auto_close: bool = True  # Auto close Chrome after getting token
    ):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.headless = headless
        self.auto_close = auto_close
        self.callback = None
        self.chrome_process = None  # Track Chrome process to close later
    
    def log(self, msg: str):
        print(f"[AutoToken] {msg}")
        if self.callback:
            self.callback(msg)

    def close_chrome(self):
        """Dong Chrome process da mo."""
        if self.chrome_process:
            try:
                self.log("Dong Chrome...")
                self.chrome_process.terminate()
                # Doi 2s roi force kill neu can
                try:
                    self.chrome_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.chrome_process.kill()
                self.chrome_process = None
                self.log("Chrome da dong")
            except Exception as e:
                self.log(f"Loi dong Chrome: {e}")
                # Fallback: kill by window title
                try:
                    if os.name == 'nt':
                        os.system('taskkill /F /IM chrome.exe /T 2>nul')
                except:
                    pass

    def minimize_chrome(self):
        """Thu nho cua so Chrome."""
        if not HAS_CTYPES or os.name != 'nt':
            return
        try:
            # Find Chrome window and minimize
            hwnd = ctypes.windll.user32.FindWindowW(None, None)
            # Alt+Space, N to minimize active window
            if pag:
                pag.hotkey('win', 'down')  # Minimize
        except:
            pass

    def restore_chrome(self):
        """Phuc hoi cua so Chrome tu minimized."""
        if not HAS_CTYPES or os.name != 'nt':
            return
        try:
            if pag:
                # Use Alt+Tab to bring Chrome to front
                pag.hotkey('alt', 'tab')
                time.sleep(0.3)
        except:
            pass

    def open_chrome(self, url: str, minimized: bool = False) -> bool:
        """Mo Chrome va track process de dong sau."""
        try:
            cmd = [self.chrome_path]
            if self.profile_path and Path(self.profile_path).exists():
                cmd.extend([
                    f"--user-data-dir={Path(self.profile_path).parent}",
                    f"--profile-directory={Path(self.profile_path).name}"
                ])

            # Disable unnecessary features for faster startup
            cmd.extend([
                "--disable-extensions",
                "--disable-plugins",
                "--disable-sync",
                "--no-first-run",
                "--disable-default-apps",
            ])

            # Minimized mode - start small window at corner
            if minimized or self.headless:
                cmd.extend([
                    "--window-size=800,600",
                    "--window-position=0,0",
                ])

            cmd.append(url)

            # Track process to close later
            self.chrome_process = subprocess.Popen(cmd, shell=False)
            self.log(f"Chrome PID: {self.chrome_process.pid}")
            return True
        except Exception as e:
            self.log(f"Loi: {e}")
            return False
    
    def inject_capture_only(self) -> bool:
        """
        Mo DevTools, inject SCRIPT CAPTURE, dong DevTools ngay.
        Script chi de hook fetch, KHONG lam gi khac.
        """
        if not pag or not pyperclip:
            return False
        
        self.log("Inject capture script...")
        
        # Script chi hook fetch de capture token
        capture_script = '''window._tk=null;window._pj=null;(function(){var f=window.fetch;window.fetch=function(u,o){var s=u?u.toString():'';if(s.includes('flowMedia')||s.includes('aisandbox')){var h=o&&o.headers?o.headers:{};var a=h.Authorization||h.authorization||'';if(a.startsWith('Bearer ')){window._tk=a.substring(7);var m=s.match(/\\/projects\\/([^\\/]+)\\//);if(m)window._pj=m[1];console.log('TOKEN CAPTURED!');}}return f.apply(this,arguments);};console.log('Capture ready');})();'''
        
        try:
            # Mo DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)
            
            # Paste va chay
            pyperclip.copy(capture_script)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)
            
            # DONG DevTools NGAY
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            
            self.log("Capture script injected, DevTools closed")
            return True
        except Exception as e:
            self.log(f"Inject error: {e}")
            return False
    
    def click_new_project_js(self) -> bool:
        """Click 'Du an moi' bang JS (DevTools)."""
        if not pag or not pyperclip:
            return False
        
        js = '''(function(){var btns=document.querySelectorAll('button');for(var b of btns){if(b.textContent.includes('Dự án mới')){b.click();console.log('Clicked Du an moi');return true;}}return false;})();'''
        
        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            return True
        except:
            return False
    
    def click_image_mode_js(self) -> bool:
        """Click dropdown va chon 'Tao hinh anh' bang JS."""
        if not pag or not pyperclip:
            return False
        
        # Script click dropdown roi click option
        js = '''(async function(){var dd=document.querySelector('button[role="combobox"]');if(dd){dd.click();await new Promise(r=>setTimeout(r,500));var all=document.querySelectorAll('*');for(var el of all){var t=el.textContent||'';if(t==='Tạo hình ảnh'||t.includes('Tạo hình ảnh từ văn bản')){var r=el.getBoundingClientRect();if(r.height>10&&r.height<80){el.click();console.log('Clicked: '+t.substring(0,40));return true;}}}}return false;})();'''
        
        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            return True
        except:
            return False
    
    def focus_textarea_js(self) -> bool:
        """Dung JS de focus vao textarea, sau do dong DevTools."""
        if not pag or not pyperclip:
            return False
        
        js = '''(function(){var ta=document.querySelector('textarea');if(ta){ta.focus();ta.click();console.log('Textarea focused');return true;}return false;})();'''
        
        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.5)
            pag.hotkey("ctrl", "shift", "j")  # DONG DevTools
            time.sleep(0.5)
            return True
        except:
            return False
    
    def send_prompt_manual(self, prompt: str) -> bool:
        """
        Gui prompt BANG PYAUTOGUI.
        Textarea da duoc focus bang JS truoc do.
        DevTools phai DONG truoc khi goi ham nay!
        """
        if not pag or not pyperclip:
            return False
        
        self.log("Gui prompt (PyAutoGUI)...")
        
        try:
            # Textarea da focus, chi can paste va enter
            
            # Paste prompt
            pyperclip.copy(prompt)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.5)
            
            self.log("Da paste prompt, nhan Enter...")
            
            # ENTER de gui
            pag.press("enter")
            time.sleep(0.5)
            
            self.log("Prompt sent!")
            return True
        except Exception as e:
            self.log(f"Send prompt error: {e}")
            return False
    
    def get_token_from_devtools(self) -> Tuple[Optional[str], Optional[str]]:
        """Mo DevTools, lay token, dong."""
        if not pag or not pyperclip:
            return None, None
        
        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.2)
            
            js = 'copy(JSON.stringify({t:window._tk,p:window._pj}))'
            pyperclip.copy(js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(0.8)
            
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)
            
            import json
            try:
                text = pyperclip.paste()
                if text and text.startswith('{'):
                    data = json.loads(text)
                    tk = data.get("t")
                    pj = data.get("p")
                    if tk and len(str(tk)) > 50:
                        return tk, pj
            except:
                pass
            return None, None
        except:
            return None, None
    
    def extract_token(
        self,
        project_id: str = None,
        callback: Callable = None,
        timeout: int = 60  # Reduced from 90
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Main function - lay token roi DONG Chrome.

        Returns: (token, project_id, error_message)
        """
        self.callback = callback

        if not pag:
            return None, None, "Thieu pyautogui"
        if not pyperclip:
            return None, None, "Thieu pyperclip"

        token = None
        proj = None
        error = ""

        try:
            # === 1. Mo Chrome ===
            url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}" if project_id else self.FLOW_URL
            self.log("Mo Chrome...")

            if not self.open_chrome(url):
                return None, None, "Khong mo duoc Chrome"

            # === 2. Doi trang load (giam tu 12s -> 8s) ===
            self.log("Doi trang load (8s)...")
            time.sleep(8)

            # === 3. Inject capture (DevTools mo roi dong) ===
            self.inject_capture_only()
            time.sleep(0.5)

            # === 4. Click "Du an moi" (JS) ===
            if not project_id:
                self.log("Click Du an moi...")
                self.click_new_project_js()
                self.log("Doi 3s...")
                time.sleep(3)

            # === 5. Click dropdown + chon "Tao hinh anh" (JS) ===
            self.log("Chon mode Tao hinh anh...")
            self.click_image_mode_js()
            time.sleep(2)

            # === 6. Focus textarea (JS) ===
            self.log("Focus textarea...")
            self.focus_textarea_js()
            time.sleep(0.5)

            # === 7. Gui prompt BANG PYAUTOGUI ===
            prompt = "beautiful sunset over ocean with golden clouds and birds flying"
            self.send_prompt_manual(prompt)

            # === 8. Doi token (giam tu 60s -> 45s) ===
            self.log("Doi capture token (45s max)...")

            for i in range(15):  # 15 * 3s = 45s max
                time.sleep(3)
                self.log(f"Kiem tra #{i+1}...")

                token, proj = self.get_token_from_devtools()

                if token:
                    self.log("=== DA LAY DUOC TOKEN! ===")
                    break

            if not token:
                error = "Khong lay duoc token. Thu lai."

        except Exception as e:
            error = f"Loi: {e}"

        finally:
            # === 9. DONG Chrome (QUAN TRONG!) ===
            if self.auto_close:
                time.sleep(0.5)
                self.close_chrome()

        return token, proj or project_id, error


# Aliases
FlowAutoToken = ChromeAutoToken

def get_flow_token(chrome_path=None, profile_path=None, project_id=None, callback=None):
    return ChromeAutoToken(chrome_path, profile_path).extract_token(project_id, callback)
