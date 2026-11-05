import asyncio
import json
import hashlib
import time
import uuid
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QThread, pyqtSignal, QObject
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
from debug_logger import log_debug

import ssl

STUN_SERVERS = [
    "stun:stun.l.google.com:19302",
    "stun:stun1.l.google.com:19302",
    "stun:stun2.l.google.com:19302"
]

RELAY_SERVERS = [
    "https://ntfy.tedomum.fr",
    "https://ntfy.adminforge.de",
    "https://ntfy.sh"
]

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

def open_resilient(req: urllib.request.Request, timeout: int = 10):
    """
    Executes urllib request with standard verification, falling back to an unverified
    SSL context on any Windows root CA or third-party antivirus SSL interception error.
    """
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        err = str(e).lower()
        if any(k in err for k in ["ssl", "certificate", "verify failed", "cert", "handshake"]):
            unverified_ctx = ssl._create_unverified_context()
            return urllib.request.urlopen(req, timeout=timeout, context=unverified_ctx)
        raise e

def derive_signaling_room(channel_name: str, passkey: str) -> str:
    """Derives a one-way deterministic room identifier for ephemeral signaling."""
    clean_ch = (channel_name or "").lower().strip().lstrip("@")
    if "twitch.tv/" in clean_ch:
        clean_ch = clean_ch.split("twitch.tv/")[-1].split("/")[0].split("?")[0].strip()
    clean_pk = (passkey or "").strip().upper().replace(" ", "").replace("-", "")
    seed = f"hk_director_sig:{clean_ch}:{clean_pk}".encode("utf-8")
    return "hk_" + hashlib.sha256(seed).hexdigest()[:24]


class WebRTCManager(QThread):
    """
    Manages peer-to-peer WebRTC connections with DTLS-SRTP encryption
    for Stream Director remote control (Host or Client).
    """
    connection_status_changed = pyqtSignal(str, str)  # (status_tag, message)
    peer_authenticated = pyqtSignal(str, str)         # (peer_id, twitch_user)
    peer_disconnected = pyqtSignal(str)              # (peer_id)
    command_received = pyqtSignal(str, dict)          # (peer_id, payload)
    state_received = pyqtSignal(dict)                 # (state_payload)
    error_occurred = pyqtSignal(str)

    def __init__(self, role: str, channel_name: str, passkey: str, twitch_user: str = "", twitch_token: str = "", parent: Optional[QObject] = None):
        super().__init__(parent)
        self.role = role.lower().strip()  # "host" or "client"
        self.channel_name = channel_name.strip()
        self.passkey = passkey.strip()
        self.twitch_user = twitch_user.strip()
        self.twitch_token = twitch_token.strip()

        self.instance_id = str(uuid.uuid4())[:8]
        self.room_id = derive_signaling_room(self.channel_name, self.passkey)
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._peers: Dict[str, dict] = {}
        self._client_channel = None
        self._client_pc: Optional[RTCPeerConnection] = None
        self._signaling_active = True
        self._last_signal_error = ""
        self._handshake_authenticated = False

    @property
    def is_connected(self) -> bool:
        if not self._running:
            return False
        if self.role == "client":
            return bool(self._client_channel and getattr(self._client_channel, "readyState", "") == "open" and self._handshake_authenticated)
        else:
            return any(p.get("auth", False) for p in self._peers.values())

    def run(self):
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        log_debug("WEBRTC", f"Starting WebRTCManager ({self.role}) in room {self.room_id}...")
        self.connection_status_changed.emit("signaling", "🟡 Initializing P2P signaling...")

        try:
            if self.role == "host":
                self._loop.run_until_complete(self._run_host_loop())
            else:
                self._loop.run_until_complete(self._run_client_loop())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log_debug("WEBRTC", f"WebRTC run loop exception: {e}")
            self.error_occurred.emit(str(e))
            self.connection_status_changed.emit("disconnected", f"🔴 Connection error: {e}")
        finally:
            self._cleanup_all()
            if self._loop and not self._loop.is_closed():
                self._loop.close()
            log_debug("WEBRTC", f"WebRTCManager ({self.role}) terminated.")

    def stop_session(self):
        """Signals background loop to stop and close all connections."""
        self._running = False
        self._signaling_active = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._cancel_tasks)
        self.wait(2000)

    def _cancel_tasks(self):
        if not self._loop or self._loop.is_closed():
            return
        try:
            for task in asyncio.all_tasks(self._loop):
                task.cancel()
        except Exception:
            pass

    def _cleanup_all(self):
        try:
            for peer_id, info in list(self._peers.items()):
                pc = info.get("pc")
                ch = info.get("channel")
                if ch:
                    try: ch.close()
                    except Exception: pass
                if pc:
                    try:
                        if self._loop and self._loop.is_running() and not self._loop.is_closed():
                            asyncio.run_coroutine_threadsafe(pc.close(), self._loop)
                    except Exception:
                        pass
            self._peers.clear()

            if self._client_channel:
                try: self._client_channel.close()
                except Exception: pass
                self._client_channel = None
            if self._client_pc:
                try:
                    if self._loop and self._loop.is_running() and not self._loop.is_closed():
                        asyncio.run_coroutine_threadsafe(self._client_pc.close(), self._loop)
                except Exception:
                    pass
                self._client_pc = None
        except Exception:
            pass

    # =========================================================================
    # SIGNALING HELPERS (Multi-Relay HTTP Pub/Sub)
    # =========================================================================

    async def _post_signal(self, payload: dict) -> bool:
        """Broadcasts a signaling message (offer/answer) across all available relay servers with SSL fallback and retries."""
        data = json.dumps(payload).encode("utf-8")
        headers = dict(COMMON_HEADERS)
        headers["Title"] = "DirectorSignal"
        headers["Priority"] = "high"
        loop = asyncio.get_running_loop()

        def post_single(base_url: str) -> bool:
            url = f"{base_url}/{self.room_id}"
            req = urllib.request.Request(url, data=data, headers=headers)
            for attempt in range(2):
                try:
                    with open_resilient(req, timeout=4) as res:
                        if res.status in (200, 201, 204):
                            return True
                except Exception as e:
                    self._last_signal_error = str(e)
                    if attempt == 0:
                        time.sleep(0.2)
            return False

        async def post_task(r):
            return await loop.run_in_executor(None, post_single, r)

        tasks = [asyncio.create_task(post_task(relay)) for relay in RELAY_SERVERS]
        for fut in asyncio.as_completed(tasks):
            try:
                res = await fut
                if res is True:
                    log_debug("WEBRTC", f"Broadcast {payload.get('type')}: accepted by relay")
                    return True
            except Exception:
                pass
        return False

    # =========================================================================
    # HOST (STREAMER PC) LOOP
    # =========================================================================

    async def _run_host_loop(self):
        self.connection_status_changed.emit("signaling", "🟡 Waiting for remote director to connect...")
        seen_msg_ids = set()
        seen_offers = set()
        loop = asyncio.get_running_loop()

        def fetch_relay_messages(base_url: str):
            poll_url = f"{base_url}/{self.room_id}/json?since=2m&poll=1"
            req = urllib.request.Request(poll_url, headers=COMMON_HEADERS)
            messages = []
            try:
                with open_resilient(req, timeout=3.5) as resp:
                    for raw_line in resp:
                        if not self._running:
                            break
                        line = raw_line.decode("utf-8").strip()
                        if line:
                            try:
                                msg_obj = json.loads(line)
                                mid = msg_obj.get("id")
                                if mid and mid in seen_msg_ids:
                                    continue
                                if msg_obj.get("event") == "message":
                                    if mid:
                                        seen_msg_ids.add(mid)
                                        if len(seen_msg_ids) > 1000:
                                            seen_msg_ids.pop()
                                    messages.append(json.loads(msg_obj.get("message", "{}")))
                            except Exception:
                                continue
            except Exception:
                return messages
            return messages

        while self._running:
            try:
                tasks = [loop.run_in_executor(None, fetch_relay_messages, r) for r in RELAY_SERVERS]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, list):
                        for msg in res:
                            sender = msg.get("from")
                            if not sender or sender == self.instance_id:
                                continue  # Ignore our own messages

                            mtype = msg.get("type")
                            if mtype == "OFFER":
                                sdp_sample = msg.get("sdp", {}).get("sdp", "")[:40]
                                offer_key = f"{sender}_{sdp_sample}"
                                if offer_key not in seen_offers:
                                    seen_offers.add(offer_key)
                                    if len(seen_offers) > 200:
                                        seen_offers.pop()
                                    log_debug("WEBRTC", f"Host received OFFER from client: {sender} in room {self.room_id}")
                                    await self._handle_client_offer(sender, msg.get("sdp"))

                # Periodic dead-peer sweep (peers inactive for >15s)
                now = time.time()
                for cid, pinfo in list(self._peers.items()):
                    if pinfo.get("auth", False) and (now - pinfo.get("last_seen", now) > 15.0):
                        log_debug("WEBRTC", f"Host detected peer timeout: {cid} inactive >15s")
                        self.disconnect_peer(cid)

                await asyncio.sleep(0.8)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log_debug("WEBRTC", f"Host signaling error: {e}")
                await asyncio.sleep(1.0)

    async def _handle_client_offer(self, client_id: str, sdp_dict: dict):
        if client_id in self._peers:
            old_info = self._peers.pop(client_id, None)
            if old_info:
                old_ch = old_info.get("channel")
                if old_ch:
                    try: old_ch.close()
                    except Exception: pass
                old_pc = old_info.get("pc")
                if old_pc:
                    try: await old_pc.close()
                    except Exception: pass

        config = RTCConfiguration(iceServers=[RTCIceServer(urls=STUN_SERVERS)])
        pc = RTCPeerConnection(configuration=config)
        self._peers[client_id] = {
            "pc": pc,
            "channel": None,
            "user": "",
            "auth": False,
            "last_seen": time.time()
        }

        @pc.on("datachannel")
        def on_datachannel(channel):
            log_debug("WEBRTC", f"Host DataChannel opened with client {client_id}")
            self._peers[client_id]["channel"] = channel

            @channel.on("message")
            def on_message(message):
                try:
                    payload = json.loads(message)
                except Exception:
                    return
                self._handle_incoming_host_message(client_id, channel, payload)

            @channel.on("close")
            def on_close():
                log_debug("WEBRTC", f"Host DataChannel closed with client {client_id}")
                self._peers.pop(client_id, None)
                self.peer_disconnected.emit(client_id)
                if not self._peers:
                    self.connection_status_changed.emit("signaling", "🟡 Waiting for remote director to connect...")

        @pc.on("iceconnectionstatechange")
        def on_ice_change():
            log_debug("WEBRTC", f"Host ICE state with {client_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState == "connected":
                self.connection_status_changed.emit("connected", f"🟢 Remote Director P2P Connected ({client_id})")
            elif pc.iceConnectionState in ["failed", "disconnected", "closed"]:
                self._peers.pop(client_id, None)
                self.peer_disconnected.emit(client_id)
                if not self._peers and self._running:
                    self.connection_status_changed.emit("signaling", "🟡 Waiting for remote director to connect...")

        # Set remote offer and create answer
        offer = RTCSessionDescription(sdp=sdp_dict["sdp"], type=sdp_dict["type"])
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        # Send answer back through signaling room
        answer_payload = {
            "type": "ANSWER",
            "from": self.instance_id,
            "to": client_id,
            "sdp": {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
        }
        await self._post_signal(answer_payload)
        log_debug("WEBRTC", f"Host sent ANSWER to client {client_id}")

    def _handle_incoming_host_message(self, client_id: str, channel, payload: dict):
        mtype = payload.get("type", "")
        if client_id in self._peers:
            self._peers[client_id]["last_seen"] = time.time()

        # 1. Handshake Phase
        if mtype == "HANDSHAKE":
            # Handshake is dispatched to Bouncer via command_received signal with action='HANDSHAKE'
            self.command_received.emit(client_id, {
                "action": "HANDSHAKE",
                "client_id": client_id,
                "passkey": payload.get("passkey", ""),
                "twitch_user": payload.get("twitch_user", ""),
                "twitch_token": payload.get("twitch_token", "")
            })
            return

        # 2. Ping-Pong Keepalive
        if mtype == "PING":
            self._send_on_channel(channel, {
                "type": "PONG",
                "timestamp": payload.get("timestamp", time.time())
            })
            return

        # 3. Director Command
        if self._peers.get(client_id, {}).get("auth", False):
            self.command_received.emit(client_id, payload)
        else:
            log_debug("WEBRTC", f"Ignored command from unauthenticated client: {client_id}")

    def _send_on_channel(self, channel, payload: dict):
        """Thread-safe dispatch of JSON payload over an RTCDataChannel onto the asyncio loop."""
        if not channel:
            return
        try:
            msg = json.dumps(payload)
        except Exception as e:
            log_debug("WEBRTC", f"JSON serialization error in _send_on_channel: {e}")
            return

        def _do_send():
            try:
                channel.send(msg)
            except Exception as e:
                log_debug("WEBRTC", f"DataChannel send error: {e}")

        if self._loop and self._loop.is_running():
            try:
                current_loop = None
                try:
                    current_loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
                if current_loop is self._loop:
                    _do_send()
                else:
                    self._loop.call_soon_threadsafe(_do_send)
            except Exception as e:
                log_debug("WEBRTC", f"Error dispatching send to loop: {e}")

    def approve_peer_handshake(self, client_id: str, twitch_user: str, initial_state: dict):
        """Called by Host UI when Bouncer approves the client's handshake."""
        if client_id in self._peers:
            self._peers[client_id]["auth"] = True
            self._peers[client_id]["user"] = twitch_user
            ch = self._peers[client_id].get("channel")
            if ch:
                self._send_on_channel(ch, {
                    "type": "HANDSHAKE_OK",
                    "user": twitch_user,
                    "state": initial_state
                })
                log_debug("WEBRTC", f"Dispatched HANDSHAKE_OK to client {client_id}")
            self.peer_authenticated.emit(client_id, twitch_user)

    def reject_peer_handshake(self, client_id: str, reason: str):
        """Called by Host UI when Bouncer rejects the client's handshake."""
        if client_id in self._peers:
            ch = self._peers[client_id].get("channel")
            if ch:
                self._send_on_channel(ch, {
                    "type": "HANDSHAKE_FAIL",
                    "reason": reason
                })
                if self._loop and self._loop.is_running():
                    try:
                        self._loop.call_soon_threadsafe(ch.close)
                    except Exception:
                        pass
            self.disconnect_peer(client_id)

    def broadcast_state(self, state: dict):
        """Broadcasts scene & mixer state update to all authenticated connected remote directors."""
        all_perms = state.get("user_permissions", {})
        for client_id, info in list(self._peers.items()):
            if info.get("auth", False) and info.get("channel"):
                peer_state = dict(state)
                peer_user = (info.get("user") or "").strip().lower().lstrip("@")
                if peer_user and all_perms:
                    for u, p in all_perms.items():
                        if u.lower().strip().lstrip("@") == peer_user:
                            peer_state["permissions"] = p
                            break
                elif not peer_user and "permissions" in state:
                    peer_state["permissions"] = state["permissions"]
                self._send_on_channel(info["channel"], {"type": "STATE_UPDATE", "state": peer_state})


    def disconnect_peer(self, client_id: str):
        """Terminates connection to a specific peer."""
        info = self._peers.pop(client_id, None)
        if info:
            ch = info.get("channel")
            if ch:
                try: ch.close()
                except Exception: pass
            pc = info.get("pc")
            if pc and self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(pc.close(), self._loop)
            self.peer_disconnected.emit(client_id)

    # =========================================================================
    # CLIENT (REMOTE DIRECTOR PC) LOOP
    # =========================================================================

    async def _run_client_loop(self):
        self.connection_status_changed.emit("signaling", "🟡 Connecting to Streamer via P2P signaling...")
        config = RTCConfiguration(iceServers=[RTCIceServer(urls=STUN_SERVERS)])
        self._client_pc = RTCPeerConnection(configuration=config)
        pc = self._client_pc

        channel = pc.createDataChannel("stream-director")
        self._client_channel = channel

        handshake_done = asyncio.Event()

        @channel.on("open")
        def on_open():
            log_debug("WEBRTC", "Client DataChannel opened! Sending Handshake...")
            self.connection_status_changed.emit("signaling", "🟡 P2P DataChannel open. Authenticating...")
            hs_msg = {
                "type": "HANDSHAKE",
                "passkey": self.passkey,
                "twitch_user": self.twitch_user,
                "twitch_token": self.twitch_token
            }
            channel.send(json.dumps(hs_msg))

        @channel.on("message")
        def on_message(message):
            try:
                payload = json.loads(message)
            except Exception:
                return

            mtype = payload.get("type")
            if mtype == "HANDSHAKE_OK":
                self._handshake_authenticated = True
                log_debug("WEBRTC", "Client handshake APPROVED by streamer!")
                self.connection_status_changed.emit("connected", f"🟢 Connected to {self.channel_name} (Encrypted P2P)")
                state = payload.get("state", {})
                if "user" in payload and "user" not in state:
                    state["user"] = payload["user"]
                if state:
                    self.state_received.emit(state)
                handshake_done.set()
                self.send_command("REQUEST_STATE")

            elif mtype == "HANDSHAKE_FAIL":
                reason = payload.get("reason", "Unauthorized")
                log_debug("WEBRTC", f"Client handshake REJECTED: {reason}")
                self.connection_status_changed.emit("disconnected", f"🔴 Access Denied: {reason}")
                self.error_occurred.emit(f"Handshake failed: {reason}")
                self.stop_session()

            elif mtype == "STATE_UPDATE":
                state = payload.get("state", {})
                if state:
                    self.state_received.emit(state)

            elif mtype == "PONG":
                self._last_pong = time.time()
                sent_ts = payload.get("timestamp")
                if sent_ts:
                    try:
                        rtt_ms = max(1, int((time.time() - float(sent_ts)) * 1000))
                        self.connection_status_changed.emit("connected", f"🟢 Connected to {self.channel_name} (Encrypted P2P • {rtt_ms}ms)")
                    except Exception:
                        pass

        @pc.on("iceconnectionstatechange")
        def on_ice():
            log_debug("WEBRTC", f"Client ICE State: {pc.iceConnectionState}")
            if self._running and handshake_done.is_set():
                if pc.iceConnectionState in ["failed", "disconnected"]:
                    self.connection_status_changed.emit("disconnected", "🔴 P2P Connection Lost")

        try:
            # 1. Create offer
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)

            # 2. Post offer to signaling room
            offer_payload = {
                "type": "OFFER",
                "from": self.instance_id,
                "sdp": {"type": pc.localDescription.type, "sdp": pc.localDescription.sdp}
            }
            log_debug("WEBRTC", f"Client posting OFFER to room {self.room_id}...")
            self.connection_status_changed.emit("signaling", "🟡 Contacting Streamer gateway...")
            post_ok = await self._post_signal(offer_payload)
            if not post_ok:
                log_debug("WEBRTC", f"Client failed to publish OFFER to signaling room {self.room_id}")
                err_detail = f": {self._last_signal_error}" if self._last_signal_error else ""
                self.connection_status_changed.emit("disconnected", f"🔴 Network Error: Failed to reach signaling relay{err_detail}")
                return

            log_debug("WEBRTC", f"Client posted OFFER in room {self.room_id}")
            self.connection_status_changed.emit("signaling", "🟡 Waiting for Streamer response...")

            # 3. Poll signaling room for ANSWER from Host across all relays with ?since=2m&poll=1
            loop = asyncio.get_running_loop()

            def poll_relay_for_answer(relay_base: str):
                poll_url = f"{relay_base}/{self.room_id}/json?since=2m&poll=1"
                req = urllib.request.Request(poll_url, headers=COMMON_HEADERS)
                try:
                    with open_resilient(req, timeout=3.5) as resp:
                        for raw_line in resp:
                            if not self._running:
                                break
                            line = raw_line.decode("utf-8").strip()
                            if line:
                                try:
                                    msg_obj = json.loads(line)
                                    if msg_obj.get("event") == "message":
                                        data = json.loads(msg_obj.get("message", "{}"))
                                        if data.get("type") == "ANSWER" and data.get("to") == self.instance_id:
                                            return data
                                except Exception:
                                    continue
                except Exception:
                    return None
                return None

            answer_msg = None
            start_wait = time.time()
            while self._running and (time.time() - start_wait < 30.0):
                tasks = [loop.run_in_executor(None, poll_relay_for_answer, r) for r in RELAY_SERVERS]
                for fut in asyncio.as_completed(tasks):
                    try:
                        res = await fut
                        if isinstance(res, dict) and res.get("type") == "ANSWER":
                            answer_msg = res
                            break
                    except Exception:
                        pass
                if answer_msg:
                    break
                await asyncio.sleep(0.5)

            if not answer_msg or not self._running:
                self.connection_status_changed.emit("disconnected", "🔴 Connection timed out (Streamer not responding)")
                return

            log_debug("WEBRTC", f"Client received ANSWER from Host: {answer_msg.get('from')}")
            ans_sdp = answer_msg.get("sdp", {})
            answer = RTCSessionDescription(sdp=ans_sdp["sdp"], type=ans_sdp["type"])
            await pc.setRemoteDescription(answer)

            # Keep client running while connected with 5-second heartbeat
            self._last_pong = time.time()
            while self._running:
                await asyncio.sleep(5)
                if not self._running:
                    break
                if self._client_channel and handshake_done.is_set():
                    self._send_on_channel(self._client_channel, {
                        "type": "PING",
                        "timestamp": time.time()
                    })
                    if time.time() - self._last_pong > 15.0:
                        log_debug("WEBRTC", "Client heartbeat timeout: streamer unreachable for >15s")
                        self.connection_status_changed.emit("disconnected", "🔴 Connection Lost (Streamer unreachable)")
                        self.stop_session()
                        break
        finally:
            if self._client_channel:
                try: self._client_channel.close()
                except Exception: pass
                self._client_channel = None
            if self._client_pc:
                try: await self._client_pc.close()
                except Exception: pass
                self._client_pc = None

    def send_command(self, action: str, target: str = "", value: Any = None):
        """Called by Client UI to send a sanitized command over the P2P DataChannel."""
        if not self._client_channel:
            return
        payload = {"action": action}
        if target:
            payload["target"] = target
        if value is not None:
            if action == "SET_VOLUME":
                payload["volume"] = value
            elif action == "TOGGLE_MUTE":
                payload["muted"] = value
            elif action == "SET_VISIBILITY":
                payload["visible"] = value
            elif action == "PLAY_SOUND":
                payload["clip_id"] = value

        self._send_on_channel(self._client_channel, payload)
