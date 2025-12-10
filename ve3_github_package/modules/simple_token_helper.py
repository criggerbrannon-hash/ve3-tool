"""
VE3 Tool - Simple Token Helper
==============================
Mo browser va huong dan user lay token.
Khong dung Selenium phuc tap.
"""

import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple


class SimpleTokenHelper:
    """
    Helper don gian de lay Bearer Token.
    Chi mo browser va huong dan user.
    """
    
    FLOW_URL = "https://labs.google/fx/vi/tools/flow"
    
    def __init__(
        self,
        chrome_path: str = None,
        profile_path: str = None
    ):
        self.chrome_path = chrome_path or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.profile_path = profile_path
    
    def open_flow_in_chrome(self) -> bool:
        """
        Mo Google Flow trong Chrome voi profile cu the.
        
        Returns:
            True neu mo thanh cong
        """
        try:
            if sys.platform == "win32" and Path(self.chrome_path).exists():
                # Open Chrome with specific profile
                cmd = [self.chrome_path]
                
                if self.profile_path:
                    profile_name = Path(self.profile_path).name
                    user_data_dir = str(Path(self.profile_path).parent)
                    cmd.extend([
                        f"--user-data-dir={user_data_dir}",
                        f"--profile-directory={profile_name}"
                    ])
                
                cmd.append(self.FLOW_URL)
                
                subprocess.Popen(cmd, shell=False)
                return True
            else:
                # Fallback to default browser
                webbrowser.open(self.FLOW_URL)
                return True
                
        except Exception as e:
            print(f"Error opening browser: {e}")
            # Fallback
            webbrowser.open(self.FLOW_URL)
            return True
    
    def open_project_url(self, project_id: str) -> bool:
        """
        Mo truc tiep URL cua project.
        
        Args:
            project_id: ID cua project (vd: cb88b1d9-fb2c-4f0c-95af-0205e435fd5b)
        """
        url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}"
        
        try:
            if sys.platform == "win32" and Path(self.chrome_path).exists():
                cmd = [self.chrome_path]
                
                if self.profile_path:
                    profile_name = Path(self.profile_path).name
                    user_data_dir = str(Path(self.profile_path).parent)
                    cmd.extend([
                        f"--user-data-dir={user_data_dir}",
                        f"--profile-directory={profile_name}"
                    ])
                
                cmd.append(url)
                subprocess.Popen(cmd, shell=False)
                return True
            else:
                webbrowser.open(url)
                return True
        except:
            webbrowser.open(url)
            return True
    
    @staticmethod
    def get_instructions() -> str:
        """Tra ve huong dan lay token."""
        return """
╔══════════════════════════════════════════════════════════════════╗
║               HUONG DAN LAY BEARER TOKEN                         ║
╚══════════════════════════════════════════════════════════════════╝

BUOC 1: Tao Project moi
───────────────────────
1. Khi trang Flow mo len, click vao "[+ Du an moi]"
2. Mot project moi se duoc tao voi URL dang:
   https://labs.google/fx/vi/tools/flow/project/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

BUOC 2: Chuyen sang che do Tao anh
──────────────────────────────────
1. Tim nut "Tu van ban sang video" (dropdown o goc trai)
2. Click vao no
3. Chon "Tao hinh anh"

BUOC 3: Mo DevTools va Tao anh
──────────────────────────────
1. Nhan F12 de mo DevTools
2. Chon tab "Network"
3. Trong o chat "Tao hinh anh tu van ban...", go: test
4. Nhan Enter de gui

BUOC 4: Copy Token
──────────────────
1. Trong tab Network, tim request "flowMedia:batchGenerateImages"
2. Click vao request do
3. Chon tab "Headers"
4. Tim dong "authorization: Bearer ya29.xxxxx..."
5. Copy TOAN BO gia tri sau "Bearer " (bat dau bang ya29.)

BUOC 5: Paste vao Tool
──────────────────────
1. Quay lai Tool
2. Paste token vao

⚠️  LUU Y: Token chi co hieu luc khoang 1 gio!
"""

    @staticmethod
    def extract_project_id_from_url(url: str) -> Optional[str]:
        """
        Trich xuat Project ID tu URL.
        
        Args:
            url: URL dang https://labs.google/fx/vi/tools/flow/project/xxx
            
        Returns:
            Project ID hoac None
        """
        if "/project/" in url:
            parts = url.split("/project/")
            if len(parts) > 1:
                project_id = parts[1].split("/")[0].split("?")[0]
                return project_id
        return None


def open_flow_browser(chrome_path: str = None, profile_path: str = None) -> bool:
    """
    Ham tien ich de mo Flow trong browser.
    """
    helper = SimpleTokenHelper(chrome_path, profile_path)
    return helper.open_flow_in_chrome()


def show_token_guide():
    """Hien thi huong dan."""
    print(SimpleTokenHelper.get_instructions())


if __name__ == "__main__":
    print("Opening Google Flow...")
    open_flow_browser()
    print("\n")
    show_token_guide()
