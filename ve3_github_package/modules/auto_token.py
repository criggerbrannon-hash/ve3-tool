"""
VE3 Tool - Auto Token v14
=========================
Flow:
1. Mo Chrome
2. DevTools -> Inject capture -> DONG DevTools
3. PyAutoGUI: Click dropdown -> Click "Tao hinh anh" -> Click textarea -> Paste -> Enter
4. Doi
5. DevTools -> Lay token -> Dong
"""

import sys
import time
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Callable

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
    """Auto lay token."""
    
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"
    
    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        headless: bool = False
    ):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.headless = headless
        self.callback = None
    
    def log(self, msg: str):
        print(f"[AutoToken] {msg}")
        if self.callback:
            self.callback(msg)
    
    def open_chrome(self, url: str) -> bool:
        try:
            cmd = [self.chrome_path]
            if self.profile_path and Path(self.profile_path).exists():
                cmd.extend([
                    f"--user-data-dir={Path(self.profile_path).parent}",
                    f"--profile-directory={Path(self.profile_path).name}"
                ])
            
            # Headless/minimized mode
            if self.headless:
                # Note: True headless won't work with PyAutoGUI
                # So we start minimized and restore when needed
                cmd.extend([
                    "--start-minimized",
                    "--window-position=-32000,-32000"  # Off-screen
                ])
            
            cmd.append(url)
            subprocess.Popen(cmd, shell=False)
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
        timeout: int = 90
    ) -> Tuple[Optional[str], Optional[str], str]:
        """Main function."""
        self.callback = callback
        
        if not pag:
            return None, None, "Thieu pyautogui"
        if not pyperclip:
            return None, None, "Thieu pyperclip"
        
        try:
            # === 1. Mo Chrome ===
            url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}" if project_id else self.FLOW_URL
            self.log("Mo Chrome...")
            
            if not self.open_chrome(url):
                return None, None, "Khong mo duoc Chrome"
            
            # === 2. Doi trang load ===
            self.log("Doi trang load (12s)...")
            time.sleep(12)
            
            # === 3. Inject capture (DevTools mo roi dong) ===
            self.inject_capture_only()
            time.sleep(1)
            
            # === 4. Click "Du an moi" (JS) ===
            if not project_id:
                self.log("Click Du an moi...")
                self.click_new_project_js()
                self.log("Doi 5s...")
                time.sleep(5)
            
            # === 5. Click dropdown + chon "Tao hinh anh" (JS) ===
            self.log("Chon mode Tao hinh anh...")
            self.click_image_mode_js()
            time.sleep(3)
            
            # === 6. Focus textarea (JS) ===
            self.log("Focus textarea...")
            self.focus_textarea_js()
            time.sleep(1)
            
            # === 7. Gui prompt BANG PYAUTOGUI ===
            # DevTools da dong, textarea da focus
            # Chi can Ctrl+V va Enter
            prompt = "beautiful sunset over ocean with golden clouds and birds flying"
            self.send_prompt_manual(prompt)
            
            # === 8. Doi token ===
            self.log("Doi capture token (60s)...")
            
            for i in range(20):
                time.sleep(3)
                self.log(f"Kiem tra #{i+1}...")
                
                token, proj = self.get_token_from_devtools()
                
                if token:
                    self.log("=== DA LAY DUOC TOKEN! ===")
                    return token, proj or project_id, ""
            
            return None, None, "Khong lay duoc token. Thu lai."
            
        except Exception as e:
            return None, None, f"Loi: {e}"


# Aliases
FlowAutoToken = ChromeAutoToken

def get_flow_token(chrome_path=None, profile_path=None, project_id=None, callback=None):
    return ChromeAutoToken(chrome_path, profile_path).extract_token(project_id, callback)
