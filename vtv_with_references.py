#!/usr/bin/env python3
"""
VTV Tool - Generate Images với Reference Images
================================================
Workflow đúng:
1. Upload ảnh reference (nv, loc) -> lấy media_name
2. Generate scene với media_name (KHÔNG phải base64)

Usage:
    python vtv_with_references.py <project_path> <bearer_token>

Example:
    python vtv_with_references.py "PROJECTS/1" "ya29.xxx..."
"""

import os
import sys
import json
import time
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.google_flow_api import (
    GoogleFlowAPI,
    AspectRatio,
    ImageInput,
    ImageInputType,
    GeneratedImage
)


class VTVGenerator:
    """
    VTV Generator với Reference Images support.

    Workflow:
    1. Upload ảnh từ nv/ folder -> lấy media_name
    2. Generate scene images với media_name làm reference
    """

    def __init__(
        self,
        project_path: str,
        bearer_token: str,
        parallel_workers: int = 2,
        delay: float = 2.0,
        verbose: bool = True
    ):
        self.project_path = Path(project_path)
        self.bearer_token = bearer_token
        self.parallel = parallel_workers
        self.delay = delay
        self.verbose = verbose

        # Paths
        self.nv_path = self.project_path / "nv"
        self.img_path = self.project_path / "img"
        self.prompts_path = self.project_path / "prompts"

        # Ensure directories exist
        self.nv_path.mkdir(parents=True, exist_ok=True)
        self.img_path.mkdir(parents=True, exist_ok=True)

        # API client
        self.api = GoogleFlowAPI(
            bearer_token=bearer_token,
            verbose=verbose
        )

        # Reference cache: char_id -> media_name
        # QUAN TRỌNG: Lưu media_name, KHÔNG phải base64!
        self.reference_cache: Dict[str, str] = {}

        # Lock for thread safety
        self._lock = threading.Lock()
        self._stop = False

    def log(self, msg: str, level: str = "INFO"):
        """Log message."""
        if self.verbose:
            ts = datetime.now().strftime("%H:%M:%S")
            prefix = {"OK": "✅", "ERROR": "❌", "WARN": "⚠️", "INFO": "ℹ️"}.get(level, "•")
            print(f"[{ts}] [{level}] {prefix} {msg}")

    # =========================================================================
    # STEP 1: Upload references để lấy media_name
    # =========================================================================

    def upload_reference(self, image_path: Path) -> Optional[str]:
        """
        Upload 1 ảnh reference và trả về media_name.

        QUAN TRỌNG: Trả về media_name (string từ API response),
        KHÔNG phải base64 data!

        Returns:
            media_name string hoặc None nếu fail
        """
        if not image_path.exists():
            self.log(f"Reference not found: {image_path}", "WARN")
            return None

        self.log(f"Uploading reference: {image_path.name}...")

        success, img_input, error = self.api.upload_image(image_path)

        if success and img_input:
            media_name = img_input.name  # Đây là media_name từ API, KHÔNG phải base64
            self.log(f"  -> Got media_name: {media_name[:50]}...", "OK")
            return media_name
        else:
            self.log(f"  -> Upload failed: {error}", "ERROR")
            return None

    def upload_all_references(self) -> int:
        """
        Upload tất cả ảnh trong nv/ folder.

        Returns:
            Số lượng references đã upload thành công
        """
        self.log("=" * 50)
        self.log("UPLOADING REFERENCE IMAGES")
        self.log("=" * 50)

        if not self.nv_path.exists():
            self.log(f"NV folder not found: {self.nv_path}", "WARN")
            return 0

        uploaded = 0

        for img_path in self.nv_path.glob("*.png"):
            ref_id = img_path.stem  # nv1.png -> nv1, loc1.png -> loc1

            # Skip if already in cache
            if ref_id in self.reference_cache:
                self.log(f"  {ref_id}: Already cached, skip")
                uploaded += 1
                continue

            media_name = self.upload_reference(img_path)

            if media_name:
                self.reference_cache[ref_id] = media_name
                uploaded += 1

        self.log(f"Total: {uploaded} references uploaded", "OK")
        return uploaded

    # =========================================================================
    # STEP 2: Generate với references
    # =========================================================================

    def generate_with_references(
        self,
        prompt: str,
        reference_ids: List[str],  # ["nv1", "nv2", "loc1"]
        output_path: Path
    ) -> bool:
        """
        Generate 1 ảnh với references.

        Args:
            prompt: Text prompt
            reference_ids: List of reference IDs (phải đã upload trước)
            output_path: Đường dẫn lưu ảnh output

        Returns:
            True nếu thành công
        """
        # Build image_inputs từ cache
        image_inputs = []

        for ref_id in reference_ids:
            if ref_id in self.reference_cache:
                media_name = self.reference_cache[ref_id]

                # QUAN TRỌNG: Gửi media_name, KHÔNG phải base64!
                image_inputs.append(ImageInput(
                    name=media_name,  # Đây phải là media_name từ upload response
                    input_type=ImageInputType.REFERENCE
                ))
                self.log(f"  -> Using reference: {ref_id}")
            else:
                self.log(f"  -> Reference not in cache: {ref_id}", "WARN")

        if image_inputs:
            self.log(f"  -> Total {len(image_inputs)} references")

        # Generate
        success, images, error = self.api.generate_images(
            prompt=prompt,
            count=1,
            aspect_ratio=AspectRatio.LANDSCAPE,
            image_inputs=image_inputs if image_inputs else None
        )

        if success and images:
            # Download
            downloaded = self.api.download_image(
                images[0],
                output_path.parent,
                output_path.stem
            )

            if downloaded:
                self.log(f"  -> Saved: {downloaded}", "OK")
                return True

        self.log(f"  -> Generate failed: {error}", "ERROR")
        return False

    # =========================================================================
    # MAIN: Load prompts và generate
    # =========================================================================

    def load_prompts(self) -> List[Dict]:
        """Load prompts từ Excel."""
        import openpyxl

        # Find Excel file
        excel_files = list(self.prompts_path.glob("*_prompts.xlsx")) + \
                     list(self.prompts_path.glob("*.xlsx"))

        if not excel_files:
            # Try project root
            excel_files = list(self.project_path.glob("*_prompts.xlsx")) + \
                         list(self.project_path.glob("*.xlsx"))

        if not excel_files:
            self.log("No Excel file found!", "ERROR")
            return []

        excel_path = excel_files[0]
        self.log(f"Loading prompts from: {excel_path}")

        prompts = []
        wb = openpyxl.load_workbook(excel_path, read_only=True)

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            headers = [c.value for c in ws[1]]

            if not headers:
                continue

            # Find columns
            id_col = prompt_col = ref_col = None

            for i, h in enumerate(headers):
                if not h:
                    continue
                h_lower = str(h).lower()

                if 'id' in h_lower and id_col is None:
                    id_col = i
                if 'english' in h_lower and 'prompt' in h_lower:
                    prompt_col = i
                elif h_lower == 'img_prompt' and prompt_col is None:
                    prompt_col = i
                elif 'prompt' in h_lower and prompt_col is None and 'video' not in h_lower:
                    prompt_col = i
                if h_lower in ['references', 'ref', 'nv', 'characters', 'refs']:
                    ref_col = i

            if id_col is None or prompt_col is None:
                continue

            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or len(row) <= max(id_col, prompt_col):
                    continue

                pid = row[id_col]
                prompt = row[prompt_col]

                if not pid or not prompt:
                    continue

                # Parse references
                refs = []
                if ref_col is not None and ref_col < len(row) and row[ref_col]:
                    ref_str = str(row[ref_col])
                    for sep in [',', ';', '|', ' ']:
                        if sep in ref_str:
                            refs = [r.strip() for r in ref_str.split(sep) if r.strip()]
                            break
                    if not refs:
                        refs = [ref_str.strip()]

                # Determine output path
                pid_str = str(pid).strip()
                if pid_str.startswith('nv') or pid_str.startswith('loc'):
                    out_path = self.nv_path / f"{pid_str}.png"
                else:
                    out_path = self.img_path / f"{pid_str}.png"

                prompts.append({
                    'id': pid_str,
                    'prompt': str(prompt),
                    'references': refs,
                    'output_path': out_path,
                    'sheet': sheet_name
                })

        wb.close()
        self.log(f"Loaded {len(prompts)} prompts", "OK")
        return prompts

    def run(self, skip_existing: bool = True) -> Dict:
        """
        Chạy toàn bộ pipeline.

        Returns:
            Dict với kết quả
        """
        self.log("=" * 60)
        self.log("VTV GENERATOR WITH REFERENCES")
        self.log("=" * 60)

        results = {"success": 0, "failed": 0, "skipped": 0}

        # Step 1: Upload all references
        self.upload_all_references()

        if not self.reference_cache:
            self.log("No references uploaded. Continuing without references...", "WARN")

        # Step 2: Load prompts
        prompts = self.load_prompts()

        if not prompts:
            self.log("No prompts to process!", "ERROR")
            return results

        # Filter existing
        if skip_existing:
            prompts = [p for p in prompts if not p['output_path'].exists()]
            self.log(f"After filtering existing: {len(prompts)} to generate")

        if not prompts:
            self.log("All images already exist!", "OK")
            return results

        # Step 3: Generate images
        self.log("=" * 50)
        self.log(f"GENERATING {len(prompts)} IMAGES")
        self.log("=" * 50)

        for i, p in enumerate(prompts):
            if self._stop:
                break

            pid = p['id']
            prompt = p['prompt']
            refs = p['references']
            out_path = p['output_path']

            self.log(f"\n[{i+1}/{len(prompts)}] {pid}")
            self.log(f"  Prompt: {prompt[:60]}...")

            if refs:
                self.log(f"  References: {refs}")

            success = self.generate_with_references(prompt, refs, out_path)

            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

            # Delay
            if i < len(prompts) - 1:
                time.sleep(self.delay)

        # Summary
        self.log("\n" + "=" * 50)
        self.log("SUMMARY")
        self.log("=" * 50)
        self.log(f"Success: {results['success']}", "OK")
        self.log(f"Failed: {results['failed']}", "ERROR" if results['failed'] > 0 else "INFO")

        return results

    def stop(self):
        """Stop processing."""
        self._stop = True


# =============================================================================
# CLI
# =============================================================================

def main():
    if len(sys.argv) < 3:
        print("""
VTV Generator với Reference Images
===================================
Usage:
    python vtv_with_references.py <project_path> <bearer_token>

Example:
    python vtv_with_references.py "PROJECTS/1" "ya29.a0AfH6..."

Project structure:
    PROJECTS/1/
    ├── nv/           # Ảnh reference (nv1.png, nv2.png, loc1.png, ...)
    ├── img/          # Output images
    └── prompts/      # Excel file với prompts
        └── xxx_prompts.xlsx
            - Sheet với columns: id, english_prompt/img_prompt, references
            - references column: "nv1, nv2, loc1" (comma-separated)
""")
        sys.exit(1)

    project_path = sys.argv[1]
    bearer_token = sys.argv[2]

    generator = VTVGenerator(
        project_path=project_path,
        bearer_token=bearer_token,
        parallel_workers=2,
        delay=2.0,
        verbose=True
    )

    results = generator.run()

    # Exit code
    sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
