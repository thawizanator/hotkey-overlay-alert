import os
import sys
import subprocess

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QLineEdit, QCheckBox, QGroupBox,
    QListWidget, QListWidgetItem, QFileDialog, QMessageBox,
    QFrame, QDialog, QDialogButtonBox, QFormLayout, QTabWidget
)
from PyQt6.QtGui import QGuiApplication, QFont

from cycler_engine import CyclerEngine, CyclerMode, CyclerState, DEFAULT_CYCLER_FILE
import theme_manager

class EditItemDialog(QDialog):
    """Dialog to edit an individual question/answer or text line."""
    def __init__(self, parent, q_val: str, a_val: str):
        super().__init__(parent)
        self.setWindowTitle("Edit Text / Trivia Item")
        self.setFixedWidth(440)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        self.txt_q = QLineEdit(q_val)
        self.txt_a = QLineEdit(a_val)
        self.txt_a.setPlaceholderText("Optional answer for Trivia mode")

        form.addRow("Text / Question:", self.txt_q)
        form.addRow("Answer (optional):", self.txt_a)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_values(self):
        return self.txt_q.text().strip(), self.txt_a.text().strip()


class CyclerTab(QWidget):
    """Interactive Stream Note & Trivia Cycler with real-time OBS file sync."""
    def __init__(self, main_win, engine: CyclerEngine):
        super().__init__()
        self.main_win = main_win
        self.engine = engine

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(12, 4, 12, 4)

        # ---------------- 1. LIVE DIGITAL HUD DISPLAY BANNER ----------------
        self.card_display = QFrame()
        self.card_display.setObjectName("cyclerDisplayCard")
        self.card_display.setStyleSheet("""
            QFrame#cyclerDisplayCard {
                background-color: #18181b;
                border: 1px solid #2d2d30;
                border-radius: 8px;
                padding: 4px 10px;
            }
        """)
        display_lay = QVBoxLayout(self.card_display)
        display_lay.setSpacing(3)
        display_lay.setContentsMargins(6, 4, 6, 4)

        # Top row: mode indicator & status pill
        top_status_row = QHBoxLayout()
        self.lbl_mode_badge = QLabel("TRIVIA Q&A MODE")
        self.lbl_mode_badge.setStyleSheet("font-size: 11px; font-weight: bold; color: #a1a1aa;")
        top_status_row.addWidget(self.lbl_mode_badge, 1)

        self.lbl_subphase_badge = QLabel("[QUESTION]")
        self.lbl_subphase_badge.setStyleSheet("""
            background-color: #2e1065;
            color: #c084fc;
            font-size: 10px;
            font-weight: bold;
            padding: 1px 8px;
            border-radius: 4px;
        """)
        top_status_row.addWidget(self.lbl_subphase_badge)

        self.lbl_status_pill = QLabel("■ STOPPED")
        self.lbl_status_pill.setStyleSheet("""
            background-color: #3f3f46;
            color: #ffffff;
            font-size: 11px;
            font-weight: bold;
            padding: 2px 10px;
            border-radius: 10px;
        """)
        top_status_row.addWidget(self.lbl_status_pill)
        display_lay.addLayout(top_status_row)

        # Live Broadcasting Text Display
        self.lbl_text_display = QLabel("What was Mario's original name when he debuted in Donkey Kong (1981)?")
        self.lbl_text_display.setWordWrap(True)
        self.lbl_text_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_text_display.setStyleSheet("""
            font-family: 'Segoe UI', sans-serif;
            font-size: 14px;
            font-weight: 600;
            color: #9146ff;
            margin: 2px 0px;
            min-height: 34px;
        """)
        display_lay.addWidget(self.lbl_text_display)

        # Sub-status indicator (e.g. Line 1 of 10 • Next in: 20s)
        self.lbl_meta_info = QLabel("Item 1 of 10 • Next rotation in 20s")
        self.lbl_meta_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_meta_info.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        display_lay.addWidget(self.lbl_meta_info)

        # Live Action Buttons Row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)

        self.btn_toggle = QPushButton("▶ Start")
        self.btn_toggle.setObjectName("btn_cycler_start")
        self.btn_toggle.setStyleSheet("""
            QPushButton#btn_cycler_start {
                background-color: #9146ff;
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #772ce8;
                border-radius: 4px;
                padding: 3px 14px;
                min-height: 20px;
            }
            QPushButton#btn_cycler_start:hover {
                background-color: #772ce8;
            }
        """)
        self.btn_toggle.clicked.connect(self._toggle_start_pause)
        ctrl_layout.addWidget(self.btn_toggle)

        self.btn_prev = QPushButton("⏮ Prev")
        self.btn_prev.setFixedWidth(65)
        self.btn_prev.clicked.connect(self._on_prev_clicked)
        ctrl_layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("⏭ Next")
        self.btn_next.setFixedWidth(65)
        self.btn_next.clicked.connect(self._on_next_clicked)
        ctrl_layout.addWidget(self.btn_next)

        self.btn_reset = QPushButton("↺ Restart")
        self.btn_reset.setFixedWidth(70)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        ctrl_layout.addWidget(self.btn_reset)

        ctrl_layout.addStretch()
        display_lay.addLayout(ctrl_layout)
        main_layout.addWidget(self.card_display)

        # ---------------- 2. ITEM LIST & MANAGER ----------------
        grp_list = QGroupBox("Text Lines && Trivia Collection")
        grp_list_lay = QVBoxLayout(grp_list)
        grp_list_lay.setSpacing(3)
        grp_list_lay.setContentsMargins(10, 4, 10, 4)

        # Quick Add Row
        add_box = QHBoxLayout()
        add_box.setSpacing(6)
        self.txt_add_q = QLineEdit()
        self.txt_add_q.setPlaceholderText("Add Question or Text Line...")
        self.txt_add_q.returnPressed.connect(self._on_add_clicked)
        add_box.addWidget(self.txt_add_q, 3)

        self.txt_add_a = QLineEdit()
        self.txt_add_a.setPlaceholderText("Answer (optional)...")
        self.txt_add_a.returnPressed.connect(self._on_add_clicked)
        add_box.addWidget(self.txt_add_a, 2)

        self.btn_add = QPushButton("+ Add")
        self.btn_add.setMinimumWidth(55)
        self.btn_add.clicked.connect(self._on_add_clicked)
        add_box.addWidget(self.btn_add)
        grp_list_lay.addLayout(add_box)

        # Interactive List Widget
        self.list_items = QListWidget()
        self.list_items.setObjectName("cyclerList")
        self.list_items.setFixedHeight(100)
        self.list_items.itemDoubleClicked.connect(self._on_item_double_clicked)
        grp_list_lay.addWidget(self.list_items)

        # Item Action Toolbar - Row 1 (Selection & File IO)
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(6)

        self.btn_move_up = QPushButton("▲ Up")
        self.btn_move_up.clicked.connect(self._on_move_up)
        tb_layout.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("▼ Down")
        self.btn_move_down.clicked.connect(self._on_move_down)
        tb_layout.addWidget(self.btn_move_down)

        self.btn_edit = QPushButton("✏️ Edit")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        tb_layout.addWidget(self.btn_edit)

        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        tb_layout.addWidget(self.btn_delete)

        tb_layout.addStretch()

        self.btn_import = QPushButton("📂 Import .txt")
        self.btn_import.clicked.connect(self._on_import_txt)
        tb_layout.addWidget(self.btn_import)

        self.btn_export = QPushButton("💾 Export .txt")
        self.btn_export.clicked.connect(self._on_export_txt)
        tb_layout.addWidget(self.btn_export)
        grp_list_lay.addLayout(tb_layout)

        # Item Action Toolbar - Row 2 (Quick Preset Packs)
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(6)
        lbl_presets = QLabel("Presets:")
        lbl_presets.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        preset_layout.addWidget(lbl_presets)

        self.btn_sample_trivia = QPushButton("💡 Gaming Trivia Pack")
        self.btn_sample_trivia.setToolTip("Load default video game & stream trivia pack (10 Q&A items)")
        self.btn_sample_trivia.clicked.connect(self._load_sample_trivia)
        preset_layout.addWidget(self.btn_sample_trivia)

        self.btn_sample_socials = QPushButton("📢 Stream Socials && Rules")
        self.btn_sample_socials.setToolTip("Load stream socials & rules template (5 lines)")
        self.btn_sample_socials.clicked.connect(self._load_sample_socials)
        preset_layout.addWidget(self.btn_sample_socials)
        preset_layout.addStretch()
        grp_list_lay.addLayout(preset_layout)

        main_layout.addWidget(grp_list)

        # ---------------- 3. BOTTOM CONFIGURATION TABS ----------------
        self.tabs_config = QTabWidget()
        self.tabs_config.setObjectName("cyclerConfigTabs")

        # Tab 1: Timing & Mode
        tab_timing = QWidget()
        tab_timing_lay = QVBoxLayout(tab_timing)
        tab_timing_lay.setContentsMargins(8, 8, 8, 8)
        tab_timing_lay.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.addWidget(QLabel("Cycling Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("❓ Trivia Q&A Mode", CyclerMode.TRIVIA_QA)
        self.combo_mode.addItem("📜 Sequential (1➔2➔3)", CyclerMode.SEQUENTIAL)
        self.combo_mode.addItem("🎲 Shuffle / Random", CyclerMode.SHUFFLE)
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.combo_mode)
        mode_row.addStretch()
        tab_timing_lay.addLayout(mode_row)

        timing_row = QHBoxLayout()
        timing_row.setSpacing(8)
        timing_row.addWidget(QLabel("Rotation Interval:"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(3, 300)
        self.spin_interval.setValue(self.engine.interval_seconds)
        self.spin_interval.setSuffix(" s")
        self.spin_interval.valueChanged.connect(self._on_interval_changed)
        timing_row.addWidget(self.spin_interval)

        timing_row.addSpacing(16)
        self.lbl_ans_dur = QLabel("Answer Reveal:")
        timing_row.addWidget(self.lbl_ans_dur)
        self.spin_ans_dur = QSpinBox()
        self.spin_ans_dur.setRange(2, 60)
        self.spin_ans_dur.setValue(self.engine.trivia_answer_seconds)
        self.spin_ans_dur.setSuffix(" s")
        self.spin_ans_dur.valueChanged.connect(self._on_ans_dur_changed)
        timing_row.addWidget(self.spin_ans_dur)
        timing_row.addStretch()
        tab_timing_lay.addLayout(timing_row)
        tab_timing_lay.addStretch()

        self.tabs_config.addTab(tab_timing, "⏱️  Rotation Timing && Mode")

        # Tab 2: OBS Text Sync
        tab_obs = QWidget()
        tab_obs_lay = QVBoxLayout(tab_obs)
        tab_obs_lay.setContentsMargins(8, 8, 8, 8)
        tab_obs_lay.setSpacing(5)

        # Path banner row
        path_box = QHBoxLayout()
        path_box.setSpacing(8)
        path_box.addWidget(QLabel("Output File:"))
        self.txt_obs_path = QLineEdit(DEFAULT_CYCLER_FILE)
        self.txt_obs_path.setReadOnly(True)
        self.txt_obs_path.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        path_box.addWidget(self.txt_obs_path)
        tab_obs_lay.addLayout(path_box)

        # Prefix / Suffix template
        template_row = QHBoxLayout()
        template_row.setSpacing(8)
        template_row.addWidget(QLabel("Prefix:"))
        self.txt_prefix = QLineEdit(self.engine.prefix)
        self.txt_prefix.setPlaceholderText("e.g., Trivia: ")
        self.txt_prefix.textChanged.connect(self._on_prefix_changed)
        template_row.addWidget(self.txt_prefix)

        template_row.addWidget(QLabel("Suffix:"))
        self.txt_suffix = QLineEdit(self.engine.suffix)
        self.txt_suffix.setPlaceholderText("e.g.,  | !chat")
        self.txt_suffix.textChanged.connect(self._on_suffix_changed)
        template_row.addWidget(self.txt_suffix)
        tab_obs_lay.addLayout(template_row)

        # File actions row & checkboxes
        bot_row = QHBoxLayout()
        bot_row.setSpacing(6)

        self.btn_copy_path = QPushButton("📋 Copy Path")
        self.btn_copy_path.clicked.connect(self._copy_file_path)
        bot_row.addWidget(self.btn_copy_path)

        self.btn_open_folder = QPushButton("📂 Open Folder")
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        bot_row.addWidget(self.btn_open_folder)

        self.btn_open_file = QPushButton("📄 Open File")
        self.btn_open_file.setToolTip("Open obs_text_cycler.txt in default text editor")
        self.btn_open_file.clicked.connect(self._open_output_file)
        bot_row.addWidget(self.btn_open_file)

        bot_row.addSpacing(10)
        self.chk_clear_on_stop = QCheckBox("Clear file when stopped")
        self.chk_clear_on_stop.setChecked(self.engine.clear_file_on_stop)
        self.chk_clear_on_stop.toggled.connect(self._on_clear_on_stop_toggled)
        bot_row.addWidget(self.chk_clear_on_stop)
        bot_row.addStretch()
        tab_obs_lay.addLayout(bot_row)
        tab_obs_lay.addStretch()

        self.tabs_config.addTab(tab_obs, "📡  OBS / Streamlabs Text Sync")

        main_layout.addWidget(self.tabs_config)
        main_layout.addStretch()

        # Connect engine signals
        self.engine.tick.connect(self._on_engine_tick)
        self.engine.state_changed.connect(self._on_engine_state_changed)
        self.engine.items_changed.connect(self._refresh_list_ui)

        # Initial UI synchronization
        self._sync_ui_from_engine()

    def _sync_ui_from_engine(self):
        idx = self.combo_mode.findData(self.engine.mode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)
        self.spin_interval.setValue(self.engine.interval_seconds)
        self.spin_ans_dur.setValue(self.engine.trivia_answer_seconds)
        self._refresh_list_ui()
        self._update_mode_controls(self.engine.mode)
        disp = self.engine._get_current_display()
        self._on_engine_tick(disp, self.engine.state, self.engine.current_index, len(self.engine.items), self.engine.seconds_remaining, self.engine.subphase)

    def _refresh_list_ui(self):
        self.list_items.clear()
        for i, item in enumerate(self.engine.items):
            q = item.get("q", "")
            a = item.get("a", "")
            if a and a != q:
                label = f"{i + 1}. Q: {q}  ➔  A: {a}"
            else:
                label = f"{i + 1}. {q}"
            it = QListWidgetItem(label)
            it.setSizeHint(QSize(0, 22))
            self.list_items.addItem(it)

        if 0 <= self.engine.current_index < self.list_items.count():
            self.list_items.setCurrentRow(self.engine.current_index)

    def _toggle_start_pause(self):
        self.engine.toggle_start_pause()
        self._persist_settings()

    def _on_prev_clicked(self):
        self.engine.prev_item()
        self._persist_settings()

    def _on_next_clicked(self):
        self.engine.next_item()
        self._persist_settings()

    def _on_reset_clicked(self):
        self.engine.reset_to_first()
        self._persist_settings()

    def _on_mode_changed(self, idx):
        mode = self.combo_mode.currentData()
        self.engine.set_mode(mode)
        self._update_mode_controls(mode)
        self._persist_settings()

    def _update_mode_controls(self, mode):
        is_trivia = (mode == CyclerMode.TRIVIA_QA)
        self.lbl_ans_dur.setVisible(is_trivia)
        self.spin_ans_dur.setVisible(is_trivia)
        self.lbl_subphase_badge.setVisible(is_trivia)

        titles = {
            CyclerMode.TRIVIA_QA: "TRIVIA Q&A MODE",
            CyclerMode.SEQUENTIAL: "SEQUENTIAL CYCLER",
            CyclerMode.SHUFFLE: "SHUFFLE / RANDOM CYCLER"
        }
        self.lbl_mode_badge.setText(titles.get(mode, "TEXT CYCLER"))

    def _on_interval_changed(self, val):
        self.engine.interval_seconds = val
        if self.engine.subphase == "QUESTION":
            self.engine.seconds_remaining = val
        self._persist_settings()

    def _on_ans_dur_changed(self, val):
        self.engine.trivia_answer_seconds = val
        if self.engine.subphase == "ANSWER":
            self.engine.seconds_remaining = val
        self._persist_settings()

    def _on_prefix_changed(self, text):
        self.engine.prefix = text
        self.engine._publish_current_state()
        self._persist_settings()

    def _on_suffix_changed(self, text):
        self.engine.suffix = text
        self.engine._publish_current_state()
        self._persist_settings()

    def _on_clear_on_stop_toggled(self, checked):
        self.engine.clear_file_on_stop = checked
        self._persist_settings()

    def _on_add_clicked(self):
        q = self.txt_add_q.text().strip()
        a = self.txt_add_a.text().strip()
        if not q:
            return
        # Support Question | Answer in single field
        if not a and "|" in q:
            parts = q.split("|", 1)
            q = parts[0].strip()
            a = parts[1].strip()

        self.engine.add_item(q, a)
        self.txt_add_q.clear()
        self.txt_add_a.clear()
        self.list_items.setCurrentRow(len(self.engine.items) - 1)
        self._persist_settings()

    def _on_edit_clicked(self):
        row = self.list_items.currentRow()
        if row < 0 or row >= len(self.engine.items):
            return
        item = self.engine.items[row]
        dlg = EditItemDialog(self, item.get("q", ""), item.get("a", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_q, new_a = dlg.get_values()
            if new_q:
                self.engine.update_item(row, new_q, new_a)
                self._persist_settings()

    def _on_item_double_clicked(self, it):
        self._on_edit_clicked()

    def _on_delete_clicked(self):
        row = self.list_items.currentRow()
        if row < 0 or row >= len(self.engine.items):
            return
        self.engine.remove_item(row)
        self._persist_settings()

    def _on_move_up(self):
        row = self.list_items.currentRow()
        if row <= 0:
            return
        self.engine.move_item(row, row - 1)
        self.list_items.setCurrentRow(row - 1)
        self._persist_settings()

    def _on_move_down(self):
        row = self.list_items.currentRow()
        if row < 0 or row >= len(self.engine.items) - 1:
            return
        self.engine.move_item(row, row + 1)
        self.list_items.setCurrentRow(row + 1)
        self._persist_settings()

    def _load_sample_trivia(self):
        self.engine.load_sample_trivia()
        self._persist_settings()

    def _load_sample_socials(self):
        self.engine.load_sample_socials()
        self._persist_settings()

    def _on_import_txt(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Import Text Lines or Trivia", "", "Text Files (*.txt);;All Files (*.*)")
        if not fn or not os.path.exists(fn):
            return
        try:
            imported = []
            with open(fn, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    clean = line.strip()
                    if not clean:
                        continue
                    if "|" in clean:
                        parts = clean.split("|", 1)
                        imported.append({"q": parts[0].strip(), "a": parts[1].strip()})
                    else:
                        imported.append({"q": clean, "a": ""})
            if imported:
                self.engine.items.extend(imported)
                self.engine.items_changed.emit()
                self._persist_settings()
                QMessageBox.information(self, "Import Successful", f"Successfully imported {len(imported)} item(s) from {os.path.basename(fn)}.")
        except Exception as e:
            QMessageBox.warning(self, "Import Failed", f"Failed to import file:\n\n{e}")

    def _on_export_txt(self):
        if not self.engine.items:
            QMessageBox.information(self, "Empty Collection", "There are no items to export.")
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Export Collection to Text File", "stream_trivia.txt", "Text Files (*.txt);;All Files (*.*)")
        if not fn:
            return
        try:
            with open(fn, "w", encoding="utf-8") as f:
                for it in self.engine.items:
                    q = it.get("q", "").strip()
                    a = it.get("a", "").strip()
                    if a and a != q:
                        f.write(f"{q} | {a}\n")
                    else:
                        f.write(f"{q}\n")
            QMessageBox.information(self, "Export Successful", f"Successfully exported {len(self.engine.items)} item(s) to:\n\n{fn}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Failed to export file:\n\n{e}")

    def _copy_file_path(self):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(DEFAULT_CYCLER_FILE)
        QMessageBox.information(
            self,
            "Path Copied",
            f"OBS Text Cycler file path copied to clipboard:\n\n{DEFAULT_CYCLER_FILE}\n\n"
            "In OBS or Streamlabs, add a Text (GDI+) source, check 'Read from file', and paste this path!"
        )

    def _open_output_folder(self):
        folder = os.path.dirname(DEFAULT_CYCLER_FILE)
        try:
            subprocess.Popen(f'explorer "{os.path.normpath(folder)}"')
        except Exception:
            try:
                os.startfile(folder)
            except Exception:
                pass

    def _open_output_file(self):
        if not os.path.exists(DEFAULT_CYCLER_FILE):
            self.engine._publish_current_state()
        try:
            os.startfile(DEFAULT_CYCLER_FILE)
        except Exception:
            pass

    def _persist_settings(self):
        if hasattr(self.main_win, "overlay") and hasattr(self.main_win.overlay, "save_settings"):
            self.main_win.overlay.save_settings()

    def _on_engine_tick(self, display_text: str, state: str, idx: int, total: int, seconds_left: int, subphase: str):
        self.lbl_text_display.setText(display_text)
        sub_str = f"[{subphase}]" if self.engine.mode == CyclerMode.TRIVIA_QA else ""
        self.lbl_subphase_badge.setText(sub_str)
        if subphase == "ANSWER":
            self.lbl_subphase_badge.setStyleSheet("""
                background-color: #14532d;
                color: #86efac;
                font-size: 10px;
                font-weight: bold;
                padding: 1px 8px;
                border-radius: 4px;
            """)
        else:
            self.lbl_subphase_badge.setStyleSheet("""
                background-color: #2e1065;
                color: #c084fc;
                font-size: 10px;
                font-weight: bold;
                padding: 1px 8px;
                border-radius: 4px;
            """)

        pos_str = f"Item {idx + 1} of {total}" if total > 0 else "0 items"
        if state == CyclerState.RUNNING:
            self.lbl_meta_info.setText(f"{pos_str} • Next rotation in {seconds_left}s")
        elif state == CyclerState.PAUSED:
            self.lbl_meta_info.setText(f"{pos_str} • PAUSED (holding at {seconds_left}s)")
        else:
            self.lbl_meta_info.setText(f"{pos_str} • Ready to start (interval: {self.engine.interval_seconds}s)")

        if 0 <= idx < self.list_items.count() and not self.list_items.hasFocus():
            self.list_items.setCurrentRow(idx)

        self._update_state_ui(state)

    def _on_engine_state_changed(self, new_state: str):
        self._update_state_ui(new_state)

    def _update_state_ui(self, state: str):
        if state == CyclerState.RUNNING:
            self.btn_toggle.setText("⏸ Pause")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_cycler_start {
                    background-color: #d97706;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 12px;
                    border: 1px solid #b45309;
                    border-radius: 4px;
                    padding: 3px 14px;
                    min-height: 20px;
                }
                QPushButton#btn_cycler_start:hover {
                    background-color: #b45309;
                }
            """)
            self.lbl_status_pill.setText("● CYCLING")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #15803d;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)
        elif state == CyclerState.PAUSED:
            self.btn_toggle.setText("▶ Resume")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_cycler_start {
                    background-color: #9146ff;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 12px;
                    border: 1px solid #772ce8;
                    border-radius: 4px;
                    padding: 3px 14px;
                    min-height: 20px;
                }
                QPushButton#btn_cycler_start:hover {
                    background-color: #772ce8;
                }
            """)
            self.lbl_status_pill.setText("❚❚ PAUSED")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #b45309;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)
        else:  # STOPPED
            self.btn_toggle.setText("▶ Start")
            self.btn_toggle.setStyleSheet("""
                QPushButton#btn_cycler_start {
                    background-color: #9146ff;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 12px;
                    border: 1px solid #772ce8;
                    border-radius: 4px;
                    padding: 3px 14px;
                    min-height: 20px;
                }
                QPushButton#btn_cycler_start:hover {
                    background-color: #772ce8;
                }
            """)
            self.lbl_status_pill.setText("■ STOPPED")
            self.lbl_status_pill.setStyleSheet("""
                background-color: #3f3f46;
                color: #ffffff;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 10px;
                border-radius: 10px;
            """)

    def refresh_theme_labels(self, effective: str):
        is_dark = (effective == "dark")
        card_bg = "#18181b" if is_dark else "#ffffff"
        card_border = "#2d2d30" if is_dark else "#d4d4d8"
        self.card_display.setStyleSheet(f"""
            QFrame#cyclerDisplayCard {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 8px;
                padding: 6px 12px;
            }}
        """)
        mode_color = "#a1a1aa" if is_dark else "#71717a"
        self.lbl_mode_badge.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {mode_color};")
        self.lbl_meta_info.setStyleSheet(f"font-size: 11px; color: {mode_color};")

        pane_bg = "#18181b" if is_dark else "#f4f4f5"
        pane_border = "#2d2d30" if is_dark else "#d4d4d8"
        list_bg = "#121214" if is_dark else "#ffffff"
        list_border = "#2d2d30" if is_dark else "#d4d4d8"
        item_color = "#f4f4f5" if is_dark else "#18181b"
        self.tabs_config.setStyleSheet(f"""
            QTabWidget#cyclerConfigTabs::pane {{
                border: 1px solid {pane_border};
                border-radius: 6px;
                padding: 4px;
                background-color: {pane_bg};
            }}
            QTabBar::tab {{
                padding: 3px 12px;
                font-weight: 600;
                font-size: 11px;
            }}
        """)
        self.list_items.setStyleSheet(f"""
            QListWidget#cyclerList {{
                background-color: {list_bg};
                border: 1px solid {list_border};
                border-radius: 4px;
                font-size: 11px;
            }}
            QListWidget#cyclerList::item {{
                padding: 1px 4px;
                min-height: 18px;
                color: {item_color};
            }}
            QListWidget#cyclerList::item:selected {{
                background-color: #9146ff;
                color: #ffffff;
                border-radius: 3px;
            }}
        """)
