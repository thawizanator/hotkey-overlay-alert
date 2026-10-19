import hmac
import hashlib
import secrets
import time
from typing import Optional, Tuple, List, Dict, Any
from debug_logger import log_debug

class PasskeyManager:
    """
    Generates, hashes, and validates cryptographically secure pairing passkeys
    for remote Stream Director access.
    """
    @staticmethod
    def generate_passkey() -> Tuple[str, str, str]:
        """
        Generates a human-friendly, cryptographically random passkey and salt.
        Returns: (raw_passkey, salt, sha256_hash)
        Example raw_passkey: 'DIR-8824-XK9P'
        """
        alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # Excludes ambiguous characters (0, O, 1, I)
        part1 = "".join(secrets.choice(alphabet) for _ in range(4))
        part2 = "".join(secrets.choice(alphabet) for _ in range(4))
        raw_passkey = f"DIR-{part1}-{part2}"

        salt = secrets.token_hex(16)
        hash_val = PasskeyManager.hash_passkey(raw_passkey, salt)
        return raw_passkey, salt, hash_val

    @staticmethod
    def hash_passkey(raw_passkey: str, salt: str) -> str:
        """Computes salted SHA-256 hash of a passkey, normalized for spaces and hyphens."""
        clean_key = raw_passkey.strip().upper().replace(" ", "").replace("-", "")
        data = f"{salt}:{clean_key}".encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def verify_passkey(provided_key: str, salt: str, expected_hash: str) -> bool:
        """Constant-time verification of a provided passkey against stored hash."""
        if not provided_key or not salt or not expected_hash:
            return False
        computed = PasskeyManager.hash_passkey(provided_key, salt)
        return hmac.compare_digest(computed, expected_hash)


class BouncerValidator:
    """
    The Bouncer: strictly validates and scopes all incoming remote director commands.
    Ensures remote users can ONLY interact with pre-approved scenes and audio channels,
    and blocks unauthorized or malformed requests.
    """
    def __init__(self, allowed_twitch_user: str = "", rate_limit_per_sec: int = 10):
        self.allowed_twitch_user = allowed_twitch_user.lower().strip()
        self.rate_limit_per_sec = rate_limit_per_sec
        self._peer_request_times: Dict[str, List[float]] = {}
        self.active_scenes_whitelist: List[str] = []
        self.active_audio_whitelist: List[str] = []

    def set_whitelists(self, scenes: List[dict], audio_toggles: List[dict], faders: Optional[List[dict]] = None):
        """Updates the list of approved scene names and audio names."""
        self.active_scenes_whitelist = [
            s.get("name", "").strip().lower() for s in scenes if s.get("name")
        ]
        audio_names = [
            a.get("name", "").strip().lower() for a in audio_toggles if a.get("name")
        ]
        if faders:
            for f in faders:
                fn = f.get("name", "").strip().lower()
                if fn and fn not in audio_names:
                    audio_names.append(fn)
        self.active_audio_whitelist = audio_names

    def verify_identity(self, twitch_username: str, twitch_user_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Checks if the connecting remote user's Twitch identity is authorized.
        If allowed_twitch_user is empty or '*', any user with a valid passkey is accepted.
        """
        clean_user = (twitch_username or "").lower().strip().lstrip("@")
        if not self.allowed_twitch_user or self.allowed_twitch_user == "*":
            return True, f"Open access with valid passkey (User: @{clean_user or 'anonymous'})"

        expected = self.allowed_twitch_user.lstrip("@")
        if clean_user == expected:
            return True, f"Twitch identity verified: @{clean_user}"
        return False, f"Twitch user @{clean_user} is not authorized (Expected: @{expected})"

    def _check_rate_limit(self, peer_id: str) -> bool:
        """Enforces sliding-window rate limit per peer."""
        now = time.time()
        timestamps = self._peer_request_times.get(peer_id, [])
        # Keep only timestamps in the last second
        timestamps = [t for t in timestamps if now - t < 1.0]
        if len(timestamps) >= self.rate_limit_per_sec:
            return False
        timestamps.append(now)
        self._peer_request_times[peer_id] = timestamps
        return True

    def validate_command(self, peer_id: str, payload: dict) -> Tuple[bool, str, Optional[dict]]:
        """
        Strictly sanitizes and validates an incoming command against allowed schema and whitelists.
        Returns: (is_valid, reason, sanitized_command)
        """
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object", None

        if not self._check_rate_limit(peer_id):
            log_debug("BOUNCER", f"Rate limit exceeded for peer: {peer_id}")
            return False, "Rate limit exceeded. Please slow down.", None

        action = payload.get("action", "")
        if not isinstance(action, str):
            return False, "Action must be a string", None

        action = action.upper().strip()
        allowed_actions = {"SWITCH_SCENE", "TOGGLE_MUTE", "SET_VOLUME", "REQUEST_STATE", "PING"}
        if action not in allowed_actions:
            log_debug("BOUNCER", f"Unauthorized action rejected: '{action}' from {peer_id}")
            return False, f"Action '{action}' is not allowed", None

        # REQUEST_STATE and PING require no target
        if action in {"REQUEST_STATE", "PING"}:
            return True, "Valid", {"action": action}

        target = payload.get("target", "")
        if not isinstance(target, str) or not target.strip():
            return False, "Target name is required", None
        clean_target = target.strip()
        lower_target = clean_target.lower()

        # Validate SWITCH_SCENE against configured scenes whitelist
        if action == "SWITCH_SCENE":
            if lower_target not in self.active_scenes_whitelist:
                log_debug("BOUNCER", f"Rejected scene switch to non-whitelisted scene: '{clean_target}'")
                return False, f"Scene '{clean_target}' is not in the approved scenes list", None
            return True, "Valid", {"action": action, "target": clean_target}

        # Validate TOGGLE_MUTE against configured audio whitelist
        elif action == "TOGGLE_MUTE":
            if lower_target not in self.active_audio_whitelist:
                log_debug("BOUNCER", f"Rejected mute toggle for non-whitelisted audio: '{clean_target}'")
                return False, f"Audio source '{clean_target}' is not in the approved audio list", None
            mute_state = payload.get("muted")
            sanitized = {"action": action, "target": clean_target}
            if mute_state is not None:
                sanitized["muted"] = bool(mute_state)
            return True, "Valid", sanitized

        # Validate SET_VOLUME against configured audio whitelist and clamp range 0.0 - 1.0
        elif action == "SET_VOLUME":
            if lower_target not in self.active_audio_whitelist:
                log_debug("BOUNCER", f"Rejected volume change for non-whitelisted audio: '{clean_target}'")
                return False, f"Audio source '{clean_target}' is not in the approved audio list", None
            try:
                volume = float(payload.get("volume", 1.0))
                volume = max(0.0, min(1.0, volume))  # Clamp strictly to 0.0 - 1.0
            except (ValueError, TypeError):
                return False, "Volume must be a numeric value between 0.0 and 1.0", None
            return True, "Valid", {"action": action, "target": clean_target, "volume": volume}

        return False, "Unknown command format", None
