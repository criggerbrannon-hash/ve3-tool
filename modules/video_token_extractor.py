"""
VE3 Tool - Video Token Extractor
================================
Tự động lấy Bearer token cho Video API.

Flow:
1. Mở Chrome với profile
2. Vào labs.google/fx/vi/tools/flow
3. Click "Dự án mới"
4. Click dropdown → Chọn "Tạo video từ các thành phần"
5. Click "Tạo một video bằng văn bản và các thành phần"
6. Đính kèm ảnh + nhập prompt + Enter
7. Bắt token từ Network request
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


class VideoTokenExtractor:
    """Auto lấy token cho Video API."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None,
        image_path: str = None  # Ảnh để đính kèm khi tạo video
    ):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
        self.image_path = image_path  # Ảnh từ thư mục nv/
        self.callback = None

    def log(self, msg: str):
        print(f"[VideoToken] {msg}")
        if self.callback:
            self.callback(msg)

    def open_chrome(self, url: str) -> bool:
        """Mở Chrome với profile."""
        try:
            cmd = [self.chrome_path]
            if self.profile_path and Path(self.profile_path).exists():
                cmd.extend([
                    f"--user-data-dir={Path(self.profile_path).parent}",
                    f"--profile-directory={Path(self.profile_path).name}"
                ])
            cmd.append(url)
            subprocess.Popen(cmd, shell=False)
            return True
        except Exception as e:
            self.log(f"Lỗi mở Chrome: {e}")
            return False

    def inject_capture_script(self) -> bool:
        """
        Inject script để capture token từ video API requests.
        """
        if not pag or not pyperclip:
            return False

        self.log("Inject capture script...")

        # Script hook fetch để bắt token từ video API
        capture_script = '''window._vtk=null;window._vpj=null;(function(){var f=window.fetch;window.fetch=function(u,o){var s=u?u.toString():'';if(s.includes('video')||s.includes('flowMedia')||s.includes('aisandbox')){var h=o&&o.headers?o.headers:{};var a=h.Authorization||h.authorization||'';if(a.startsWith('Bearer ')){window._vtk=a.substring(7);var m=s.match(/\\/projects\\/([^\\/]+)\\//);if(m)window._vpj=m[1];console.log('VIDEO TOKEN CAPTURED!');}}return f.apply(this,arguments);};console.log('Video capture ready');})();'''

        try:
            # Mở DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.5)

            # Paste và chạy
            pyperclip.copy(capture_script)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.3)
            pag.press("enter")
            time.sleep(0.5)

            # Đóng DevTools
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)

            self.log("Capture script injected")
            return True
        except Exception as e:
            self.log(f"Inject error: {e}")
            return False

    def click_new_project(self) -> bool:
        """Click 'Dự án mới' bằng JS."""
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

    def click_video_mode(self) -> bool:
        """
        Click dropdown và chọn 'Tạo video từ các thành phần'.
        """
        if not pag or not pyperclip:
            return False

        # Script click dropdown rồi click option video
        js = '''(async function(){
            var dd=document.querySelector('button[role="combobox"]');
            if(dd){
                dd.click();
                await new Promise(r=>setTimeout(r,500));
                var all=document.querySelectorAll('*');
                for(var el of all){
                    var t=el.textContent||'';
                    if(t.includes('Tạo video từ các thành phần')){
                        var r=el.getBoundingClientRect();
                        if(r.height>10&&r.height<80){
                            el.click();
                            console.log('Clicked: Tao video tu cac thanh phan');
                            return true;
                        }
                    }
                }
            }
            return false;
        })();'''

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

    def click_text_to_video_option(self) -> bool:
        """
        Click 'Tạo một video bằng văn bản và các thành phần'.
        """
        if not pag or not pyperclip:
            return False

        js = '''(function(){
            var all=document.querySelectorAll('*');
            for(var el of all){
                var t=el.textContent||'';
                if(t.includes('Tạo một video bằng văn bản') || t.includes('văn bản và các thành phần')){
                    var r=el.getBoundingClientRect();
                    if(r.height>10&&r.height<100){
                        el.click();
                        console.log('Clicked: Tao video bang van ban');
                        return true;
                    }
                }
            }
            return false;
        })();'''

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

    def click_add_image_button(self) -> bool:
        """
        Click nút add để mở panel chọn ảnh.
        Button: <button class="sc-c177465c-1 hVamcH sc-d02e9a37-1 hvUQuN">
                   <i class="... google-symbols ...">add</i>
                </button>
        """
        if not pag or not pyperclip:
            return False

        js = '''(function(){
            // Tìm button có icon "add"
            var btns = document.querySelectorAll('button');
            for(var btn of btns){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'add'){
                    btn.click();
                    console.log('Clicked add button');
                    return true;
                }
            }
            // Fallback: tìm theo class
            var addBtn = document.querySelector('button.sc-d02e9a37-1');
            if(addBtn){
                addBtn.click();
                console.log('Clicked add button (fallback)');
                return true;
            }
            return false;
        })();'''

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

    def select_first_image(self) -> bool:
        """
        Chọn ảnh đầu tiên trong panel (ảnh đã upload trước đó).
        """
        if not pag or not pyperclip:
            return False

        js = '''(function(){
            // Tìm và click ảnh đầu tiên trong panel
            var imgs = document.querySelectorAll('img[src*="blob:"], img[src*="googleusercontent"], div[role="option"] img');
            if(imgs.length > 0){
                imgs[0].click();
                console.log('Selected first image');
                return true;
            }
            // Fallback: click div có role="option"
            var options = document.querySelectorAll('[role="option"]');
            if(options.length > 0){
                options[0].click();
                console.log('Selected first option');
                return true;
            }
            return false;
        })();'''

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

    def focus_textarea(self) -> bool:
        """Focus vào textarea để nhập prompt."""
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
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            return True
        except:
            return False

    def send_prompt(self, prompt: str) -> bool:
        """Gửi prompt bằng PyAutoGUI."""
        if not pag or not pyperclip:
            return False

        self.log("Gửi prompt...")

        try:
            pyperclip.copy(prompt)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.5)

            self.log("Đã paste prompt, nhấn Enter...")
            pag.press("enter")
            time.sleep(0.5)

            self.log("Prompt sent!")
            return True
        except Exception as e:
            self.log(f"Send prompt error: {e}")
            return False

    def get_token_from_devtools(self) -> Tuple[Optional[str], Optional[str]]:
        """Mở DevTools, lấy token, đóng."""
        if not pag or not pyperclip:
            return None, None

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1.2)

            # Lấy video token (_vtk thay vì _tk)
            js = 'copy(JSON.stringify({t:window._vtk,p:window._vpj}))'
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
        timeout: int = 120
    ) -> Tuple[Optional[str], Optional[str], str]:
        """
        Main function - Lấy token cho Video API.

        Returns:
            Tuple[token, project_id, error_message]
        """
        self.callback = callback

        if not pag:
            return None, None, "Thiếu pyautogui"
        if not pyperclip:
            return None, None, "Thiếu pyperclip"

        try:
            # === 1. Mở Chrome ===
            url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}" if project_id else self.FLOW_URL
            self.log("Mở Chrome...")

            if not self.open_chrome(url):
                return None, None, "Không mở được Chrome"

            # === 2. Đợi trang load ===
            self.log("Đợi trang load (12s)...")
            time.sleep(12)

            # === 3. Inject capture script ===
            self.inject_capture_script()
            time.sleep(1)

            # === 4. Click "Dự án mới" (nếu chưa có project) ===
            if not project_id:
                self.log("Click Dự án mới...")
                self.click_new_project()
                self.log("Đợi 5s...")
                time.sleep(5)

            # === 5. Click dropdown → "Tạo video từ các thành phần" ===
            self.log("Chọn mode Tạo video...")
            self.click_video_mode()
            time.sleep(3)

            # === 6. Click "Tạo một video bằng văn bản và các thành phần" ===
            self.log("Click option tạo video bằng văn bản...")
            self.click_text_to_video_option()
            time.sleep(2)

            # === 7. Click nút Add để mở panel chọn ảnh ===
            self.log("Click nút Add để chọn ảnh...")
            self.click_add_image_button()
            time.sleep(2)

            # === 8. Chọn ảnh đầu tiên ===
            self.log("Chọn ảnh đầu tiên...")
            self.select_first_image()
            time.sleep(1)

            # === 9. Focus textarea ===
            self.log("Focus textarea...")
            self.focus_textarea()
            time.sleep(1)

            # === 10. Gửi prompt ===
            prompt = "gentle camera movement, soft wind blowing, cinematic"
            self.send_prompt(prompt)

            # === 11. Đợi capture token ===
            self.log("Đợi capture token (90s)...")

            for i in range(30):
                time.sleep(3)
                self.log(f"Kiểm tra #{i+1}...")

                token, proj = self.get_token_from_devtools()

                if token:
                    self.log("=== ĐÃ LẤY ĐƯỢC VIDEO TOKEN! ===")
                    return token, proj or project_id, ""

            return None, None, "Không lấy được token. Thử lại."

        except Exception as e:
            return None, None, f"Lỗi: {e}"


# =============================================================================
# HELPER FUNCTION
# =============================================================================

def get_video_token(chrome_path=None, profile_path=None, project_id=None, callback=None):
    """Quick function để lấy video token."""
    return VideoTokenExtractor(chrome_path, profile_path).extract_token(project_id, callback)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║               VIDEO TOKEN EXTRACTOR                                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Tự động lấy Bearer Token cho Google Video API                               ║
║                                                                              ║
║  Yêu cầu:                                                                    ║
║  - Chrome đã đăng nhập Google                                                ║
║  - Profile có quyền truy cập Google Labs                                     ║
║  - Có ảnh đã tạo trước đó (trong project)                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    # Test
    extractor = VideoTokenExtractor()
    token, project_id, error = extractor.extract_token(callback=print)

    if token:
        print(f"\n✅ Token: {token[:50]}...")
        print(f"   Project: {project_id}")
    else:
        print(f"\n❌ Error: {error}")
