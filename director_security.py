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
    Supports granular Windows-style per-user permission profiles.
    """
    def __init__(self, allowed_twitch_user: str = "", rate_limit_per_sec: int = 10, user_permissions: Optional[Dict[str, dict]] = None):
        self.allowed_twitch_user = allowed_twitch_user.lower().strip()
        self.rate_limit_per_sec = rate_limit_per_sec
        self._peer_request_times: Dict[str, List[float]] = {}
        self.active_scenes_whitelist: List[str] = []
        self.active_audio_whitelist: List[str] = []
        self.user_permissions: Dict[str, dict] = user_permissions or {}
        self._peer_usernames: Dict[str, str] = {}

    def register_peer(self, peer_id: str, twitch_username: str):
        """Associates a connected peer with their verified Twitch username."""
        clean_user = (twitch_username or "").lower().strip().lstrip("@")
        self._peer_usernames[peer_id] = clean_user

    def unregister_peer(self, peer_id: str):
        """Removes a peer association upon disconnect."""
        self._peer_usernames.pop(peer_id, None)

    def set_user_permissions(self, permissions_dict: Dict[str, dict]):
        """Updates the dictionary of user-specific granular permissions."""
        self.user_permissions = permissions_dict or {}

    def get_user_permissions(self, twitch_username: str) -> Optional[dict]:
        clean_user = (twitch_username or "").lower().strip().lstrip("@")
        return self.user_permissions.get(clean_user)

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
        If user_permissions is defined with specific users, checks if the user is in the list.
        Otherwise falls back to allowed_twitch_user.
        """
        clean_user = (twitch_username or "").lower().strip().lstrip("@")
        if self.user_permissions:
            if clean_user in self.user_permissions:
                return True, f"Twitch co-host verified: @{clean_user}"
            expected = self.allowed_twitch_user.lstrip("@")
            if expected and expected != "*" and clean_user == expected:
                return True, f"Twitch co-host verified: @{clean_user}"
            return False, f"Twitch user @{clean_user} is not in the authorized co-host list"

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
        Strictly sanitizes and validates an incoming command against allowed schema,
        global whitelists, and per-user granular permissions.
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

        # Check granular per-user permissions
        username = self._peer_usernames.get(peer_id, "")
        user_perm = self.user_permissions.get(username, {}) if username else {}
        full_control = user_perm.get("full_control", False) if user_perm else (not self.user_permissions)

        # 1. Validate SWITCH_SCENE
        if action == "SWITCH_SCENE":
            if lower_target not in self.active_scenes_whitelist:
                log_debug("BOUNCER", f"Rejected scene switch to non-whitelisted scene: '{clean_target}'")
                return False, f"Scene '{clean_target}' is not in the approved scenes list", None

            if not full_control:
                allowed_scenes = [s.lower() for s in user_perm.get("allowed_scenes", [])]
                if lower_target not in allowed_scenes:
                    log_debug("BOUNCER", f"Permission denied: @{username} is not permitted to switch scene '{clean_target}'")
                    return False, f"Permission denied: user @{username} cannot switch to scene '{clean_target}'", None

            return True, "Valid", {"action": action, "target": clean_target}

        # 2. Validate TOGGLE_MUTE
        elif action == "TOGGLE_MUTE":
            if lower_target not in self.active_audio_whitelist:
                log_debug("BOUNCER", f"Rejected mute toggle for non-whitelisted audio: '{clean_target}'")
                return False, f"Audio source '{clean_target}' is not in the approved audio list", None

            if not full_control:
                allowed_mutes = [m.lower() for m in user_perm.get("allowed_audio_mutes", [])]
                if lower_target not in allowed_mutes:
                    log_debug("BOUNCER", f"Permission denied: @{username} is not permitted to mute '{clean_target}'")
                    return False, f"Permission denied: user @{username} cannot mute/unmute '{clean_target}'", None

            mute_state = payload.get("muted")
            sanitized = {"action": action, "target": clean_target}
            if mute_state is not None:
                sanitized["muted"] = bool(mute_state)
            return True, "Valid", sanitized

        # 3. Validate SET_VOLUME
        elif action == "SET_VOLUME":
            if lower_target not in self.active_audio_whitelist:
                log_debug("BOUNCER", f"Rejected volume change for non-whitelisted audio: '{clean_target}'")
                return False, f"Audio source '{clean_target}' is not in the approved audio list", None

            if not full_control:
                allowed_vols = [v.lower() for v in user_perm.get("allowed_audio_volume", [])]
                if lower_target not in allowed_vols:
                    log_debug("BOUNCER", f"Permission denied: @{username} is not permitted to adjust volume for '{clean_target}'")
                    return False, f"Permission denied: user @{username} cannot adjust volume for '{clean_target}'", None

            try:
                volume = float(payload.get("volume", 1.0))
                volume = max(0.0, min(1.0, volume))  # Clamp strictly to 0.0 - 1.0
            except (ValueError, TypeError):
                return False, "Volume must be a numeric value between 0.0 and 1.0", None
            return True, "Valid", {"action": action, "target": clean_target, "volume": volume}

        return False, "Unknown command format", None
