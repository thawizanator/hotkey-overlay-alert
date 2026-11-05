# 🌿 Streamer Calyx

[![Release](https://img.shields.io/github/v/release/thawizanator/streamer-calyx?label=release&color=10b981)](https://github.com/thawizanator/streamer-calyx/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078d4.svg)](https://github.com/thawizanator/streamer-calyx)
[![Code Signing](https://img.shields.io/badge/code%20signing-DigiCert%20EV%20Signed-green)](https://github.com/thawizanator/streamer-calyx)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)

**Streamer Calyx** is a high-performance, native Windows backstage command center and multitool suite for streamers, co-hosts, and broadcast producers.

In botany, the *calyx* is the protective outer whorl of sepals that encloses, protects, and supports the budding flower as it blossoms. In that same spirit, **Streamer Calyx** holds and protects all your essential streaming tools—**replacing multiple separate utilities** with a single unified, lightweight, sub-second application.

---

## ⚡ Quick Download

Download the latest production release directly from [GitHub Releases](https://github.com/thawizanator/streamer-calyx/releases/latest):

| Package | Filename | Size | Description |
| :--- | :--- | :---: | :--- |
| **Installer (Recommended)** | [**`StreamerCalyx_Setup.exe`**](https://github.com/thawizanator/streamer-calyx/releases/latest/download/StreamerCalyx_Setup.exe) | **~52 MB** | Modern NSIS installer, sub-second boot time, zero UAC elevation, Start Menu & Desktop shortcuts. |
| **Standalone Portable** | [**`StreamerCalyx_Portable.exe`**](https://github.com/thawizanator/streamer-calyx/releases/latest/download/StreamerCalyx_Portable.exe) | **~71 MB** | Single-file zero-install executable for USB flash drives and portable workflows. |
| **Standalone Mirror** | [**`StreamerCalyx.exe`**](https://github.com/thawizanator/streamer-calyx/releases/latest/download/StreamerCalyx.exe) | **~71 MB** | Standalone mirror executable. |
| **Update Encyclopedia** | [**`StreamerCalyx_Ledger.html`**](https://github.com/thawizanator/streamer-calyx/releases/latest/download/StreamerCalyx_Ledger.html) | **~1 MB** | Complete interactive development ledger & commit encyclopedia. |

*All binaries are Authenticode digitally signed with a **DigiCert EV Hardware Token** and RFC 3161 timestamps.*

---

## 🧰 The Streamer Multitool Suite ("One Tool to Replace Multiples")

Streamer Calyx unifies 10 core broadcast modules into a modern, collapsible left-sidebar interface:

### 1. 🖥️ Monitor Highlight Border Alerts
- **Visual Toggle Feedback**: Full-screen or per-monitor edge-to-edge glowing border highlight (ideal for muted mic indicators, active recording, or live broadcast status).
- **Per-Monitor V2 DPI Awareness**: Pixel-perfect alignment across mixed-DPI displays (100%, 125%, 175%) using explicit Win32 `SetWindowPos` locking.
- **Customizable Appearance**: Full RGB color palette, thickness slider (2px–30px), transparency (10%–100%), and breathing/flashing effects (*Snail, Turtle, Squirrel, Cheetah, Lightning, or Static*).
- **Zero Input Interception**: Uses `WS_EX_TRANSPARENT` (`WindowTransparentForInput`) so the overlay never steals mouse focus or clicks during gameplay.

### 2. 🚀 Stream Launchpad ("Go for Launch")
- **Mission Control Pre-Flight**: Centralized broadcast readiness dashboard.
- **1-Click Broadcast Launch**: Streamlined initiation with optional automatic start for Chronos countdown timers and Trivia cyclers.
- **Real-Time SLOBS Watchdog**: Listens for Streamlabs Desktop `streamingStatusChange` RPC events and automatically resets the launch button back to **Standby** whenever a stream ends.

### 3. 🎛️ Stream Director & Remote Co-Host Dock
- **Dual WebSocket & RPC Bridge**: Simultaneous native control for OBS Studio (`ws://localhost:4455`) and Streamlabs Desktop (SLOBS).
- **Encrypted WebRTC P2P**: Zero-port-forward WAN and LAN remote co-host docking over secure WebRTC data channels with signaling bouncer verification.
- **Live 5-Fader Mixer & 8-Scene Grid**: Responsive floating monitor dock with smooth 1:1 fader tracking and scene switching.
- **Granular Permissions Matrix**: Windows-style permission checklist per co-host with instant visual locking (`[🔒 LOCKED]`).

### 4. 🔊 Soundboard Deck & LAN Bridge
- **Ultra-Low Latency Soundboard**: Native audio playback via `PyQt6.QtMultimedia` with zero external audio engine bloat.
- **Mobile LAN Bridge**: Trigger sound effects directly from your phone, tablet, or secondary device over local network.
- **SandMan Anti-Spam Troll Shield**: Rate-limiting rapid-fire playback, panic lock, and loud alarm buzzer protection for remote soundboard access.

### 5. 🎙️ Voice Session Anchoring & Auto-Clip Engine
- **Dynamic Voice Anchoring**: Dual-baseline acoustic engine that anchors microphone levels dynamically above background game audio and music.
- **40-Segment LED VU Meter**: Hardware-accurate peak and RMS visual audio feedback.
- **Twitch Stream Marker Auto-Tagging**: Dispatches instant stream markers during hype audio peaks.
- **60-Second Replay Clip Buffer**: Automatically logs 40 seconds before and 20 seconds after reaction peaks.

### 6. ⏱️ Chronos Timers Engine
- **Multi-Timer Operations**: Countdowns, stopwatches, and interval timers.
- **OBS Text Synchronization**: Automatically updates on-stream text files (`timer_display.txt`) in real time.
- **Audio Chimes & Toasts**: Synthesized alert beeps and custom WAV audio triggers on completion.

### 7. 💬 Rotating Text & Trivia Cycler
- **Timed Line Rotator**: Cycles community rules, sponsor banners, social links, and stream schedules.
- **Interactive Trivia Q&A**: Question-to-answer countdown reveals synchronized to OBS text overlays.

### 8. 🎮 Hotkeys & Gamepad Center (XInput)
- **Zero-Dependency Gamepad Polling**: Native Windows `xinput1_4.dll` integration with Xbox Guide button support.
- **Streamer Chords & Hold Delays**: Supports combination buttons (e.g., `LT + LS Click + Y`, `LB + RB`) and hold thresholds to prevent accidental mid-game triggers.
- **Peak Chord Accumulator**: Prevents misfires during sequential button releases.
- **Multi-Device Input Hooks**: Mouse 3, 4, 5, and arbitrary 1-to-5 keyboard key combinations.

### 9. 🟣 Twitch Helix API Automation
- **Zero-Setup Local OAuth**: One-click authentication with automated token discovery.
- **Broadcaster & Mod Role Support**: Execute `/marker`, `/announce`, and `/shoutout` commands from custom hotkeys.
- **Streamer Mode HUD**: Non-intrusive transparent toasts and auto-fading overlays that never disrupt full-screen gameplay.

### 10. ⚙️ System Settings, Privacy & Auto-Updater
- **Integrated Auto-Updater**: Direct update checks and seamless self-replacing upgrades via GitHub Releases.
- **Privacy First**: Optional local session diagnostics toggle; keystrokes are never recorded or transmitted.
- **Automated Crash Logging**: Silently captures unhandled exceptions into `%APPDATA%\StreamerCalyx\logs\crash_log.txt` for fast troubleshooting.

---

## 🛡️ Antivirus, SmartScreen & Digital Signing

Every release of Streamer Calyx is **100% open source** and digitally signed:

- **DigiCert EV Hardware Token Signed**: Verified with Authenticode SHA-256 and RFC 3161 timestamps.
- **Avast CyberCapture**: Because each newly compiled release has a brand-new SHA-256 hash, Avast's cloud scanner will hold the file for ~60 seconds to inspect the digital signature. Once verified, it opens normally.
- **Behavior Shield Hardening**: Process startup low-level hooks (`WH_KEYBOARD_LL`) and command-line termination scripts have been eliminated to prevent false-positive heuristic flags (`IDP.HELU`).
- **Installed Edition Recommended**: The NSIS Modern Installer runs directly from `%LOCALAPPDATA%\Programs\StreamerCalyx`, avoiding `%TEMP%` extraction and launching in sub-second time.

---

## 🚀 Running from Source

### Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Python**: Version 3.10 to 3.14

### Installation
1. Clone the repository:
   ```powershell
   git clone https://github.com/thawizanator/streamer-calyx.git
   cd streamer-calyx
   ```

2. Create and activate a virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Launch Streamer Calyx:
   ```powershell
   python main.py
   ```

---

## 🔨 Building Release Binaries

To build the debloated onedir application, the standalone portable `.exe`, the NSIS Modern Installer, and run Authenticode code-signing:

```powershell
python build_release.py
```

Outputs will be placed in `dist/`:
- `dist/StreamerCalyx_Setup.exe` (NSIS Installer, ~52 MB)
- `dist/StreamerCalyx_Portable.exe` (Standalone Portable, ~71 MB)
- `dist/StreamerCalyx.exe` (Standalone Mirror, ~71 MB)

---

## ⚙️ Configuration & Storage

Settings and user data are stored per-user at:
```
%APPDATA%\StreamerCalyx\
├── config.json               # Main application settings
├── soundboard_config.json    # Soundboard deck slots and audio paths
├── director_permissions.json # Co-host permissions matrix
└── logs\
    └── crash_log.txt         # Crash diagnostic handler
```

---

## 🗺️ Project Roadmap
For past milestones and upcoming v4 planning (mobile web deck companion, browser extension), see **[ROADMAP.md](ROADMAP.md)**.

---

## 👤 Author & Support
- **Created by**: ThaWizanator
- **Twitch**: [twitch.tv/thawizanator](https://twitch.tv/thawizanator)
- **GitHub**: [github.com/thawizanator](https://github.com/thawizanator)
- **Version**: `v3.0.0` (Stable)

---

## 📄 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
