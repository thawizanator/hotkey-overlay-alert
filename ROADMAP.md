# HotKey Overlay Alert — Project Roadmap 🗺️

Welcome to the development roadmap for **HotKey Overlay Alert**. This document tracks completed milestones, current progress, and upcoming features designed to make this the ultimate visual overlay and workflow utility for streamers and gamers.

---

## 🧭 Release Architecture & Branches

- **`main` Branch**: Tracks stable production releases (currently **`v2.5.0`**).
- **`develop` Branch**: Tracks active feature branches, alpha builds, and early access previews (currently **`v3.0.0-beta.2`**).

---

## ✅ Completed Milestones

### Phase 1: Modern Left Sidebar Navigation Shell (`v3.0.0-alpha`) — *Completed*
- Replaced classic vertical tab widget with a scalable, modern **Left Sidebar Shell** (`SettingsWindow`).
- Grouped views into logical categories: **DISPLAY & ALERTS**, **STREAM TOOLS**, and **APP & CONFIG**.
- Preserved existing views: Main Overlay, Monitor Setup, Alert Overlay, Twitch Macros, and System & Logs.
- Full Light and Dark theme synchronization with dynamic OS color scheme detection.

### Phase 2: Chronos Timers Engine & OBS Integration (`v3.0.0-beta.1`) — *Completed*
- Multi-timer engine supporting **Countdowns**, **Stopwatches**, and **Interval Timers**.
- Real-time OBS / Streamlabs file-based text sync (`timer_display.txt`) with custom templates.
- Audio alerts with synthesized chime beeps and custom WAV audio playback.
- Configurable completion actions, custom banner toasts, and independent timer state preservation.

### Phase 3: Rotating Text & Trivia Cycler Engine (`v3.0.0-beta.2`) — *Completed*
- Timed line rotator for stream trivia, community rules, sponsor messages, and social links.
- Interactive **Trivia Q&A Mode** with customizable question-to-answer reveal countdowns.
- Real-time OBS / Streamlabs output sync with prefix/suffix formatting.
- Compacted UI item rows and collapsible sidebar navigation (`◀` / `▶` and `Ctrl+B`) fitting compact and portrait displays (Monitor #3).

### Phase 3.5: Multi-Monitor Cross-DPI Handling & Traceability — *Partial / Backburner*
- Unified multi-monitor virtual coordinate space via **System DPI Awareness** (`windows:dpiawareness=1`) and user-selectable toggle under **Monitor Setup**.
- Integrated Git commit hash (`get_build_commit()`) across sidebar footer, window titles, Updates tab, and diagnostic bug report templates.
- *Status Note*: Core DPI mode toggle and build commit tracking are functional; minor cross-monitor spanning refinements placed on the backburner to prioritize Phase 4.

---

## 🚀 Newly Added: Phase 4 — Unified Hotkey Center & Gamepad Controller Support (`v3.0.0-beta.3`)

> [!NOTE]
> **Streamer Problem Statement**: Streamers and gamers who play with a controller (Xbox, PlayStation, or generic gamepad) currently have to let go of their controller to reach for the keyboard to trigger hotkeys (muting/unmuting alerts, clipping stream markers, sending announcements, or controlling timers). Phase 4 introduces native background gamepad support so hotkeys can be triggered directly from the controller without interrupting gameplay!

### 4.1 ⌨️ Central Hotkey Overview & Management Tab
- **Dedicated Sidebar View**: A single central place in the sidebar (**Hotkeys & Gamepad**) to view, test, and rebind all shortcuts across the entire app.
- **Unified Shortcut Matrix**:
  - 🖥️ Primary Monitor Highlight Overlay
  - 🟣 Twitch Macros (Slots 1–4: Markers, Announcements, Shoutouts)
  - ⏱️ Chronos Timers (Timer #1–#4 Start/Stop/Reset)
  - 📜 Rotating Text / Trivia (Next Line, Previous Line, Reveal Answer)
  - 🗂️ App Controls (Toggle Sidebar `Ctrl+B`, Show/Hide Settings)
- **Inline Conflict Detection**: Visual alert tags (`⚠️ Conflict`) if duplicate keyboard hotkeys or gamepad chords are assigned to multiple actions.
- **Master Toggle & Per-Action Muting**: Temporarily disable individual hotkeys or the entire hotkey hook without deleting the assigned key combinations.

### 4.2 🎮 Native Gamepad & Controller Support (Xbox, PlayStation, Gamepads)
- **Background Controller Hooking**:
  - Utilizes Windows **XInput API** (`xinput1_4.dll`) to capture Xbox 360, Xbox One, Xbox Series X|S, and XInput-compatible PC gamepads globally in the background even while full-screen games have exclusive focus.
  - Zero third-party heavyweight dependencies; pure low-latency Windows API integration running in an asynchronous worker thread.
  - Automatic support for PlayStation DualShock 4 / DualSense controllers running through Steam Input or DS4Windows.
- **Controller Button Mapping**:
  - D-Pad: Up, Down, Left, Right
  - Face Buttons: A, B, X, Y (Cross, Circle, Square, Triangle)
  - Bumpers & Triggers: LB, RB, Left Trigger (LT > 50%), Right Trigger (RT > 50%)
  - Stick Clicks: Left Stick Click (L3 / LS), Right Stick Click (R3 / RS)
  - Center Buttons: Back / View, Start / Menu, Guide / Xbox button
- **Safe "Streamer Chords" (Combinations & Hold Delays)**:
  - Prevents game interference: In-game actions (e.g. jumping or shooting with A/RT) will not accidentally trigger hotkeys.
  - Supports **Chords / Combinations**: e.g., `LB + RB`, `Back + Y`, `LT + D-Pad Down`, `L3 + R3`.
  - Supports **Long-Press Threshold** (e.g., hold `Back` for 0.75 seconds) so tap functions in-game remain unaffected.

### 4.3 🕹️ Live Controller Visualizer & Button Recorder
- **Live Controller Tester**: An interactive visual HUD inside the Hotkey Tab that lights up controller buttons in real-time as you press them, confirming your gamepad is connected and detected.
- **Click-to-Record Gamepad Button**:
  1. Click **Assign Controller Button**.
  2. Press your desired button or chord on your controller.
  3. The app detects the combination and locks it in automatically.

---

## 🔮 Future Roadmap Milestones

### Phase 5: Stream Director (Multi-Action Orchestration & OBS WebSocket)
- **OBS Studio WebSocket v5 Integration**: Direct connection to OBS Studio to switch scenes, toggle sources, and start/stop recordings.
- **Multi-Action Macros**: Chain actions together (e.g., *One button triggers monitor highlight + starts Chronos 5-minute break timer + switches OBS to "Be Right Back" scene*).
- **Soundboard Triggering**: Assign local sound effects to hotkey actions.

### Phase 6: Mobile & Local Web Deck Companion
- Lightweight local HTTP/WebSocket dashboard accessible from phones, tablets, or secondary browsers on the local Wi-Fi.
- Touch buttons to trigger monitor alerts, timers, trivia cycling, and Twitch commands without needing external hardware like an Elgato Stream Deck.
