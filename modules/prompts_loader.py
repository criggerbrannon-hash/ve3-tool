"""
VE3 Tool - Prompts Loader
=========================
Load prompts từ file config/prompts.yaml
Cho phép chỉnh sửa prompts mà không cần sửa code
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

import yaml


class PromptsLoader:
    """Load và cache prompts từ YAML file."""

    _instance = None
    _prompts = None
    _last_modified = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        config_dir = os.environ.get('VE3_CONFIG_DIR', 'config')
        self.prompts_path = Path(config_dir) / "prompts.yaml"

    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompts từ file, auto-reload nếu file thay đổi."""
        if not self.prompts_path.exists():
            return self._get_defaults()

        try:
            mtime = self.prompts_path.stat().st_mtime
            if self._prompts is None or mtime > self._last_modified:
                with open(self.prompts_path, 'r', encoding='utf-8') as f:
                    self._prompts = yaml.safe_load(f) or {}
                self._last_modified = mtime
            return self._prompts
        except Exception as e:
            print(f"[PromptsLoader] Error loading prompts: {e}")
            return self._get_defaults()

    def _get_defaults(self) -> Dict[str, Any]:
        """Default prompts nếu file không tồn tại."""
        return {
            "analyze_story": "Analyze the story and identify characters...",
            "generate_scenes": "Generate image and video prompts for scenes...",
            "test_prompt": "beautiful sunset over ocean",
            "style_prefix": "",
            "video_style_prefix": ""
        }

    def get(self, key: str, default: str = "") -> str:
        """Lấy một prompt theo key."""
        prompts = self._load_prompts()
        return prompts.get(key, default)

    def get_analyze_story(self) -> str:
        """Lấy prompt phân tích nhân vật."""
        return self.get("analyze_story", "")

    def get_generate_scenes(self) -> str:
        """Lấy prompt tạo scene."""
        return self.get("generate_scenes", "")

    def get_test_prompt(self) -> str:
        """Lấy prompt test cho token extraction."""
        return self.get("test_prompt", "beautiful sunset over ocean")

    def get_style_prefix(self) -> str:
        """Lấy style prefix cho image prompts."""
        return self.get("style_prefix", "")

    def get_video_style_prefix(self) -> str:
        """Lấy style prefix cho video prompts."""
        return self.get("video_style_prefix", "")

    def get_global_style(self) -> str:
        """Lấy global style cho tất cả scenes."""
        return self.get("global_style", "Cinematic 4K photorealistic")

    def get_global_lighting(self) -> str:
        """Lấy global lighting protocol."""
        return self.get("global_lighting", "Face illuminated by soft volumetric light")

    def reload(self):
        """Force reload prompts từ file."""
        self._prompts = None
        self._last_modified = 0
        self._load_prompts()


# Singleton instance
_loader = None

def get_prompts_loader() -> PromptsLoader:
    """Get singleton PromptsLoader instance."""
    global _loader
    if _loader is None:
        _loader = PromptsLoader()
    return _loader


# Convenience functions
def get_prompt(key: str, default: str = "") -> str:
    """Lấy prompt theo key."""
    return get_prompts_loader().get(key, default)

def get_analyze_story_prompt() -> str:
    """Lấy prompt phân tích nhân vật."""
    return get_prompts_loader().get_analyze_story()

def get_generate_scenes_prompt() -> str:
    """Lấy prompt tạo scene."""
    return get_prompts_loader().get_generate_scenes()

def get_test_prompt() -> str:
    """Lấy prompt test."""
    return get_prompts_loader().get_test_prompt()

def get_global_style() -> str:
    """Lấy global style."""
    return get_prompts_loader().get_global_style()

def get_global_lighting() -> str:
    """Lấy global lighting."""
    return get_prompts_loader().get_global_lighting()

def reload_prompts():
    """Force reload prompts."""
    get_prompts_loader().reload()
