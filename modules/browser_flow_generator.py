"""
VE3 Tool - Browser Flow Generator Module
========================================
Tich hop browser automation voi Excel workflow.

Workflow:
1. Doc Excel prompts (PromptWorkbook)
2. Lay cac scenes chua tao anh (status_img != 'done')
3. Mo trinh duyet, inject JS
4. Goi VE3.run() voi [{sceneId, prompt}]
5. Di chuyen file tu Downloads -> project/img/
6. Cap nhat Excel (img_path, status_img = 'done')

Usage:
    from modules.browser_flow_generator import BrowserFlowGenerator

    gen = BrowserFlowGenerator("PROJECTS/KA1-0001")
    gen.generate_all_images()
"""

import os
import sys
import time
import json
import shutil
import glob
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

# Import PromptWorkbook
from modules.excel_manager import PromptWorkbook, Scene
from modules.utils import get_logger, load_settings

# Browser driver imports - PREFER SELENIUM (more stable)
DRIVER_TYPE = None

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        WebDriverException,
        JavascriptException
    )
    DRIVER_TYPE = "selenium"
except ImportError:
    DRIVER_TYPE = None

SELENIUM_AVAILABLE = DRIVER_TYPE is not None


class BrowserFlowGenerator:
    """
    Tao anh tu Excel bang browser automation.

    Su dung JavaScript injection de dieu khien Google Flow.
    Tu dong di chuyen file tu Downloads va cap nhat Excel.
    """

    FLOW_URL = "https://labs.google/fx/vi/tools/flow"

    def __init__(
        self,
        project_path: str,
        profile_name: str = "main",
        headless: bool = False,
        verbose: bool = True,
        config_path: str = "config/settings.yaml"
    ):
        """
        Khoi tao BrowserFlowGenerator.

        Args:
            project_path: Duong dan den thu muc project (PROJECTS/KA1-0001)
            profile_name: Ten Chrome profile (luu trong chrome_profiles/)
            headless: Chay an (khong hien UI) - nen False lan dau de dang nhap
            verbose: In log chi tiet
            config_path: Duong dan file config
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "Selenium chua duoc cai dat. "
                "Chay: pip install selenium undetected-chromedriver"
            )

        self.project_path = Path(project_path)
        self.profile_name = profile_name
        self.headless = headless
        self.verbose = verbose

        # Load config
        self.config = {}
        config_file = Path(config_path)
        if config_file.exists():
            self.config = load_settings(config_file)  # Pass Path object, not string

        # Paths
        self.img_path = self.project_path / "img"
        self.prompts_path = self.project_path / "prompts"
        self.nv_path = self.project_path / "nv"

        # Tao thu muc neu chua co
        self.img_path.mkdir(parents=True, exist_ok=True)
        self.nv_path.mkdir(parents=True, exist_ok=True)

        # Chrome profile
        base_dir = Path(__file__).parent.parent
        profiles_dir = self.config.get("browser_profiles_dir", "./chrome_profiles")
        if not os.path.isabs(profiles_dir):
            profiles_dir = base_dir / profiles_dir
        self.profile_dir = Path(profiles_dir) / profile_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        # Downloads folder - noi browser tai anh ve
        self.downloads_dir = Path.home() / "Downloads"

        # Project code (dung cho ten file)
        self.project_code = self.project_path.name  # VD: KA1-0001

        # Driver
        self.driver = None
        self._js_injected = False

        # Logger
        self.logger = get_logger("browser_flow")

        # Stats
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

    def _log(self, message: str, level: str = "info") -> None:
        """Print log message."""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            icons = {
                "info": "[INFO]",
                "success": "[OK]",
                "error": "[ERROR]",
                "warn": "[WARN]",
            }
            print(f"[{timestamp}] {icons.get(level, '')} {message}")

    def _find_excel_file(self) -> Optional[Path]:
        """Tim file Excel prompts trong project."""
        # Tim trong prompts/
        for pattern in ["*_prompts.xlsx", "*.xlsx"]:
            files = list(self.prompts_path.glob(pattern))
            if files:
                return files[0]

        # Tim trong project root
        for pattern in ["*_prompts.xlsx", "*.xlsx"]:
            files = list(self.project_path.glob(pattern))
            if files:
                return files[0]

        return None

    def _get_js_script(self) -> str:
        """Doc file JavaScript automation."""
        script_path = Path(__file__).parent.parent / "scripts" / "ve3_browser_automation.js"

        if script_path.exists():
            with open(script_path, "r", encoding="utf-8") as f:
                return f.read()

        raise FileNotFoundError(f"JS script khong tim thay: {script_path}")

    def _create_driver(self):
        """
        Tao Chrome WebDriver - PARALLEL SAFE.
        - Moi instance dung port rieng (khong xung dot)
        - Profile rieng biet
        - Mac dinh headless (chay an)
        """
        import random
        import tempfile

        # Download prefs
        prefs = {
            "download.default_directory": str(self.downloads_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
        }

        self._log(f"Headless: {self.headless}")
        self._log("Su dung Selenium WebDriver (Parallel Safe)")

        try:
            options = Options()

            # Tim Chrome binary
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
            ]
            for chrome_path in chrome_paths:
                if os.path.exists(chrome_path):
                    options.binary_location = chrome_path
                    self._log(f"Chrome: {chrome_path}")
                    break

            # PARALLEL SAFE: Copy profile sang temp directory
            # Giu nguyen profile goc (khong bi lock), dung ban copy
            self.profile_dir.mkdir(parents=True, exist_ok=True)

            # Tao temp profile
            temp_profile = tempfile.mkdtemp(prefix=f"ve3_chrome_{self.profile_name}_")
            self._log(f"Profile goc: {self.profile_dir}")
            self._log(f"Profile temp: {temp_profile}")

            # Copy data tu profile goc sang temp (de co session dang nhap)
            import shutil
            if any(self.profile_dir.iterdir()):  # Neu profile goc co data
                for item in self.profile_dir.iterdir():
                    try:
                        dest = Path(temp_profile) / item.name
                        if item.is_dir():
                            shutil.copytree(item, dest, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dest)
                    except Exception:
                        pass  # Skip locked files
                self._log(f"Da copy profile data")

            self._temp_profile = temp_profile  # Luu de cleanup sau
            options.add_argument(f"--user-data-dir={temp_profile}")

            # PARALLEL SAFE: Moi instance dung port rieng
            debug_port = random.randint(9222, 9999)
            options.add_argument(f"--remote-debugging-port={debug_port}")

            # Headless mac dinh (chay an, toi uu cho auto)
            if self.headless:
                options.add_argument("--headless=new")
                options.add_argument("--disable-gpu")

            # Cac options cho automation
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-infobars")
            options.add_argument("--window-size=1920,1080")
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("prefs", prefs)

            self._log(f"Dang khoi dong Chrome (port {debug_port})...")
            driver = webdriver.Chrome(options=options)

            # An webdriver flag
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            self._log("Chrome da san sang!", "success")

            return driver

        except Exception as e:
            self._log(f"Loi khoi dong Chrome: {e}", "error")
            import traceback
            traceback.print_exc()
            raise

    def start_browser(self) -> bool:
        """
        Khoi dong trinh duyet va navigate den Google Flow.

        Returns:
            True neu thanh cong
        """
        self._log("Khoi dong trinh duyet...")

        try:
            self.driver = self._create_driver()
            self._log("Da khoi dong Chrome", "success")

            # Navigate den Google Flow
            self._log(f"Navigate den: {self.FLOW_URL}")
            self.driver.get(self.FLOW_URL)

            # Cho page load
            time.sleep(5)

            return True

        except Exception as e:
            self._log(f"Loi khoi dong: {e}", "error")
            return False

    def stop_browser(self) -> None:
        """Dong trinh duyet va cleanup temp profile."""
        if self.driver:
            self._log("Dong trinh duyet...")
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self._js_injected = False

        # Cleanup temp profile (giu nguyen profile goc)
        if hasattr(self, '_temp_profile') and self._temp_profile:
            try:
                import shutil
                shutil.rmtree(self._temp_profile, ignore_errors=True)
                self._log(f"Da xoa temp profile")
            except:
                pass
            self._temp_profile = None

    def wait_for_login(self, timeout: int = 300) -> bool:
        """
        Cho nguoi dung dang nhap.

        Args:
            timeout: Thoi gian cho (giay)

        Returns:
            True neu da dang nhap
        """
        self._log(f"Cho dang nhap (timeout: {timeout}s)...")
        self._log("Vui long dang nhap Google account tren trinh duyet")

        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                textarea = self.driver.find_element(By.CSS_SELECTOR, "textarea")
                if textarea:
                    self._log("Da phat hien dang nhap thanh cong!", "success")
                    return True
            except:
                pass

            time.sleep(2)

        self._log("Timeout - chua dang nhap", "error")
        return False

    def _inject_js(self) -> bool:
        """Inject JavaScript automation script."""
        if self._js_injected:
            return True

        try:
            self._log("Buoc 1: Inject JavaScript script...")
            js_code = self._get_js_script()
            self.driver.execute_script(js_code)

            # Init VE3 voi project name
            self._log("Buoc 2: Init VE3...")
            self.driver.execute_script(f'VE3.init("{self.project_code}")')

            # Setup UI: Click "Du an moi" + Chon "Tao hinh anh"
            self._log("Buoc 3: Setup UI (Du an moi + Tao hinh anh)...")
            setup_result = self.driver.execute_async_script("""
                const callback = arguments[arguments.length - 1];
                (async () => {
                    try {
                        await VE3.setup();
                        callback({success: true});
                    } catch(e) {
                        callback({success: false, error: e.message});
                    }
                })();
            """)

            if setup_result and setup_result.get('success'):
                self._log("Setup UI thanh cong!", "success")
            else:
                error = setup_result.get('error', 'Unknown') if setup_result else 'No response'
                self._log(f"Setup UI that bai: {error}", "warn")

            self._js_injected = True
            self._log("Da san sang tao anh!", "success")
            return True

        except Exception as e:
            self._log(f"Loi inject JS: {e}", "error")
            import traceback
            traceback.print_exc()
            return False

    def _find_downloaded_files(self, pattern: str, wait_timeout: int = 30) -> List[Path]:
        """
        Tim file vua download trong Downloads folder.

        Args:
            pattern: Pattern de match (vd: KA1-0001_scene_*)
            wait_timeout: Thoi gian cho file xuat hien

        Returns:
            List cac file tim duoc
        """
        start_time = time.time()
        search_pattern = str(self.downloads_dir / pattern)

        while time.time() - start_time < wait_timeout:
            files = glob.glob(search_pattern)
            # Loai bo file .crdownload (dang tai)
            files = [f for f in files if not f.endswith('.crdownload')]

            if files:
                return [Path(f) for f in files]

            time.sleep(0.5)

        return []

    def _select_best_image(self, files: List[Path], is_character: bool = False) -> Tuple[Path, float]:
        """
        Chon anh tot nhat tu nhieu files.
        Su dung ImageEvaluator de danh gia chat luong anh (sharpness, brightness, contrast, faces).
        Fallback: dung file size neu khong co opencv.

        Args:
            files: List cac file anh
            is_character: Co phai anh nhan vat (nvc/nv*/loc*) - uu tien face detection

        Returns:
            Tuple[Path den file tot nhat, score]
        """
        if len(files) == 1:
            # Van danh gia de biet score
            try:
                from modules.image_evaluator import ImageEvaluator
                evaluator = ImageEvaluator(verbose=False)
                _, score = evaluator.evaluate(files[0], is_character)
                return files[0], score.total_score
            except ImportError:
                return files[0], 100.0  # Assume good if can't evaluate

        # Thu dung ImageEvaluator (tot hon)
        try:
            from modules.image_evaluator import ImageEvaluator
            evaluator = ImageEvaluator(verbose=False)
            best_path, best_score = evaluator.select_best(files, is_character)

            self._log(f"Chon anh tot nhat: {best_path.name} (score={best_score.total_score}, grade={best_score.grade})")

            # Log comparison
            if len(files) > 1:
                scores_str = []
                for f in files:
                    _, score = evaluator.evaluate(f, is_character)
                    scores_str.append(f"{f.name}={score.total_score}")
                self._log(f"  So sanh: {', '.join(scores_str)}")

            return best_path, best_score.total_score

        except ImportError:
            self._log("ImageEvaluator khong co, dung file size", "warn")

        # Fallback: Lay file size cua moi file
        file_sizes = []
        for f in files:
            try:
                size = f.stat().st_size
                file_sizes.append((f, size))
            except:
                file_sizes.append((f, 0))

        # Sort theo size giam dan (lon nhat = tot nhat)
        file_sizes.sort(key=lambda x: x[1], reverse=True)

        best_file = file_sizes[0][0]
        best_size = file_sizes[0][1]

        self._log(f"Chon anh tot nhat: {best_file.name} ({best_size/1024:.1f}KB)")

        # Log comparison
        if len(file_sizes) > 1:
            sizes_str = ", ".join([f"{f.name}={s/1024:.1f}KB" for f, s in file_sizes])
            self._log(f"  So sanh: {sizes_str}")

        return best_file, 70.0  # Assume decent score for fallback

    def _move_downloaded_images(
        self,
        scene_id: str,
        min_score: float = 50.0
    ) -> Tuple[Optional[Path], float, bool]:
        """
        Di chuyen anh vua download tu Downloads vao project/img/ hoac nv/.
        Neu co 2 anh, chon anh tot nhat bang ImageEvaluator.
        Tra ve score de biet co can tao lai khong.

        Args:
            scene_id: ID cua scene (1, 2, ... hoac nvc, nv1, loc1...)
            min_score: Diem toi thieu de pass (0-100)

        Returns:
            Tuple[Path da di chuyen, score, needs_regeneration]
        """
        # Pattern: {project_code}_{scene_id}*.png
        pattern = f"{self.project_code}_{scene_id}*.png"

        files = self._find_downloaded_files(pattern, wait_timeout=120)

        if not files:
            self._log(f"Khong tim thay file: {pattern}", "warn")
            return None, 0.0, True

        # Xac dinh co phai nhan vat/dia diem khong (uu tien face detection)
        scene_id_str = str(scene_id)
        is_character = scene_id_str.startswith('nv') or scene_id_str.startswith('loc')

        # QUAN TRONG: Chon anh tot nhat va danh gia chat luong
        best_file, score = self._select_best_image(files, is_character)

        # Check neu can tao lai
        needs_regeneration = score < min_score
        if needs_regeneration:
            self._log(f"Anh {scene_id} chua dat chuan: {score:.1f} < {min_score}", "warn")

        # Xac dinh thu muc dich: nv/ cho nvc/nv*/loc*, img/ cho scenes
        if is_character:
            dst_dir = self.nv_path
        else:
            dst_dir = self.img_path

        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_file = dst_dir / f"{scene_id}.png"

        try:
            shutil.move(str(best_file), str(dst_file))
            self._log(f"Da di chuyen: {best_file.name} -> {dst_file} (score={score:.1f})", "success")

            # Xoa cac file con lai (khong can nua)
            for f in files:
                if f != best_file and f.exists():
                    try:
                        os.remove(f)
                        self._log(f"  Xoa file du: {f.name}")
                    except:
                        pass

            return dst_file, score, needs_regeneration

        except Exception as e:
            self._log(f"Loi di chuyen file: {e}", "error")
            return None, 0.0, True

    def generate_scene_images(
        self,
        excel_path: Optional[Path] = None,
        start_scene: int = 1,
        end_scene: Optional[int] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Tao anh cho cac scenes trong Excel.

        Args:
            excel_path: Duong dan file Excel (tu tim neu khong chi dinh)
            start_scene: Scene bat dau (1-indexed)
            end_scene: Scene ket thuc (None = tat ca)
            overwrite: Ghi de anh da co

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("BROWSER FLOW GENERATOR - TAO ANH TU EXCEL")
        self._log("=" * 60)

        # Tim file Excel
        if excel_path is None:
            excel_path = self._find_excel_file()

        if excel_path is None or not excel_path.exists():
            return {"success": False, "error": "Khong tim thay file Excel"}

        self._log(f"Excel: {excel_path}")
        self._log(f"Project: {self.project_code}")

        # Load Excel
        workbook = PromptWorkbook(excel_path)
        workbook.load_or_create()

        # Lay cac scene can tao anh
        all_scenes = workbook.get_scenes()
        scenes_to_process = []

        for scene in all_scenes:
            # Filter theo range
            if scene.scene_id < start_scene:
                continue
            if end_scene is not None and scene.scene_id > end_scene:
                break

            # Skip neu khong co prompt
            if not scene.img_prompt:
                continue

            # Skip neu da done va khong overwrite
            if scene.status_img == "done" and not overwrite:
                self.stats["skipped"] += 1
                continue

            scenes_to_process.append(scene)

        if not scenes_to_process:
            self._log("Khong co scene nao can tao anh", "warn")
            return {"success": True, "message": "No scenes to process"}

        self._log(f"Se tao {len(scenes_to_process)} anh")
        self.stats["total"] = len(scenes_to_process)

        # Khoi dong browser
        if not self.driver:
            if not self.start_browser():
                return {"success": False, "error": "Khong khoi dong duoc browser"}

            # Cho dang nhap
            if not self.wait_for_login(timeout=120):
                self.stop_browser()
                return {"success": False, "error": "Chua dang nhap"}

        # Inject JS
        if not self._inject_js():
            return {"success": False, "error": "Khong inject duoc JS"}

        # Chuan bi prompts cho VE3.run()
        # QUAN TRONG: Dung numeric ID (1, 2, 3) de khop voi SmartEngine video composer
        prompts_data = []
        for scene in scenes_to_process:
            scene_id = str(scene.scene_id)  # Dung numeric ID, khong phai scene_001
            prompts_data.append({
                "sceneId": scene_id,
                "prompt": scene.img_prompt
            })

        self._log(f"\nBat dau tao {len(prompts_data)} anh...")

        # DEBUG: Hien thi scene dau tien de kiem tra data
        if scenes_to_process:
            s = scenes_to_process[0]
            self._log(f"[DEBUG] Scene dau tien: id={s.scene_id}, srt_start={s.srt_start}")
            self._log(f"[DEBUG] img_prompt = '{s.img_prompt[:100] if s.img_prompt else 'EMPTY'}'")

        # Goi VE3.run() - xu ly tung prompt mot de cap nhat Excel theo thoi gian thuc
        for i, item in enumerate(prompts_data):
            scene = scenes_to_process[i]
            scene_id = item["sceneId"]
            prompt = item["prompt"]

            self._log(f"\n[{i+1}/{len(prompts_data)}] Scene {scene_id}")
            self._log(f"Prompt ({len(prompt)} chars): {prompt[:100]}...")

            try:
                # Goi VE3.run() cho 1 prompt
                result = self.driver.execute_async_script(f"""
                    const callback = arguments[arguments.length - 1];
                    const timeout = setTimeout(() => {{
                        callback({{ success: false, error: 'Timeout 120s' }});
                    }}, 120000);

                    VE3.run([{{
                        sceneId: "{scene_id}",
                        prompt: `{self._escape_js_string(prompt)}`
                    }}]).then(r => {{
                        clearTimeout(timeout);
                        callback({{ success: true, result: r }});
                    }}).catch(e => {{
                        clearTimeout(timeout);
                        callback({{ success: false, error: e.message }});
                    }});
                """)

                if result and result.get("success"):
                    # Di chuyen file - scene_id la numeric ("1", "2", ...)
                    img_file, score, needs_regen = self._move_downloaded_images(scene_id)

                    if img_file:
                        # Cap nhat Excel - dung numeric ID
                        relative_path = f"img/{scene_id}.png"
                        workbook.update_scene(
                            scene.scene_id,  # scene.scene_id la int
                            img_path=relative_path,
                            status_img="done" if not needs_regen else "low_quality"
                        )
                        workbook.save()

                        if needs_regen:
                            self._log(f"Anh {scene_id} chua dat chuan (score={score:.1f}), can tao lai", "warn")
                            self.stats["low_quality"] = self.stats.get("low_quality", 0) + 1
                        else:
                            self._log(f"Da cap nhat Excel: {scene_id} = done (score={score:.1f})", "success")
                        self.stats["success"] += 1
                    else:
                        workbook.update_scene(scene.scene_id, status_img="error")
                        workbook.save()
                        self.stats["failed"] += 1
                else:
                    error = result.get("error", "Unknown") if result else "No response"
                    self._log(f"Loi: {error}", "error")
                    workbook.update_scene(scene.scene_id, status_img="error")
                    workbook.save()
                    self.stats["failed"] += 1

                # Delay giua cac prompt
                if i < len(prompts_data) - 1:
                    time.sleep(2)

            except Exception as e:
                self._log(f"Exception: {e}", "error")
                workbook.update_scene(scene.scene_id, status_img="error")
                workbook.save()
                self.stats["failed"] += 1

        # Summary
        self._log("\n" + "=" * 60)
        self._log("HOAN THANH")
        self._log("=" * 60)
        self._log(f"Tong: {self.stats['total']}")
        self._log(f"Thanh cong: {self.stats['success']}")
        self._log(f"That bai: {self.stats['failed']}")
        self._log(f"Bo qua: {self.stats['skipped']}")

        return {
            "success": True,
            "stats": self.stats.copy()
        }

    def _process_single_prompt(self, prompt_data: Dict, index: int, total: int) -> Tuple[bool, Optional[Path], float]:
        """
        Xu ly mot prompt don le.

        Returns:
            Tuple[success, image_path, score]
        """
        pid = str(prompt_data.get('id', index + 1))
        prompt = prompt_data.get('prompt', '')

        self._log(f"\n[{index+1}/{total}] ID: {pid}")
        self._log(f"Prompt ({len(prompt)} chars): {prompt[:100]}...")

        if not prompt:
            self._log("Skip - prompt rong", "warn")
            return False, None, 0.0

        try:
            # Goi VE3.run() cho 1 prompt
            result = self.driver.execute_async_script(f"""
                const callback = arguments[arguments.length - 1];
                const timeout = setTimeout(() => {{
                    callback({{ success: false, error: 'Timeout 120s' }});
                }}, 120000);

                VE3.run([{{
                    sceneId: "{pid}",
                    prompt: `{self._escape_js_string(prompt)}`
                }}]).then(r => {{
                    clearTimeout(timeout);
                    callback({{ success: true, result: r }});
                }}).catch(e => {{
                    clearTimeout(timeout);
                    callback({{ success: false, error: e.message }});
                }});
            """)

            if result and result.get("success"):
                # Di chuyen file tu Downloads (timeout 2 phut)
                img_file, score, needs_regen = self._move_downloaded_images(pid)

                if img_file:
                    if needs_regen:
                        self._log(f"OK - Da tao anh nhung chua dat chuan (score={score:.1f})", "warn")
                    else:
                        self._log(f"OK - Da tao va luu anh (score={score:.1f})", "success")
                    return True, img_file, score
                else:
                    self._log(f"Khong tim thay file download sau 2 phut", "warn")
                    return False, None, 0.0
            else:
                error = result.get("error", "Unknown") if result else "No response"
                self._log(f"Loi: {error}", "error")
                return False, None, 0.0

        except Exception as e:
            self._log(f"Exception: {e}", "error")
            return False, None, 0.0

    def _restart_browser_and_setup(self) -> bool:
        """
        Khoi dong lai browser va setup (dung khi setup that bai).

        Returns:
            True neu thanh cong
        """
        self._log("Khoi dong lai browser...", "warn")

        # Dong browser cu
        self.stop_browser()
        self._js_injected = False

        # Doi 3 giay
        time.sleep(3)

        # Khoi dong lai
        if not self.start_browser():
            return False

        if not self.wait_for_login(timeout=120):
            self.stop_browser()
            return False

        # Inject JS
        if not self._inject_js():
            return False

        return True

    def generate_from_prompts(
        self,
        prompts: List[Dict],
        excel_path: Optional[Path] = None,
        max_setup_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Tao anh tu danh sach prompts da load san (tu smart_engine._load_prompts).
        Method nay nhan prompts truc tiep thay vi doc lai tu Excel.

        Features:
        - Neu prompt dau tien that bai (co the do setup loi), tu dong restart browser va thu lai (toi da 3 lan)
        - Theo doi cac prompt that bai va retry o cuoi
        - Timeout 2 phut cho moi anh

        Args:
            prompts: List cac dict co dang {'id': '1', 'prompt': '...', 'output_path': '...'}
            excel_path: Duong dan Excel (de cap nhat status)
            max_setup_retries: So lan retry toi da neu setup that bai (default: 3)

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("BROWSER FLOW GENERATOR - TAO ANH TU PROMPTS")
        self._log("=" * 60)

        if not prompts:
            return {"success": False, "error": "Khong co prompts"}

        self._log(f"Tong: {len(prompts)} prompts")
        self._log(f"Project: {self.project_code}")

        # Reset stats
        self.stats = {"total": len(prompts), "success": 0, "failed": 0, "skipped": 0, "low_quality": 0}

        # Khoi dong browser
        if not self.driver:
            if not self.start_browser():
                return {"success": False, "error": "Khong khoi dong duoc browser"}

            if not self.wait_for_login(timeout=120):
                self.stop_browser()
                return {"success": False, "error": "Chua dang nhap"}

        # Inject JS
        if not self._inject_js():
            return {"success": False, "error": "Khong inject duoc JS"}

        self._log(f"\nBat dau tao {len(prompts)} anh...")

        # DEBUG: Hien thi prompt dau tien
        if prompts:
            p = prompts[0]
            self._log(f"[DEBUG] Prompt dau tien: id={p.get('id')}")
            self._log(f"[DEBUG] prompt = '{str(p.get('prompt', ''))[:100]}'")

        # Track failed prompts de retry sau
        failed_prompts = []  # List of (prompt_data, original_index)

        # === XU LY PROMPT DAU TIEN VOI SETUP RETRY ===
        first_prompt_success = False
        setup_attempts = 0

        while not first_prompt_success and setup_attempts < max_setup_retries:
            setup_attempts += 1

            if setup_attempts > 1:
                self._log(f"\n=== SETUP RETRY {setup_attempts}/{max_setup_retries} ===", "warn")
                if not self._restart_browser_and_setup():
                    self._log(f"Khong the khoi dong lai browser", "error")
                    continue

            # Thu prompt dau tien
            success, img_file, score = self._process_single_prompt(prompts[0], 0, len(prompts))

            if success:
                first_prompt_success = True
                self.stats["success"] += 1
                if score < 50.0:
                    self.stats["low_quality"] += 1
            else:
                self._log(f"Prompt dau tien that bai (lan {setup_attempts})", "error")

        if not first_prompt_success:
            # Da thu het so lan retry, ghi nhan that bai
            self._log(f"Prompt dau tien that bai sau {max_setup_retries} lan thu", "error")
            failed_prompts.append((prompts[0], 0))
            self.stats["failed"] += 1

        # === XU LY CAC PROMPT CON LAI ===
        for i, prompt_data in enumerate(prompts[1:], start=1):
            pid = str(prompt_data.get('id', i + 1))
            prompt = prompt_data.get('prompt', '')

            if not prompt:
                self._log(f"\n[{i+1}/{len(prompts)}] ID: {pid} - Skip (prompt rong)", "warn")
                self.stats["skipped"] += 1
                continue

            success, img_file, score = self._process_single_prompt(prompt_data, i, len(prompts))

            if success:
                self.stats["success"] += 1
                if score < 50.0:
                    self.stats["low_quality"] += 1
            else:
                failed_prompts.append((prompt_data, i))
                self.stats["failed"] += 1

            # Delay giua cac prompt
            if i < len(prompts) - 1:
                time.sleep(2)

        # === RETRY FAILED PROMPTS ===
        if failed_prompts:
            self._log("\n" + "=" * 60)
            self._log(f"RETRY {len(failed_prompts)} ANH THAT BAI")
            self._log("=" * 60)

            retry_success = 0
            for prompt_data, original_index in failed_prompts:
                pid = str(prompt_data.get('id', original_index + 1))
                self._log(f"\nRetry ID: {pid}")

                success, img_file, score = self._process_single_prompt(
                    prompt_data, original_index, len(prompts)
                )

                if success:
                    retry_success += 1
                    self.stats["success"] += 1
                    self.stats["failed"] -= 1  # Giam failed vi da thanh cong
                    if score < 50.0:
                        self.stats["low_quality"] += 1

                # Delay
                time.sleep(2)

            self._log(f"\nRetry: {retry_success}/{len(failed_prompts)} thanh cong")

        # Summary
        self._log("\n" + "=" * 60)
        self._log("HOAN THANH")
        self._log("=" * 60)
        self._log(f"Tong: {self.stats['total']}")
        self._log(f"Thanh cong: {self.stats['success']}")
        self._log(f"That bai: {self.stats['failed']}")
        self._log(f"Bo qua: {self.stats['skipped']}")
        if self.stats.get('low_quality', 0) > 0:
            self._log(f"Chat luong thap: {self.stats['low_quality']}")

        return {
            "success": True,
            "stats": self.stats.copy()
        }

    def generate_character_images(
        self,
        excel_path: Optional[Path] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Tao anh cho cac nhan vat trong Excel.

        Args:
            excel_path: Duong dan file Excel
            overwrite: Ghi de anh da co

        Returns:
            Dict voi ket qua
        """
        self._log("=" * 60)
        self._log("TAO ANH NHAN VAT")
        self._log("=" * 60)

        # Tim file Excel
        if excel_path is None:
            excel_path = self._find_excel_file()

        if excel_path is None or not excel_path.exists():
            return {"success": False, "error": "Khong tim thay file Excel"}

        # Load Excel
        workbook = PromptWorkbook(excel_path)
        workbook.load_or_create()

        # Lay cac nhan vat can tao anh
        characters = workbook.get_characters()
        chars_to_process = []

        for char in characters:
            if not char.english_prompt:
                continue

            if char.status == "done" and not overwrite:
                continue

            chars_to_process.append(char)

        if not chars_to_process:
            self._log("Khong co nhan vat nao can tao anh", "warn")
            return {"success": True, "message": "No characters to process"}

        self._log(f"Se tao {len(chars_to_process)} anh nhan vat")

        # Khoi dong browser neu chua
        if not self.driver:
            if not self.start_browser():
                return {"success": False, "error": "Khong khoi dong duoc browser"}

            if not self.wait_for_login(timeout=120):
                self.stop_browser()
                return {"success": False, "error": "Chua dang nhap"}

        if not self._inject_js():
            return {"success": False, "error": "Khong inject duoc JS"}

        success_count = 0
        failed_count = 0

        for i, char in enumerate(chars_to_process):
            char_id = char.id or f"char_{i+1}"
            prompt = char.english_prompt

            self._log(f"\n[{i+1}/{len(chars_to_process)}] Nhan vat: {char_id}")

            try:
                result = self.driver.execute_async_script(f"""
                    const callback = arguments[arguments.length - 1];
                    VE3.run([{{
                        sceneId: "{char_id}",
                        prompt: `{self._escape_js_string(prompt)}`
                    }}]).then(r => {{
                        callback({{ success: true, result: r }});
                    }}).catch(e => {{
                        callback({{ success: false, error: e.message }});
                    }});
                """)

                if result and result.get("success"):
                    # Di chuyen file vao nv/
                    pattern = f"{self.project_code}_{char_id}*.png"
                    files = self._find_downloaded_files(pattern, wait_timeout=120)

                    if files:
                        dst_file = self.nv_path / f"{char_id}.png"
                        shutil.move(str(files[0]), str(dst_file))

                        workbook.update_character(char_id, status="done", image_file=f"{char_id}.png")
                        workbook.save()

                        self._log(f"Da luu: {dst_file}", "success")
                        success_count += 1
                    else:
                        workbook.update_character(char_id, status="error")
                        workbook.save()
                        failed_count += 1
                else:
                    failed_count += 1

                if i < len(chars_to_process) - 1:
                    time.sleep(2)

            except Exception as e:
                self._log(f"Loi: {e}", "error")
                failed_count += 1

        self._log(f"\nNhan vat: {success_count} thanh cong, {failed_count} that bai")

        return {
            "success": True,
            "characters_success": success_count,
            "characters_failed": failed_count
        }

    def generate_all(
        self,
        characters: bool = True,
        scenes: bool = True,
        start_scene: int = 1,
        end_scene: Optional[int] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Tao tat ca anh (nhan vat + scenes).

        Args:
            characters: Tao anh nhan vat
            scenes: Tao anh scenes
            start_scene: Scene bat dau
            end_scene: Scene ket thuc
            overwrite: Ghi de

        Returns:
            Dict voi ket qua
        """
        results = {
            "characters": {},
            "scenes": {},
        }

        try:
            if characters:
                results["characters"] = self.generate_character_images(overwrite=overwrite)

            if scenes:
                results["scenes"] = self.generate_scene_images(
                    start_scene=start_scene,
                    end_scene=end_scene,
                    overwrite=overwrite
                )
        finally:
            # Dong browser khi xong
            self.stop_browser()

        return results

    def _escape_js_string(self, s: str) -> str:
        """Escape string cho JavaScript."""
        return (s
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("$", "\\$")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t"))

    def __enter__(self):
        """Context manager entry."""
        self.start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_browser()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_browser_flow_generator(
    project_path: str,
    profile_name: str = "main",
    headless: bool = False,
    verbose: bool = True
) -> BrowserFlowGenerator:
    """
    Factory function de tao BrowserFlowGenerator.

    Args:
        project_path: Duong dan project
        profile_name: Ten Chrome profile
        headless: Chay an
        verbose: In log

    Returns:
        BrowserFlowGenerator instance
    """
    return BrowserFlowGenerator(
        project_path=project_path,
        profile_name=profile_name,
        headless=headless,
        verbose=verbose
    )


def generate_images_from_excel(
    project_path: str,
    profile_name: str = "main",
    headless: bool = False,
    characters: bool = True,
    scenes: bool = True,
    start_scene: int = 1,
    end_scene: Optional[int] = None,
    overwrite: bool = False
) -> Dict[str, Any]:
    """
    Ham tien ich de tao anh tu Excel.

    Args:
        project_path: Duong dan project (PROJECTS/KA1-0001)
        profile_name: Ten Chrome profile
        headless: Chay an
        characters: Tao anh nhan vat
        scenes: Tao anh scenes
        start_scene: Scene bat dau
        end_scene: Scene ket thuc
        overwrite: Ghi de anh cu

    Returns:
        Dict voi ket qua
    """
    generator = BrowserFlowGenerator(
        project_path=project_path,
        profile_name=profile_name,
        headless=headless,
        verbose=True
    )

    return generator.generate_all(
        characters=characters,
        scenes=scenes,
        start_scene=start_scene,
        end_scene=end_scene,
        overwrite=overwrite
    )


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    print("""
+============================================================+
|      BROWSER FLOW GENERATOR - VE3 TOOL                     |
+============================================================+
|  Tao anh tu Excel bang browser automation                  |
|                                                            |
|  Usage:                                                    |
|    python browser_flow_generator.py <project_path>         |
|                                                            |
|  Options:                                                  |
|    --profile <name>    Chrome profile name (default: main) |
|    --headless          Chay an (khong hien UI)             |
|    --characters        Chi tao anh nhan vat                |
|    --scenes            Chi tao anh scenes                  |
|    --start N           Bat dau tu scene N                  |
|    --end N             Ket thuc o scene N                  |
|    --overwrite         Ghi de anh da co                    |
+============================================================+
""")

    if not SELENIUM_AVAILABLE:
        print("Error: Selenium chua duoc cai dat")
        print("Chay: pip install selenium undetected-chromedriver")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Vui long cung cap duong dan project")
        print("Vi du: python browser_flow_generator.py ./PROJECTS/KA1-0001")
        sys.exit(1)

    project_path = sys.argv[1]

    # Parse options
    profile_name = "main"
    headless = "--headless" in sys.argv
    do_characters = "--characters" in sys.argv or "--scenes" not in sys.argv
    do_scenes = "--scenes" in sys.argv or "--characters" not in sys.argv
    overwrite = "--overwrite" in sys.argv
    start_scene = 1
    end_scene = None

    for i, arg in enumerate(sys.argv):
        if arg == "--profile" and i + 1 < len(sys.argv):
            profile_name = sys.argv[i + 1]
        if arg == "--start" and i + 1 < len(sys.argv):
            start_scene = int(sys.argv[i + 1])
        if arg == "--end" and i + 1 < len(sys.argv):
            end_scene = int(sys.argv[i + 1])

    # Run
    results = generate_images_from_excel(
        project_path=project_path,
        profile_name=profile_name,
        headless=headless,
        characters=do_characters,
        scenes=do_scenes,
        start_scene=start_scene,
        end_scene=end_scene,
        overwrite=overwrite
    )

    # Exit code
    scenes_failed = results.get("scenes", {}).get("stats", {}).get("failed", 0)
    chars_failed = results.get("characters", {}).get("characters_failed", 0)

    sys.exit(0 if (scenes_failed + chars_failed) == 0 else 1)
