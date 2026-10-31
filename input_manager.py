"""
Input Manager for Streamer Calyx (Phase 5)
Provides unified peripheral shortcut management across Keyboards, Mouse Buttons,
and Gamepads (Xbox, PowerA, PlayStation, and standard XInput controllers).
"""

import sys
import os
import time
import json
import ctypes
from ctypes import wintypes, WINFUNCTYPE
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer
from debug_logger import log_debug

# Windows User32 for mouse and keyboard modifier polling
user32 = ctypes.windll.user32 if sys.platform == "win32" else None

# Load Windows XInput library dynamically
xinput = None
_xinput_get_state = None
if sys.platform == "win32":
    for dll_name in ['xinput1_4.dll', 'xinput1_3.dll', 'xinput9_1_0.dll']:
        try:
            xinput = ctypes.windll.LoadLibrary(dll_name)
            break
        except Exception:
            pass

    if xinput:
        # Ordinal 100 on XInput DLLs is XInputGetStateEx (includes Xbox Guide button bit 0x0400)
        try:
            proto = WINFUNCTYPE(wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
            _xinput_get_state = proto((100, xinput))
        except Exception:
            _xinput_get_state = getattr(xinput, "XInputGetState", None)


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ('wButtons', wintypes.WORD),
        ('bLeftTrigger', wintypes.BYTE),
        ('bRightTrigger', wintypes.BYTE),
        ('sThumbLX', wintypes.SHORT),
        ('sThumbLY', wintypes.SHORT),
        ('sThumbRX', wintypes.SHORT),
        ('sThumbRY', wintypes.SHORT),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ('dwPacketNumber', wintypes.DWORD),
        ('Gamepad', XINPUT_GAMEPAD),
    ]


# XInput Bitmask Map
XINPUT_BUTTON_MAP = {
    0x0001: "D-Pad Up",
    0x0002: "D-Pad Down",
    0x0004: "D-Pad Left",
    0x0008: "D-Pad Right",
    0x0010: "Start",
    0x0020: "Back",
    0x0040: "LS Click",
    0x0080: "RS Click",
    0x00100: "LB",
    0x00200: "RB",
    0x00400: "Guide",
    0x1000: "A",
    0x2000: "B",
    0x4000: "X",
    0x8000: "Y",
}

# Mouse Virtual Keys
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05  # Mouse 4 (Back)
VK_XBUTTON2 = 0x06  # Mouse 5 (Forward)

VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12  # Alt


BUTTON_PRIORITY = {
    # Keyboard modifiers
    "Ctrl": 1, "Alt": 2, "Shift": 3, "Win": 4, "Windows": 4,
    # Gamepad triggers & bumpers (primary chord modifiers)
    "LT": 10, "RT": 11, "LB": 12, "RB": 13,
    # Gamepad stick clicks & special buttons
    "LS Click": 20, "RS Click": 21, "Guide": 22, "Back": 23, "Start": 24,
    # D-Pad
    "D-Pad Up": 30, "D-Pad Down": 31, "D-Pad Left": 32, "D-Pad Right": 33,
    # Face buttons
    "X": 40, "Y": 41, "A": 42, "B": 43,
    # Mouse buttons
    "Middle Click": 50, "Mouse 4": 51, "Mouse 5": 52,
}


def normalize_chord(btn_list):
    """Returns canonical, sorted string of button names (e.g., 'LT+LS Click+Y')."""
    if not btn_list:
        return ""
    clean = sorted(
        list(set(b.strip() for b in btn_list if b.strip())),
        key=lambda x: (BUTTON_PRIORITY.get(x, 100), x)
    )
    return "+".join(clean)


class PeripheralWorker(QThread):
    """
    Dedicated 60Hz background thread for non-blocking gamepad and mouse button polling.
    Zero external dependencies, highly responsive with negligible CPU usage (<0.1%).
    """
    # Signals
    gamepad_status_signal = pyqtSignal(int, bool, list, int, int) # slot, connected, pressed_buttons, LT, RT
    mouse_status_signal = pyqtSignal(list, bool, bool, bool)       # pressed_buttons, ctrl, shift, alt
    action_triggered_signal = pyqtSignal(str)                     # action_id
    raw_input_captured_signal = pyqtSignal(str, str)              # device_type ("gamepad"/"mouse"), formatted_binding

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._bindings = {}  # action_id -> dict(device, binding, hold, enabled)
        
        # State tracking for gamepads
        self._last_gamepad_state = {}     # slot -> set(buttons)
        self._gamepad_press_time = {}     # (slot, chord) -> timestamp
        self._gamepad_fired = set()       # set of (slot, chord) already triggered while held
        self._gamepad_chord_active = {}   # slot -> bool (True if chord was reached during current press gesture)
        
        # State tracking for mouse
        self._last_mouse_state = set()
        self._mouse_press_time = {}       # chord -> timestamp
        self._mouse_fired = set()
        self._mouse_chord_active = False
        
        # Recording mode state (Peak chord accumulator)
        self.recording_mode = False
        self._rec_gamepad_accum = {}      # slot -> set(button names)
        self._rec_gamepad_active = {}     # slot -> bool
        self._rec_mouse_accum = set()
        self._rec_mouse_active = False
        self._last_emitted_rec_chord = ""

        # HUD throttling state
        self._last_hud_state = {}
        self._hud_tick = 0

    def update_bindings(self, bindings):
        """Thread-safe update of active bindings."""
        self._bindings = dict(bindings)

    def set_recording_mode(self, enabled):
        self.recording_mode = bool(enabled)
        self._rec_gamepad_accum.clear()
        self._rec_gamepad_active.clear()
        self._rec_mouse_accum.clear()
        self._rec_mouse_active = False
        self._last_emitted_rec_chord = ""

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            now = time.time()
            
            # 1. POLL XINPUT GAMEPAD (Slots 0 to 3)
            if _xinput_get_state:
                for slot in range(4):
                    state = XINPUT_STATE()
                    res = _xinput_get_state(slot, ctypes.byref(state))
                    if res == 0:
                        pressed = []
                        w = state.Gamepad.wButtons
                        for bit, name in XINPUT_BUTTON_MAP.items():
                            if w & bit:
                                pressed.append(name)
                        
                        lt = state.Gamepad.bLeftTrigger
                        rt = state.Gamepad.bRightTrigger
                        if lt > 60:
                            pressed.append("LT")
                        if rt > 60:
                            pressed.append("RT")
                            
                        # Emit status for UI visualizer only when changed or on ~1s heartbeat
                        hud_sig = (True, tuple(pressed), lt > 60, rt > 60)
                        if self._last_hud_state.get(slot) != hud_sig or (self._hud_tick % 60 == 0):
                            self._last_hud_state[slot] = hud_sig
                            self.gamepad_status_signal.emit(slot, True, pressed, lt, rt)
                        
                        # Process recording or runtime binding triggers
                        if self.recording_mode:
                            if pressed:
                                if not self._rec_gamepad_active.get(slot, False):
                                    # Start fresh gesture on this controller
                                    self._rec_gamepad_accum[slot] = set(pressed)
                                    self._rec_gamepad_active[slot] = True
                                    self._last_emitted_rec_chord = ""
                                else:
                                    # Accumulate chord additions into peak set
                                    self._rec_gamepad_accum[slot].update(pressed)

                                chord = normalize_chord(self._rec_gamepad_accum[slot])
                                if chord and chord != self._last_emitted_rec_chord:
                                    self._last_emitted_rec_chord = chord
                                    self.raw_input_captured_signal.emit("gamepad", chord)
                            else:
                                self._rec_gamepad_active[slot] = False
                        else:
                            chord = normalize_chord(pressed)
                            self._process_gamepad_inputs(slot, chord, now)
                    else:
                        hud_sig = (False, (), False, False)
                        if self._last_hud_state.get(slot) != hud_sig:
                            self._last_hud_state[slot] = hud_sig
                            self.gamepad_status_signal.emit(slot, False, [], 0, 0)
                            self._last_gamepad_state[slot] = ""
            
            # 2. POLL MOUSE BUTTONS
            if user32:
                ctrl = (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0
                shift = (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0
                alt = (user32.GetAsyncKeyState(VK_MENU) & 0x8000) != 0
                
                m_pressed = []
                if (user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000) != 0:
                    m_pressed.append("Middle Click")
                if (user32.GetAsyncKeyState(VK_XBUTTON1) & 0x8000) != 0:
                    m_pressed.append("Mouse 4")
                if (user32.GetAsyncKeyState(VK_XBUTTON2) & 0x8000) != 0:
                    m_pressed.append("Mouse 5")
                
                if m_pressed:
                    self.mouse_status_signal.emit(m_pressed, ctrl, shift, alt)
                    
                    # Build chord with modifiers
                    mods = []
                    if ctrl: mods.append("Ctrl")
                    if shift: mods.append("Shift")
                    if alt: mods.append("Alt")

                    if self.recording_mode:
                        current_mouse_keys = mods + m_pressed
                        if not self._rec_mouse_active:
                            self._rec_mouse_accum = set(current_mouse_keys)
                            self._rec_mouse_active = True
                            self._last_emitted_rec_chord = ""
                        else:
                            self._rec_mouse_accum.update(current_mouse_keys)

                        m_chord = normalize_chord(self._rec_mouse_accum)
                        if m_chord and m_chord != self._last_emitted_rec_chord:
                            self._last_emitted_rec_chord = m_chord
                            self.raw_input_captured_signal.emit("mouse", m_chord)
                    else:
                        m_chord = normalize_chord(mods + m_pressed)
                        self._process_mouse_inputs(m_chord, now)
                else:
                    self._rec_mouse_active = False
                    self._last_mouse_state.clear()
                    self._mouse_press_time.clear()
                    self._mouse_fired.clear()

            # Tick at ~60Hz
            time.sleep(0.016)
            self._hud_tick = (self._hud_tick + 1) % 60000

    def _process_gamepad_inputs(self, slot, chord, now):
        last_chord = self._last_gamepad_state.get(slot, "")
        self._last_gamepad_state[slot] = chord

        if not chord:
            # All buttons released on this controller
            self._gamepad_chord_active[slot] = False
            keys_to_del = [k for k in self._gamepad_press_time if k[0] == slot]
            for k in keys_to_del:
                self._gamepad_press_time.pop(k, None)
            fired_to_del = [f for f in self._gamepad_fired if f[0] == slot]
            for f in fired_to_del:
                self._gamepad_fired.discard(f)
            return

        if "+" in chord:
            self._gamepad_chord_active[slot] = True

        is_chord_gesture = self._gamepad_chord_active.get(slot, False)

        # Check all matching bindings for gamepads
        for action_id, b_info in self._bindings.items():
            if not b_info.get("enabled", True):
                continue
            if b_info.get("device") != "gamepad":
                continue

            target_chord = normalize_chord(b_info.get("binding", "").split("+"))
            if not target_chord:
                continue

            # Shield single-button bindings if releasing from a chord gesture
            if is_chord_gesture and ("+" not in target_chord):
                continue

            # Does current controller state match the target chord?
            if chord == target_chord:
                hold_thresh = float(b_info.get("hold", 0.0))
                tracker_key = (slot, target_chord)

                if tracker_key not in self._gamepad_press_time:
                    self._gamepad_press_time[tracker_key] = now

                duration = now - self._gamepad_press_time[tracker_key]

                if tracker_key not in self._gamepad_fired:
                    if duration >= hold_thresh:
                        self.action_triggered_signal.emit(action_id)
                        self._gamepad_fired.add(tracker_key)

    def _process_mouse_inputs(self, chord, now):
        if not chord:
            self._mouse_chord_active = False
            self._mouse_press_time.clear()
            self._mouse_fired.clear()
            return

        if "+" in chord:
            self._mouse_chord_active = True

        for action_id, b_info in self._bindings.items():
            if not b_info.get("enabled", True):
                continue
            if b_info.get("device") != "mouse":
                continue

            target_chord = normalize_chord(b_info.get("binding", "").split("+"))
            if not target_chord:
                continue

            # Shield single-button bindings if releasing from a chord gesture
            if self._mouse_chord_active and ("+" not in target_chord):
                continue

            if chord == target_chord:
                hold_thresh = float(b_info.get("hold", 0.0))
                if target_chord not in self._mouse_press_time:
                    self._mouse_press_time[target_chord] = now

                duration = now - self._mouse_press_time[target_chord]

                if target_chord not in self._mouse_fired:
                    if duration >= hold_thresh:
                        self.action_triggered_signal.emit(action_id)
                        self._mouse_fired.add(target_chord)


class InputManager(QObject):
    """
    Unified manager for keyboard, mouse, and gamepad shortcuts.
    Coordinates between Python's keyboard library and the PeripheralWorker.
    """
    # High-level dispatch signals
    trigger_action = pyqtSignal(str) # action_id

    # Master Action Definitions
    ACTION_DEFINITIONS = [
        {"id": "primary_overlay", "name": "Primary Alert Overlay", "category": "Alerts & Highlights", "default_key": "ctrl+add"},
        {"id": "macro_0", "name": "Twitch Macro 1", "category": "Twitch Macros", "default_key": ""},
        {"id": "macro_1", "name": "Twitch Macro 2", "category": "Twitch Macros", "default_key": ""},
        {"id": "macro_2", "name": "Twitch Macro 3", "category": "Twitch Macros", "default_key": ""},
        {"id": "macro_3", "name": "Twitch Macro 4", "category": "Twitch Macros", "default_key": ""},
        {"id": "macro_4", "name": "Twitch Macro 5", "category": "Twitch Macros", "default_key": ""},
        {"id": "chronos_toggle", "name": "Chronos Timer Start / Stop", "category": "Stream Timing", "default_key": ""},
        {"id": "chronos_reset", "name": "Chronos Timer Reset", "category": "Stream Timing", "default_key": ""},
        {"id": "cycler_next", "name": "Text Cycler Next Item", "category": "Trivia & Text", "default_key": ""},
        {"id": "cycler_prev", "name": "Text Cycler Previous Item", "category": "Trivia & Text", "default_key": ""},
        {"id": "cycler_pause", "name": "Text Cycler Pause / Resume", "category": "Trivia & Text", "default_key": ""},
        {"id": "director_toggle", "name": "Stream Director Dock Toggle", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_1", "name": "Switch Scene 1", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_2", "name": "Switch Scene 2", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_3", "name": "Switch Scene 3", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_4", "name": "Switch Scene 4", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_5", "name": "Switch Scene 5", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_6", "name": "Switch Scene 6", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_7", "name": "Switch Scene 7", "category": "Stream Director", "default_key": ""},
        {"id": "director_scene_8", "name": "Switch Scene 8", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_1", "name": "Toggle Mute Audio 1 (Mic)", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_2", "name": "Toggle Mute Audio 2 (Game)", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_3", "name": "Toggle Mute Audio 3 (Music)", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_4", "name": "Toggle Mute Audio 4 (Discord)", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_5", "name": "Toggle Mute Audio 5 (Alerts)", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_6", "name": "Toggle Mute Audio 6", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_7", "name": "Toggle Mute Audio 7", "category": "Stream Director", "default_key": ""},
        {"id": "director_mute_8", "name": "Toggle Mute Audio 8", "category": "Stream Director", "default_key": ""},
        {"id": "soundboard_stop_all", "name": "Soundboard Emergency Silence (Stop All)", "category": "Soundboard", "default_key": ""},
    ]

    def __init__(self, overlay=None, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.bindings = {}
        self.bound_keyboard_hooks = {} # action_id -> hook_ref
        
        # Initialize background worker for mouse & gamepad
        self.worker = PeripheralWorker()
        self.worker.action_triggered_signal.connect(self._on_peripheral_action)
        self.worker.start()

    def get_action_definitions(self):
        """Returns action definitions with enriched display names reflecting active settings."""
        defs = []
        for item in self.ACTION_DEFINITIONS:
            act = dict(item)
            aid = act["id"]
            if aid.startswith("macro_") and self.overlay and hasattr(self.overlay, "twitch_macros"):
                try:
                    idx = int(aid.split("_")[1])
                    if idx < len(self.overlay.twitch_macros):
                        cmd = self.overlay.twitch_macros[idx].get("command", "")
                        if cmd:
                            act["name"] = f"Twitch Macro {idx + 1} ({cmd})"
                except Exception:
                    pass
            elif aid.startswith("director_scene_") and self.overlay:
                try:
                    idx = int(aid.split("_")[-1]) - 1
                    sw = getattr(self.overlay, "settings_window", None)
                    if sw and hasattr(sw, "tab_director") and idx < len(sw.tab_director.scenes):
                        sc_name = sw.tab_director.scenes[idx].get("name", "")
                        if sc_name:
                            act["name"] = f"Switch Scene {idx + 1} ({sc_name})"
                except Exception:
                    pass
            elif aid.startswith("director_mute_") and self.overlay:
                try:
                    idx = int(aid.split("_")[-1]) - 1
                    sw = getattr(self.overlay, "settings_window", None)
                    if sw and hasattr(sw, "tab_director") and idx < len(sw.tab_director.audio_toggles):
                        aud_name = sw.tab_director.audio_toggles[idx].get("name", "")
                        if aud_name:
                            act["name"] = f"Toggle Mute Audio {idx + 1} ({aud_name})"
                except Exception:
                    pass
            defs.append(act)
        return defs

    def shutdown(self):
        """Unregisters all hooks and stops the worker thread cleanly."""
        self.unbind_all_keyboard()
        if self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)

    def load_bindings(self, config_dict=None):
        """Loads bindings from configuration, migrating legacy keys if necessary."""
        self.unbind_all_keyboard()
        self.bindings = {}

        saved_bindings = config_dict.get("bindings", {}) if config_dict else {}

        for act in self.ACTION_DEFINITIONS:
            act_id = act["id"]
            if act_id in saved_bindings:
                b = dict(saved_bindings[act_id])
            else:
                # Fallback / Migration logic for existing primary & macro hotkeys
                if act_id == "primary_overlay" and config_dict:
                    b = {
                        "device": "keyboard",
                        "binding": config_dict.get("activation_hotkey", act["default_key"]),
                        "hold": 0.0,
                        "enabled": config_dict.get("primary_hotkey_enabled", True)
                    }
                elif act_id.startswith("macro_") and config_dict:
                    macros = config_dict.get("twitch_macros", config_dict.get("macro_hotkeys", []))
                    try:
                        idx = int(act_id.split("_")[1])
                        if idx < len(macros):
                            m = macros[idx]
                            b = {
                                "device": "keyboard",
                                "binding": m.get("hotkey", ""),
                                "hold": 0.0,
                                "enabled": bool(m.get("hotkey", ""))
                            }
                        else:
                            b = {"device": "keyboard", "binding": "", "hold": 0.0, "enabled": False}
                    except Exception:
                        b = {"device": "keyboard", "binding": "", "hold": 0.0, "enabled": False}
                else:
                    b = {
                        "device": "keyboard",
                        "binding": act["default_key"],
                        "hold": 0.0,
                        "enabled": bool(act["default_key"])
                    }
            self.bindings[act_id] = b

        # Register keyboard hooks
        self._sync_keyboard_hooks()

        # Update peripheral worker bindings
        self.worker.update_bindings(self.bindings)

    def save_bindings_to_config(self, config_dict):
        """Serializes bindings back to the configuration dictionary."""
        config_dict["bindings"] = self.bindings
        
        # Maintain sync with legacy keys for external consumers
        if "primary_overlay" in self.bindings:
            b = self.bindings["primary_overlay"]
            if b.get("device") == "keyboard":
                config_dict["activation_hotkey"] = b.get("binding", "")
                if self.overlay and hasattr(self.overlay, "activation_hotkey"):
                    self.overlay.activation_hotkey = b.get("binding", "")
            config_dict["primary_hotkey_enabled"] = b.get("enabled", True)
            if self.overlay and hasattr(self.overlay, "primary_hotkey_enabled"):
                self.overlay.primary_hotkey_enabled = b.get("enabled", True)

        for mlk in ["twitch_macros", "macro_hotkeys"]:
            if mlk in config_dict:
                for idx, m in enumerate(config_dict[mlk]):
                    act_id = f"macro_{idx}"
                    if act_id in self.bindings:
                        b = self.bindings[act_id]
                        if b.get("device") == "keyboard":
                            m["hotkey"] = b.get("binding", "")

        if self.overlay and hasattr(self.overlay, "twitch_macros"):
            for idx, m in enumerate(self.overlay.twitch_macros):
                act_id = f"macro_{idx}"
                if act_id in self.bindings:
                    b = self.bindings[act_id]
                    if b.get("device") == "keyboard":
                        m["hotkey"] = b.get("binding", "")

    def set_binding(self, action_id, device, binding_str, hold=0.0, enabled=True):
        """Updates a single binding, rebinding keyboard hooks and notifying worker."""
        self.bindings[action_id] = {
            "device": device,
            "binding": binding_str,
            "hold": float(hold),
            "enabled": bool(enabled)
        }
        if action_id == "primary_overlay" and self.overlay:
            if device == "keyboard" and hasattr(self.overlay, "activation_hotkey"):
                self.overlay.activation_hotkey = binding_str
            if hasattr(self.overlay, "primary_hotkey_enabled"):
                self.overlay.primary_hotkey_enabled = bool(enabled)
        elif action_id.startswith("macro_") and self.overlay and hasattr(self.overlay, "twitch_macros"):
            try:
                idx = int(action_id.split("_")[1])
                if idx < len(self.overlay.twitch_macros):
                    if device == "keyboard":
                        self.overlay.twitch_macros[idx]["hotkey"] = binding_str
            except Exception:
                pass

        self._sync_keyboard_hooks()
        self.worker.update_bindings(self.bindings)

    def clear_binding(self, action_id):
        if action_id in self.bindings:
            self.bindings[action_id]["binding"] = ""
            self.bindings[action_id]["enabled"] = False
            self._sync_keyboard_hooks()
            self.worker.update_bindings(self.bindings)

    def check_conflict(self, new_device, new_binding, exclude_action_id=None):
        """Returns action definition dict if a conflict exists, otherwise None."""
        if not new_binding or new_binding.lower() in ["not set", "none", ""]:
            return None
        norm_new = normalize_chord(new_binding.split("+"))
        for act in self.ACTION_DEFINITIONS:
            act_id = act["id"]
            if act_id == exclude_action_id:
                continue
            b = self.bindings.get(act_id)
            if not b or not b.get("enabled", True):
                continue
            if b.get("device") == new_device:
                cur_norm = normalize_chord(b.get("binding", "").split("+"))
                if cur_norm == norm_new:
                    return act
        return None

    def _sync_keyboard_hooks(self):
        """Re-registers keyboard hooks using python's keyboard library with dual-alias support."""
        try:
            import keyboard
        except ImportError:
            return

        self.unbind_all_keyboard()

        for action_id, b in self.bindings.items():
            if not b.get("enabled", True) or b.get("device") != "keyboard":
                continue
            k_str = b.get("binding", "").strip()
            if not k_str or k_str.lower() in ["not set", "set hotkey...", "press key...", "press key(s)..."]:
                continue

            # Dual-alias normalization: allow both 'ctrl+add' and 'ctrl++'
            keys_to_bind = [k_str]
            k_lower = k_str.lower()
            if "+add" in k_lower:
                keys_to_bind.append(k_lower.replace("+add", "++"))
            elif "++" in k_lower:
                keys_to_bind.append(k_lower.replace("++", "+add"))
            elif "+plus" in k_lower:
                keys_to_bind.append(k_lower.replace("+plus", "+add"))

            registered = []
            for candidate in set(keys_to_bind):
                try:
                    def make_callback(aid=action_id, key_name=candidate):
                        return lambda: self._on_keyboard_triggered(aid, key_name)

                    keyboard.add_hotkey(candidate, make_callback(action_id, candidate))
                    registered.append(candidate)
                    log_debug("INPUT", f"Successfully registered keyboard hook: action='{action_id}', key='{candidate}'")
                except Exception as e:
                    log_debug("INPUT_ERR", f"Could not bind keyboard shortcut '{candidate}' for {action_id}: {e}")

            if registered:
                self.bound_keyboard_hooks[action_id] = registered

    def _on_keyboard_triggered(self, action_id, key_name):
        log_debug("INPUT", f"Keyboard hotkey triggered: action_id='{action_id}', key='{key_name}'")
        self.trigger_action.emit(action_id)

    def unbind_all_keyboard(self):
        try:
            import keyboard
            for aid, hooks in list(self.bound_keyboard_hooks.items()):
                if isinstance(hooks, list):
                    for k_str in hooks:
                        try:
                            keyboard.remove_hotkey(k_str)
                        except Exception:
                            pass
                else:
                    try:
                        keyboard.remove_hotkey(hooks)
                    except Exception:
                        pass
            self.bound_keyboard_hooks.clear()
        except Exception:
            pass

    def _on_peripheral_action(self, action_id):
        """Dispatches action triggered by mouse or gamepad."""
        self.trigger_action.emit(action_id)
