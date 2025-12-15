"""
Test Video Token Extraction
============================
Flow:
1. Mo Chrome
2. Inject capture script
3. Click dropdown -> "Tạo video từ các thành phần"
4. Click "Tạo một video bằng văn bản và các thành phần…"
5. Paste prompt
6. Click nút "add" để thêm media
7. Click chọn ảnh đã tải trước đó
8. Nhấn Enter -> Lấy token
"""

import sys
import time
import subprocess
import json
from pathlib import Path
from typing import Optional, Tuple

try:
    import pyautogui as pag
    pag.FAILSAFE = True
    pag.PAUSE = 0.1
except ImportError:
    pag = None
    print("Cần cài: pip install pyautogui")

try:
    import pyperclip
except ImportError:
    pyperclip = None
    print("Cần cài: pip install pyperclip")


class VideoTokenTest:
    """Test lấy token cho video generation."""

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(self, chrome_path: str = None, profile_path: str = None):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path

    def log(self, msg: str):
        print(f"[VideoToken] {msg}")

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
        """Inject script để bắt token từ network requests."""
        if not pag or not pyperclip:
            return False

        self.log("Inject capture script...")

        # Script hook fetch để capture token
        capture_script = '''window._tk=null;window._pj=null;(function(){var f=window.fetch;window.fetch=function(u,o){var s=u?u.toString():'';if(s.includes('flowMedia')||s.includes('aisandbox')||s.includes('video')){var h=o&&o.headers?o.headers:{};var a=h.Authorization||h.authorization||'';if(a.startsWith('Bearer ')){window._tk=a.substring(7);var m=s.match(/\\/projects\\/([^\\/]+)\\//);if(m)window._pj=m[1];console.log('TOKEN CAPTURED! URL:',s.substring(0,100));}}return f.apply(this,arguments);};console.log('Video capture ready');})();'''

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

            self.log("Capture script injected!")
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
            self.log("Clicked 'Dự án mới'")
            return True
        except:
            return False

    def click_video_mode(self) -> bool:
        """
        Click dropdown và chọn "Tạo video từ các thành phần"
        (Khác với image mode là "Tạo hình ảnh")
        """
        if not pag or not pyperclip:
            return False

        # Script click dropdown rồi tìm option video
        js = '''(async function(){
            var dd=document.querySelector('button[role="combobox"]');
            if(dd){
                dd.click();
                await new Promise(r=>setTimeout(r,800));
                var all=document.querySelectorAll('*');
                for(var el of all){
                    var t=el.textContent||'';
                    // Tìm "Tạo video từ các thành phần" hoặc tương tự
                    if(t.includes('Tạo video từ các thành phần') || t.includes('video từ các thành phần')){
                        var r=el.getBoundingClientRect();
                        if(r.height>10 && r.height<80){
                            el.click();
                            console.log('Clicked VIDEO mode: '+t.substring(0,50));
                            return true;
                        }
                    }
                }
                console.log('Khong tim thay option video');
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
            time.sleep(1.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            self.log("Đã chọn VIDEO mode")
            return True
        except:
            return False

    def click_create_video_button(self) -> bool:
        """
        Click nút "Tạo một video bằng văn bản và các thành phần…"
        để mở form nhập prompt
        """
        if not pag or not pyperclip:
            return False

        # Tìm và click button/element chứa text này
        js = '''(async function(){
            await new Promise(r=>setTimeout(r,500));
            var all=document.querySelectorAll('button, div[role="button"], span, p');
            for(var el of all){
                var t=el.textContent||'';
                // Tìm "Tạo một video bằng văn bản và các thành phần"
                if(t.includes('Tạo một video bằng văn bản') || t.includes('video bằng văn bản và các thành phần')){
                    var r=el.getBoundingClientRect();
                    if(r.height>10 && r.width>50){
                        el.click();
                        console.log('Clicked: '+t.substring(0,60));
                        return true;
                    }
                }
            }
            console.log('Khong tim thay button tao video');
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
            self.log("Clicked 'Tạo một video bằng văn bản...'")
            return True
        except:
            return False

    def focus_textarea(self) -> bool:
        """Focus vào textarea."""
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

    def paste_prompt(self, prompt: str) -> bool:
        """Paste prompt (KHÔNG nhấn Enter, chờ thêm ảnh trước)."""
        if not pag or not pyperclip:
            return False

        self.log(f"Paste prompt: {prompt[:50]}...")

        try:
            pyperclip.copy(prompt)
            time.sleep(0.2)
            pag.hotkey("ctrl", "v")
            time.sleep(0.5)
            self.log("Prompt pasted! (chưa gửi)")
            return True
        except Exception as e:
            self.log(f"Paste error: {e}")
            return False

    def click_add_button(self) -> bool:
        """
        Click nút "add" để thêm media.
        Button có class chứa icon "add" google-symbols
        """
        if not pag or not pyperclip:
            return False

        self.log("Click nút ADD...")

        # Tìm button có icon "add"
        js = '''(function(){
            // Tìm button có icon add
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var icon = btn.querySelector('i.google-symbols');
                if(icon && icon.textContent.trim() === 'add'){
                    btn.click();
                    console.log('Clicked ADD button');
                    return true;
                }
            }
            console.log('Khong tim thay ADD button');
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
            self.log("Đã click ADD button")
            return True
        except Exception as e:
            self.log(f"Click ADD error: {e}")
            return False

    def click_uploaded_media(self) -> bool:
        """
        Click chọn ảnh đã tải lên trước đó.
        Button có span text: "Một thành phần nội dung nghe nhìn mà bạn đã tải lên hoặc chọn trước đây"
        """
        if not pag or not pyperclip:
            return False

        self.log("Click chọn ảnh đã tải...")

        # Tìm button chứa text về uploaded media
        js = '''(async function(){
            await new Promise(r=>setTimeout(r,500));

            // Cách 1: Tìm button có span chứa text về uploaded media
            var buttons = document.querySelectorAll('button');
            for(var btn of buttons){
                var spans = btn.querySelectorAll('span');
                for(var span of spans){
                    var t = span.textContent || '';
                    if(t.includes('đã tải lên') || t.includes('chọn trước đây') || t.includes('nội dung nghe nhìn')){
                        btn.click();
                        console.log('Clicked uploaded media button (by span)');
                        return true;
                    }
                }
            }

            // Cách 2: Tìm theo class pattern
            var mediaBtn = document.querySelector('button[class*="fbea20b2"]');
            if(mediaBtn){
                mediaBtn.click();
                console.log('Clicked uploaded media button (by class)');
                return true;
            }

            // Cách 3: Click vào item đầu tiên trong media grid/list
            var mediaItems = document.querySelectorAll('[role="listitem"] button, [role="option"] button');
            if(mediaItems.length > 0){
                mediaItems[0].click();
                console.log('Clicked first media item');
                return true;
            }

            console.log('Khong tim thay uploaded media button');
            return false;
        })();'''

        try:
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(1)
            pyperclip.copy(js)
            pag.hotkey("ctrl", "v")
            time.sleep(0.2)
            pag.press("enter")
            time.sleep(1.5)
            pag.hotkey("ctrl", "shift", "j")
            time.sleep(0.5)
            self.log("Đã chọn ảnh")
            return True
        except Exception as e:
            self.log(f"Click media error: {e}")
            return False

    def press_enter_to_send(self) -> bool:
        """Nhấn Enter để gửi prompt + media."""
        if not pag:
            return False

        self.log("Nhấn Enter để gửi...")

        try:
            pag.press("enter")
            time.sleep(0.5)
            self.log("Đã gửi!")
            return True
        except Exception as e:
            self.log(f"Enter error: {e}")
            return False

    def get_token(self) -> Tuple[Optional[str], Optional[str]]:
        """Lấy token từ DevTools."""
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

    def extract_token(self, timeout: int = 90) -> Tuple[Optional[str], Optional[str], str]:
        """
        Main function - Lấy token cho video generation.

        Flow:
        1. Mở Chrome
        2. Inject capture script
        3. Click "Dự án mới"
        4. Click dropdown -> "Tạo video từ các thành phần"
        5. Click "Tạo một video bằng văn bản và các thành phần…"
        6. Focus textarea
        7. Paste prompt (CHƯA gửi)
        8. Click nút ADD để thêm media
        9. Click chọn ảnh đã tải trước đó
        10. Nhấn Enter để gửi
        11. Đợi và lấy token
        """
        if not pag:
            return None, None, "Thiếu pyautogui"
        if not pyperclip:
            return None, None, "Thiếu pyperclip"

        try:
            # === 1. Mở Chrome ===
            self.log("Mở Chrome...")
            if not self.open_chrome(self.FLOW_URL):
                return None, None, "Không mở được Chrome"

            # === 2. Đợi trang load ===
            self.log("Đợi trang load (12s)...")
            time.sleep(12)

            # === 3. Inject capture ===
            self.inject_capture_script()
            time.sleep(1)

            # === 4. Click "Dự án mới" ===
            self.log("Click 'Dự án mới'...")
            self.click_new_project()
            self.log("Đợi 5s...")
            time.sleep(5)

            # === 5. Chọn VIDEO mode (khác với image!) ===
            self.log("Chọn mode VIDEO...")
            self.click_video_mode()
            time.sleep(3)

            # === 6. Click "Tạo một video bằng văn bản..." ===
            self.log("Click 'Tạo một video bằng văn bản...'...")
            self.click_create_video_button()
            time.sleep(2)

            # === 7. Focus textarea ===
            self.log("Focus textarea...")
            self.focus_textarea()
            time.sleep(1)

            # === 8. Paste prompt (CHƯA gửi) ===
            prompt = "A beautiful sunset over the ocean with waves crashing"
            self.paste_prompt(prompt)
            time.sleep(1)

            # === 9. Click nút ADD để thêm media ===
            self.log("Click ADD button...")
            self.click_add_button()
            time.sleep(2)

            # === 10. Click chọn ảnh đã tải trước đó ===
            self.log("Chọn ảnh đã tải...")
            self.click_uploaded_media()
            time.sleep(2)

            # === 11. Nhấn Enter để gửi ===
            self.press_enter_to_send()

            # === 12. Đợi và lấy token ===
            self.log("Đợi capture token (60s)...")

            for i in range(20):
                time.sleep(3)
                self.log(f"Kiểm tra #{i+1}...")

                token, proj = self.get_token()

                if token:
                    self.log("=== ĐÃ LẤY ĐƯỢC TOKEN! ===")
                    self.log(f"Token: {token[:50]}...")
                    self.log(f"Project ID: {proj}")
                    return token, proj, ""

            return None, None, "Không lấy được token. Thử lại."

        except Exception as e:
            return None, None, f"Lỗi: {e}"


def main():
    """Test function."""
    print("=" * 50)
    print("VIDEO TOKEN TEST")
    print("=" * 50)

    # Config - thay đổi theo máy của bạn
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    profile_path = None  # Hoặc path đến profile: r"C:\Users\...\Profile 1"

    # Load từ config nếu có
    config_file = Path(__file__).parent / "config" / "accounts.json"
    if config_file.exists():
        try:
            import json
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            chrome_path = config.get("chrome_path", chrome_path)
            profiles = config.get("chrome_profiles", [])
            if profiles:
                profile_path = profiles[0]
                print(f"Loaded profile: {profile_path}")
        except:
            pass

    print(f"Chrome: {chrome_path}")
    print(f"Profile: {profile_path}")
    print()

    # Run test
    tester = VideoTokenTest(chrome_path, profile_path)
    token, project_id, error = tester.extract_token()

    print()
    print("=" * 50)
    print("KẾT QUẢ:")
    print("=" * 50)

    if token:
        print(f"✓ TOKEN: {token[:80]}...")
        print(f"✓ PROJECT ID: {project_id}")

        # Save để dùng sau
        result = {
            "token": token,
            "project_id": project_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open("video_token_result.json", "w") as f:
            json.dump(result, f, indent=2)
        print("✓ Đã lưu vào video_token_result.json")
    else:
        print(f"✗ LỖI: {error}")

    return token is not None


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
