# Streamer Calyx — Project Roadmap 🗺️

Welcome to the development roadmap for **Streamer Calyx** (formerly *HotKey Overlay Alert*). This document tracks completed milestones, current progress, and upcoming features designed to make this the ultimate backstage broadcast suite for streamers, co-hosts, and remote directors.

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

### Phase 3.5: Multi-Monitor Cross-DPI Handling & Traceability — *Completed*
- Unified multi-monitor virtual coordinate space via **System DPI Awareness** (`windows:dpiawareness=1`) and user-selectable toggle under **Monitor Setup**.
- Integrated Git commit hash (`get_build_commit()`) across sidebar footer, window titles, Updates tab, and diagnostic bug report templates.

### Phase 4.1: OBS Studio & Streamlabs Desktop WebSocket Gateway — *Completed*
- **WebSocket Integration**: Direct low-latency connection to local OBS Studio and Streamlabs Desktop via OBS WebSocket protocol (`ws://localhost:4455`).
- **Scene & Source Control**: Instantly switch scenes, toggle display/browser sources, mute/unmute audio tracks, and trigger transitions.
- **LAN & Multi-PC Verification**: Verified operational across local PCs connected to the same LAN.

### Phase 4.2: Stream Director, Remote P2P WebRTC & Fine-Grained Permissions (`v3.0.0-beta.3`) — *Completed*
- **P2P WebRTC Data Channels + Signaling Bouncer Proxy**: Encrypted WAN remote control between streamer and remote director with zero port forwarding.
- **Twitch Identity Whitelist & Pairing Passkeys**: Automated handshake combining Twitch username verification with AES-256 encrypted pairing keys.
- **3-Tab Layout & Conditional Visibility**: Dedicated tabs for *Scenes & Controls*, *Audio Mixer*, and *Remote Co-Host* (automatically shown/hidden based on Streamer Mode).
- **Granular Windows-Style User Permissions Matrix**: Element-by-element permission checklist per remote director (allowed scenes, mute controls, volume adjustments, or full control).
- **Instant Visual Locking**: Gated controls display `[🔒 LOCKED]` badge and disabled state on initial connect without requiring first click.
- **Smooth Fader Dragging & Non-Destructive Layout**: Custom `SmoothSlider` with 1:1 mouse tracking and in-place widget updates eliminating flickering, sizing glitches, and mouse-grab drops.
- **Live Peer Testing Passed**: Successfully validated in live peer-to-peer remote testing with co-host `@purplen3rd`.
- **Identity Rebrand**: Transitioned full project identity to **Streamer Calyx** (`StreamerCalyx.exe`, `%APPDATA%\StreamerCalyx` zero-downtime auto-migration).

---

### Phase 5: Unified Hotkey Center & Peripheral Support (`v3.0.0-beta.4`) — *Completed*
- **Central Hotkey Manager Tab**: A dedicated view (**Hotkeys & Peripherals**) in the navigation sidebar displaying an expandable accordion drawer interface for all 22 stream actions with zero horizontal clipping.
- **Native Zero-Dependency XInput Gamepad Support**:
  - Low-latency background controller polling via Windows `xinput1_4.dll` (with ordinal 100 for central Xbox Guide button support).
  - Captures inputs globally across games and full-screen streaming setups (<0.1% CPU).
  - **Streamer Chords & Hold Delays**: Supports combination buttons (e.g., `LT + LS Click + Y`, `LB + RB`, `Back + Y`) and configurable hold thresholds (0.5s, 0.75s, 1.0s) so active gameplay controls are shielded.
  - **Peak Chord Accumulator & Release Shielding**: Multi-button combos persist through sequential button releases without accidental single-button trigger misfires.
- **2-Row Live Controller Visualizer HUD & 1-Click Recorder**: Real-time HUD lighting up physical buttons as pressed, fitting comfortably within collapsed 570px windows (>140px clearance).
- **Multi-Device Mouse & Keyboard Hooks**: Full global mapping for Mouse 3, 4, 5, modifiers, and keyboard keys.

---

## 🚀 Active Milestones: Phase 6 — Soundboard Triggering & Audio Production Hub (`v3.1.0`)

> [!IMPORTANT]
> **Phase 6 Focus**: With multi-device input and backstage Stream Director established, Phase 6 brings native soundboard triggering and audio production routing to Streamer Calyx.

### Phase 6: Soundboard Triggering & Audio Production Hub (`v3.2.0`)
- Standalone sound effect player and audio production routing.
- Assign local sound effects, chimes, and audio cues to stream events and hotkeys.

### Phase 7: Mobile & Local Web Deck Companion (`v3.3.0`)
- Lightweight local and remote web dashboard accessible from phones, tablets, or secondary browsers.
- Touch buttons to trigger monitor alerts, timers, trivia cycling, and Stream Director commands without needing external hardware like an Elgato Stream Deck.

### Phase 8: Optimization & Debloat Architecture (`v4.0.0`)
- **Binary Slimming & Codec Debloating**:
  - Exclude heavy, unused FFmpeg video codec DLLs from PyInstaller bundle (`libx265.dll` [12 MB], `libSvtAv1Enc.dll` [7.3 MB], `libvpx.dll`, etc.) since P2P WebRTC Director only requires RTCDataChannel JSON messaging.
  - Exclude unused Qt6 components (`opengl32sw.dll` [19.7 MB], `Qt6Pdf.dll` [4.4 MB]) to shave ~25 MB off the standalone executable size.
- **Dual-Distribution Packaging**:
  - **Portable Standalone Executable**: `StreamerCalyx-Portable.exe` for streamers who prefer zero-installation portability.
  - **Lightweight Windows Installer**: `StreamerCalyx-Setup.exe` (via Inno Setup with LZMA2 compression) for instant boot without `%TEMP%` extraction, Start Menu integration, desktop shortcuts, and a download size under 30 MB.

---

## 💡 Future Ideas & Research Backlog

- **Dedicated Browser Extension / Chrome Plugin**:
  - Research and develop a custom browser extension that can be packaged or installed alongside the app.
  - Potential features: Custom stream video formatting, embedding the Stream Director dock directly within Twitch/YouTube web pages, synchronized two-way communication between the web stream player/chat and the desktop app, and automated stream viewport docking.
