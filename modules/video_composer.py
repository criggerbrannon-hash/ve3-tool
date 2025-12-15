"""
Video Composer Module
Ghép ảnh thành video hoàn chỉnh với voice và phụ đề.

Requires: FFmpeg installed on system
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import tempfile
import shutil

from modules.excel_manager import PromptWorkbook, Scene


@dataclass
class VideoConfig:
    """Cấu hình video output."""
    width: int = 1920
    height: int = 1080
    fps: int = 30
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 23  # Quality (0-51, lower = better)
    preset: str = "medium"  # ultrafast, fast, medium, slow

    # Subtitle settings
    font_name: str = "Arial"
    font_size: int = 24
    font_color: str = "white"
    outline_color: str = "black"
    outline_width: int = 2
    margin_bottom: int = 50

    # Transition settings (seconds)
    fade_duration: float = 0.0  # 0 = no fade, 0.5 = half second fade


class VideoComposer:
    """
    Ghép ảnh thành video hoàn chỉnh.

    Flow:
    1. Đọc scenes từ Excel (ảnh + timestamps)
    2. Tạo video từ ảnh (FFmpeg)
    3. Thêm audio (voice)
    4. Burn phụ đề
    5. Output video hoàn chỉnh
    """

    def __init__(self, config: Optional[VideoConfig] = None):
        self.config = config or VideoConfig()
        self.logger = logging.getLogger(__name__)

        # Check FFmpeg availability
        if not self._check_ffmpeg():
            raise RuntimeError("FFmpeg not found! Please install FFmpeg.")

    def _check_ffmpeg(self) -> bool:
        """Kiểm tra FFmpeg đã cài đặt chưa."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _parse_timestamp(self, timestamp: str) -> float:
        """
        Chuyển timestamp SRT sang giây.
        Format: "00:01:23,456" -> 83.456
        """
        if not timestamp:
            return 0.0

        # Handle both "," and "." as millisecond separator
        timestamp = timestamp.replace(",", ".")

        parts = timestamp.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        elif len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        else:
            return float(timestamp)

    def compose_video(
        self,
        excel_path: str,
        voice_path: str,
        output_path: str,
        srt_path: Optional[str] = None
    ) -> bool:
        """
        Ghép video hoàn chỉnh từ Excel + voice + phụ đề.

        Args:
            excel_path: Đường dẫn file Excel chứa scenes
            voice_path: Đường dẫn file audio (mp3/wav)
            output_path: Đường dẫn video output
            srt_path: Đường dẫn file SRT (optional, nếu không có sẽ dùng text từ Excel)

        Returns:
            True nếu thành công
        """
        try:
            self.logger.info("=" * 50)
            self.logger.info("VIDEO COMPOSER - Bắt đầu ghép video")
            self.logger.info("=" * 50)

            # 1. Load scenes từ Excel
            workbook = PromptWorkbook(excel_path)
            scenes = workbook.get_scenes()

            if not scenes:
                self.logger.error("Không có scenes trong Excel!")
                return False

            # Filter scenes có ảnh
            valid_scenes = [s for s in scenes if s.img_path and os.path.exists(s.img_path)]
            self.logger.info(f"Tìm thấy {len(valid_scenes)}/{len(scenes)} scenes có ảnh")

            if not valid_scenes:
                self.logger.error("Không có ảnh nào để ghép!")
                return False

            # 2. Tạo video từ ảnh
            temp_dir = tempfile.mkdtemp()
            try:
                video_no_audio = os.path.join(temp_dir, "video_no_audio.mp4")
                video_with_audio = os.path.join(temp_dir, "video_with_audio.mp4")

                # Step 1: Ghép ảnh thành video
                self.logger.info("Step 1: Ghép ảnh thành video...")
                if not self._create_video_from_images(valid_scenes, video_no_audio):
                    return False

                # Step 2: Thêm audio
                self.logger.info("Step 2: Thêm voice audio...")
                if not self._add_audio(video_no_audio, voice_path, video_with_audio):
                    return False

                # Step 3: Burn phụ đề
                self.logger.info("Step 3: Burn phụ đề...")
                if srt_path and os.path.exists(srt_path):
                    if not self._burn_subtitles(video_with_audio, srt_path, output_path):
                        return False
                else:
                    # Không có SRT, copy video
                    shutil.copy(video_with_audio, output_path)

                self.logger.info("=" * 50)
                self.logger.info(f"✓ VIDEO HOÀN THÀNH: {output_path}")
                self.logger.info("=" * 50)
                return True

            finally:
                # Cleanup temp files
                shutil.rmtree(temp_dir, ignore_errors=True)

        except Exception as e:
            self.logger.error(f"Video compose failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _create_video_from_images(self, scenes: List[Scene], output_path: str) -> bool:
        """
        Tạo video từ danh sách ảnh với duration từ scenes.

        Sử dụng FFmpeg concat demuxer với duration cho mỗi ảnh.

        FIX: Xử lý gap giữa các scenes bằng cách kéo dài ảnh đến start của scene tiếp theo.
        Ví dụ:
          Scene 1: 00:00 - 00:05 → kéo dài đến 00:06 (start của scene 2)
          Scene 2: 00:06 - 00:09 → kéo dài đến 00:10 (start của scene 3)
          Scene 3: 00:10 - 00:18 → giữ nguyên (scene cuối)
        """
        try:
            # Tạo file list cho FFmpeg concat
            temp_dir = os.path.dirname(output_path)
            list_file = os.path.join(temp_dir, "images.txt")

            with open(list_file, "w", encoding="utf-8") as f:
                for i, scene in enumerate(scenes):
                    # Lấy start time của scene hiện tại
                    current_start = self._parse_timestamp(scene.srt_start) if scene.srt_start else 0

                    # Tính duration: kéo dài đến start của scene tiếp theo (fix gap)
                    if i < len(scenes) - 1:
                        # Còn scene tiếp theo → kéo dài đến start của scene tiếp theo
                        next_scene = scenes[i + 1]
                        next_start = self._parse_timestamp(next_scene.srt_start) if next_scene.srt_start else 0
                        duration = next_start - current_start

                        # Fallback nếu tính toán sai
                        if duration <= 0:
                            if scene.duration and scene.duration > 0:
                                duration = scene.duration
                            elif scene.srt_end:
                                duration = self._parse_timestamp(scene.srt_end) - current_start
                            else:
                                duration = 5.0
                    else:
                        # Scene cuối cùng → dùng end time gốc
                        if scene.duration and scene.duration > 0:
                            duration = scene.duration
                        elif scene.srt_start and scene.srt_end:
                            start = self._parse_timestamp(scene.srt_start)
                            end = self._parse_timestamp(scene.srt_end)
                            duration = end - start
                        else:
                            duration = 5.0

                    # Log để debug
                    self.logger.debug(f"Scene {scene.scene_id}: start={current_start:.2f}, duration={duration:.2f}s")

                    # Escape path cho FFmpeg
                    img_path = scene.img_path.replace("\\", "/").replace("'", "'\\''")

                    f.write(f"file '{img_path}'\n")
                    f.write(f"duration {duration}\n")

                # Thêm ảnh cuối một lần nữa (FFmpeg requirement)
                if scenes:
                    last_img = scenes[-1].img_path.replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{last_img}'\n")

            # FFmpeg command
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_file,
                "-vf", f"scale={self.config.width}:{self.config.height}:force_original_aspect_ratio=decrease,pad={self.config.width}:{self.config.height}:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", self.config.video_codec,
                "-preset", self.config.preset,
                "-crf", str(self.config.crf),
                "-pix_fmt", "yuv420p",
                "-r", str(self.config.fps),
                output_path
            ]

            self.logger.info(f"Running: {' '.join(cmd[:10])}...")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"FFmpeg error: {result.stderr}")
                return False

            self.logger.info(f"✓ Video từ ảnh: {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Create video from images failed: {e}")
            return False

    def _add_audio(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Thêm audio vào video."""
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", self.config.audio_codec,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",  # Cắt theo video/audio ngắn hơn
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"Add audio error: {result.stderr}")
                return False

            self.logger.info(f"✓ Video với audio: {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Add audio failed: {e}")
            return False

    def _burn_subtitles(self, video_path: str, srt_path: str, output_path: str) -> bool:
        """Burn phụ đề vào video."""
        try:
            # Escape path cho FFmpeg filter
            srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

            # Subtitle filter
            sub_filter = (
                f"subtitles='{srt_escaped}':"
                f"force_style='FontName={self.config.font_name},"
                f"FontSize={self.config.font_size},"
                f"PrimaryColour=&H00FFFFFF,"  # White
                f"OutlineColour=&H00000000,"  # Black outline
                f"Outline={self.config.outline_width},"
                f"MarginV={self.config.margin_bottom}'"
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", sub_filter,
                "-c:v", self.config.video_codec,
                "-preset", self.config.preset,
                "-crf", str(self.config.crf),
                "-c:a", "copy",
                output_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                self.logger.error(f"Burn subtitles error: {result.stderr}")
                # Fallback: copy without subtitles
                self.logger.warning("Fallback: Copy video without subtitles")
                shutil.copy(video_path, output_path)
                return True

            self.logger.info(f"✓ Video với phụ đề: {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Burn subtitles failed: {e}")
            return False


def compose_final_video(
    project_dir: str,
    output_name: str = "final_video.mp4",
    config: Optional[VideoConfig] = None
) -> Optional[str]:
    """
    Convenience function để ghép video từ project directory.

    Args:
        project_dir: Thư mục project chứa Excel, voice, SRT
        output_name: Tên file video output
        config: VideoConfig (optional)

    Returns:
        Đường dẫn video output nếu thành công
    """
    project_path = Path(project_dir)

    # Tìm các file cần thiết
    excel_files = list(project_path.glob("*.xlsx"))
    voice_files = list(project_path.glob("*.mp3")) + list(project_path.glob("*.wav"))
    srt_files = list(project_path.glob("*.srt"))

    if not excel_files:
        logging.error(f"Không tìm thấy file Excel trong {project_dir}")
        return None

    if not voice_files:
        logging.error(f"Không tìm thấy file voice (mp3/wav) trong {project_dir}")
        return None

    excel_path = str(excel_files[0])
    voice_path = str(voice_files[0])
    srt_path = str(srt_files[0]) if srt_files else None
    output_path = str(project_path / output_name)

    logging.info(f"Excel: {excel_path}")
    logging.info(f"Voice: {voice_path}")
    logging.info(f"SRT: {srt_path or 'None'}")
    logging.info(f"Output: {output_path}")

    composer = VideoComposer(config)

    if composer.compose_video(excel_path, voice_path, output_path, srt_path):
        return output_path
    return None


# CLI usage
if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    if len(sys.argv) < 2:
        print("Usage: python video_composer.py <project_dir> [output_name]")
        print("Example: python video_composer.py ./output/my_story final_video.mp4")
        sys.exit(1)

    project_dir = sys.argv[1]
    output_name = sys.argv[2] if len(sys.argv) > 2 else "final_video.mp4"

    result = compose_final_video(project_dir, output_name)

    if result:
        print(f"\n✓ Video created: {result}")
    else:
        print("\n✗ Failed to create video")
        sys.exit(1)
