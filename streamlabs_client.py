"""
Streamlabs Desktop (SLOBS) Dual-Transport Client
Supports:
1. Local PC Mode: Sub-millisecond, tokenless live communication via Windows named pipe (\\\\.\\pipe\\slobs)
2. Remote LAN Mode: Network live communication via WebSocket (ws://<host>:59650/api/websocket) with token auth
"""

import sys
import json
import time
import socket
import threading
from typing import Dict, List, Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QUrl, QEventLoop
from PyQt6.QtWebSockets import QWebSocket
from debug_logger import log_debug

SLOBS_PIPE_PATH = r"\\.\pipe\slobs"
SLOBS_DEFAULT_PORT = 59650

class StreamlabsClient(QObject):
    """
    Manages communication with Streamlabs Desktop via local Named Pipe or remote LAN WebSocket.
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
        self._running = False
        self._mode = "local"  # "local" (Named Pipe) or "remote" (WebSocket)
        self._remote_host = "127.0.0.1"
        self._remote_port = SLOBS_DEFAULT_PORT
        self._remote_token = ""

        # Named Pipe Transport
        self._cmd_pipe = None
        self._sub_pipe = None
        self._cmd_lock = threading.Lock()
        self._listener_thread: Optional[threading.Thread] = None

        # WebSocket Transport
        self._ws: Optional[QWebSocket] = None
        self._pending_ws: Dict[int, Dict[str, Any]] = {}

        self._req_counter = 0
        self._scenes_cache: List[Dict[str, Any]] = []
        self._active_scene_id: Optional[str] = None
        self._active_scene_name: Optional[str] = None
        self._audio_cache: List[Dict[str, Any]] = []

        # Watchdog timer to auto-reconnect if connection drops
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(3000)
        self._watchdog.timeout.connect(self._check_watchdog)
        self._watchdog.start()

    def configure_connection(self, mode: str = "local", host: str = "127.0.0.1", port: int = 59650, token: str = ""):
        """Configures transport mode and target parameters."""
        new_mode = "remote" if mode == "remote" else "local"
        new_host = host.strip() or "127.0.0.1"
        try:
            new_port = int(port)
        except Exception:
            new_port = SLOBS_DEFAULT_PORT
        new_token = token.strip()

        changed = (
            self._mode != new_mode or
            self._remote_host != new_host or
            self._remote_port != new_port or
            self._remote_token != new_token
        )

        self._mode = new_mode
        self._remote_host = new_host
        self._remote_port = new_port
        self._remote_token = new_token

        if changed and self._is_connected:
            log_debug("SLOBS", f"Connection settings changed, reconnecting in {self._mode} mode...")
            self.disconnect_client()
            self.connect_client()

    def get_connection_config(self) -> dict:
        return {
            "mode": self._mode,
            "host": self._remote_host,
            "port": self._remote_port,
            "token": self._remote_token,
        }

    def is_connected(self) -> bool:
        return self._is_connected

    def get_cached_scenes(self) -> List[Dict[str, Any]]:
        return list(self._scenes_cache)

    def get_cached_audio_sources(self) -> List[Dict[str, Any]]:
        return list(self._audio_cache)

    def get_active_scene_info(self) -> tuple[Optional[str], Optional[str]]:
        return self._active_scene_id, self._active_scene_name

    def connect_client(self) -> bool:
        """Attempts connection using the configured transport mode."""
        if self._is_connected:
            return True

        if self._mode == "remote":
            return self._connect_websocket()
        return self._connect_named_pipe()

    def disconnect_client(self):
        """Disconnects and tears down active transport cleanly."""
        if not self._is_connected and not self._running:
            return

        log_debug("SLOBS", f"Disconnecting from Streamlabs Desktop ({self._mode} mode)...")
        self._running = False
        self._is_connected = False
        if self._mode == "remote":
            self._cleanup_ws()
        else:
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

    def _cleanup_ws(self):
        if self._ws:
            try:
                self._ws.blockSignals(True)
                self._ws.close()
                self._ws.deleteLater()
            except Exception:
                pass
            self._ws = None

        for entry in list(self._pending_ws.values()):
            try:
                entry["loop"].quit()
            except Exception:
                pass
        self._pending_ws.clear()

    # =========================================================================
    # NAMED PIPE TRANSPORT (Local PC Mode)
    # =========================================================================

    def _connect_named_pipe(self) -> bool:
        if sys.platform != "win32":
            log_debug("SLOBS", "Named pipe transport is only supported on Windows.")
            return False

        try:
            log_debug("SLOBS", f"Attempting connection to {SLOBS_PIPE_PATH}...")
            self._cmd_pipe = open(SLOBS_PIPE_PATH, "r+b", buffering=0)
            self._sub_pipe = open(SLOBS_PIPE_PATH, "r+b", buffering=0)
        except (FileNotFoundError, OSError, PermissionError) as e:
            log_debug("SLOBS", f"Streamlabs pipe not available: {e}")
            self._cleanup_pipes()
            return False

        self._is_connected = True
        self._running = True

        self._subscribe_to_events_pipe()

        self._listener_thread = threading.Thread(
            target=self._event_listener_loop,
            daemon=True,
            name="StreamlabsEventListener"
        )
        self._listener_thread.start()

        self.fetch_scenes()
        self.fetch_active_scene()
        self.fetch_audio_sources()

        log_debug("SLOBS", "Connected to Streamlabs Desktop successfully via Named Pipe!")
        self.connected.emit()
        return True

    def _subscribe_to_events_pipe(self):
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
                self._process_slobs_event(res)

            except Exception as e:
                if self._running:
                    log_debug("SLOBS", f"Event listener loop exception: {e}")
                break

        log_debug("SLOBS", "Event listener thread terminated.")
        if self._running:
            self._is_connected = False
            self.disconnected.emit()

    # =========================================================================
    # WEBSOCKET TRANSPORT (Remote LAN Mode)
    # =========================================================================

    def _connect_websocket(self) -> bool:
        self._cleanup_ws()
        url_str = f"ws://{self._remote_host}:{self._remote_port}/api/websocket"
        log_debug("SLOBS", f"Attempting WebSocket connection to {url_str}...")

        self._ws = QWebSocket()
        self._ws.textMessageReceived.connect(self._on_ws_text_message)
        self._ws.disconnected.connect(self._on_ws_disconnected)

        # Synchronous wait for WebSocket handshake (max 3500ms)
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        self._ws.connected.connect(loop.quit)
        self._ws.errorOccurred.connect(lambda err: loop.quit())
        timer.start(3500)
        self._ws.open(QUrl(url_str))
        loop.exec()

        if not self._ws or not self._ws.isValid():
            log_debug("SLOBS", f"WebSocket handshake failed to {url_str}")
            self._cleanup_ws()
            return False

        # Authenticate with token via TcpServerService.auth
        if self._remote_token:
            log_debug("SLOBS", "Authenticating WebSocket session with token...")
            auth_res = self._call_rpc_ws("auth", "TcpServerService", [self._remote_token])
            if auth_res is not True:
                log_debug("SLOBS", f"WebSocket authentication failed: {auth_res}")
                self._cleanup_ws()
                return False
            log_debug("SLOBS", "WebSocket authentication successful!")
        else:
            log_debug("SLOBS", "WebSocket connected without token.")

        self._is_connected = True
        self._running = True

        self._subscribe_to_events_ws()

        self.fetch_scenes()
        self.fetch_active_scene()
        self.fetch_audio_sources()

        log_debug("SLOBS", "Connected to Streamlabs Desktop successfully via WebSocket!")
        self.connected.emit()
        return True

    def _subscribe_to_events_ws(self):
        if not self._ws or not self._ws.isValid():
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
                self._ws.sendTextMessage(json.dumps(req))
            except Exception as e:
                log_debug("SLOBS", f"WebSocket subscription failed for {method}: {e}")

    def _on_ws_disconnected(self):
        log_debug("SLOBS", "WebSocket transport disconnected.")
        if self._running:
            self._is_connected = False
            self.disconnected.emit()

    def _on_ws_text_message(self, msg_str: str):
        try:
            data = json.loads(msg_str)
        except Exception:
            return

        req_id = data.get("id")
        if req_id in self._pending_ws:
            self._pending_ws[req_id]["result"] = data.get("result")
            self._pending_ws[req_id]["error"] = data.get("error")
            self._pending_ws[req_id]["loop"].quit()
            return

        res = data.get("result", {})
        if isinstance(res, dict) and res.get("_type") == "EVENT":
            self._process_slobs_event(res)

    def _call_rpc_ws(self, method: str, resource: str, args: Optional[list] = None) -> Optional[Any]:
        if not self._ws or not self._ws.isValid():
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

        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        self._pending_ws[req_id] = {"loop": loop, "result": None, "error": None}
        self._ws.sendTextMessage(json.dumps(payload))
        timer.start(2500)
        loop.exec()

        entry = self._pending_ws.pop(req_id, None)
        if entry and entry["result"] is not None:
            return entry["result"]
        if entry and entry["error"]:
            log_debug("SLOBS", f"WebSocket RPC error on {method}({resource}): {entry['error']}")
        return None

    # =========================================================================
    # UNIFIED RPC CALL & EVENT DISPATCH
    # =========================================================================

    def _next_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    def _call_rpc(self, method: str, resource: str, args: Optional[list] = None) -> Optional[Any]:
        if self._mode == "remote":
            return self._call_rpc_ws(method, resource, args)
        return self._call_rpc_pipe(method, resource, args)

    def _call_rpc_pipe(self, method: str, resource: str, args: Optional[list] = None) -> Optional[Any]:
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
                self._is_connected = False
                return None

    def _process_slobs_event(self, res: dict):
        if not isinstance(res, dict):
            return
        if res.get("_type") != "EVENT":
            return

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

            self._update_local_audio_cache_entry(data)

            if "muted" in data:
                is_muted = bool(data.get("muted"))
                self.audio_muted_changed.emit(src_name or src_id, is_muted)

            fader = data.get("fader")
            if isinstance(fader, dict) and "deflection" in fader:
                deflection = float(fader.get("deflection", 1.0))
                self.audio_volume_changed.emit(src_name or src_id, deflection)

    def _check_watchdog(self):
        """Watchdog checks if connection is alive; if not, attempts reconnect."""
        if not self._is_connected:
            self.connect_client()
        else:
            if self._mode == "remote":
                if not self._ws or not self._ws.isValid():
                    log_debug("SLOBS", "Watchdog detected dead WebSocket connection.")
                    self.disconnect_client()
            else:
                try:
                    with self._cmd_lock:
                        if self._cmd_pipe is None or self._cmd_pipe.closed:
                            raise OSError("Pipe handle closed")
                except Exception:
                    log_debug("SLOBS", "Watchdog detected dead pipe connection.")
                    self.disconnect_client()

    def auto_detect_local_settings(self) -> Optional[dict]:
        """Attempts to query token and settings from local Streamlabs Desktop via TcpServerService.getSettings."""
        if sys.platform != "win32":
            return None
        try:
            with open(SLOBS_PIPE_PATH, "r+b", buffering=0) as f:
                req = {"jsonrpc": "2.0", "id": 1, "method": "getSettings", "params": {"resource": "TcpServerService"}}
                f.write((json.dumps(req) + "\n").encode("utf-8"))
                line = f.readline()
                if line:
                    data = json.loads(line.decode("utf-8"))
                    res = data.get("result", {})
                    local_ip = "127.0.0.1"
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s.connect(("8.8.8.8", 80))
                        local_ip = s.getsockname()[0]
                        s.close()
                    except Exception:
                        pass
                    return {
                        "token": res.get("token", ""),
                        "port": res.get("websockets", {}).get("port", SLOBS_DEFAULT_PORT),
                        "local_ip": local_ip,
                        "allow_remote": res.get("websockets", {}).get("allowRemote", True)
                    }
        except Exception:
            return None

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
