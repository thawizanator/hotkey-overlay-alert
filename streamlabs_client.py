"""
Streamlabs Desktop (SLOBS) Local Named Pipe Client
Provides sub-millisecond, tokenless live communication with Streamlabs Desktop
via the local Windows named pipe: \\\\.\\pipe\\slobs

Supports:
- Scene switching and real-time active scene monitoring (ScenesService)
- Audio source muting / unmuting with real-time feedback (AudioService / SourcesService)
- Audio fader volume adjustment and deflection tracking (AudioSource)
- Auto-reconnect watchdog
"""

import sys
import json
import time
import threading
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from debug_logger import log_debug

SLOBS_PIPE_PATH = r"\\.\pipe\slobs"

class StreamlabsClient(QObject):
    """
    Manages communication with Streamlabs Desktop via \\\\.\\pipe\\slobs.
    Runs a dual-pipe architecture:
    - Dedicated command pipe for synchronous RPC requests (mutex-protected)
    - Dedicated subscription pipe for real-time background event stream
    """
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    scene_switched = pyqtSignal(str, str)          # (scene_id, scene_name)
    scenes_updated = pyqtSignal(list)              # list of scene dicts
    audio_sources_updated = pyqtSignal(list)       # list of audio source dicts
    audio_muted_changed = pyqtSignal(str, bool)    # (source_name_or_id, is_muted)
    audio_volume_changed = pyqtSignal(str, float)  # (source_name_or_id, deflection 0.0-1.0)
    source_updated = pyqtSignal(dict)              # source event dict

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._is_connected = False
        self._cmd_pipe = None
        self._sub_pipe = None
        self._cmd_lock = threading.Lock()
        self._req_counter = 0

        self._listener_thread: Optional[threading.Thread] = None
        self._running = False

        self._scenes_cache: List[Dict[str, Any]] = []
        self._active_scene_id: Optional[str] = None
        self._active_scene_name: Optional[str] = None
        self._audio_cache: List[Dict[str, Any]] = []

        # Watchdog timer to auto-reconnect if Streamlabs restarts
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(3000)
        self._watchdog.timeout.connect(self._check_watchdog)
        self._watchdog.start()

    def is_connected(self) -> bool:
        return self._is_connected

    def get_cached_scenes(self) -> List[Dict[str, Any]]:
        return list(self._scenes_cache)

    def get_cached_audio_sources(self) -> List[Dict[str, Any]]:
        return list(self._audio_cache)

    def get_active_scene_info(self) -> tuple[Optional[str], Optional[str]]:
        return self._active_scene_id, self._active_scene_name

    def connect_client(self) -> bool:
        """Attempts to open named pipes and start background event listener."""
        if self._is_connected:
            return True

        if sys.platform != "win32":
            return False

        try:
            log_debug("SLOBS", f"Attempting connection to {SLOBS_PIPE_PATH}...")
            # Open command pipe
            self._cmd_pipe = open(SLOBS_PIPE_PATH, "r+b", buffering=0)
            # Open subscription pipe
            self._sub_pipe = open(SLOBS_PIPE_PATH, "r+b", buffering=0)
        except (FileNotFoundError, OSError, PermissionError) as e:
            log_debug("SLOBS", f"Streamlabs pipe not available: {e}")
            self._cleanup_pipes()
            return False

        self._is_connected = True
        self._running = True

        # Initial subscribe on subscription pipe BEFORE starting listener thread
        self._subscribe_to_events()

        # Start listener thread for subscription events (sole owner of _sub_pipe now)
        self._listener_thread = threading.Thread(
            target=self._event_listener_loop,
            daemon=True,
            name="StreamlabsEventListener"
        )
        self._listener_thread.start()

        # Initial data fetch on command pipe
        self.fetch_scenes()
        self.fetch_active_scene()
        self.fetch_audio_sources()

        log_debug("SLOBS", "Connected to Streamlabs Desktop successfully!")
        self.connected.emit()
        return True

    def disconnect_client(self):
        """Disconnects and tears down pipes cleanly."""
        if not self._is_connected and not self._running:
            return

        log_debug("SLOBS", "Disconnecting from Streamlabs Desktop...")
        self._running = False
        self._is_connected = False
        self._cleanup_pipes()
        self.disconnected.emit()

    def _cleanup_pipes(self):
        with self._cmd_lock:
            if self._cmd_pipe:
                try:
                    self._cmd_pipe.close()
                except Exception:
                    pass
                self._cmd_pipe = None

        if self._sub_pipe:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    import ctypes
                    try:
                        handle = msvcrt.get_osfhandle(self._sub_pipe.fileno())
                        ctypes.windll.kernel32.CancelIoEx(handle, None)
                    except Exception:
                        pass
                self._sub_pipe.close()
            except Exception:
                pass
            self._sub_pipe = None

    def _check_watchdog(self):
        """Watchdog checks if connection is alive; if not, attempts reconnect."""
        if not self._is_connected:
            self.connect_client()
        else:
            # Lightweight ping / health check
            try:
                with self._cmd_lock:
                    if self._cmd_pipe is None or self._cmd_pipe.closed:
                        raise OSError("Pipe handle closed")
            except Exception:
                log_debug("SLOBS", "Watchdog detected dead pipe connection.")
                self.disconnect_client()

    def _next_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    def _call_rpc(self, method: str, resource: str, args: Optional[list] = None) -> Optional[Any]:
        """Synchronously calls a JSON-RPC method on the command pipe with mutex protection."""
        if not self._is_connected or self._cmd_pipe is None:
            return None

        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": {
                "resource": resource
            }
        }
        if args is not None:
            payload["params"]["args"] = args

        raw_bytes = (json.dumps(payload) + "\n").encode("utf-8")

        with self._cmd_lock:
            try:
                self._cmd_pipe.write(raw_bytes)
                line = self._cmd_pipe.readline()
                if not line:
                    raise ConnectionResetError("Empty response from Streamlabs pipe")
                data = json.loads(line.decode("utf-8"))
                if "error" in data:
                    log_debug("SLOBS", f"RPC error on {method}({resource}): {data['error']}")
                    return None
                return data.get("result")
            except Exception as e:
                log_debug("SLOBS", f"RPC execution failed: {e}")
                # Mark disconnected so watchdog can recover
                self._is_connected = False
                return None

    def _subscribe_to_events(self):
        """Sends subscription requests on the dedicated subscription pipe."""
        if not self._sub_pipe:
            return

        events = [
            ("sceneSwitched", "ScenesService"),
            ("sourceUpdated", "SourcesService"),
            ("audioSourceUpdated", "AudioService"),
        ]

        for method, resource in events:
            req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": method,
                "params": {
                    "resource": resource,
                    "args": []
                }
            }
            try:
                self._sub_pipe.write((json.dumps(req) + "\n").encode("utf-8"))
                resp_line = self._sub_pipe.readline()
                ack = json.loads(resp_line.decode("utf-8"))
                log_debug("SLOBS", f"Subscription ACK for {method}: {ack.get('result', {}).get('_type')}")
            except Exception as e:
                log_debug("SLOBS", f"Failed subscribing to {method}: {e}")

    def _event_listener_loop(self):
        """Dedicated background reader loop for streaming events from Streamlabs."""
        log_debug("SLOBS", "Event listener thread started.")
        while self._running:
            try:
                if not self._sub_pipe or self._sub_pipe.closed:
                    break
                line = self._sub_pipe.readline()
                if not line:
                    log_debug("SLOBS", "Event listener reached EOF.")
                    break

                try:
                    msg = json.loads(line.decode("utf-8"))
                except Exception:
                    continue

                res = msg.get("result", {})
                if not isinstance(res, dict):
                    continue

                _type = res.get("_type")
                if _type != "EVENT":
                    continue

                res_id = res.get("resourceId", "")
                data = res.get("data", {})

                # 1. Scene Switched
                if "sceneSwitched" in res_id:
                    sc_id = data.get("id", "")
                    sc_name = data.get("name", "")
                    self._active_scene_id = sc_id
                    self._active_scene_name = sc_name
                    log_debug("SLOBS", f"EVENT: Scene Switched -> '{sc_name}' ({sc_id})")
                    self.scene_switched.emit(sc_id, sc_name)

                # 2. Source Updated (Mute or properties)
                elif "sourceUpdated" in res_id or "audioSourceUpdated" in res_id:
                    self.source_updated.emit(data)
                    src_name = data.get("name", "")
                    src_id = data.get("sourceId") or data.get("id", "")
                    
                    # Update local cache entry if matched
                    self._update_local_audio_cache_entry(data)

                    if "muted" in data:
                        is_muted = bool(data.get("muted"))
                        self.audio_muted_changed.emit(src_name or src_id, is_muted)

                    fader = data.get("fader")
                    if isinstance(fader, dict) and "deflection" in fader:
                        deflection = float(fader.get("deflection", 1.0))
                        self.audio_volume_changed.emit(src_name or src_id, deflection)

            except Exception as e:
                if self._running:
                    log_debug("SLOBS", f"Event listener loop exception: {e}")
                break

        log_debug("SLOBS", "Event listener thread terminated.")
        if self._running:
            self._is_connected = False
            self.disconnected.emit()

    def _update_local_audio_cache_entry(self, data: dict):
        src_name = data.get("name")
        src_id = data.get("sourceId") or data.get("id")
        for item in self._audio_cache:
            if (src_name and item.get("name") == src_name) or (src_id and (item.get("sourceId") == src_id or item.get("id") == src_id)):
                if "muted" in data:
                    item["muted"] = data["muted"]
                if "fader" in data and isinstance(data["fader"], dict):
                    if "fader" not in item:
                        item["fader"] = {}
                    item["fader"].update(data["fader"])
                break

    # =========================================================================
    # QUERY COMMANDS
    # =========================================================================

    def fetch_scenes(self) -> List[Dict[str, Any]]:
        """Retrieves all scenes from Streamlabs Desktop."""
        result = self._call_rpc("getScenes", "ScenesService")
        if isinstance(result, list):
            self._scenes_cache = [
                {"id": s.get("id", ""), "name": s.get("name", "")}
                for s in result if isinstance(s, dict) and s.get("name")
            ]
            log_debug("SLOBS", f"Fetched {len(self._scenes_cache)} scenes from Streamlabs.")
            self.scenes_updated.emit(self._scenes_cache)
            return self._scenes_cache
        return []

    def fetch_active_scene(self) -> Optional[Dict[str, str]]:
        """Retrieves current active scene."""
        result = self._call_rpc("activeScene", "ScenesService")
        if isinstance(result, dict):
            self._active_scene_id = result.get("id", "")
            self._active_scene_name = result.get("name", "")
            log_debug("SLOBS", f"Current active scene: '{self._active_scene_name}'")
            return {"id": self._active_scene_id, "name": self._active_scene_name}
        return None

    def fetch_audio_sources(self) -> List[Dict[str, Any]]:
        """Retrieves all audio mixer sources from Streamlabs Desktop."""
        result = self._call_rpc("getSources", "AudioService")
        if isinstance(result, list):
            self._audio_cache = result
            log_debug("SLOBS", f"Fetched {len(self._audio_cache)} audio sources from Streamlabs.")
            self.audio_sources_updated.emit(self._audio_cache)
            return self._audio_cache
        return []

    # =========================================================================
    # CONTROL COMMANDS
    # =========================================================================

    def make_scene_active(self, scene_id_or_name: str) -> bool:
        """
        Switches the live scene in Streamlabs Desktop.
        Accepts either a scene ID or scene name.
        """
        if not scene_id_or_name:
            return False

        target_id = scene_id_or_name
        # If it's a name, resolve to ID
        for sc in self._scenes_cache:
            if sc.get("name", "").strip().lower() == scene_id_or_name.strip().lower():
                target_id = sc.get("id", "")
                break

        log_debug("SLOBS", f"Switching live scene to target ID '{target_id}'...")
        res = self._call_rpc("makeSceneActive", "ScenesService", [target_id])
        return res is not None

    def _resolve_audio_resource_id(self, target: str) -> Optional[str]:
        """Resolves an audio source name or ID into its Streamlabs resourceId handle."""
        if not target:
            return None

        # Already a resourceId (e.g., AudioSource["..."])
        if target.startswith("AudioSource["):
            return target

        # Check local cache
        tgt_lower = target.strip().lower()
        for s in self._audio_cache:
            name = (s.get("name") or "").strip().lower()
            sid = str(s.get("sourceId") or "").strip().lower()
            aid = str(s.get("id") or "").strip().lower()
            if tgt_lower in (name, sid, aid):
                return s.get("resourceId")

        # Fallback: substring match on name
        for s in self._audio_cache:
            name = (s.get("name") or "").strip().lower()
            if tgt_lower in name or name in tgt_lower:
                return s.get("resourceId")

        # Try refreshing cache once
        refreshed = self.fetch_audio_sources()
        for s in refreshed:
            name = (s.get("name") or "").strip().lower()
            sid = str(s.get("sourceId") or "").strip().lower()
            aid = str(s.get("id") or "").strip().lower()
            if tgt_lower in (name, sid, aid) or tgt_lower in name:
                return s.get("resourceId")

        return None

    def set_audio_muted(self, target_name_or_id: str, muted: bool) -> bool:
        """Sets mute state for a given audio source name or ID."""
        res_id = self._resolve_audio_resource_id(target_name_or_id)
        if not res_id:
            log_debug("SLOBS", f"Could not find audio source matching '{target_name_or_id}'")
            return False

        log_debug("SLOBS", f"Setting mute={muted} on {res_id} ('{target_name_or_id}')")
        res = self._call_rpc("setMuted", res_id, [bool(muted)])
        if res is not None or res is True:
            # Update local audio cache entry
            for s in self._audio_cache:
                if s.get("resourceId") == res_id:
                    s["muted"] = bool(muted)
                    break
            # Optimistically notify
            self.audio_muted_changed.emit(target_name_or_id, muted)
            return True
        return False

    def set_audio_deflection(self, target_name_or_id: str, deflection: float) -> bool:
        """
        Sets volume deflection (0.0 to 1.0) for a given audio source.
        """
        res_id = self._resolve_audio_resource_id(target_name_or_id)
        if not res_id:
            log_debug("SLOBS", f"Could not find audio source matching '{target_name_or_id}'")
            return False

        # Clamp between 0.0 and 1.0
        val = max(0.0, min(1.0, float(deflection)))
        log_debug("SLOBS", f"Setting volume deflection={val:.2f} on {res_id} ('{target_name_or_id}')")
        res = self._call_rpc("setDeflection", res_id, [val])
        if res is not None or res is True:
            # Update local audio cache entry
            for s in self._audio_cache:
                if s.get("resourceId") == res_id:
                    if "fader" not in s or not isinstance(s["fader"], dict):
                        s["fader"] = {}
                    s["fader"]["deflection"] = val
                    break
            self.audio_volume_changed.emit(target_name_or_id, val)
            return True
        return False

    def get_source_muted_state(self, target_name_or_id: str) -> bool:
        """Returns cached mute state for an audio source."""
        tgt_lower = target_name_or_id.strip().lower()
        for s in self._audio_cache:
            name = (s.get("name") or "").strip().lower()
            sid = str(s.get("sourceId") or "").strip().lower()
            if tgt_lower in (name, sid) or tgt_lower in name or name in tgt_lower:
                return bool(s.get("muted", False))
        return False

    def get_source_volume_percent(self, target_name_or_id: str) -> int:
        """Returns cached volume percentage (0-100) for an audio source."""
        tgt_lower = target_name_or_id.strip().lower()
        for s in self._audio_cache:
            name = (s.get("name") or "").strip().lower()
            sid = str(s.get("sourceId") or "").strip().lower()
            if tgt_lower in (name, sid) or tgt_lower in name or name in tgt_lower:
                fader = s.get("fader", {})
                deflection = fader.get("deflection", 0.75)
                return int(round(deflection * 100))
        return 75


# Global singleton client instance
_global_streamlabs_client: Optional[StreamlabsClient] = None

def get_streamlabs_client() -> StreamlabsClient:
    global _global_streamlabs_client
    if _global_streamlabs_client is None:
        _global_streamlabs_client = StreamlabsClient()
    return _global_streamlabs_client
