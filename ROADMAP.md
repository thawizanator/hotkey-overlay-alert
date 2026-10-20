# HotKey Overlay Alert — Project Roadmap 🗺️

Welcome to the development roadmap for **HotKey Overlay Alert**. This document tracks completed milestones, current progress, and upcoming features designed to make this the ultimate visual overlay and workflow utility for streamers and gamers.

---

## 🧭 Release Architecture & Branches

- **`main` Branch**: Tracks stable production releases (currently **`v2.5.2`**).
- **`develop` Branch**: Tracks active feature branches, alpha builds, and early access previews (currently **`v3.0.0-beta.3`**).

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

### Phase 4.1: OBS Studio & Streamlabs Desktop WebSocket Gateway — *Completed*
- **WebSocket Integration**: Direct low-latency connection to local OBS Studio and Streamlabs Desktop via OBS WebSocket protocol (`ws://localhost:4455`).
- **Scene & Source Control**: Instantly switch scenes, toggle display/browser sources, mute/unmute audio tracks, and trigger transitions.
- **LAN & Multi-PC Verification**: Verified operational across local PCs connected to the same LAN.

---

## 🚀 Active Milestones: Phase 4.2 — Stream Director & Secure Remote OBS Integration (`v3.0.0-beta.3`)

> [!IMPORTANT]
> **Remote Producer & Director Vision**: Allow the streamer, trusted co-hosts, or remote channel directors to trigger actions and switch scenes in **OBS Studio** and **Streamlabs Desktop** from anywhere over the internet, while enforcing strict per-user authentication so only authorized users can connect.

### 4.2 🔒 Secure Remote Access Control ("Connect from Anywhere") — *Built, Awaiting Testing*
- **Architecture Implemented**:
  - **P2P WebRTC Data Channels + Signaling Bouncer Proxy**: Direct peer-to-peer encrypted data channel between streamer and remote director without exposing private IP addresses.
  - **Twitch Identity Whitelist & Pairing Passkey**: Handshake combining Twitch username verification with AES-encrypted pairing keys.
  - **3-Tab Layout & Conditional Visibility**: Dedicated tabs for *Scenes & Controls*, *Audio Mixer*, and *Remote Co-Host* (automatically shown/hidden based on Streamer Mode).
  - **Granular Windows-Style User Permissions Matrix**: Element-by-element permission checklist per remote director (allowed scenes, mute controls, volume adjustments, or full control).
- **Status & Testing Delay**:
  - Feature implementation is fully built and integrated in `v3.0.0-beta.3`.
  - Testing was temporarily delayed due to host/tester environment issues (hidden drawer tray context menu and contrast display bugs), which were successfully resolved and backported in stable releases **v2.5.1** and **v2.5.2**.
  - Ready for live peer-to-peer remote testing.

---

## 🔮 Upcoming Roadmap Milestones

### Phase 5: Unified Hotkey Center & Gamepad Controller Support (`v3.1.0`)
- **Central Hotkey Manager Tab**: A dedicated view (**Hotkeys & Gamepad**) in the left sidebar displaying a master table of all configured shortcuts across the entire app with inline conflict detection.
- **Background Gamepad & Controller Support (Xbox, PlayStation, Generic Gamepads)**:
  - Low-latency background controller polling via Windows **XInput API** (`xinput1_4.dll`), allowing gamepad players to trigger alerts, macros, and timers without setting down their controller.
  - Works globally even when full-screen games have exclusive focus.
  - **Safe "Streamer Chords" & Hold Delays**: Supports combination buttons (e.g., `LB + RB`, `Back + Y`, `L3 + R3`) or 0.75s hold thresholds so normal in-game button taps (jumping, shooting) are never disrupted.
- **Live Controller Visualizer & Button Recorder**: Real-time HUD that highlights gamepad buttons as you press them, with a 1-click button recorder.

### Phase 6: Soundboard Triggering & Audio Production Hub (`v3.2.0`)
- Standalone sound effect player and audio production routing.
- Assign local sound effects, chimes, and audio cues to stream events and hotkeys.

### Phase 7: Mobile & Local Web Deck Companion (`v3.3.0`)
- Lightweight local and remote web dashboard accessible from phones, tablets, or secondary browsers.
- Touch buttons to trigger monitor alerts, timers, trivia cycling, and Stream Director commands without needing external hardware like an Elgato Stream Deck.

---

## 💡 Future Ideas & Research Backlog

- **Dedicated Browser Extension / Chrome Plugin**:
  - Research and develop a custom browser extension that can be packaged or installed alongside the app.
  - Potential features: Custom stream video formatting, embedding the Stream Director dock directly within Twitch/YouTube web pages, synchronized two-way communication between the web stream player/chat and the desktop app, and automated stream viewport docking.
