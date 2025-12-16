"""
VE3 Tool - Auto Token v16
=========================
Flow:
1. Mo Chrome (HIDDEN - off screen)
2. DevTools -> Inject capture -> DONG DevTools
3. PyAutoGUI: Click dropdown -> Click "Tao hinh anh" -> Click textarea -> Paste -> Enter
4. Doi
5. DevTools -> Lay token -> Dong
6. TAT Chrome

Updates v16:
- Chrome chay AN (off-screen) - khong hien thi tren man hinh
- Tu dong minimize ngay sau khi tuong tac xong
- Nhanh hon, it anh huong user
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

    # Windows API constants
    SW_HIDE = 0
    SW_MINIMIZE = 6
    SW_SHOW = 5
    SW_RESTORE = 9

    user32 = ctypes.windll.user32
    HAS_CTYPES = True
except ImportError:
    HAS_CTYPES = False

try:
    import pyautogui as pag
    pag.FAILSAFE = True
    pag.PAUSE = 0.05  # Faster - giam tu 0.1 -> 0.05
except ImportError:
    pag = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

# Load prompts from config
try:
    from modules.prompts_loader import get_test_prompt
except ImportError:
    def get_test_prompt():
        return "beautiful sunset over ocean"


class ChromeAutoToken:
    """Auto lay token voi Chrome HIDDEN (off-screen)."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        headless: bool = False,
        auto_close: bool = True,
        hidden: bool = True  # NEW: Chay an mac dinh
    ):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.headless = headless
        self.auto_close = auto_close
        self.hidden = hidden
        self.callback = None
        self.chrome_process = None
        self.chrome_hwnd = None  # Track window handle

    def log(self, msg: str):
        print(f"[AutoToken] {msg}")
        if self.callback:
            self.callback(msg)

    def find_chrome_window(self, timeout: int = 5) -> Optional[int]:
        """Tim Chrome window handle."""
        if not HAS_CTYPES or os.name != 'nt':
            return None

        start = time.time()
        found_windows = []  # List luu ket qua

        # Callback dung closure de truy cap found_windows
        def enum_callback(hwnd, lParam):
            try:
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        if 'Google' in title or 'Chrome' in title or 'Flow' in title:
                            found_windows.append(hwnd)
            except:
                pass
            return True

        # Tao callback type dung
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        callback = WNDENUMPROC(enum_callback)

        while time.time() - start < timeout:
            found_windows.clear()
            user32.EnumWindows(callback, 0)

            if found_windows:
                self.chrome_hwnd = found_windows[0]
                return self.chrome_hwnd
            time.sleep(0.5)
        return None

    def hide_chrome_window(self):
        """An cua so Chrome (off-screen)."""
        if not HAS_CTYPES or os.name != 'nt':
            return
        try:
            if self.chrome_hwnd:
                # Di chuyen off-screen thay vi hide hoan toan
                user32.SetWindowPos(self.chrome_hwnd, 0, -2000, -2000, 800, 600, 0)
        except:
            pass

    def show_chrome_window(self):
        """Hien Chrome window de tuong tac."""
        if not HAS_CTYPES or os.name != 'nt':
            return
        try:
            if self.chrome_hwnd:
                # Move to visible area
                user32.SetWindowPos(self.chrome_hwnd, 0, 50, 50, 900, 700, 0)
                user32.SetForegroundWindow(self.chrome_hwnd)
        except:
            pass

    def minimize_chrome_window(self):
        """Minimize Chrome sau khi xong."""
        if not HAS_CTYPES or os.name != 'nt':
            return
        try:
            if self.chrome_hwnd:
                user32.ShowWindow(self.chrome_hwnd, SW_MINIMIZE)
        except:
            pass

    def close_chrome(self):
        """Dong Chrome bang Ctrl+W."""
        try:
            self.log("Dong Chrome (Ctrl+W)...")

            # Hien window truoc khi dong
            if self.chrome_hwnd and HAS_CTYPES:
                user32.SetForegroundWindow(self.chrome_hwnd)
                time.sleep(0.3)

            # Ctrl+W dong tab/window
            if pag:
                pag.hotkey('ctrl', 'w')
                time.sleep(0.5)

            self.chrome_process = None
            self.chrome_hwnd = None
            self.log("Chrome da dong")
        except Exception as e:
            self.log(f"Loi dong Chrome: {e}")

    def open_chrome(self, url: str) -> bool:
        """Mo Chrome - an hoac hien tuy thuan hidden setting."""
        try:
            cmd = [self.chrome_path]
            if self.profile_path and Path(self.profile_path).exists():
                cmd.extend([
                    f"--user-data-dir={Path(self.profile_path).parent}",
                    f"--profile-directory={Path(self.profile_path).name}"
                ])

            # Disable unnecessary features
            cmd.extend([
                "--disable-extensions",
                "--disable-plugins",
                "--disable-sync",
                "--no-first-run",
                "--disable-default-apps",
                "--disable-background-networking",
                "--disable-client-side-phishing-detection",
            ])

            # Start off-screen if hidden mode
            if self.hidden:
                cmd.extend([
                    "--window-size=900,700",
                    "--window-position=-2000,-2000",  # Off-screen
                ])
            else:
                cmd.extend([
                    "--window-size=900,700",
                    "--window-position=50,50",
                ])

            cmd.append(url)

            # Start process with hidden window on Windows
            startupinfo = None
            if os.name == 'nt' and self.hidden:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = SW_MINIMIZE

            self.chrome_process = subprocess.Popen(cmd, shell=False, startupinfo=startupinfo)
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
        
        # Script hook fetch + grecaptcha de capture token + recaptchaToken
        capture_script = '''window._tk=null;window._pj=null;window._rc=null;(function(){
var f=window.fetch;
window.fetch=function(u,o){
var s=u?u.toString():'';
if(s.includes('flowMedia')||s.includes('aisandbox')||s.includes('batchGenerate')){
var h=o&&o.headers?o.headers:{};
var a=h.Authorization||h.authorization||'';
if(a.startsWith('Bearer ')){window._tk=a.substring(7);var m=s.match(/\\/projects\\/([^\\/]+)\\//);if(m)window._pj=m[1];}
if(o&&o.body){
try{
var bodyStr=typeof o.body==='string'?o.body:JSON.stringify(o.body);
var b=JSON.parse(bodyStr);
if(b&&b.recaptchaToken){window._rc=b.recaptchaToken;console.log('RECAPTCHA FROM FETCH!');}
}catch(e){console.log('Body parse error:',e);}
}
console.log('TOKEN CAPTURED!');
}
return f.apply(this,arguments);
};
if(window.grecaptcha&&window.grecaptcha.enterprise){
var orig=window.grecaptcha.enterprise.execute;
window.grecaptcha.enterprise.execute=function(){
return orig.apply(this,arguments).then(function(token){
window._rc=token;console.log('RECAPTCHA FROM GRECAPTCHA!');
return token;
});
};
}
console.log('Capture ready v3');
})();'''
        
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
    
    def get_token_from_devtools(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Mo DevTools, lay token + recaptcha, dong."""
        if not pag or not pyperclip:
            return None, None, None

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.2)

            # Lay ca token, project_id va recaptchaToken
            js = 'copy(JSON.stringify({t:window._tk,p:window._pj,r:window._rc}))'
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
                    rc = data.get("r")  # recaptchaToken
                    if tk and len(str(tk)) > 50:
                        return tk, pj, rc
            except:
                pass
            return None, None, None
        except:
            return None, None, None
    
    def extract_token(
        self,
        project_id: str = None,
        callback: Callable = None,
        timeout: int = 45  # Giam tu 60 -> 45
    ) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
        """
        Main function - lay token roi DONG Chrome.
        Chrome chay AN, chi hien khi can tuong tac.

        Returns: (token, project_id, recaptcha_token, error_message)
        """
        self.callback = callback

        if not pag:
            return None, None, None, "Thieu pyautogui"
        if not pyperclip:
            return None, None, None, "Thieu pyperclip"

        token = None
        proj = None
        recaptcha = None
        error = ""

        try:
            # === 1. Mo Chrome (AN - off screen) ===
            url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}" if project_id else self.FLOW_URL
            self.log("Mo Chrome (hidden)...")

            if not self.open_chrome(url):
                return None, None, "Khong mo duoc Chrome"

            # === 2. Doi trang load ===
            self.log("Doi trang load (6s)...")
            time.sleep(6)

            # === 3. Tim va HIEN Chrome window de tuong tac ===
            self.find_chrome_window()
            self.show_chrome_window()
            time.sleep(0.5)

            # === 4. Inject capture ===
            self.inject_capture_only()
            time.sleep(0.3)

            # === 5. Click "Du an moi" (JS) ===
            if not project_id:
                self.log("Click Du an moi...")
                self.click_new_project_js()
                time.sleep(2)

            # === 6. Click dropdown + chon "Tao hinh anh" (JS) ===
            self.log("Chon mode Tao hinh anh...")
            self.click_image_mode_js()
            time.sleep(1.5)

            # === 7. Focus textarea (JS) ===
            self.log("Focus textarea...")
            self.focus_textarea_js()
            time.sleep(0.3)

            # === 8. Gui prompt ===
            prompt = get_test_prompt()  # Load từ config/prompts.yaml
            self.send_prompt_manual(prompt)

            # === 9. AN Chrome ngay sau khi gui prompt ===
            self.hide_chrome_window()

            # === 10. Doi token (30s max) ===
            self.log("Doi capture token (30s max)...")

            for i in range(10):  # 10 * 3s = 30s max
                time.sleep(3)
                self.log(f"Kiem tra #{i+1}...")

                # Hien Chrome chi de lay token
                self.show_chrome_window()
                time.sleep(0.2)
                token, proj, recaptcha = self.get_token_from_devtools()
                self.hide_chrome_window()

                if token:
                    self.log("=== DA LAY DUOC TOKEN! ===")
                    if recaptcha:
                        self.log("=== DA LAY DUOC RECAPTCHA TOKEN! ===")
                    break

            if not token:
                error = "Khong lay duoc token. Thu lai."

        except Exception as e:
            error = f"Loi: {e}"

        finally:
            # === 11. DONG Chrome (chi khi auto_close=True) ===
            if self.auto_close:
                self.close_chrome()

        return token, proj or project_id, recaptcha, error

    def get_fresh_recaptcha(self, timeout: int = 10) -> Optional[str]:
        """
        Lay recaptcha token moi tu Chrome dang mo.
        Goi khi can token moi cho moi request.

        Returns: recaptcha_token hoac None neu fail
        """
        if not pag or not pyperclip:
            return None

        try:
            # Hien Chrome window
            self.show_chrome_window()
            time.sleep(0.3)

            # Mo DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)

            # Execute grecaptcha.enterprise.execute() va doi ket qua
            # Site key cua Google Flow: 6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV
            # Dung navigator.clipboard.writeText thay vi copy() (DevTools-only)
            js = '''(async function(){
try{
var token=await grecaptcha.enterprise.execute('6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV',{action:'SUBMIT'});
window._rc=token;
await navigator.clipboard.writeText(token);
console.log('Fresh reCAPTCHA OK: '+token.substring(0,20)+'...');
return token;
}catch(e){console.log('reCAPTCHA error:',e);return null;}
})();'''

            pyperclip.copy(js)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(2)  # Doi grecaptcha execute

            # Doc token tu clipboard (da duoc JS copy vao)
            token = pyperclip.paste()

            # Neu clipboard khong co token, thu copy tu window._rc
            if not token or len(token) < 100 or token.startswith('('):
                self.log("Thu copy tu window._rc...")
                copy_cmd = "copy(window._rc)"
                pyperclip.copy(copy_cmd)
                time.sleep(0.1)
                pag.hotkey("ctrl", "v")
                time.sleep(0.1)
                pag.press("enter")
                time.sleep(0.5)
                token = pyperclip.paste()

            # Dong DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.3)

            # An Chrome
            self.hide_chrome_window()

            if token and len(token) > 100 and not token.startswith('(') and not token.startswith('copy'):
                self.log("Fresh reCAPTCHA token OK!")
                return token

            self.log("Khong lay duoc fresh reCAPTCHA", "WARN")
            return None

        except Exception as e:
            self.log(f"Fresh reCAPTCHA error: {e}", "ERROR")
            return None


# Aliases
FlowAutoToken = ChromeAutoToken

def get_flow_token(chrome_path=None, profile_path=None, project_id=None, callback=None):
    return ChromeAutoToken(chrome_path, profile_path).extract_token(project_id, callback)
