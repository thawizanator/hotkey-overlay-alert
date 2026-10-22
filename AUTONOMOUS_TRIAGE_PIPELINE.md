# 🌿 Streamer Calyx Autonomous Support & Triage Pipeline

> **Master Protocol for Coding Agents Working on Streamer Calyx**  
> **Repository**: `thawizanator/hotkey-overlay-alert`  
> **Local Triage Queue**: `_monitior highlight/.triage/`  
> **Target Release**: Streamer Calyx Transition / `v3.0.0 Milestone`

---

## 🎯 Purpose

This document instructs the AI Coding Agent in the **Streamer Calyx** conversation on how to autonomously ingest, diagnose, rate, solve, and verify community bug reports and feature requests submitted via the **Calyx Support Agent** (Discord `/bug` & in-app 1-click dialog).

---

## 🔁 The End-to-End Workflow

```
[ Discord /bug or In-App ]
            │
            ▼
[ Calyx Support Bot ] ──► Creates GitHub Issue + Discord Thread + .triage/issue_NNN.json
            │
            ▼
[ Streamer Calyx Coding Agent ]
     1. Ingests ticket from .triage/ or GitHub
     2. Conducts root-cause codebase inspection
     3. Assigns standardized Urgency Rating (Critical -> Negligible)
     4. Prepares Confirmation Checklist & Solution Artifact
     5. Waits for ThaWizanator's explicit Approval
     6. Executes fix & runs automated unit tests
     7. Closes GitHub Issue -> Calyx Bot auto-updates Discord thread!
```

---

## 📥 Step 1: Ingesting Pending Issues

When the user asks to *"Check new bug reports"*, *"Review issue #42"*, or *"Triage pending tickets"*:

1. **Check Local Triage Inbox**:
   Scan `_monitior highlight/.triage/` for any `issue_*.json` files where `"status": "pending_solution"`.
   ```powershell
   Get-ChildItem -Path "_monitior highlight/.triage/*.json"
   ```
2. **Or Query GitHub Issues**:
   ```powershell
   gh issue list --repo thawizanator/hotkey-overlay-alert --label bug
   gh issue view <issue_number>
   ```

Each ticket contains:
- `title` & `description`
- `steps` (reproduction steps)
- `component` (Overlay, Director P2P, SLOBS/OBS, Twitch, Updater)
- `diagnostics` (Monitors, DPI scaling, Python runtime, VC++ redist)
- `logs` (security-sanitized traceback or debug bundle)
- `ai_diagnosis` (initial Gemini 1.5 Flash diagnosis)

---

## 🏷️ Step 2: Urgency Classification Schema

The Coding Agent **must** classify every issue into one of these 5 standard urgency tiers:

| Urgency Tier | Definition & Criteria | Example in Streamer Calyx |
| :--- | :--- | :--- |
| 🔴 **Critical / Blocker** | Fatal unhandled exception, crash on startup, thread crash, broadcast freeze, or irreversible data corruption. Requires immediate hotfix. | `NameError: name 'QTimer' is not defined` crashing director on P2P message; crash loop on monitor disconnect. |
| 🟠 **High / Urgent** | Core feature completely broken, but application remains running; security vulnerability; persistent connection loss. | WebRTC pairing rejected due to passkey salt mismatch; OBS/SLOBS WebSocket drops and cannot reconnect. |
| 🟡 **Medium / Moderate** | Secondary feature failure, performance stutter, UI flicker, intermittent glitch, or repetitive warning spam. | Highlight border overlay flashes when moving OBS between screens; volume mixer fader drag lag. |
| 🔵 **Low / Minor** | Minor cosmetic quirk, misleading tooltip, edge-case warning, non-breaking log noise. | Text contrast issue in Settings dialog; tray icon tooltip typo; redundant debug log line. |
| ⚪ **Negligible / Wishlist** | Feature request, visual polish, non-breaking convenience shortcut, or code refactor without user-facing bug. | Add 2px border radius to scenes button; clean up unused helper imports. |

---

## 📝 Step 3: Presenting the Solution & Confirmation Checklist

Before modifying any source code, the Coding Agent **must create an Implementation Plan Artifact** (or structured confirmation message) following this exact format:

````markdown
# 🐞 Bug Triage: Issue #[Number] - [Issue Title]

### 🏷️ Urgency Rating: [🔴 Critical / 🟠 High / 🟡 Medium / 🔵 Low / ⚪ Negligible]
> **Impact Assessment**: [Brief 1-2 sentence explanation of user impact during live broadcast]

---

### 🔍 Root Cause Analysis
- **Target File(s)**: `[filename.py:line_number]`
- **Root Cause**: [Explain exactly why the bug occurs in code]
- **Component**: `[Highlight Overlay / Director & P2P / SLOBS-OBS / Twitch / Updater]`

---

### 💡 Proposed Solutions
- **Option 1 (Recommended)**: [Detailed explanation of primary fix with pros/cons]
- **Option 2 (Alternative)**: [Alternative approach if applicable]

---

### ✅ Confirmation Checklist for ThaWizanator
- [ ] Approve **Option 1** fix in `[filename.py]`
- [ ] Target Release: `[v3.0.0-beta.4 / Upcoming Patch]`
- [ ] Automated Regression Tests:
  - [ ] Run `pytest tests/`
  - [ ] Verify error condition no longer raises exception
- [ ] Manual Streamer Verification Steps:
  1. Launch Streamer Calyx
  2. Perform [Step 1]
  3. Verify [Expected result]

**👉 Awaiting your confirmation to proceed with the fix.**
````

---

## 🛠️ Step 4: Execution & Verification Protocol

Once ThaWizanator approves the plan:
1. **Apply Code Changes**: Modify the specific files using clean, minimal edits. Preserve existing docstrings and unrelated code.
2. **Execute Unit Tests**:
   ```powershell
   py -3.11 -m pytest tests/ -v
   ```
3. **Update Local Ticket Status**:
   In `_monitior highlight/.triage/issue_[number].json`, update:
   ```json
   "status": "resolved",
   "resolved_at": "YYYY-MM-DDTHH:MM:SS"
   ```

---

## 🌐 Step 5: Closing the Loop (GitHub & Discord)

Close the GitHub issue using the GitHub CLI:
```powershell
gh issue close <issue_number> --comment "Resolved in commit $(git rev-parse --short HEAD) for release v3.0.0-beta.4. Verified via automated tests."
```

### 🤖 Automatic Discord Notification:
The **Calyx Support Bot** background service will automatically detect the GitHub close event and post a celebratory update in the user's Discord thread:
> 🎉 **GitHub Issue #NN was closed by @thawizanator!**  
> *Resolution: Fixed in commit `d8ddd16` for release `v3.0.0-beta.4`. Thank you for helping improve Streamer Calyx!*
