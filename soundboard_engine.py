import os
import sys
import json
import uuid
import wave
import struct
import math
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal, QUrl, Qt, QThread
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaDevices, QAudioDevice

# Directory configuration matching Streamer Calyx conventions
APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "StreamerCalyx")
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

def get_app_dir() -> str:
    if os.path.exists(APP_DIR):
        return APP_DIR
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        return APP_DIR
    except Exception:
        return LOCAL_DIR

SOUNDS_DIR = os.path.join(get_app_dir(), "sounds")
CONFIG_PATH = os.path.join(get_app_dir(), "soundboard_config.json")
LOCAL_CONFIG_PATH = os.path.join(LOCAL_DIR, "soundboard_config.json")

@dataclass
class SoundClip:
    id: str
    name: str
    file_path: str
    hotkey: str = ""
    volume: float = 1.0       # 0.0 to 1.0
    color: str = "#38bdf8"    # Hex accent color
    category: str = "General" # Category tag
    loop: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SoundClip":
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Untitled Sound"),
            file_path=data.get("file_path", ""),
            hotkey=data.get("hotkey", ""),
            volume=float(data.get("volume", 1.0)),
            color=data.get("color", "#38bdf8"),
            category=data.get("category", "General"),
            loop=bool(data.get("loop", False))
        )


def generate_starter_sounds(sounds_dir: str):
    """Generates crisp starter .wav audio cues using standard wave synthesis with 0 external dependencies."""
    os.makedirs(sounds_dir, exist_ok=True)

    def write_wav(filename: str, sample_rate: int, duration: float, generator_fn):
        path = os.path.join(sounds_dir, filename)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
        try:
            with wave.open(path, "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                n_frames = int(duration * sample_rate)
                for i in range(n_frames):
                    t = i / sample_rate
                    val = generator_fn(t, duration)
                    int_val = int(max(-1.0, min(1.0, val)) * 32767 * 0.75)
                    wf.writeframes(struct.pack("<h", int_val))
        except Exception as e:
            print(f"[Soundboard] Could not write sample {filename}: {e}")
        return path

    # 1. Chime Alert (Soft ascending chord)
    write_wav("chime_alert.wav", 44100, 0.7, lambda t, dur: (
        sum(math.sin(2 * math.pi * f * t) for f in [523.25, 659.25, 783.99, 1046.50]) / 4.0
        * math.exp(-4.2 * t / dur)
    ))

    # 2. Stream Marker Ding (High-pitch crystal bell)
    write_wav("marker_ding.wav", 44100, 0.5, lambda t, dur: (
        (0.7 * math.sin(2 * math.pi * 1318.51 * t) + 0.3 * math.sin(2 * math.pi * 2637.02 * t))
        * math.exp(-6.0 * t / dur)
    ))

    # 3. Level Up / Success Fanfare (Two rapid upbeat tones)
    write_wav("level_up.wav", 44100, 0.65, lambda t, dur: (
        math.sin(2 * math.pi * (587.33 if t < 0.15 else (739.99 if t < 0.30 else 880.00)) * t)
        * math.exp(-2.5 * t / dur)
    ))

    # 4. Airhorn / Hype Burst (Synthetic brass chord burst)
    write_wav("airhorn_blast.wav", 44100, 0.6, lambda t, dur: (
        (math.sin(2 * math.pi * 466.16 * t) * 0.5 +
         math.sin(2 * math.pi * 587.33 * t) * 0.3 +
         math.sin(2 * math.pi * 700.00 * t) * 0.2)
        * (1.0 if t < 0.45 else math.exp(-15.0 * (t - 0.45)))
    ))

    # 5. Buzzer / Fail Tone (Low raspy square wave)
    write_wav("buzzer_fail.wav", 44100, 0.55, lambda t, dur: (
        (1.0 if (t * 140) % 1.0 > 0.5 else -1.0) * 0.4
        * math.exp(-2.0 * t / dur)
    ))


class SoundboardEngine(QObject):
    """
    Multi-channel, low-latency audio playback engine for Streamer Calyx Soundboard.
    Supports simultaneous overlapping sounds, device routing, hotkeys, and persistence.
    """
    clip_started = pyqtSignal(str, str)        # clip_id, clip_name
    clip_stopped = pyqtSignal(str)             # clip_id
    master_volume_changed = pyqtSignal(float)  # master_vol (0.0 to 1.0)
    clips_updated = pyqtSignal()               # emitted on add/edit/delete
    error_occurred = pyqtSignal(str)           # error description

    # Internal thread-safe queued dispatch signals (always executed on Qt GUI thread)
    _req_play = pyqtSignal(str)
    _req_stop = pyqtSignal(str)
    _req_toggle = pyqtSignal(str)
    _req_stop_all = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sounds_dir = SOUNDS_DIR
        os.makedirs(self.sounds_dir, exist_ok=True)
        generate_starter_sounds(self.sounds_dir)

        self.clips: List[SoundClip] = []
        self.master_volume: float = 1.0
        self.is_muted: bool = False
        self.exclusive_mode: bool = False  # If True, stops others when a new sound starts
        self.selected_device_name: str = "" # Empty = default system device

        # Active player pool: list of dicts: {'player': QMediaPlayer, 'audio': QAudioOutput, 'clip_id': str}
        self.active_players: List[Dict] = []
        self._bound_hotkeys: Dict[str, str] = {} # clip_id -> hotkey_str
        self._last_trigger_time: Dict[str, float] = {} # clip_id -> timestamp (debounce)

        # Connect internal dispatch signals with QueuedConnection to guarantee execution on GUI thread
        self._req_play.connect(self._do_play_clip, Qt.ConnectionType.QueuedConnection)
        self._req_stop.connect(self._do_stop_clip, Qt.ConnectionType.QueuedConnection)
        self._req_toggle.connect(self._do_toggle_clip, Qt.ConnectionType.QueuedConnection)
        self._req_stop_all.connect(self._do_stop_all, Qt.ConnectionType.QueuedConnection)

        self.load_config()

    def get_output_devices(self) -> List[str]:
        """Returns list of all available audio output device descriptions."""
        try:
            return [d.description() for d in QMediaDevices.audioOutputs()]
        except Exception:
            return []

    def set_output_device(self, device_name: str):
        """Sets target audio output device across active and future sound players."""
        self.selected_device_name = device_name
        target_device = self._resolve_target_device()
        for item in self.active_players:
            if target_device is not None:
                item["audio"].setDevice(target_device)
        self.save_config()

    def _resolve_target_device(self) -> Optional[QAudioDevice]:
        if not self.selected_device_name:
            return QMediaDevices.defaultAudioOutput()
        for dev in QMediaDevices.audioOutputs():
            if dev.description() == self.selected_device_name:
                return dev
        return QMediaDevices.defaultAudioOutput()

    def set_master_volume(self, volume: float):
        """Updates master volume level (0.0 to 1.0)."""
        self.master_volume = max(0.0, min(1.0, float(volume)))
        self._apply_volume_to_all_active()
        self.master_volume_changed.emit(self.master_volume)
        self.save_config()

    def set_muted(self, muted: bool):
        """Toggles global mute."""
        self.is_muted = bool(muted)
        self._apply_volume_to_all_active()

    def _apply_volume_to_all_active(self):
        for item in self.active_players:
            clip = self.get_clip_by_id(item["clip_id"])
            clip_vol = clip.volume if clip else 1.0
            effective = 0.0 if self.is_muted else (self.master_volume * clip_vol)
            item["audio"].setVolume(effective)

    # -------------------------------------------------------------
    # PLAYBACK OPERATIONS (THREAD-SAFE PUBLIC API)
    # -------------------------------------------------------------
    def play_clip(self, clip_id: str):
        """Plays sound clip by ID with polyphonic overlap or exclusive cut-off (thread-safe)."""
        if QThread.currentThread() != self.thread():
            self._req_play.emit(clip_id)
        else:
            self._do_play_clip(clip_id)

    def stop_clip(self, clip_id: str):
        """Stops all active instances of a specific sound clip (thread-safe)."""
        if QThread.currentThread() != self.thread():
            self._req_stop.emit(clip_id)
        else:
            self._do_stop_clip(clip_id)

    def toggle_clip(self, clip_id: str):
        """Toggles playback of a sound clip: plays if stopped, stops if playing (thread-safe)."""
        if QThread.currentThread() != self.thread():
            self._req_toggle.emit(clip_id)
        else:
            self._do_toggle_clip(clip_id)

    def stop_all(self):
        """Emergency silence: stops all active audio playback immediately (thread-safe)."""
        if QThread.currentThread() != self.thread():
            self._req_stop_all.emit()
        else:
            self._do_stop_all()

    def play_alarm_buzzer(self):
        """Plays the punitive loud alarm buzzer (SandMan Troll Shield / alerts)."""
        buzzer_clip = self.get_clip_by_id("cue-buzzer")
        if buzzer_clip and os.path.exists(buzzer_clip.file_path):
            self.play_clip("cue-buzzer")
            return
        for c in self.clips:
            if "buzzer" in c.name.lower() or "buzzer" in c.file_path.lower():
                if os.path.exists(c.file_path):
                    self.play_clip(c.id)
                    return
        fallback = os.path.join(self.sounds_dir, "buzzer_fail.wav")
        if os.path.exists(fallback):
            for c in self.clips:
                if os.path.normpath(c.file_path) == os.path.normpath(fallback):
                    self.play_clip(c.id)
                    return

    def is_clip_playing(self, clip_id: str) -> bool:
        """Checks if a sound clip is currently playing."""
        return any(item["clip_id"] == clip_id for item in self.active_players)

    # -------------------------------------------------------------
    # INTERNAL GUI-THREAD PLAYBACK HANDLERS
    # -------------------------------------------------------------
    def _do_toggle_clip(self, clip_id: str):
        now = time.time()
        last_t = self._last_trigger_time.get(clip_id, 0.0)
        if now - last_t < 0.25:
            return
        self._last_trigger_time[clip_id] = now

        if self.is_clip_playing(clip_id):
            self._do_stop_clip(clip_id)
        else:
            self._do_play_clip(clip_id)

    def _do_play_clip(self, clip_id: str):
        clip = self.get_clip_by_id(clip_id)
        if not clip:
            self.error_occurred.emit(f"Sound clip '{clip_id}' not found.")
            return

        if not os.path.exists(clip.file_path):
            self.error_occurred.emit(f"Audio file not found: {clip.file_path}")
            return

        if self.exclusive_mode:
            self._do_stop_all()

        # Allocate player + audio output on GUI thread
        player = QMediaPlayer(self)
        audio_output = QAudioOutput(self)
        player.setAudioOutput(audio_output)

        target_device = self._resolve_target_device()
        if target_device:
            audio_output.setDevice(target_device)

        effective_vol = 0.0 if self.is_muted else (self.master_volume * clip.volume)
        audio_output.setVolume(effective_vol)

        if clip.loop:
            player.setLoops(QMediaPlayer.Loops.Infinite)

        source_url = QUrl.fromLocalFile(os.path.abspath(clip.file_path))
        player.setSource(source_url)

        item = {
            "player": player,
            "audio": audio_output,
            "clip_id": clip.id
        }
        self.active_players.append(item)

        # Hook playback end, media status, and error handlers
        def on_state_changed(state):
            if state == QMediaPlayer.PlaybackState.StoppedState:
                self._cleanup_player(item)

        def on_media_status_changed(status):
            if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
                self._cleanup_player(item)

        def on_error(err, err_str):
            print(f"[Soundboard] Playback error on {clip.name}: {err} ({err_str})")
            self._cleanup_player(item)

        player.playbackStateChanged.connect(on_state_changed)
        player.mediaStatusChanged.connect(on_media_status_changed)
        player.errorOccurred.connect(on_error)

        player.play()
        self.clip_started.emit(clip.id, clip.name)

    def _do_stop_clip(self, clip_id: str):
        to_stop = [item for item in list(self.active_players) if item["clip_id"] == clip_id]
        for item in to_stop:
            try:
                item["player"].stop()
            except Exception:
                pass
            self._cleanup_player(item)

    def _do_stop_all(self):
        active_ids = list(set(item["clip_id"] for item in self.active_players))
        for item in list(self.active_players):
            try:
                item["player"].stop()
            except Exception:
                pass
            self._cleanup_player(item)
        for cid in active_ids:
            self.clip_stopped.emit(cid)

    def _cleanup_player(self, item: Dict):
        if item in self.active_players:
            self.active_players.remove(item)
        else:
            return  # Idempotent guard against multiple completion signals

        clip_id = item["clip_id"]
        try:
            item["player"].stop()
        except Exception:
            pass
        try:
            item["player"].deleteLater()
            item["audio"].deleteLater()
        except Exception:
            pass
        if not self.is_clip_playing(clip_id):
            self.clip_stopped.emit(clip_id)

    # -------------------------------------------------------------
    # CLIP CRUD & DATA MANAGEMENT
    # -------------------------------------------------------------
    def get_clip_by_id(self, clip_id: str) -> Optional[SoundClip]:
        for clip in self.clips:
            if clip.id == clip_id:
                return clip
        return None

    def add_clip(self, name: str, file_path: str, hotkey: str = "", volume: float = 1.0,
                 color: str = "#38bdf8", category: str = "General", loop: bool = False) -> SoundClip:
        new_clip = SoundClip(
            id=str(uuid.uuid4())[:8],
            name=name.strip() or "New Sound",
            file_path=file_path,
            hotkey=hotkey.strip().lower(),
            volume=max(0.0, min(1.0, float(volume))),
            color=color,
            category=category.strip() or "General",
            loop=bool(loop)
        )
        self.clips.append(new_clip)
        self.save_config()
        self.clips_updated.emit()
        return new_clip

    def update_clip(self, clip_id: str, **kwargs) -> bool:
        clip = self.get_clip_by_id(clip_id)
        if not clip:
            return False
        for key, val in kwargs.items():
            if hasattr(clip, key):
                if key == "volume":
                    val = max(0.0, min(1.0, float(val)))
                elif key == "hotkey":
                    val = str(val).strip().lower()
                setattr(clip, key, val)
        self.save_config()
        self.clips_updated.emit()
        return True

    def remove_clip(self, clip_id: str) -> bool:
        self.stop_clip(clip_id)
        clip = self.get_clip_by_id(clip_id)
        if clip:
            self.clips.remove(clip)
            self.save_config()
            self.clips_updated.emit()
            return True
        return False

    def get_categories(self) -> List[str]:
        """Returns sorted unique list of sound categories."""
        cats = sorted(list(set(c.category for c in self.clips if c.category)))
        return ["All"] + (cats if cats else ["General"])

    def trigger_hotkey(self, hotkey_str: str) -> bool:
        """Finds sound mapped to hotkey and toggles it. Returns True if handled."""
        target_hk = hotkey_str.strip().lower()
        for clip in self.clips:
            if clip.hotkey and clip.hotkey.strip().lower() == target_hk:
                self.toggle_clip(clip.id)
                return True
        return False

    def sync_keyboard_hooks(self):
        """Registers global OS-wide hotkeys for clips using keyboard library."""
        try:
            import keyboard
        except ImportError:
            return

        self.unbind_keyboard_hooks()
        for clip in self.clips:
            if not clip.hotkey:
                continue
            hk = clip.hotkey.strip().lower()
            try:
                # Use thread-safe queued signal emission so playback is guaranteed
                # to run on the main Qt GUI thread with an active event loop
                keyboard.add_hotkey(hk, lambda cid=clip.id: self._req_toggle.emit(cid))
                self._bound_hotkeys[clip.id] = hk
            except Exception as e:
                pass

    def unbind_keyboard_hooks(self):
        """Unregisters all bound soundboard hotkeys."""
        try:
            import keyboard
            for cid, hk in list(self._bound_hotkeys.items()):
                try:
                    keyboard.remove_hotkey(hk)
                except Exception:
                    pass
            self._bound_hotkeys.clear()
        except Exception:
            pass

    # -------------------------------------------------------------
    # PERSISTENCE
    # -------------------------------------------------------------
    def save_config(self):
        data = {
            "master_volume": self.master_volume,
            "exclusive_mode": self.exclusive_mode,
            "selected_device_name": self.selected_device_name,
            "clips": [c.to_dict() for c in self.clips]
        }
        for path in [CONFIG_PATH, LOCAL_CONFIG_PATH]:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                print(f"[Soundboard] Could not save config to {path}: {e}")
        self.sync_keyboard_hooks()

    def load_config(self):
        loaded_data = None
        for path in [CONFIG_PATH, LOCAL_CONFIG_PATH]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        loaded_data = json.load(f)
                    break
                except Exception as e:
                    print(f"[Soundboard] Could not read {path}: {e}")

        if loaded_data:
            self.master_volume = float(loaded_data.get("master_volume", 1.0))
            self.exclusive_mode = bool(loaded_data.get("exclusive_mode", False))
            self.selected_device_name = loaded_data.get("selected_device_name", "")
            raw_clips = loaded_data.get("clips", [])
            self.clips = [SoundClip.from_dict(d) for d in raw_clips]
            self.sync_keyboard_hooks()
        else:
            # Seed starter default soundboard entries
            self.clips = [
                SoundClip(
                    id="cue-chime",
                    name="Chime Alert",
                    file_path=os.path.join(self.sounds_dir, "chime_alert.wav"),
                    hotkey="ctrl+f8",
                    volume=0.9,
                    color="#38bdf8",
                    category="Alerts"
                ),
                SoundClip(
                    id="cue-marker",
                    name="Stream Marker Ding",
                    file_path=os.path.join(self.sounds_dir, "marker_ding.wav"),
                    hotkey="ctrl+f9",
                    volume=0.95,
                    color="#22c55e",
                    category="Stream Markers"
                ),
                SoundClip(
                    id="cue-levelup",
                    name="Level Up Fanfare",
                    file_path=os.path.join(self.sounds_dir, "level_up.wav"),
                    hotkey="ctrl+f10",
                    volume=0.85,
                    color="#f59e0b",
                    category="Hype"
                ),
                SoundClip(
                    id="cue-airhorn",
                    name="Airhorn Blast",
                    file_path=os.path.join(self.sounds_dir, "airhorn_blast.wav"),
                    hotkey="ctrl+f11",
                    volume=0.75,
                    color="#ec4899",
                    category="Hype"
                ),
                SoundClip(
                    id="cue-buzzer",
                    name="Buzzer Fail",
                    file_path=os.path.join(self.sounds_dir, "buzzer_fail.wav"),
                    hotkey="ctrl+f12",
                    volume=0.8,
                    color="#ef4444",
                    category="Memes"
                )
            ]
            self.save_config()
