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

### 🟣 Twitch Helix Integration
- **Zero-Setup OAuth**: One-click login using a self-contained local web server callback. Automatically validates your token and discovers your Twitch User ID and Channel Name.
- **Up to 4 Customizable Hotkeys**:
  - /marker [description] – Instantly places stream video markers for quick vod review and clipping.
  - /announce [description] – Sends highlighted chat announcements (*Primary, Blue, Green, Orange, Purple*).
  - /shoutout [username] – Issues native Twitch streamer follow shoutout cards.
- **Centered Description Overlay**: When an action requires a description or username, a sleek modal appears in the middle of your screen:
  - Text input is auto-focused with typing cursor active immediately.
  - Translucent backdrop with dark theme.
  - Press **Enter** to submit • Press **Esc** or click outside to dismiss.
- **System Tray Feedback**: Real-time balloon notifications confirm when stream markers or announcements succeed or explain why an action failed (*e.g. stream is offline*).

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
- **Version**: 2.1.1 (October 2026)

---

## 📄 License
This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
