"""
Soundboard LAN Bridge for Streamer Calyx
Enables Stream Directors on the local network (LAN) to view the streamer's soundboard
clips in real time, trigger playback on the streamer rig, and receive live Anti-Spam Troll Shield status.
"""

import json
from typing import Optional, List, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QUrl
from PyQt6.QtWebSockets import QWebSocketServer, QWebSocket
from PyQt6.QtNetwork import QHostAddress

from debug_logger import log_debug
from soundboard_spam_guard import SoundboardSpamGuard


class SoundboardLANServer(QObject):
    """
    WebSocket server hosted on the Streamer PC (default port 59651).
    Broadcasts soundboard clips to connected LAN Director Docks, receives trigger commands,
    and runs them through the SandMan Anti-Spam Troll Shield.
    """
    client_connected = pyqtSignal(str)     # client address
    client_disconnected = pyqtSignal(str)
    command_executed = pyqtSignal(str, str) # action, clip_id

    def __init__(self, engine, spam_guard: Optional[SoundboardSpamGuard] = None, port: int = 59651, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.spam_guard = spam_guard if spam_guard else SoundboardSpamGuard(parent=self)
        self.port = port
        self.server: Optional[QWebSocketServer] = None
        self.clients: List[QWebSocket] = []
        self._running = False

        # Hook engine signals to broadcast real-time state to LAN clients
        if self.engine:
            self._connect_engine()

    def _connect_engine(self):
        try:
            self.engine.clips_updated.connect(self._on_clips_updated)
            self.engine.clip_started.connect(self._on_clip_started)
            self.engine.clip_stopped.connect(self._on_clip_stopped)
        except Exception as e:
            log_debug("LAN_SOUND_SERVER", f"Error connecting engine signals: {e}")

    def start(self) -> bool:
        """Starts listening for incoming LAN Director connections."""
        if self._running:
            return True
        try:
            self.server = QWebSocketServer("StreamerCalyxSoundboardBridge", QWebSocketServer.SslMode.NonSecureMode, self)
            ok = self.server.listen(QHostAddress.SpecialAddress.AnyIPv4, self.port)
            if ok:
                self._running = True
                self.server.newConnection.connect(self._on_new_connection)
                log_debug("LAN_SOUND_SERVER", f"Soundboard LAN Bridge listening on port {self.port}")
                return True
            else:
                log_debug("LAN_SOUND_SERVER", f"Failed to bind Soundboard LAN Bridge on port {self.port}: {self.server.errorString()}")
                return False
        except Exception as e:
            log_debug("LAN_SOUND_SERVER", f"Exception starting Soundboard LAN Bridge: {e}")
            return False

    def stop(self):
        """Stops server and closes all active client connections."""
        self._running = False
        if self.server:
            self.server.close()
            self.server = None
        for client in list(self.clients):
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()
        log_debug("LAN_SOUND_SERVER", "Soundboard LAN Bridge stopped.")

    def is_listening(self) -> bool:
        return self._running and self.server is not None and self.server.isListening()

    def _on_new_connection(self):
        if not self.server:
            return
        socket = self.server.nextPendingConnection()
        if not socket:
            return

        peer_addr = f"{socket.peerAddress().toString()}:{socket.peerPort()}"
        log_debug("LAN_SOUND_SERVER", f"LAN Director connected: {peer_addr}")
        self.clients.append(socket)
        socket.textMessageReceived.connect(lambda msg, s=socket: self._on_message_received(s, msg))
        socket.disconnected.connect(lambda s=socket, addr=peer_addr: self._on_socket_disconnected(s, addr))

        # Send initial full state immediately upon connection
        init_payload = {
            "type": "INIT_STATE",
            "clips": [c.to_dict() for c in getattr(self.engine, "clips", [])] if self.engine else [],
            "active_clip_ids": [item["clip_id"] for item in getattr(self.engine, "active_players", [])] if self.engine else []
        }
        socket.sendTextMessage(json.dumps(init_payload))
        self.client_connected.emit(peer_addr)

    def _on_socket_disconnected(self, socket: QWebSocket, peer_addr: str):
        if socket in self.clients:
            self.clients.remove(socket)
        log_debug("LAN_SOUND_SERVER", f"LAN Director disconnected: {peer_addr}")
        self.client_disconnected.emit(peer_addr)

    def _on_message_received(self, socket: QWebSocket, message: str):
        try:
            data = json.loads(message)
        except Exception:
            return

        action = data.get("action", "").upper().strip()
        peer_addr = socket.peerAddress().toString()
        user = data.get("user") or f"lan_{peer_addr}"

        if action == "PLAY_SOUND":
            clip_id = data.get("clip_id") or data.get("target") or ""
            if not clip_id:
                log_debug("LAN_SOUND_SERVER", f"Received PLAY_SOUND with empty clip_id from {user}")
                return
            if not self.engine:
                log_debug("LAN_SOUND_SERVER", f"Received PLAY_SOUND '{clip_id}' from {user} but self.engine is None!")
                return

            allowed, reason, rem = self.spam_guard.check_trigger(user)
            if not allowed:
                strikes = self.spam_guard.get_strike_count(user)
                log_debug("LAN_SOUND_SERVER", f"Spam Guard blocked {user}: {reason}")
                warn_msg = {
                    "type": "SPAM_WARNING",
                    "message": reason,
                    "cooldown": rem,
                    "strikes": strikes
                }
                socket.sendTextMessage(json.dumps(warn_msg))
                if strikes >= 3:
                    if hasattr(self.engine, "play_alarm_buzzer"):
                        self.engine.play_alarm_buzzer()
                    else:
                        self.engine.play_clip("cue-buzzer")
            else:
                log_debug("LAN_SOUND_SERVER", f"Executing validated PLAY_SOUND -> '{clip_id}' from {user}")
                self.engine.toggle_clip(clip_id)
                self.command_executed.emit("PLAY_SOUND", clip_id)

        elif action == "STOP_ALL":
            log_debug("LAN_SOUND_SERVER", f"Executing validated STOP_ALL from {user}")
            if self.engine:
                self.engine.stop_all()
            self.command_executed.emit("STOP_ALL", "")

        elif action == "REQUEST_STATE":
            state_msg = {
                "type": "INIT_STATE",
                "clips": [c.to_dict() for c in getattr(self.engine, "clips", [])] if self.engine else [],
                "active_clip_ids": [item["clip_id"] for item in getattr(self.engine, "active_players", [])] if self.engine else []
            }
            socket.sendTextMessage(json.dumps(state_msg))

    def _broadcast(self, payload: dict):
        if not self.clients:
            return
        msg = json.dumps(payload)
        for client in list(self.clients):
            try:
                client.sendTextMessage(msg)
            except Exception:
                pass

    def _on_clips_updated(self):
        self._broadcast({
            "type": "CLIPS_UPDATED",
            "clips": [c.to_dict() for c in getattr(self.engine, "clips", [])] if self.engine else []
        })

    def _on_clip_started(self, clip_id: str, clip_name: str):
        self._broadcast({
            "type": "PLAYBACK_STATE",
            "clip_id": clip_id,
            "is_playing": True
        })

    def _on_clip_stopped(self, clip_id: str):
        self._broadcast({
            "type": "PLAYBACK_STATE",
            "clip_id": clip_id,
            "is_playing": False
        })


class SoundboardLANClient(QObject):
    """
    WebSocket client running on the Director PC in LAN mode.
    Connects to the Streamer's SoundboardLANServer, receives soundboard clips, and dispatches triggers.
    """
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    clips_received = pyqtSignal(list)               # list of clip dicts
    playback_state_changed = pyqtSignal(str, bool)   # clip_id, is_playing
    spam_warning_received = pyqtSignal(str, float, int) # message, cooldown, strikes
    connection_status_changed = pyqtSignal(bool, str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.ws: Optional[QWebSocket] = None
        self.host = "127.0.0.1"
        self.port = 59651
        self._is_connected = False
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(3000)
        self._reconnect_timer.timeout.connect(self._try_reconnect)
        self._should_reconnect = False
        self.cached_clips: List[dict] = []
        self.active_clip_ids: set = set()

    def connect_to_host(self, host: str, port: int = 59651):
        """Connects to the Streamer PC's Soundboard LAN Bridge."""
        self.host = host.strip() or "127.0.0.1"
        self.port = port
        self._should_reconnect = True

        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

        self.ws = QWebSocket()
        self.ws.connected.connect(self._on_ws_connected)
        self.ws.disconnected.connect(self._on_ws_disconnected)
        self.ws.textMessageReceived.connect(self._on_ws_message)

        url = QUrl(f"ws://{self.host}:{self.port}")
        log_debug("LAN_SOUND_CLIENT", f"Connecting to Streamer Soundboard at {url.toString()}...")
        self.ws.open(url)

    def is_connected(self) -> bool:
        return self._is_connected and self.ws is not None

    def send_play_sound(self, clip_id: str, user: str = "director_dock"):
        if not self.is_connected():
            log_debug("LAN_SOUND_CLIENT", f"Cannot send_play_sound('{clip_id}'): not connected to host!")
            return
        payload = {"action": "PLAY_SOUND", "clip_id": clip_id, "user": user}
        log_debug("LAN_SOUND_CLIENT", f"Client sending PLAY_SOUND -> {clip_id} ({user})")
        self.ws.sendTextMessage(json.dumps(payload))

    def send_stop_all(self, user: str = "director_dock"):
        if not self.is_connected():
            return
        payload = {"action": "STOP_ALL", "user": user}
        self.ws.sendTextMessage(json.dumps(payload))

    def request_state(self):
        if not self.is_connected():
            return
        payload = {"action": "REQUEST_STATE"}
        self.ws.sendTextMessage(json.dumps(payload))

    def disconnect_client(self):
        self._should_reconnect = False
        self._reconnect_timer.stop()
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        self._is_connected = False

    def _on_ws_connected(self):
        self._is_connected = True
        self._reconnect_timer.stop()
        log_debug("LAN_SOUND_CLIENT", "Connected to Streamer Soundboard LAN Bridge!")
        self.connected.emit()
        self.connection_status_changed.emit(True, "🟢 Connected to Streamer Soundboard")

    def _on_ws_disconnected(self):
        self._is_connected = False
        log_debug("LAN_SOUND_CLIENT", "Disconnected from Streamer Soundboard LAN Bridge.")
        self.disconnected.emit()
        self.connection_status_changed.emit(False, "🔴 Soundboard Disconnected")
        if self._should_reconnect and not self._reconnect_timer.isActive():
            self._reconnect_timer.start()

    def _try_reconnect(self):
        if not self._is_connected and self._should_reconnect:
            self.connect_to_host(self.host, self.port)

    def _on_ws_message(self, message: str):
        try:
            data = json.loads(message)
        except Exception:
            return

        mtype = data.get("type", "")
        if mtype == "INIT_STATE":
            clips = data.get("clips", [])
            active_ids = set(data.get("active_clip_ids", []))
            self.cached_clips = clips
            self.active_clip_ids = active_ids
            log_debug("LAN_SOUND_CLIENT", f"Received {len(clips)} sound clips from Streamer rig")
            self.clips_received.emit(clips)
            for cid in active_ids:
                self.playback_state_changed.emit(cid, True)

        elif mtype == "CLIPS_UPDATED":
            clips = data.get("clips", [])
            self.cached_clips = clips
            log_debug("LAN_SOUND_CLIENT", f"Clips updated: {len(clips)} clips from Streamer rig")
            self.clips_received.emit(clips)

        elif mtype == "PLAYBACK_STATE":
            cid = data.get("clip_id", "")
            is_playing = bool(data.get("is_playing", False))
            if is_playing:
                self.active_clip_ids.add(cid)
            else:
                self.active_clip_ids.discard(cid)
            self.playback_state_changed.emit(cid, is_playing)

        elif mtype == "SPAM_WARNING":
            msg = data.get("message", "Spam Warning")
            cd = float(data.get("cooldown", 5.0))
            strikes = int(data.get("strikes", 1))
            self.spam_warning_received.emit(msg, cd, strikes)
