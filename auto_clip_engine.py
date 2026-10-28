import os
import sys
import time
import math
import struct
import json
from collections import deque
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QIODevice
from PyQt6.QtMultimedia import QMediaDevices, QAudioSource, QAudioFormat, QAudioDevice

try:
    from debug_logger import log_debug
except ImportError:
    def log_debug(tag, msg):
        print(f"[{tag}] {msg}")

try:
    from streamlabs_client import get_streamlabs_client
except ImportError:
    def get_streamlabs_client():
        return None


class AutoClipEngine(QObject):
    """
    Background engine for real-time audio peak reaction & hype moment detection.
    
    Features:
    - Continuous sampling of user-selected audio input (physical mic or VoiceMeeter VAIO).
    - 10-second rolling moving average baseline buffer.
    - 4-Zone level classification: Green (Normal), Yellow (Elevated), Orange (Possible Peak), Red (Full Peak).
    - Discord-style automatic sensitivity calibration floating above ambient baseline.
    - Sustained duration filter preventing mouse clicks or desk bumps from false-triggering.
    - 60-second cooldown timer preventing spam during a single loud moment.
    - Primary peak event dispatch: Twitch Stream Marker, audio chime, and monitor border alert.
    - Secondary peak event logging to cooldown_clips.txt with calculated 40/20 split (40s pre-context / 20s aftermath).
    - Optional orange 'Possible Moments' logging.
    - Scene scoping filtering: monitoring pauses on non-whitelisted scenes (e.g., BRB).
    """

    # Signals for UI & System Integration
    level_updated = pyqtSignal(float, int, float, float)  # (current_level, zone 1-4, baseline, threshold)
    marker_triggered = pyqtSignal(dict)                   # Primary peak event payload
    secondary_peak_logged = pyqtSignal(dict)              # Secondary peak during cooldown
    possible_peak_logged = pyqtSignal(dict)               # Orange possible peak event
    cooldown_tick = pyqtSignal(int)                       # Remaining cooldown seconds (0 when idle)
    status_changed = pyqtSignal(str, bool)                # (status_message, is_active)

    ZONE_GREEN = 1
    ZONE_YELLOW = 2
    ZONE_ORANGE = 3
    ZONE_RED = 4

    def __init__(self, parent=None, app_dir=None):
        super().__init__(parent)
        self.app_dir = app_dir or os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "StreamerCalyx")
        os.makedirs(self.app_dir, exist_ok=True)
        self.log_file_path = os.path.join(self.app_dir, "cooldown_clips.txt")

        # Engine Settings
        self.enabled = True
        self.selected_device_name = ""
        self.auto_sensitivity = True
        self.input_gain = 1.0              # 0.25 to 2.0 (Input Gain Trim)
        self.trigger_offset = 0.30         # 0.15 to 0.60 (Offset above baseline)
        self.manual_threshold = 0.70       # 0.20 to 1.0
        self.min_duration_ms = 250         # 100 to 800ms
        self.log_orange_moments = True
        self.flash_overlay = True
        self.alert_color = "#f59e0b"       # Gold default
        self.play_chime = True
        self.cooldown_duration_sec = 60
        self.active_scenes = ["In-Game", "Banter"]
        self.marker_description = "Auto-Clip/Markers"
        self.streamer_mode = True

        # Audio Capture State
        self.audio_source = None
        self.audio_io = None
        self.current_device = None
        self._sample_format = None
        self._sample_rate = 48000
        self._channels = 2

        # Level & Baseline Buffer (10 seconds @ 50ms = 200 samples)
        self._buffer_capacity = 200
        self.level_buffer = deque(maxlen=self._buffer_capacity)
        for _ in range(self._buffer_capacity):
            self.level_buffer.append(0.08)  # Seed initial quiet baseline

        self.current_level = 0.0
        self.current_baseline = 0.08
        self.current_threshold = 0.68

        # Peak Detection & Duration Tracking
        self._spike_start_time = None
        self._peak_latched = False
        self._last_orange_log_time = 0.0
        self._last_secondary_log_time = 0.0

        # Cooldown State
        self.is_in_cooldown = False
        self.cooldown_remaining = 0
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setInterval(1000)
        self._cooldown_timer.timeout.connect(self._on_cooldown_tick)

        # Sampling Timer (50ms = 20Hz level updates)
        self._sample_timer = QTimer(self)
        self._sample_timer.setInterval(50)
        self._sample_timer.timeout.connect(self._process_audio_samples)

        # Session & Scene Tracking
        self._session_start_time = time.time()
        self._current_scene_name = ""
        self.slobs_client = get_streamlabs_client()
        if self.slobs_client:
            self.slobs_client.scene_switched.connect(self._on_scene_switched)

        # Start listening if enabled
        if self.enabled:
            QTimer.singleShot(500, self.start_audio_capture)

    # ------------------ Audio Device Management ------------------

    def get_available_devices(self) -> list:
        """Returns a list of QAudioDevice input devices."""
        try:
            return QMediaDevices.audioInputs()
        except Exception as e:
            log_debug("AUTOCLIP", f"Error enumerating audio inputs: {e}")
            return []

    def set_device_by_name(self, name: str):
        """Switches the listening input device to the specified device name."""
        self.selected_device_name = name
        log_debug("AUTOCLIP", f"Switching audio input device to: '{name}'")
        self.restart_audio_capture()

    def _resolve_target_device(self) -> QAudioDevice:
        """Finds matching QAudioDevice, prioritizing VoiceMeeter VAIO if nothing specified."""
        devices = self.get_available_devices()
        if not devices:
            return None

        # 1. Match explicitly configured name
        if self.selected_device_name:
            for d in devices:
                if d.description().strip() == self.selected_device_name.strip():
                    return d

        # 2. Prefer VoiceMeeter Output (B1/B2/VAIO)
        for d in devices:
            desc = d.description().lower()
            if "voicemeeter out b" in desc or "voicemeeter vaio" in desc:
                return d

        # 3. Fallback to system default
        return QMediaDevices.defaultAudioInput()

    def restart_audio_capture(self):
        """Restarts the audio capture stream on the target device."""
        self.stop_audio_capture()
        if self.enabled:
            self.start_audio_capture()

    def start_audio_capture(self):
        """Initializes and begins listening to the audio input device."""
        if not self.enabled:
            return

        if not getattr(self, "streamer_mode", True):
            log_debug("AUTOCLIP", "Audio capture skipped: Streamer Mode is disabled.")
            self.status_changed.emit("Paused (Streamer Mode disabled)", False)
            return

        # Check scene scoping
        if not self.is_scene_active():
            self.status_changed.emit(f"Paused (Scene '{self._current_scene_name}' not active)", False)
            return

        device = self._resolve_target_device()
        if not device or device.isNull():
            log_debug("AUTOCLIP", "No valid audio input device found.")
            self.status_changed.emit("No audio input device found", False)
            return

        self.current_device = device
        fmt = device.preferredFormat()
        self._sample_rate = fmt.sampleRate() or 48000
        self._channels = max(1, fmt.channelCount())
        self._sample_format = fmt.sampleFormat()

        try:
            self.audio_source = QAudioSource(device, fmt, self)
            self.audio_io = self.audio_source.start()
            self._sample_timer.start()
            dev_label = device.description()
            log_debug("AUTOCLIP", f"Audio capture active on: {dev_label} ({self._sample_rate}Hz, {self._channels}ch)")
            self.status_changed.emit(f"Active ({dev_label})", True)
        except Exception as e:
            log_debug("AUTOCLIP", f"Failed to start QAudioSource: {e}")
            self.status_changed.emit(f"Error: {e}", False)

    def stop_audio_capture(self):
        """Stops the audio capture stream."""
        self._sample_timer.stop()
        if self.audio_source:
            try:
                self.audio_source.stop()
            except Exception:
                pass
            self.audio_source = None
            self.audio_io = None

    def set_streamer_mode(self, enabled: bool):
        """Toggles streamer mode gating. Pauses capture when disabled to save CPU."""
        self.streamer_mode = bool(enabled)
        log_debug("AUTOCLIP", f"Streamer Mode set to {self.streamer_mode}")
        if not self.streamer_mode:
            self.stop_audio_capture()
            self.status_changed.emit("Paused (Streamer Mode disabled)", False)
        else:
            if self.enabled and self.is_scene_active():
                self.start_audio_capture()

    # ------------------ Scene Scoping ------------------

    def _on_scene_switched(self, scene_name: str, scene_id: str):
        self._current_scene_name = scene_name
        is_active = self.is_scene_active()
        log_debug("AUTOCLIP", f"Scene switched to '{scene_name}' | Auto-Clip Allowed={is_active}")
        if is_active:
            if not self._sample_timer.isActive():
                self.start_audio_capture()
        else:
            if self._sample_timer.isActive():
                self.stop_audio_capture()
                self.status_changed.emit(f"Paused (Scene '{scene_name}')", False)

    def is_scene_active(self) -> bool:
        """Checks if current scene is in the active_scenes whitelist."""
        if not self.active_scenes:
            return True  # If empty, allow all scenes
        if not self._current_scene_name:
            return True
        curr = self._current_scene_name.lower().strip()
        for allowed in self.active_scenes:
            a = allowed.lower().strip()
            if a in curr or curr in a:
                return True
        return False

    # ------------------ Audio Sampling & Peak Analysis ------------------

    def _process_audio_samples(self):
        """Reads pending PCM audio data, computes normalized peak/RMS, and tests thresholds."""
        if not self.audio_io:
            return

        try:
            raw_bytes = self.audio_io.readAll().data()
        except Exception:
            return

        if not raw_bytes:
            return

        # Calculate normalized perceptual level (RMS + peak blend, 0.0 to 1.0)
        level_val = self._calculate_level(raw_bytes)
        self.current_level = level_val

        # Update 10-second rolling baseline only from non-peak audio (ambient + normal talking)
        # Prevents screaming or loud laughter from dragging the baseline up and canceling triggers
        if level_val < (self.current_threshold * 0.85):
            self.level_buffer.append(level_val)
            self.current_baseline = sum(self.level_buffer) / len(self.level_buffer)

        # Calculate dynamic or manual thresholds
        if self.auto_sensitivity:
            # Discord-style: Float threshold above conversational baseline using user's offset
            offset = self.trigger_offset
            red_thresh = min(0.98, max(0.68, self.current_baseline + offset))
            orange_thresh = min(0.90, max(0.48, red_thresh * 0.78))
            yellow_thresh = min(0.60, max(0.24, red_thresh * 0.42))
        else:
            red_thresh = max(0.40, min(1.0, self.manual_threshold))
            orange_thresh = red_thresh * 0.78
            yellow_thresh = red_thresh * 0.42

        self.current_threshold = red_thresh

        # Determine current zone
        if level_val >= red_thresh:
            zone = self.ZONE_RED
        elif level_val >= orange_thresh:
            zone = self.ZONE_ORANGE
        elif level_val >= yellow_thresh:
            zone = self.ZONE_YELLOW
        else:
            zone = self.ZONE_GREEN

        # Emit live level for VU meter
        self.level_updated.emit(level_val, zone, self.current_baseline, red_thresh)

        # Handle Orange "Possible Moment" (debounced 15s)
        if zone == self.ZONE_ORANGE and self.log_orange_moments:
            now = time.time()
            if now - self._last_orange_log_time >= 15.0:
                self._last_orange_log_time = now
                self._handle_orange_possible_peak()

        # Handle Red Peak Event with Sustained Duration Filter & Hysteresis Latch
        if zone == self.ZONE_RED:
            if not self._peak_latched:
                if self._spike_start_time is None:
                    self._spike_start_time = time.time()
                elapsed_ms = (time.time() - self._spike_start_time) * 1000.0
                if elapsed_ms >= self.min_duration_ms:
                    # Genuine hype spike confirmed!
                    self._trigger_peak_event()
                    self._peak_latched = True  # Latch: will not re-trigger until audio drops!
                    self._spike_start_time = None
        else:
            self._spike_start_time = None
            # Hysteresis: unlatch once audio drops back down into Green or Yellow
            if zone in (self.ZONE_GREEN, self.ZONE_YELLOW):
                self._peak_latched = False

    def _calculate_level(self, raw_bytes: bytes) -> float:
        """Parses PCM data (Float32, Int32, or Int16) and extracts normalized perceptual level."""
        try:
            byte_len = len(raw_bytes)
            if byte_len < 2:
                return 0.0

            gain = getattr(self, "input_gain", 1.0)

            # 1. 32-bit Floating Point PCM (Standard for WASAPI / Windows 11 & VoiceMeeter)
            if getattr(self, "_sample_format", None) == QAudioFormat.SampleFormat.Float:
                num_floats = byte_len // 4
                if num_floats <= 0:
                    return 0.0
                step = max(1, num_floats // 256)
                floats = struct.unpack(f"<{num_floats}f", raw_bytes[:num_floats * 4])
                sampled = floats[::step]
                if not sampled:
                    return 0.0
                peak = min(1.0, max(abs(f) for f in sampled) * gain)
                sum_sq = sum((f * gain) ** 2 for f in sampled)
                rms = min(1.0, math.sqrt(sum_sq / len(sampled)))

            # 2. 32-bit Signed Integer PCM
            elif getattr(self, "_sample_format", None) == QAudioFormat.SampleFormat.Int32:
                num_ints = byte_len // 4
                if num_ints <= 0:
                    return 0.0
                step = max(1, num_ints // 256)
                ints = struct.unpack(f"<{num_ints}i", raw_bytes[:num_ints * 4])
                sampled = ints[::step]
                if not sampled:
                    return 0.0
                peak = min(1.0, (max(abs(i) for i in sampled) / 2147483647.0) * gain)
                sum_sq = sum(((i / 2147483647.0) * gain) ** 2 for i in sampled)
                rms = min(1.0, math.sqrt(sum_sq / len(sampled)))

            # 3. 16-bit Signed Integer PCM (Standard Fallback)
            else:
                num_shorts = byte_len // 2
                if num_shorts <= 0:
                    return 0.0
                step = max(1, num_shorts // 256)
                shorts = struct.unpack(f"<{num_shorts}h", raw_bytes[:num_shorts * 2])
                sampled = shorts[::step]
                if not sampled:
                    return 0.0
                peak = min(1.0, (max(abs(s) for s in sampled) / 32767.0) * gain)
                sum_sq = sum(((s / 32767.0) * gain) ** 2 for s in sampled)
                rms = min(1.0, math.sqrt(sum_sq / len(sampled)))

            # Perceptual loudness expansion (Stevens' power law / square-root curve):
            # Normalizes human perceived volume so speech sits cleanly in Yellow (~35%-45%)
            p_rms = math.sqrt(rms) if rms > 0.0 else 0.0
            p_peak = math.sqrt(peak) if peak > 0.0 else 0.0

            level = (0.65 * p_rms) + (0.35 * p_peak)
            return min(1.0, max(0.0, level))
        except Exception:
            pass
        return 0.0

    # ------------------ Peak Event & Cooldown Dispatch ------------------

    def _trigger_peak_event(self):
        """Fires when audio exceeds red threshold for min duration."""
        stream_pos_sec, timestamp_str = self._get_current_stream_timestamp()
        clip_start_sec = max(0, stream_pos_sec - 40)
        clip_end_sec = stream_pos_sec + 20
        clip_range_str = f"Start: {self._format_seconds(clip_start_sec)} | End: {self._format_seconds(clip_end_sec)}"

        payload = {
            "position_seconds": stream_pos_sec,
            "timestamp_str": timestamp_str,
            "clip_range_str": clip_range_str,
            "clip_start_sec": clip_start_sec,
            "clip_end_sec": clip_end_sec,
            "level": self.current_level,
            "baseline": self.current_baseline,
            "threshold": self.current_threshold,
            "description": self.marker_description
        }

        now = time.time()
        if not self.is_in_cooldown:
            # PRIMARY ACTION: Drop live Twitch marker, start 60s cooldown
            log_debug("AUTOCLIP", f"🔥 PRIMARY PEAK EVENT at {timestamp_str} (level={self.current_level:.2f}) -> {clip_range_str}")
            self.marker_triggered.emit(payload)
            self._start_cooldown()
            self._last_secondary_log_time = now
        else:
            # SECONDARY ACTION (In Cooldown): Debounce at least 15s between secondary logged clips
            if now - getattr(self, "_last_secondary_log_time", 0.0) >= 15.0:
                self._last_secondary_log_time = now
                log_debug("AUTOCLIP", f"⏱️ SECONDARY PEAK EVENT during cooldown at {timestamp_str} -> {clip_range_str}")
                self._log_clip_to_file(
                    f"[Secondary Peak at {timestamp_str}] Suggested Manual Clip -> {clip_range_str} (Cooldown active: {self.cooldown_remaining}s left)"
                )
                self.secondary_peak_logged.emit(payload)

    def _handle_orange_possible_peak(self):
        """Logs an orange possible moment to text file if enabled."""
        stream_pos_sec, timestamp_str = self._get_current_stream_timestamp()
        clip_start_sec = max(0, stream_pos_sec - 40)
        clip_end_sec = stream_pos_sec + 20
        clip_range_str = f"Start: {self._format_seconds(clip_start_sec)} | End: {self._format_seconds(clip_end_sec)}"

        payload = {
            "position_seconds": stream_pos_sec,
            "timestamp_str": timestamp_str,
            "clip_range_str": clip_range_str,
            "level": self.current_level
        }
        log_debug("AUTOCLIP", f"⚡ ORANGE POSSIBLE MOMENT at {timestamp_str} -> {clip_range_str}")
        self._log_clip_to_file(
            f"[Possible Peak at {timestamp_str}] Suggested Manual Clip -> {clip_range_str} (Orange Moment)"
        )
        self.possible_peak_logged.emit(payload)

    def _start_cooldown(self):
        """Initiates the 60-second cooldown timer."""
        self.is_in_cooldown = True
        self.cooldown_remaining = self.cooldown_duration_sec
        self.cooldown_tick.emit(self.cooldown_remaining)
        self._cooldown_timer.start()

    def _on_cooldown_tick(self):
        self.cooldown_remaining -= 1
        if self.cooldown_remaining <= 0:
            self._cooldown_timer.stop()
            self.is_in_cooldown = False
            self.cooldown_remaining = 0
            self.cooldown_tick.emit(0)
            log_debug("AUTOCLIP", "Cooldown finished. Auto-Clip armed and ready.")
        else:
            self.cooldown_tick.emit(self.cooldown_remaining)

    # ------------------ Timing & File Logging ------------------

    def _get_current_stream_timestamp(self) -> tuple:
        """Calculates current elapsed stream seconds and human-readable timestamp."""
        # 1. Check Streamlabs live streaming start time
        if self.slobs_client and hasattr(self.slobs_client, "is_streaming") and self.slobs_client.is_streaming():
            start_t = getattr(self.slobs_client, "_stream_start_time", 0.0)
            if start_t > 0:
                elapsed = max(0, int(time.time() - start_t))
                return elapsed, self._format_seconds(elapsed)

        # 2. Fallback to session elapsed time
        elapsed = max(0, int(time.time() - self._session_start_time))
        # Also include wall-clock time for clear manual editing
        now_str = datetime.now().strftime("%H:%M:%S")
        return elapsed, f"{self._format_seconds(elapsed)} ({now_str})"

    def _format_seconds(self, total_seconds: int) -> str:
        """Formats integer seconds into MM:SS or HH:MM:SS."""
        hrs = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _log_clip_to_file(self, line: str):
        """Appends a clip entry with timestamp and 40/20 window to cooldown_clips.txt."""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            needs_header = not os.path.exists(self.log_file_path) or os.path.getsize(self.log_file_path) == 0
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                if needs_header:
                    f.write(f"=== Streamer Calyx Auto-Clip / Markers Log ({today_str}) ===\n")
                    f.write("40/20 Window: 40s pre-context + 20s aftermath relative to peak.\n\n")
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
        except Exception as e:
            log_debug("AUTOCLIP_ERR", f"Failed to write to cooldown_clips.txt: {e}")

    # ------------------ Public Control Methods ------------------

    def start_monitoring(self):
        """Starts audio capture and monitoring."""
        self.enabled = True
        self.start_audio_capture()

    def stop_monitoring(self):
        """Stops audio capture and monitoring."""
        self.enabled = False
        self.stop_audio_capture()
        self.current_level = 0.0
        self.level_updated.emit(0.0, self.ZONE_GREEN, self.current_baseline, self.current_threshold)
        self.status_changed.emit("Disabled", False)

    def open_log_file(self):
        """Opens cooldown_clips.txt in the system's default text editor."""
        try:
            if not os.path.exists(self.log_file_path):
                self._log_clip_to_file("Log file initialized.")
            os.startfile(self.log_file_path)
        except Exception as e:
            log_debug("AUTOCLIP", f"Error opening log file: {e}")

    def clear_log_file(self):
        """Empties the cooldown_clips.txt log file."""
        try:
            with open(self.log_file_path, "w", encoding="utf-8") as f:
                f.write(f"=== Streamer Calyx Auto-Clip / Markers Log ({datetime.now().strftime('%Y-%m-%d')}) ===\n")
            log_debug("AUTOCLIP", "cooldown_clips.txt cleared.")
        except Exception as e:
            log_debug("AUTOCLIP", f"Error clearing log file: {e}")

    # ------------------ Configuration Import / Export ------------------

    def export_settings(self) -> dict:
        return {
            "enabled": self.enabled,
            "device_name": self.selected_device_name,
            "auto_sensitivity": self.auto_sensitivity,
            "input_gain": self.input_gain,
            "trigger_offset": self.trigger_offset,
            "manual_threshold": self.manual_threshold,
            "min_duration_ms": self.min_duration_ms,
            "log_orange_moments": self.log_orange_moments,
            "flash_overlay": self.flash_overlay,
            "alert_color": self.alert_color,
            "play_chime": self.play_chime,
            "active_scenes": list(self.active_scenes),
            "cooldown_duration_sec": self.cooldown_duration_sec,
            "marker_description": self.marker_description
        }

    def import_settings(self, d: dict):
        if not isinstance(d, dict):
            return
        self.enabled = d.get("enabled", True)
        self.selected_device_name = d.get("device_name", "")
        self.auto_sensitivity = d.get("auto_sensitivity", True)
        self.input_gain = d.get("input_gain", 1.0)
        self.trigger_offset = d.get("trigger_offset", 0.30)
        self.manual_threshold = d.get("manual_threshold", 0.70)
        self.min_duration_ms = d.get("min_duration_ms", 250)
        self.log_orange_moments = d.get("log_orange_moments", True)
        self.flash_overlay = d.get("flash_overlay", True)
        self.alert_color = d.get("alert_color", "#f59e0b")
        self.play_chime = d.get("play_chime", True)
        self.active_scenes = list(d.get("active_scenes", ["In-Game", "Banter"]))
        self.cooldown_duration_sec = d.get("cooldown_duration_sec", 60)
        self.marker_description = d.get("marker_description", "Auto-Clip/Markers")
