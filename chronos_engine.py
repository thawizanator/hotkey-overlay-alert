import os
import sys
import time
import datetime
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QDateTime

APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "ThaWizanator_Overlay")
DEFAULT_OBS_FILE = os.path.join(APP_DIR, "obs_timer.txt")

class ChronosMode:
    COUNT_UP = "count_up"
    COUNT_DOWN = "count_down"
    COUNTDOWN_TO_DATE = "countdown_to_date"
    COUNTUP_FROM_DATE = "countup_from_date"

class ChronosState:
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"

class ChronosEngine(QObject):
    """Core timing engine and OBS file broadcaster for Chronos."""
    tick = pyqtSignal(str, str, int)  # display_text, state, seconds_value
    state_changed = pyqtSignal(str)   # new_state
    completed = pyqtSignal(str)       # completion_message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = ChronosMode.COUNT_DOWN
        self.state = ChronosState.STOPPED

        # Stopwatch / Count Up settings
        self.count_up_elapsed = 0
        self.count_up_target_cap = 0  # 0 means indefinite
        self.count_up_stop_at_cap = False

        # Countdown settings
        self.countdown_initial = 600   # default 10m (in seconds)
        self.countdown_remaining = 600
        self.countdown_completion_msg = "STREAM STARTING SOON!"

        # Target date / milestone settings
        now = datetime.datetime.now()
        self.target_date = now + datetime.timedelta(days=1)
        self.date_completion_msg = "MILESTONE REACHED!"
        self.since_date = now

        # Formatting & OBS output
        self.prefix = ""
        self.suffix = ""
        self.hide_hours_if_zero = True
        self.write_to_file = True
        self.clear_file_on_reset = False
        self.custom_file_path = DEFAULT_OBS_FILE

        # Background timer (ticks every 1000ms)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)

        # Ensure directory exists
        try:
            os.makedirs(APP_DIR, exist_ok=True)
        except Exception:
            pass

    def start(self):
        if self.state == ChronosState.RUNNING:
            return
        if self.state == ChronosState.COMPLETED:
            self.reset()

        self.state = ChronosState.RUNNING
        self.timer.start()
        self.state_changed.emit(self.state)
        self._publish_current_state()

    def pause(self):
        if self.state != ChronosState.RUNNING:
            return
        self.state = ChronosState.PAUSED
        self.timer.stop()
        self.state_changed.emit(self.state)
        self._publish_current_state()

    def toggle_start_pause(self):
        if self.state == ChronosState.RUNNING:
            self.pause()
        else:
            self.start()

    def reset(self):
        self.timer.stop()
        self.state = ChronosState.STOPPED

        if self.mode == ChronosMode.COUNT_UP:
            self.count_up_elapsed = 0
        elif self.mode == ChronosMode.COUNT_DOWN:
            self.countdown_remaining = self.countdown_initial

        self.state_changed.emit(self.state)

        if self.clear_file_on_reset:
            self._write_file("")
            disp, sec = self._get_current_display()
            self.tick.emit(disp, self.state, sec)
        else:
            self._publish_current_state()

    def add_seconds(self, delta_sec: int):
        """Adds or subtracts seconds dynamically (e.g. +60 for +1 Min, +300 for +5 Min)."""
        if self.mode == ChronosMode.COUNT_DOWN:
            self.countdown_remaining = max(0, self.countdown_remaining + delta_sec)
            if self.state == ChronosState.COMPLETED and self.countdown_remaining > 0:
                self.state = ChronosState.PAUSED
                self.state_changed.emit(self.state)
        elif self.mode == ChronosMode.COUNT_UP:
            self.count_up_elapsed = max(0, self.count_up_elapsed + delta_sec)
        self._publish_current_state()

    def set_mode(self, mode_str: str):
        if self.mode == mode_str:
            return
        self.mode = mode_str
        self.reset()

    def _on_tick(self):
        if self.state != ChronosState.RUNNING:
            return

        if self.mode == ChronosMode.COUNT_UP:
            self.count_up_elapsed += 1
            if self.count_up_target_cap > 0 and self.count_up_elapsed >= self.count_up_target_cap:
                if self.count_up_stop_at_cap:
                    self.count_up_elapsed = self.count_up_target_cap
                    self.state = ChronosState.COMPLETED
                    self.timer.stop()
                    self.state_changed.emit(self.state)
                    self.completed.emit(self.countdown_completion_msg)

        elif self.mode == ChronosMode.COUNT_DOWN:
            self.countdown_remaining -= 1
            if self.countdown_remaining <= 0:
                self.countdown_remaining = 0
                self.state = ChronosState.COMPLETED
                self.timer.stop()
                self.state_changed.emit(self.state)
                self.completed.emit(self.countdown_completion_msg)

        elif self.mode == ChronosMode.COUNTDOWN_TO_DATE:
            now = datetime.datetime.now()
            diff = (self.target_date - now).total_seconds()
            if diff <= 0:
                self.state = ChronosState.COMPLETED
                self.timer.stop()
                self.state_changed.emit(self.state)
                self.completed.emit(self.date_completion_msg)

        elif self.mode == ChronosMode.COUNTUP_FROM_DATE:
            pass  # Continuous real-time difference calculation

        self._publish_current_state()

    def _format_seconds(self, total_seconds: int) -> str:
        """Formats an integer seconds count to HH:MM:SS or MM:SS."""
        total_seconds = max(0, int(total_seconds))
        days = total_seconds // 86400
        rem = total_seconds % 86400
        hours = rem // 3600
        rem %= 3600
        mins = rem // 60
        secs = rem % 60

        if days > 0:
            return f"{days}d {hours:02d}:{mins:02d}:{secs:02d}"
        if hours > 0 or not self.hide_hours_if_zero:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _get_current_display(self) -> tuple:
        """Returns (formatted_display_string, raw_seconds)."""
        if self.state == ChronosState.COMPLETED:
            msg = self.date_completion_msg if self.mode == ChronosMode.COUNTDOWN_TO_DATE else self.countdown_completion_msg
            return msg, 0

        if self.mode == ChronosMode.COUNT_UP:
            sec = self.count_up_elapsed
            return self._format_seconds(sec), sec

        elif self.mode == ChronosMode.COUNT_DOWN:
            sec = self.countdown_remaining
            return self._format_seconds(sec), sec

        elif self.mode == ChronosMode.COUNTDOWN_TO_DATE:
            now = datetime.datetime.now()
            diff = int((self.target_date - now).total_seconds())
            sec = max(0, diff)
            return self._format_seconds(sec), sec

        elif self.mode == ChronosMode.COUNTUP_FROM_DATE:
            now = datetime.datetime.now()
            diff = int((now - self.since_date).total_seconds())
            sec = max(0, diff)
            return self._format_seconds(sec), sec

        return "00:00", 0

    def _publish_current_state(self):
        disp, sec = self._get_current_display()
        full_output = f"{self.prefix}{disp}{self.suffix}".strip()
        if self.write_to_file:
            self._write_file(full_output)
        self.tick.emit(disp, self.state, sec)

    def _write_file(self, content: str):
        target = self.custom_file_path or DEFAULT_OBS_FILE
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            pass

    def export_settings(self) -> dict:
        return {
            "mode": self.mode,
            "count_up_target_cap": self.count_up_target_cap,
            "count_up_stop_at_cap": self.count_up_stop_at_cap,
            "countdown_initial": self.countdown_initial,
            "countdown_completion_msg": self.countdown_completion_msg,
            "target_date_iso": self.target_date.isoformat(),
            "since_date_iso": self.since_date.isoformat(),
            "date_completion_msg": self.date_completion_msg,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "hide_hours_if_zero": self.hide_hours_if_zero,
            "write_to_file": self.write_to_file,
            "clear_file_on_reset": self.clear_file_on_reset
        }

    def import_settings(self, d: dict):
        if not isinstance(d, dict):
            return
        self.mode = d.get("mode", self.mode)
        self.count_up_target_cap = int(d.get("count_up_target_cap", self.count_up_target_cap))
        self.count_up_stop_at_cap = bool(d.get("count_up_stop_at_cap", self.count_up_stop_at_cap))
        self.countdown_initial = int(d.get("countdown_initial", self.countdown_initial))
        self.countdown_remaining = self.countdown_initial
        self.countdown_completion_msg = str(d.get("countdown_completion_msg", self.countdown_completion_msg))
        
        try:
            if "target_date_iso" in d:
                self.target_date = datetime.datetime.fromisoformat(d["target_date_iso"])
            if "since_date_iso" in d:
                self.since_date = datetime.datetime.fromisoformat(d["since_date_iso"])
        except Exception:
            pass

        self.date_completion_msg = str(d.get("date_completion_msg", self.date_completion_msg))
        self.prefix = str(d.get("prefix", self.prefix))
        self.suffix = str(d.get("suffix", self.suffix))
        self.hide_hours_if_zero = bool(d.get("hide_hours_if_zero", self.hide_hours_if_zero))
        self.write_to_file = bool(d.get("write_to_file", self.write_to_file))
        self.clear_file_on_reset = bool(d.get("clear_file_on_reset", self.clear_file_on_reset))

        self._publish_current_state()
