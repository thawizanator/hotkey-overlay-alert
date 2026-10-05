import json
import urllib.request
import urllib.error
import urllib.parse
from PyQt6.QtCore import QThread, pyqtSignal

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
            print(msg)
            self.result_signal.emit(msg, False)
            return

        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}"
        }

        try:
            # 1. Resolve broadcaster ID (use cached if available, otherwise fetch via Helix)
            broadcaster_id = self.user_id
            if not broadcaster_id and self.channel_name:
                user_url = f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(self.channel_name.lower().strip())}"
                user_req = urllib.request.Request(user_url, headers=headers)
                with urllib.request.urlopen(user_req) as res:
                    user_data = json.loads(res.read().decode('utf-8'))
                    users = user_data.get("data", [])
                    if not users:
                        msg = f"Twitch channel '{self.channel_name}' not found."
                        print(msg)
                        self.result_signal.emit(msg, False)
                        return
                    broadcaster_id = users[0]["id"]

            if not broadcaster_id:
                msg = "Could not identify Twitch broadcaster account."
                print(msg)
                self.result_signal.emit(msg, False)
                return

            # Route A: Stream Marker (POST /helix/streams/markers)
            if "marker" in self.command.lower():
                url = "https://api.twitch.tv/helix/streams/markers"
                p_dict = {"user_id": str(broadcaster_id)}
                if self.argument:
                    p_dict["description"] = self.argument[:140]

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
                    msg = f"Stream Marker created successfully{pos_str}!"
                    print(msg)
                    self.result_signal.emit(msg, True)

            # Route B: Chat Announcement (POST /helix/chat/announcements)
            elif "announce" in self.command.lower():
                url = f"https://api.twitch.tv/helix/chat/announcements?broadcaster_id={broadcaster_id}&moderator_id={broadcaster_id}"
                color = "primary"
                for c in ["blue", "green", "orange", "purple"]:
                    if c in self.command.lower():
                        color = c
                        break

                p_dict = {
                    "message": self.argument[:500] if self.argument else "Attention Chat!",
                    "color": color
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(p_dict).encode('utf-8'),
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req):
                    msg = f"Chat Announcement ({color}) sent successfully."
                    print(msg)
                    self.result_signal.emit(msg, True)

            # Route C: Follow-card Shoutout (POST /helix/chat/shoutouts)
            elif "shoutout" in self.command.lower():
                target_name = self.argument.lower().strip().lstrip('@')
                if not target_name:
                    msg = "No target username specified for shoutout."
                    print(msg)
                    self.result_signal.emit(msg, False)
                    return

                t_url = f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(target_name)}"
                with urllib.request.urlopen(urllib.request.Request(t_url, headers=headers)) as t_res:
                    t_data = json.loads(t_res.read().decode('utf-8'))
                    targets = t_data.get("data", [])
                    if not targets:
                        msg = f"Target user '{target_name}' not found on Twitch."
                        print(msg)
                        self.result_signal.emit(msg, False)
                        return
                    target_id = targets[0]["id"]

                url = f"https://api.twitch.tv/helix/chat/shoutouts?from_broadcaster_id={broadcaster_id}&to_broadcaster_id={target_id}&moderator_id={broadcaster_id}"
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method="POST")):
                    msg = f"Shoutout sent for @{target_name}."
                    print(msg)
                    self.result_signal.emit(msg, True)

            # Route D: General chat message fallback (POST /helix/chat/messages)
            else:
                url = "https://api.twitch.tv/helix/chat/messages"
                chat_msg = self.argument if self.argument else self.command
                p_dict = {
                    "broadcaster_id": str(broadcaster_id),
                    "sender_id": str(broadcaster_id),
                    "message": chat_msg[:500]
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(p_dict).encode('utf-8'),
                    headers={**headers, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req):
                    msg = f"Twitch chat message sent: {chat_msg}"
                    print(msg)
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
                user_friendly = "Cannot create marker: Stream is not currently live."
            elif he.code == 401:
                user_friendly = "Twitch authorization token expired. Please re-link your Twitch account in Settings."
            elif he.code == 403:
                user_friendly = "Twitch permission denied. Ensure your account has broadcaster or moderator permissions."
            else:
                user_friendly = f"Twitch API Error ({he.code}): {err_msg}"

            print(user_friendly)
            self.result_signal.emit(user_friendly, False)

        except Exception as e:
            err_str = f"Twitch request error: {e}"
            print(err_str)
            self.result_signal.emit(err_str, False)
