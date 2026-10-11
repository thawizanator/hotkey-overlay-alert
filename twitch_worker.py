import json
import urllib.request
import urllib.error
import urllib.parse
from PyQt6.QtCore import QThread, pyqtSignal

BROADCASTER_ID_CACHE = {}
from debug_logger import log_debug

def safe_log(category, msg):
    try:
        log_debug(category, msg)
    except Exception:
        print(f"[{category}] {msg}")

class TwitchCommandWorker(QThread):
    """
    Executes non-blocking Twitch Helix REST API calls asynchronously.
    Maintains a clean separation between network operations and UI drawing.
    """
    result_signal = pyqtSignal(str, bool)  # (message, is_success)

    def __init__(self, command, argument, token, client_id, channel_name, user_id=None):
        super().__init__()
        self.command = command
        self.argument = argument
        self.token = token
        self.client_id = client_id
        self.channel_name = channel_name
        self.user_id = user_id

    def run(self):
        # Gracefully abort if authentication credentials are unassigned
        if not self.token or not self.client_id:
            msg = "Twitch credentials incomplete. Please link your Twitch account in Settings."
            safe_log("TWITCH_WORKER", msg)
            self.result_signal.emit(msg, False)
            return

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }

        try:
            moderator_id = str(self.user_id) if self.user_id else None
            broadcaster_id = None

            # 1. Resolve broadcaster ID from target channel
            target_channel = self.channel_name.lower().strip() if self.channel_name else ""
            if target_channel:
                if target_channel in BROADCASTER_ID_CACHE:
                    broadcaster_id = BROADCASTER_ID_CACHE[target_channel]
                    safe_log("TWITCH_WORKER", f"Found broadcaster_id {broadcaster_id} for '{target_channel}' in cache")
                else:
                    user_url = f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(target_channel)}"
                    user_req = urllib.request.Request(user_url, headers=headers)
                    with urllib.request.urlopen(user_req) as res:
                        user_data = json.loads(res.read().decode('utf-8'))
                        users = user_data.get("data", [])
                        if users:
                            broadcaster_id = str(users[0]["id"])
                            BROADCASTER_ID_CACHE[target_channel] = broadcaster_id
                            safe_log("TWITCH_WORKER", f"Resolved broadcaster_id {broadcaster_id} for '{target_channel}' via Helix")
                        else:
                            msg = f"Twitch channel '{self.channel_name}' not found."
                            safe_log("TWITCH_WORKER", msg)
                            self.result_signal.emit(msg, False)
                            return

            # Fallbacks: if no separate channel ID resolved, default to authenticated user
            if not broadcaster_id:
                broadcaster_id = moderator_id
            if not moderator_id:
                moderator_id = broadcaster_id

            if not broadcaster_id:
                msg = "Could not identify Twitch broadcaster account."
                safe_log("TWITCH_WORKER", msg)
                self.result_signal.emit(msg, False)
                return

            safe_log("TWITCH_WORKER", f"Invoking command='{self.command}', arg='{self.argument}' | broadcaster_id={broadcaster_id}, moderator_id={moderator_id}")

            # Route A: Stream Marker (POST /helix/streams/markers)
            if "marker" in self.command.lower():
                url = "https://api.twitch.tv/helix/streams/markers"
                desc = self.argument.strip() if self.argument else (self.channel_name or "streamer")
                p_dict = {
                    "user_id": str(broadcaster_id),
                    "description": desc[:140]
                }
                safe_log("TWITCH_WORKER", f"POST {url} with body={p_dict}")

                req = urllib.request.Request(
                    url,
                    data=json.dumps(p_dict).encode('utf-8'),
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req) as res:
                    marker_data = json.loads(res.read().decode('utf-8'))
                    marker_info = marker_data.get("data", [{}])[0]
                    pos = marker_info.get("position_seconds", "")
                    pos_str = f" at {pos}s" if pos != "" else ""
                    msg = f"Stream Marker created successfully{pos_str} ({desc})!"
                    safe_log("TWITCH_WORKER", f"Success: {msg}")
                    self.result_signal.emit(msg, True)

            # Route B: Chat Announcement (POST /helix/chat/announcements)
            elif "announce" in self.command.lower():
                url = f"https://api.twitch.tv/helix/chat/announcements?broadcaster_id={broadcaster_id}&moderator_id={moderator_id}"
                color = "primary"
                for c in ["blue", "green", "orange", "purple"]:
                    if c in self.command.lower():
                        color = c
                        break

                p_dict = {
                    "message": self.argument[:500] if self.argument else "Attention Chat!",
                    "color": color
                }
                safe_log("TWITCH_WORKER", f"POST {url} with body={p_dict}")
                req = urllib.request.Request(
                    url,
                    data=json.dumps(p_dict).encode('utf-8'),
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req):
                    msg = f"Chat Announcement ({color}) sent successfully."
                    safe_log("TWITCH_WORKER", f"Success: {msg}")
                    self.result_signal.emit(msg, True)

            # Route C: Follow-card Shoutout (POST /helix/chat/shoutouts)
            elif "shoutout" in self.command.lower():
                target_name = self.argument.lower().strip().lstrip('@')
                if not target_name:
                    msg = "No target username specified for shoutout."
                    safe_log("TWITCH_WORKER", msg)
                    self.result_signal.emit(msg, False)
                    return

                t_url = f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(target_name)}"
                with urllib.request.urlopen(urllib.request.Request(t_url, headers=headers)) as t_res:
                    t_data = json.loads(t_res.read().decode('utf-8'))
                    targets = t_data.get("data", [])
                    if not targets:
                        msg = f"Target user '{target_name}' not found on Twitch."
                        safe_log("TWITCH_WORKER", msg)
                        self.result_signal.emit(msg, False)
                        return
                    target_id = targets[0]["id"]

                url = f"https://api.twitch.tv/helix/chat/shoutouts?from_broadcaster_id={broadcaster_id}&to_broadcaster_id={target_id}&moderator_id={moderator_id}"
                safe_log("TWITCH_WORKER", f"POST {url} for target={target_name} ({target_id})")
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method="POST")):
                    msg = f"Shoutout sent for @{target_name}."
                    safe_log("TWITCH_WORKER", f"Success: {msg}")
                    self.result_signal.emit(msg, True)

            # Route D: General chat message fallback (POST /helix/chat/messages)
            else:
                url = "https://api.twitch.tv/helix/chat/messages"
                chat_msg = self.argument if self.argument else self.command
                p_dict = {
                    "broadcaster_id": str(broadcaster_id),
                    "sender_id": str(moderator_id),
                    "message": chat_msg[:500]
                }
                safe_log("TWITCH_WORKER", f"POST {url} with body={p_dict}")
                req = urllib.request.Request(
                    url,
                    data=json.dumps(p_dict).encode('utf-8'),
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req):
                    msg = f"Twitch chat message sent: {chat_msg}"
                    safe_log("TWITCH_WORKER", f"Success: {msg}")
                    self.result_signal.emit(msg, True)

        except urllib.error.HTTPError as he:
            err_msg = str(he)
            try:
                raw_body = he.read().decode('utf-8', errors='ignore')
                body_json = json.loads(raw_body)
                if "message" in body_json:
                    err_msg = body_json["message"]
            except Exception:
                pass

            if he.code == 404 and "marker" in self.command.lower():
                user_friendly = "Cannot create marker: Stream is not currently live (broadcaster is offline)."
            elif he.code == 401:
                user_friendly = "Twitch authorization token expired. Please re-link your Twitch account in Settings."
            elif he.code == 403:
                user_friendly = f"Twitch permission denied (403): Your account must be a Moderator or Broadcaster in '{self.channel_name}'."
            elif he.code == 429:
                if "announce" in self.command.lower():
                    user_friendly = "Twitch Announcement Cooldown: Twitch limits announcements to once every 2 minutes. Please wait before sending another."
                elif "shoutout" in self.command.lower():
                    user_friendly = "Twitch Shoutout Cooldown: Twitch limits shoutouts to once every 2 minutes per broadcaster."
                else:
                    user_friendly = f"Twitch Rate Limit (429): {err_msg}. Please wait a moment before trying again."
            else:
                user_friendly = f"Twitch API Error ({he.code}): {err_msg}"

            safe_log("TWITCH_WORKER", f"HTTPError {he.code}: {err_msg} | User notice: {user_friendly}")
            self.result_signal.emit(user_friendly, False)

        except Exception as e:
            err_str = f"Twitch request error: {e}"
            safe_log("TWITCH_WORKER", f"Exception: {e}")
            self.result_signal.emit(err_str, False)
