# HotKey Overlay Alert 🔔

A lightweight, high-performance Windows system tray utility created to prevent streaming on mute! **HotKey Overlay Alert** renders an on-screen colored border highlight around your chosen monitor to remind you when a hotkey is active, plus features direct **Twitch Helix API** integration for stream markers, announcements, and shoutouts.

---

## ✨ Features

### 🖥️ Visual Monitor Alert
- **Stay Alert While Streaming**: Designed primarily to prevent muted-mic blunders, but can monitor any toggle hotkey.
- **Multi-Monitor Support**: Automatically identifies monitors and renders the border overlay on the exact display you select.
- **Customizable Appearance**:
  - Full RGB color picker
  - Border thickness slider (2px – 30px)
  - Opacity and transparency adjustments (10% – 100%)
  - Breathing/flashing animation effect with adjustable speeds (*Snail, Turtle, Squirrel, Cheetah, Lightning, or Always On*)
- **Non-Intrusive**: Runs with WindowTransparentForInput and WindowStaysOnTopHint so it never steals focus or intercepts mouse clicks during gameplay.

### ⌨️ Flexible Hotkey Recorder (1 to 5 Keys)
- Record simple single keys (*e.g., F8, F12*) or combinations up to 5 keys (*e.g., Ctrl+Alt+Shift+1*).
- **Click-to-Record Workflow**:
  1. Click **Change Hotkey** or any Twitch hotkey button.
  2. Press your desired keys (modifiers or standard keys).
  3. Click the button again with your mouse to lock and save.
  4. Press **Esc** anytime during recording to cancel without saving.
- Dedicated **Reset Default** button to restore the primary activation hotkey (*Ctrl + Numpad +*).
- **Enable / Disable Toggle**: Dedicated checkbox on the Main tab to enable or disable the primary monitor highlight hotkey entirely without losing your saved key combination.

### 🟣 Twitch Helix Integration
- **Zero-Setup OAuth**: One-click login using a self-contained local web server callback. Automatically validates your token and discovers your Twitch User ID and Channel Name.
- **Broadcaster & Moderator Role Support**: Seamlessly executes commands whether you are the channel owner or an authorized Twitch Channel Moderator.
- **Up to 4 Customizable Hotkeys**:
  - `/marker [username]` or `/marker [description]` – Instantly places stream video markers for quick VOD review and clipping.
  - `/announce [description]` – Sends highlighted chat announcements (*Primary, Blue, Green, Orange, Purple*).
  - `/shoutout [username]` – Issues native Twitch streamer follow shoutout cards.
- **Streamer Mode vs. Desktop Modal Popups**:
  - **Streamer Mode (Enabled by default)**: Uses non-intrusive transparent HUD overlays and auto-fading toasts so game captures and full-screen streaming are never interrupted.
  - **Non-Streamer Mode (Disabled)**: Switches to standard desktop modal dialogs with title bars, context prompts, and message boxes with "OK" confirmation buttons so desktop users and mods can read responses at their own pace.
- **Instant Auto-Focused Modal**: When an action requires text input, the input prompt appears with immediate keyboard focus—start typing right away without touching your mouse:
  - Text input is auto-focused with typing cursor active immediately via Win32 foreground activation.
  - Press **Enter** to submit • Press **Esc** or click outside / Cancel to dismiss.
- **HUD Toast & System Tray Feedback**: Real-time on-screen HUD alerts and balloon notifications confirm action status (*e.g., marker timestamp, chat message status, cooldown warnings*).
- **Diagnostics, Debug Logging & Automated Crash Capture**:
  - Checkbox and "debug.txt" button on the System settings screen logs all hotkey events, window actions, Twitch API requests, and responses.
  - Global crash interceptor (`sys.excepthook`, `threading.excepthook`, and `faulthandler`) catches unexpected errors and writes full stack traces to `%APPDATA%\ThaWizanator_Overlay\crash_log.txt` with one-click access in Settings.

### 🗂️ Clean 5-Tab Modern Settings Layout
- **Main Tab (🏠)**: Streamer Mode toggle (in-game HUD vs. desktop modals) and primary activation hotkey recorder.
- **Monitor Tab (🖥️)**: Display selection dropdown and on-screen monitor identification overlay.
- **Alert Overlay Tab (🎨)**: Border RGB color picker, thickness slider, opacity/transparency slider, and breathing/flashing effects.
- **Twitch Tab (🟣)**: Account linking, broadcaster channel name, and up to 4 custom macro hotkeys with safe row management.
- **System Tab (⚙️)**: Integrated updater, startup update checks, Windows startup launch option, diagnostics/logging, crash logs, and app folder shortcuts. Compact 520x545 size cleanly fits on any monitor.

### 🔄 GitHub Application Updates & Auto-Updater
- **Direct GitHub Releases Integration**: Checks for new versions directly against GitHub Releases without requiring manual downloads.
- **Interactive Update Prompts**: When an update is detected, presents an alert asking whether to update now or later.
- **Opt-In Auto-Updating**: Checkbox option to automatically download new versions in the background when available and prompt for restart.
- **Safe Self-Replacing Executable**: Standalone builds safely swap out the running `.exe` via a detached PowerShell updater process and relaunch the new version.

---

## 🚀 Getting Started

### Prerequisites
- **Operating System**: Windows 10 or Windows 11
- **Python**: Version 3.10 or newer (tested up to Python 3.14)

### Installation
1. Clone this repository:
   `ash
   git clone https://github.com/thawizanator/hotkey-overlay-alert.git
   cd hotkey-overlay-alert
   `

2. Create and activate a Python virtual environment:
   `powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   `

3. Install required dependencies:
   `powershell
   pip install -r requirements.txt
   `

4. Launch the application:
   `powershell
   python main.py
   `

---

## 🛠️ Building Standalone Executable

To compile a standalone .exe with embedded icon and resources using PyInstaller:

```powershell
.\venv\Scripts\pyinstaller.exe --noconfirm main.spec
```

The compiled binary will be placed in `dist\HotKeyOverlayAlert.exe` and `dist\main.exe`.

---

## 🛡️ Antivirus & Windows SmartScreen Notice

If Windows Defender SmartScreen, Avast CyberCapture, or other antivirus software displays an alert or popup when first launching the standalone `.exe`, **this is a normal false positive common to newly compiled Python tools**.

### Why does this happen?
1. **PyInstaller Packaging**: The standalone executable is bundled using PyInstaller, which packs Python and dependencies into a self-extracting archive in `%TEMP%`. Many heuristic scanners flag newly seen packed executables until they gain public reputation.
2. **Global Hotkey Hooks**: The app listens for global hotkeys across Windows using standard low-level Windows keyboard hooks (`SetWindowsHookEx`), an API heuristic security tools monitor closely.
3. **New Release & Zero Cloud Reputation**: Antivirus cloud networks (such as Avast Cloud or Microsoft SmartScreen) rely on crowd-sourced download telemetry. Brand-new releases have not yet accumulated enough worldwide downloads to be automatically whitelisted by cloud engines.

### How to verify & proceed safely:
- **100% Open Source**: You can review and inspect every line of Python code directly in this repository.
- **Digitally Signed**: The binary is Authenticode signed and timestamped with a DigiCert timestamp server.
- **Run from Source**: If you prefer not to run the pre-compiled `.exe`, you can run the app directly with Python (`python main.py`) or compile it yourself (`pyinstaller --noconfirm main.spec`).
- **In Avast**: Allow the CyberCapture analysis to complete (it will verify the file clean), or click **More Details** → **Run Anyway**.
- **In Windows SmartScreen**: Click **More Info** → **Run anyway**.

---

## ⚙️ Configuration & Storage

Settings are automatically synchronized to:
- `%APPDATA%\ThaWizanator_Overlay\config.json`
- `./config.json` *(local fallback)*

Sensitive OAuth credentials are obfuscated and stored locally only. A template is provided in [config.example.json](config.example.json).

---

## 👤 Author & Support

- **Created by**: ThaWizanator
- **Twitch**: [twitch.tv/thawizanator](https://twitch.tv/thawizanator)
- **Version**: 2.3.3 (October 2026)

---

## 📄 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
