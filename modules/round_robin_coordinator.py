"""
Round-Robin Coordinator cho Multi-Folder Processing

Quản lý nhiều "voice" (folder) chạy xếp hàng luân phiên:
- Voice 1: ảnh 1 → đợi
- Voice 2: ảnh 1 → đợi
- Voice 3: ảnh 1 → đợi
- Voice 1: ảnh 2 → đợi
- ...

Ưu điểm:
1. Giữ logic file đơn đã hoạt động - mỗi voice y hệt file đơn
2. Tự động giãn cách API - không cần thêm delay thủ công
3. Proxy rõ ràng - mỗi Chrome có proxy riêng, không nhầm lẫn
4. Đơn giản hóa - không có race condition, không focus sai Chrome
"""

import threading
import queue
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field


@dataclass
class VoiceTask:
    """Một task cần xử lý cho một voice."""
    voice_id: int
    prompt_data: Dict[str, Any]
    output_path: Path
    excel_path: Optional[Path] = None


@dataclass
class VoiceState:
    """Trạng thái của một voice (folder)."""
    voice_id: int
    folder_path: Path
    excel_path: Optional[Path] = None
    prompts: List[Dict] = field(default_factory=list)
    current_index: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    is_done: bool = False
    chrome_ready: bool = False
    last_error: Optional[str] = None


class RoundRobinCoordinator:
    """
    Coordinator quản lý nhiều voice chạy Round-Robin.

    Usage:
        coordinator = RoundRobinCoordinator(num_voices=3)

        # Thêm voice
        coordinator.add_voice(0, folder_path, prompts)
        coordinator.add_voice(1, folder_path2, prompts2)

        # Chạy với callback
        coordinator.run(process_callback=my_process_function)
    """

    def __init__(
        self,
        num_voices: int = 2,
        log_callback: Optional[Callable] = None
    ):
        """
        Args:
            num_voices: Số lượng voice tối đa
            log_callback: Callback để log messages
        """
        self.num_voices = num_voices
        self.log_callback = log_callback

        # Voice states
        self.voices: Dict[int, VoiceState] = {}

        # Turn management
        self._current_turn = 0
        self._turn_lock = threading.Lock()
        self._turn_event = threading.Event()

        # Completion tracking
        self._all_done = False
        self._stop_flag = False

    def _log(self, msg: str, level: str = "INFO"):
        """Log message."""
        timestamp = time.strftime("%H:%M:%S")
        formatted = f"[{timestamp}] [RR] {msg}"
        print(formatted)
        if self.log_callback:
            self.log_callback(msg, level)

    def add_voice(
        self,
        voice_id: int,
        folder_path: Path,
        prompts: List[Dict],
        excel_path: Optional[Path] = None
    ) -> bool:
        """
        Thêm một voice vào coordinator.

        Args:
            voice_id: ID của voice (0, 1, 2, ...)
            folder_path: Đường dẫn folder project
            prompts: Danh sách prompts cần xử lý
            excel_path: Đường dẫn Excel file (optional)

        Returns:
            True nếu thành công
        """
        if voice_id >= self.num_voices:
            self._log(f"Voice {voice_id} vượt quá giới hạn ({self.num_voices})", "ERROR")
            return False

        self.voices[voice_id] = VoiceState(
            voice_id=voice_id,
            folder_path=Path(folder_path),
            excel_path=Path(excel_path) if excel_path else None,
            prompts=prompts,
            current_index=0,
            is_done=len(prompts) == 0
        )

        self._log(f"Voice {voice_id}: Added {len(prompts)} prompts from {folder_path.name}")
        return True

    def get_next_task(self, voice_id: int) -> Optional[VoiceTask]:
        """
        Lấy task tiếp theo cho voice.
        Voice phải đợi đến lượt của mình trước khi nhận task.

        Args:
            voice_id: ID của voice

        Returns:
            VoiceTask hoặc None nếu hết task
        """
        if voice_id not in self.voices:
            return None

        voice = self.voices[voice_id]

        if voice.is_done:
            return None

        # Đợi đến lượt
        self._wait_for_turn(voice_id)

        if self._stop_flag:
            return None

        # Lấy prompt tiếp theo
        if voice.current_index >= len(voice.prompts):
            voice.is_done = True
            self._advance_turn()
            return None

        prompt_data = voice.prompts[voice.current_index]

        # Tạo output path
        pid = prompt_data.get('id', voice.current_index + 1)
        if str(pid).lower().startswith('nv') or str(pid).lower().startswith('loc'):
            output_dir = voice.folder_path / "nv"
        else:
            output_dir = voice.folder_path / "img"
        output_dir.mkdir(parents=True, exist_ok=True)

        task = VoiceTask(
            voice_id=voice_id,
            prompt_data=prompt_data,
            output_path=output_dir / f"{pid}.png",
            excel_path=voice.excel_path
        )

        return task

    def complete_task(
        self,
        voice_id: int,
        success: bool,
        error: Optional[str] = None
    ):
        """
        Báo hoàn thành task và chuyển lượt.

        Args:
            voice_id: ID của voice
            success: Task thành công hay không
            error: Thông báo lỗi (nếu có)
        """
        if voice_id not in self.voices:
            return

        voice = self.voices[voice_id]

        if success:
            voice.success_count += 1
        else:
            voice.failed_count += 1
            voice.last_error = error

        # Di chuyển đến prompt tiếp theo
        voice.current_index += 1

        if voice.current_index >= len(voice.prompts):
            voice.is_done = True
            self._log(f"Voice {voice_id}: DONE! Success={voice.success_count}, Failed={voice.failed_count}")

        # Chuyển lượt cho voice tiếp theo
        self._advance_turn()

    def skip_task(self, voice_id: int):
        """Bỏ qua task (đã có ảnh)."""
        if voice_id not in self.voices:
            return

        voice = self.voices[voice_id]
        voice.skipped_count += 1
        voice.current_index += 1

        if voice.current_index >= len(voice.prompts):
            voice.is_done = True

        # Không chuyển lượt khi skip - voice tiếp tục ngay

    def _wait_for_turn(self, voice_id: int):
        """Đợi đến lượt của voice."""
        while not self._stop_flag:
            with self._turn_lock:
                # Tìm voice tiếp theo chưa done
                active_voices = [vid for vid, v in self.voices.items() if not v.is_done]

                if not active_voices:
                    self._all_done = True
                    return

                # Xác định voice hiện tại (round-robin)
                current_voice = active_voices[self._current_turn % len(active_voices)]

                if current_voice == voice_id:
                    return  # Đến lượt của voice này

            # Chưa đến lượt, đợi
            time.sleep(0.1)

    def _advance_turn(self):
        """Chuyển sang lượt tiếp theo."""
        with self._turn_lock:
            self._current_turn += 1

            # Kiểm tra tất cả đã done chưa
            active_voices = [vid for vid, v in self.voices.items() if not v.is_done]
            if not active_voices:
                self._all_done = True

            self._turn_event.set()
            self._turn_event.clear()

    def is_all_done(self) -> bool:
        """Kiểm tra tất cả voice đã hoàn thành chưa."""
        return self._all_done or all(v.is_done for v in self.voices.values())

    def stop(self):
        """Dừng coordinator."""
        self._stop_flag = True
        self._turn_event.set()

    def get_stats(self) -> Dict[str, Any]:
        """Lấy thống kê."""
        total_success = sum(v.success_count for v in self.voices.values())
        total_failed = sum(v.failed_count for v in self.voices.values())
        total_skipped = sum(v.skipped_count for v in self.voices.values())
        total_prompts = sum(len(v.prompts) for v in self.voices.values())

        return {
            "total_voices": len(self.voices),
            "total_prompts": total_prompts,
            "success": total_success,
            "failed": total_failed,
            "skipped": total_skipped,
            "voices": {
                vid: {
                    "folder": str(v.folder_path.name),
                    "total": len(v.prompts),
                    "current": v.current_index,
                    "success": v.success_count,
                    "failed": v.failed_count,
                    "skipped": v.skipped_count,
                    "is_done": v.is_done
                }
                for vid, v in self.voices.items()
            }
        }

    def run_voice_worker(
        self,
        voice_id: int,
        process_callback: Callable[[int, VoiceTask], bool],
        setup_callback: Optional[Callable[[int], bool]] = None
    ):
        """
        Worker function cho một voice. Chạy trong thread riêng.

        Args:
            voice_id: ID của voice
            process_callback: Callback để xử lý task (voice_id, task) -> success
            setup_callback: Callback để setup Chrome/proxy (voice_id) -> success
        """
        self._log(f"Voice {voice_id}: Worker started")

        # Setup Chrome nếu cần
        if setup_callback:
            if not setup_callback(voice_id):
                self._log(f"Voice {voice_id}: Setup failed!", "ERROR")
                return
            self.voices[voice_id].chrome_ready = True
            self._log(f"Voice {voice_id}: Chrome ready")

        # Xử lý từng task
        while not self._stop_flag and not self.is_all_done():
            task = self.get_next_task(voice_id)

            if task is None:
                if self.voices[voice_id].is_done:
                    break
                continue

            pid = task.prompt_data.get('id', '?')
            self._log(f"Voice {voice_id}: Processing {pid}")

            try:
                success = process_callback(voice_id, task)
                self.complete_task(voice_id, success)
            except Exception as e:
                self._log(f"Voice {voice_id}: Error - {e}", "ERROR")
                self.complete_task(voice_id, False, str(e))

        self._log(f"Voice {voice_id}: Worker finished")


def run_round_robin(
    folders: List[Path],
    prompts_per_folder: Dict[int, List[Dict]],
    process_callback: Callable[[int, VoiceTask], bool],
    setup_callback: Optional[Callable[[int], bool]] = None,
    num_workers: int = 2,
    log_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Convenience function để chạy Round-Robin processing.

    Args:
        folders: Danh sách folder paths
        prompts_per_folder: Dict mapping folder_index -> prompts list
        process_callback: Callback xử lý task
        setup_callback: Callback setup Chrome
        num_workers: Số workers
        log_callback: Log callback

    Returns:
        Stats dict
    """
    coordinator = RoundRobinCoordinator(
        num_voices=num_workers,
        log_callback=log_callback
    )

    # Add voices
    for i, folder in enumerate(folders[:num_workers]):
        prompts = prompts_per_folder.get(i, [])
        coordinator.add_voice(i, folder, prompts)

    # Start worker threads
    threads = []
    for i in range(min(num_workers, len(folders))):
        t = threading.Thread(
            target=coordinator.run_voice_worker,
            args=(i, process_callback, setup_callback),
            daemon=True
        )
        t.start()
        threads.append(t)

    # Wait for all workers
    for t in threads:
        t.join()

    return coordinator.get_stats()
