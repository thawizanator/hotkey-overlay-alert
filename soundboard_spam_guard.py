"""
Soundboard Spam Guard (SandMan Anti-Spam Troll Shield 🛡️) for Streamer Calyx
Enforces progressive rate-limiting and anti-spam deterrence on soundboard triggers
from stream directors, co-hosts, and dock users.

Escalation Ladder:
- Fast Click Threshold: Max 2 triggers within 3.0 seconds (or < 1.2s between clicks)
- Strike 1: 5-second cooldown + Warning Notice
- Strike 2: 10-second cooldown + Stern Warning Notice
- Strike 3: 30-second complete lockout + Automatic Loud Alarm Buzzer Punishment 🚨
- Decay: Strikes reset to 0 after 30 seconds of quiet behavior
"""

import time
from typing import Dict, Tuple, List, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class SoundboardSpamGuard(QObject):
    """
    Monitors soundboard trigger frequency per user/peer, prevents sound spamming,
    and deploys escalating punishments including warning cooldowns and punitive buzzer alarms.
    """
    warning_issued = pyqtSignal(str, int, float, str)  # user_id, strike_count, cooldown_sec, message
    alarm_triggered = pyqtSignal(str, float, str)      # user_id, cooldown_sec, message
    cooldown_ended = pyqtSignal(str)                   # user_id

    def __init__(self,
                 max_triggers_in_window: int = 2,
                 window_seconds: float = 3.0,
                 min_interval_seconds: float = 1.0,
                 parent=None):
        super().__init__(parent)
        self.max_triggers = max_triggers_in_window
        self.window_seconds = window_seconds
        self.min_interval = min_interval_seconds

        # Per-user tracking state:
        # user_id -> List of recent click timestamps
        self._click_history: Dict[str, List[float]] = {}
        # user_id -> strike count (0, 1, 2, 3+)
        self._strikes: Dict[str, int] = {}
        # user_id -> cooldown expiration timestamp
        self._cooldown_until: Dict[str, float] = {}
        # user_id -> timestamp of last violation (for strike decay)
        self._last_violation_time: Dict[str, float] = {}

        # Maintenance timer for strike decay and cooldown cleanup (checks every 1s)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._check_decay)
        self._timer.start()

    def check_trigger(self, user_id: str = "local_dock") -> Tuple[bool, str, float]:
        """
        Evaluates an attempted soundboard trigger.
        Returns: (allowed: bool, reason: str, remaining_cooldown: float)
        """
        now = time.time()
        uid = (user_id or "local_dock").strip().lower()

        # 1. Check if user is currently locked out in an active cooldown
        cooldown_end = self._cooldown_until.get(uid, 0.0)
        if now < cooldown_end:
            rem = cooldown_end - now
            strikes = self._strikes.get(uid, 1)
            msg = f"Cooldown active ({rem:.1f}s remaining). Slow down!"
            if strikes >= 3:
                msg = f"🚨 TROLL SHIELD LOCKED ({rem:.1f}s remaining) - Alarm Buzzer Sounded!"
            return False, msg, rem

        # 2. Retrieve click timestamps within sliding window
        history = self._click_history.get(uid, [])
        history = [t for t in history if now - t <= self.window_seconds]

        # 3. Check for spam: too fast (< min_interval) or too many in window
        is_spam = False
        if history and (now - history[-1]) < self.min_interval:
            is_spam = True
        elif len(history) >= self.max_triggers:
            is_spam = True

        if is_spam:
            # Increment strike count
            current_strikes = self._strikes.get(uid, 0) + 1
            self._strikes[uid] = current_strikes
            self._last_violation_time[uid] = now

            if current_strikes == 1:
                cooldown_dur = 5.0
                self._cooldown_until[uid] = now + cooldown_dur
                msg = "⚠️ Anti-Spam Warning: Slow down! You're clicking too fast. (Cooldown: 5s)"
                self.warning_issued.emit(uid, 1, cooldown_dur, msg)
                return False, msg, cooldown_dur

            elif current_strikes == 2:
                cooldown_dur = 10.0
                self._cooldown_until[uid] = now + cooldown_dur
                msg = "⚠️ Strike 2: Persistent spamming will trigger the Loud Alarm Buzzer! (Cooldown: 10s)"
                self.warning_issued.emit(uid, 2, cooldown_dur, msg)
                return False, msg, cooldown_dur

            else: # Strike 3 or higher: THE SANDMAN PUNISHMENT 🚨
                cooldown_dur = 30.0
                self._cooldown_until[uid] = now + cooldown_dur
                msg = "🚨 SPAM DETECTED: SandMan Troll Shield Activated! Loud Alarm Buzzer Sounded (Locked for 30s)."
                self.alarm_triggered.emit(uid, cooldown_dur, msg)
                return False, msg, cooldown_dur

        # Trigger is allowed: record timestamp
        history.append(now)
        self._click_history[uid] = history
        return True, "OK", 0.0

    def get_remaining_cooldown(self, user_id: str = "local_dock") -> float:
        """Returns remaining cooldown seconds for user, or 0.0 if not in cooldown."""
        uid = (user_id or "local_dock").strip().lower()
        now = time.time()
        end_t = self._cooldown_until.get(uid, 0.0)
        return max(0.0, end_t - now)

    def get_strike_count(self, user_id: str = "local_dock") -> int:
        """Returns active strike level for user (0 to 3+)."""
        uid = (user_id or "local_dock").strip().lower()
        return self._strikes.get(uid, 0)

    def is_locked_out(self, user_id: str = "local_dock") -> bool:
        """Returns True if user is currently under any cooldown/lockout."""
        return self.get_remaining_cooldown(user_id) > 0.0

    def reset_user(self, user_id: str = "local_dock"):
        """Manually clears all cooldowns and strikes for a user."""
        uid = (user_id or "local_dock").strip().lower()
        self._click_history.pop(uid, None)
        self._strikes.pop(uid, None)
        self._cooldown_until.pop(uid, None)
        self._last_violation_time.pop(uid, None)
        self.cooldown_ended.emit(uid)

    def _check_decay(self):
        """Gradually decays and resets strikes after 30 seconds of peaceful behavior."""
        now = time.time()
        decay_timeout = 30.0

        for uid, last_v in list(self._last_violation_time.items()):
            cooldown_end = self._cooldown_until.get(uid, 0.0)
            # If cooldown has ended and 30s have elapsed since last violation, reset strikes
            if now > cooldown_end and (now - last_v) > decay_timeout:
                had_strikes = self._strikes.get(uid, 0) > 0
                self._strikes[uid] = 0
                self._last_violation_time.pop(uid, None)
                if had_strikes:
                    self.cooldown_ended.emit(uid)
