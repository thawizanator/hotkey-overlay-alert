import os
import sys
import random
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

APP_DIR = os.path.join(os.environ.get("APPDATA", ""), "StreamerCalyx")
DEFAULT_CYCLER_FILE = os.path.join(APP_DIR, "obs_text_cycler.txt")

SAMPLE_TRIVIA = [
    {"q": "What was Mario's original name when he debuted in Donkey Kong (1981)?", "a": "Jumpman"},
    {"q": "What was Twitch originally called before rebranding in 2011?", "a": "Justin.tv (Gaming section)"},
    {"q": "What was the first commercial video game ever released (1971)?", "a": "Computer Space (by Nolan Bushnell & Ted Dabney)"},
    {"q": "In The Legend of Zelda (NES), what iconic phrase does the Old Man say when giving you the wooden sword?", "a": "\"It's dangerous to go alone! Take this.\""},
    {"q": "What year was the original PlayStation (PS1) released in Japan?", "a": "December 3, 1994"},
    {"q": "What is the highest-selling video game of all time?", "a": "Minecraft (over 300 million copies sold)"},
    {"q": "What is the name of Master Chief's AI companion in Halo?", "a": "Cortana"},
    {"q": "Which game popularised the famous Konami Code (↑↑↓↓←→←→BA)?", "a": "Gradius (1986) on NES (famous in Contra)"},
    {"q": "What was the very first Pokémon ever designed?", "a": "Rhydon (Index number 001 in Gen 1 data)"},
    {"q": "What was the original release year of World of Warcraft?", "a": "November 23, 2004"}
]

SAMPLE_SOCIALS = [
    {"q": "Welcome to the stream!", "a": "Enjoying the broadcast? Make sure to drop a follow to be notified when we go live!"},
    {"q": "Join our Community Discord!", "a": "discord.gg/thawizanator - Hang out with us off-stream!"},
    {"q": "Stream Schedule", "a": "Live every Monday, Wednesday, & Friday at 7 PM EST!"},
    {"q": "Chat Rules", "a": "Be respectful to others, no self-promo, and have fun!"}
]

class CyclerMode:
    SEQUENTIAL = "sequential"
    SHUFFLE = "shuffle"
    TRIVIA_QA = "trivia_qa"

class CyclerState:
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"

class CyclerEngine(QObject):
    """Core rotating text engine and OBS file broadcaster."""
    # display_text, state, current_index, total_items, seconds_remaining, subphase
    tick = pyqtSignal(str, str, int, int, int, str)
    state_changed = pyqtSignal(str)
    items_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = CyclerMode.TRIVIA_QA
        self.state = CyclerState.STOPPED

        # Rotation timing
        self.interval_seconds = 20         # standard rotation interval (or Question duration)
        self.trivia_answer_seconds = 8      # how long the answer stays visible before advancing
        self.seconds_remaining = self.interval_seconds

        # Items list: list of dicts {"q": str, "a": str}
        # If it's a simple text line, "a" may be empty or match "q"
        self.items = [dict(item) for item in SAMPLE_TRIVIA]
        self.current_index = 0
        self.subphase = "QUESTION"  # "QUESTION" or "ANSWER"

        # Shuffle tracking to prevent immediate repeats
        self._shuffle_history = []

        # Formatting & OBS output
        self.prefix = ""
        self.suffix = ""
        self.write_to_file = True
        self.clear_file_on_stop = False
        self.custom_file_path = DEFAULT_CYCLER_FILE

        # Background timer (ticks every 1000ms)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)

        try:
            os.makedirs(APP_DIR, exist_ok=True)
        except Exception:
            pass

    def start(self):
        if self.state == CyclerState.RUNNING:
            return
        if not self.items:
            return
        self.state = CyclerState.RUNNING
        self.timer.start()
        self.state_changed.emit(self.state)
        self._publish_current_state()

    def pause(self):
        if self.state != CyclerState.RUNNING:
            return
        self.state = CyclerState.PAUSED
        self.timer.stop()
        self.state_changed.emit(self.state)
        self._publish_current_state()

    def toggle_start_pause(self):
        if self.state == CyclerState.RUNNING:
            self.pause()
        else:
            self.start()

    def stop(self):
        self.timer.stop()
        self.state = CyclerState.STOPPED
        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self.state_changed.emit(self.state)

        if self.clear_file_on_stop:
            self._write_file("")
            disp = self._get_current_display()
            self.tick.emit(disp, self.state, self.current_index, len(self.items), self.seconds_remaining, self.subphase)
        else:
            self._publish_current_state()

    def reset_to_first(self):
        self.current_index = 0
        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self._publish_current_state()

    def next_item(self):
        if not self.items:
            return
        if self.mode == CyclerMode.SHUFFLE:
            self._pick_next_shuffle_index()
        else:
            self.current_index = (self.current_index + 1) % len(self.items)

        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self._publish_current_state()

    def prev_item(self):
        if not self.items:
            return
        if self.mode == CyclerMode.SHUFFLE:
            self._pick_next_shuffle_index()
        else:
            self.current_index = (self.current_index - 1) % len(self.items)

        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self._publish_current_state()

    def set_mode(self, mode_str: str):
        if self.mode == mode_str:
            return
        self.mode = mode_str
        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self._publish_current_state()

    def _pick_next_shuffle_index(self):
        n = len(self.items)
        if n <= 1:
            self.current_index = 0
            return
        candidates = [i for i in range(n) if i != self.current_index]
        self.current_index = random.choice(candidates)

    def _on_tick(self):
        if self.state != CyclerState.RUNNING:
            return
        if not self.items:
            return

        self.seconds_remaining -= 1

        if self.mode == CyclerMode.TRIVIA_QA:
            current_item = self.items[self.current_index]
            has_answer = bool(current_item.get("a", "").strip()) and (current_item.get("a", "").strip() != current_item.get("q", "").strip())

            if self.seconds_remaining <= 0:
                if self.subphase == "QUESTION" and has_answer:
                    # Switch to Answer phase
                    self.subphase = "ANSWER"
                    self.seconds_remaining = max(1, self.trivia_answer_seconds)
                else:
                    # Advance to next Question
                    self.next_item()
                    return
        else:
            # Sequential or Shuffle mode
            if self.seconds_remaining <= 0:
                self.next_item()
                return

        self._publish_current_state()

    def _get_current_display(self) -> str:
        if not self.items:
            return "No lines configured"
        if self.current_index >= len(self.items):
            self.current_index = 0

        item = self.items[self.current_index]
        q = item.get("q", "").strip()
        a = item.get("a", "").strip()

        if self.mode == CyclerMode.TRIVIA_QA:
            if self.subphase == "ANSWER" and a:
                return f"Answer: {a}"
            return q or a

        elif self.mode == CyclerMode.SEQUENTIAL or self.mode == CyclerMode.SHUFFLE:
            if a and a != q:
                return f"{q} - {a}"
            return q or a

        return q

    def _publish_current_state(self):
        disp = self._get_current_display()
        full_output = f"{self.prefix}{disp}{self.suffix}".strip()
        if self.write_to_file and self.state != CyclerState.STOPPED:
            self._write_file(full_output)
        elif self.write_to_file and self.state == CyclerState.STOPPED and not self.clear_file_on_stop:
            self._write_file(full_output)

        tot = len(self.items)
        idx = self.current_index if tot > 0 else 0
        self.tick.emit(disp, self.state, idx, tot, self.seconds_remaining, self.subphase)

    def _write_file(self, content: str):
        target = self.custom_file_path or DEFAULT_CYCLER_FILE
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

    def add_item(self, q_text: str, a_text: str = ""):
        q_clean = q_text.strip()
        a_clean = a_text.strip()
        if not q_clean and not a_clean:
            return
        self.items.append({"q": q_clean, "a": a_clean})
        self.items_changed.emit()
        self._publish_current_state()

    def update_item(self, index: int, q_text: str, a_text: str = ""):
        if 0 <= index < len(self.items):
            self.items[index] = {"q": q_text.strip(), "a": a_text.strip()}
            self.items_changed.emit()
            self._publish_current_state()

    def remove_item(self, index: int):
        if 0 <= index < len(self.items):
            del self.items[index]
            if self.current_index >= len(self.items):
                self.current_index = max(0, len(self.items) - 1)
            self.items_changed.emit()
            self._publish_current_state()

    def move_item(self, old_index: int, new_index: int):
        if 0 <= old_index < len(self.items) and 0 <= new_index < len(self.items):
            item = self.items.pop(old_index)
            self.items.insert(new_index, item)
            if self.current_index == old_index:
                self.current_index = new_index
            self.items_changed.emit()
            self._publish_current_state()

    def load_sample_trivia(self):
        self.items = [dict(item) for item in SAMPLE_TRIVIA]
        self.current_index = 0
        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self.items_changed.emit()
        self._publish_current_state()

    def load_sample_socials(self):
        self.items = [dict(item) for item in SAMPLE_SOCIALS]
        self.current_index = 0
        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self.items_changed.emit()
        self._publish_current_state()

    def clear_all_items(self):
        self.items = []
        self.current_index = 0
        self.subphase = "QUESTION"
        self.seconds_remaining = self.interval_seconds
        self.items_changed.emit()
        self._publish_current_state()

    def export_settings(self) -> dict:
        return {
            "mode": self.mode,
            "interval_seconds": self.interval_seconds,
            "trivia_answer_seconds": self.trivia_answer_seconds,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "write_to_file": self.write_to_file,
            "clear_file_on_stop": self.clear_file_on_stop,
            "items": [dict(it) for it in self.items]
        }

    def import_settings(self, d: dict):
        if not isinstance(d, dict):
            return
        self.mode = d.get("mode", self.mode)
        self.interval_seconds = max(3, int(d.get("interval_seconds", self.interval_seconds)))
        self.trivia_answer_seconds = max(2, int(d.get("trivia_answer_seconds", self.trivia_answer_seconds)))
        self.prefix = str(d.get("prefix", self.prefix))
        self.suffix = str(d.get("suffix", self.suffix))
        self.write_to_file = bool(d.get("write_to_file", self.write_to_file))
        self.clear_file_on_stop = bool(d.get("clear_file_on_stop", self.clear_file_on_stop))

        loaded_items = d.get("items")
        if isinstance(loaded_items, list):
            valid_items = []
            for it in loaded_items:
                if isinstance(it, dict) and "q" in it:
                    valid_items.append({"q": str(it.get("q", "")), "a": str(it.get("a", ""))})
                elif isinstance(it, str):
                    if "|" in it:
                        parts = it.split("|", 1)
                        valid_items.append({"q": parts[0].strip(), "a": parts[1].strip()})
                    else:
                        valid_items.append({"q": it.strip(), "a": ""})
            if valid_items:
                self.items = valid_items

        self.seconds_remaining = self.interval_seconds
        self.items_changed.emit()
        self._publish_current_state()
