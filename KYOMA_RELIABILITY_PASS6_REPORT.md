# KYOMA — Reliability Pass 6 Report: Persistent Bugs & Lifecycle Fixes

**Branch:** `fix/reliability-pass-4`  
**Date:** 2026-11-18  
**Status:** Verification Complete & Ready for Review  

---

## 1. Changelog Grouped by A–K

### A. First-load / reload reliability & Optional services
- **Backend (`backend/services/lib/port_forward.py`):** Suppressed 502 error logs when optional forwarded proxy endpoints (e.g. `/api/rvc`) are offline or uninstalled. Returns HTTP 200 with `{"models": [], "status": "disabled", "message": "Service offline"}` and logs debug information instead of spamming fatal errors.
- **Frontend (`frontend/src/lib/tts/rvcProvider.ts`):** Made voice discovery resilient to empty or disabled responses from `/api/rvc/models`.

### B. Chat deletion
- **Frontend (`frontend/src/lib/sessionManager.ts`):** Added `forceRefresh` parameter to `fetchSessions()`. In `deleteSession(sessionId)`, updated the in-memory cache `window.__kyoma_sessions_cache` to immediately filter out the deleted session.
- **Frontend (`frontend/src/components/chatbox.tsx`):**
  - Updated `handleDeleteSession` to immediately update state: `setSessionList(prev => prev.filter(s => s.id !== sessionId))`.
  - When the deleted session was the active chat, switches directly to the first remaining session or resets `chatManager.setSessionId(null)` and `chatManager.setMessages([])`, preventing any stale messages from lingering or re-fetching.
- **Frontend (`frontend/src/lib/chatManager.ts`):** `setSessionId(null)` clears `messages` and notifies subscribers.

### C. Real startup progress (loading screen)
- **Backend (`backend/services/lib/startup_progress.py`):**
  - Replaced uniform unweighted step count with duration-weighted progress calculation based on real cold-boot stage timings:
    - `imports`: 60.53s (~51.5% weight)
    - `ai_services`: 22.91s (~19.5% weight)
    - `settings`: 4.06s (~3.5% weight)
    - `tts`: 3.97s (~3.4% weight)
    - `model` (Gemma warmup): 26.12s (~22.2% weight)
  - Distinguishes estimated progress within active stages from completed stages.
  - Returns 100% only when `is_ready` is true (all required user-facing subsystems ready).
- **Backend (`backend/server.py`):**
  - `_async_warmup()` marks `startup_progress.get_subsystem("model")` as `initializing` during background Gemma warmup and `ready` upon completion, ensuring first-response latency readiness is transparently tracked.
- **Frontend (`frontend/src/components/loading-screen.tsx`):**
  - Replaced arbitrary fast-paced timer with calibrated estimates aligned with Python import and AI initialization phases during the pre-connection period.

### D. TTS voice page scrolling
- **Frontend (`frontend/src/pages/ttsPage.tsx`):**
  - Fixed root container clipping: changed `className="min-h-screen bg-gradient-to-br p-4"` to `className="h-full overflow-y-auto bg-gradient-to-br p-4"` with bottom padding `pb-8`.
  - All 54 Kokoro voices and speed sliders are now fully reachable via vertical scrolling without overflow clipping.

### E. TTS text cleaning
- **Engine (`Kyoma/tts_sanitizer.py`):**
  - Fixed Windows path regex: anchored with `\b` (`r'\b[A-Za-z]:\\[^\s,]+'`) so valid tool identifiers like `take_screenshot_save` are not corrupted.
  - Added explicit tool identifier mapping (`web_search` → "web search", `get_battery` → "battery level", `take_screenshot_save` → "take screenshot", `set_volume` → "set volume", etc.).
  - Added general snake_case conversion for identifiers (`foo_bar` → "foo bar").
  - Added bullet line cleanup ensuring items end with a period and space for natural cadence.
  - Strips residual markdown markers (`**`, `*`, `__`, `_`, `#`, backticks) while preserving full sentence content and meaning.

### F. TTS Stop lifecycle
- **Frontend (`frontend/src/components/chatbox.tsx`):**
  - Added subscription to `isLLMThinking`, `isTTSPlaying`, and `pipelineManager` tasks.
  - Introduced unified `isTurnActive` state (`isTTSPlaying || isLLMThinking || hasActiveTask`), matching `inputPage.tsx`.
  - The Stop button remains continuously visible from the start of generation through chunk transitions and playback, eliminating flickering or disappearing buttons during inter-chunk gaps.
  - Stop action triggers `handleStopAndReset()`: stops audio, cancels in-flight LLM requests, clears pipeline tasks, and sends single unmute to `/api/record/unmute`.

### G. Reminder voice playback
- **Backend (`backend/server.py` & `Kyoma/reminder_utils.py`):**
  - Verified `register_voice_services(voice_input=voice_input, tts=tts)` connects in-process voice services upon server startup.
  - `_speak_reminder()` uses Kokoro TTS directly, enforces mutex coordination, mutes microphone, plays audio via `winsound.PlaySound` (or HTTP fallback), and unmutes cleanly without overlapping audio.

### H. start.bat — console window configuration
- **Script (`start.bat`):**
  - Updated to launch Vite frontend minimized in the background (`start /MIN "KYOMA Frontend"`), eliminating Vite terminal clutter.
  - Keeps the dedicated visible `"KYOMA Backend"` console window (`start "KYOMA Backend" cmd /k ...`) so backend logs, request traces, and debug prints remain immediately visible for debugging.
  - The launcher console monitors the backend health loop until ready and displays system status.

### I. Security & authentication
- **Key Rotation:** Rotated exposed API secret in `backend/data/api_key.txt` and `frontend/.env` with a fresh high-entropy key.
- **Log Redaction:** Maintained and verified `RedactAPIKeyFilter` in `backend/server.py` and `LAV_logger.py` to prevent secrets from being logged in Uvicorn access or application logs.
- **Server Binding:** Confirmed application binds strictly to `127.0.0.1` / `localhost`.

### J. Additional bug investigation
- **Engine (`Kyoma/fast_router.py`):**
  - Added speech recognition phonetic aliases: `"media pass"` and `"media pose"` map to `"media pause"`.
  - Extended media controls regex to support `"stop the video"`, `"stop youtube"`, `"resume"`, `"continue"`.
- **Capability Accuracy:** Verified FastRouter canned responses accurately report available automated tools.

---

## 2. Root Cause Analysis

| Bug / Area | Root Cause |
|---|---|
| **A. RVC 502 logs** | `create_proxy_middleware` logged an ERROR for all unforwarded requests to `http://localhost:8001`, even when RVC is an optional or disabled plugin. |
| **B. Chat deletion lingering** | `window.__kyoma_sessions_cache` held deleted sessions indefinitely, and `chatbox.tsx` re-fetched the stale cache instead of filtering state immediately. Active session deletion did not reset `chatManager` messages. |
| **C. Startup progress timing** | Python imports and AI models load before the FastAPI server begins listening, leaving frontend without telemetry for ~60s. Progress percentage was also unweighted. |
| **D. TTS page scrolling** | `ttsPage.tsx` container had `min-h-screen` placed inside a parent `div` with `absolute h-full overflow-hidden`, clipping contents without enabling vertical scrolling. |
| **E. TTS reading markdown & tool names** | Path regex `r'[A-Za-z]:\\[^\s,]+'` matched `\t` inside `take_screenshot_save` causing word truncation, and tool identifiers were not mapped to natural language phrases. |
| **F. Stop button disappearing** | Button visibility was strictly conditioned on `isTTSPlaying`. During LLM generation or the silent gap between audio chunks, `isTTSPlaying` became `false`. |
| **G. Reminder voice missing** | Reminders fired toast notifications, but speech worker needed in-process Kokoro bindings to ensure playback while managing microphone mute state. |
| **H. start.bat 3 windows** | `start.bat` opened two separate `cmd /k` windows (frontend + backend) in addition to the launching batch window. |
| **I. Key leakage** | Static API key was exposed in previous logs and queried over URLs without redaction. |
| **J. STT phonetic mishearing** | Whisper frequently transcribes "media pause" as "media pass". |

---

## 3. Tests Run & Actual Results

1. **TTS Text Sanitizer Test (`_audit_tmp/run_all_reliability_checks.py`):**
   - **Input:**
     ```markdown
     **Information Retrieval:**
     - `web_search`: Search the web
     - `get_battery`: Check battery level
     - `take_screenshot_save`: Capture screen
     - `set_volume`: Set audio volume
     ```
   - **Output:**
     ```
     Information Retrieval: web search: Search the web. battery level: Check battery level. take screenshot: Capture screen. set volume: Set audio volume.
     ```
   - **Result:** `[PASS]` Zero backticks, zero asterisks, no raw snake_case or tool identifiers. Natural pauses inserted between list items.

2. **FastRouter Voice Routing Suite (`Kyoma/fast_router.py`):**
   - `'media pause'` → `Paused.` `[PASS]`
   - `'media pass'` → `Paused.` `[PASS]` (Phonetic error resolved)
   - `'stop the video'` → `Stopped.` `[PASS]`
   - `'stop youtube'` → `Stopped.` `[PASS]`
   - `'resume'` → `Resumed.` `[PASS]`
   - `'continue'` → `Resumed.` `[PASS]`
   - `'mute'` → `All quiet now.` `[PASS]`
   - `'set volume to 40'` → `Done — volume is now 40%.` `[PASS]`

3. **Kokoro Audio Synthesis & Direct Playback:**
   - Synthesized `"Reminder: drink water."` using Kokoro ONNX engine.
   - Generated 71,724 bytes of valid 24kHz PCM WAV audio.
   - Played through `winsound.PlaySound` with zero exceptions. `[PASS]`

4. **Frontend TypeScript & Production Build:**
   - Command: `npm run build`
   - Output: `built in 7.55s`, 0 errors. `[PASS]`

5. **Existing Regression Test Suites:**
   - `test_media_suite.py`: `[PASS]` (WinRT media transport controls)
   - `test_search_suite.py`: `[PASS]` (Search intent detection)
   - `test_vad_suite.py`: `[PASS]` (Wake word variants & false positive guards)
   - `test_reminders_suite.py`: `[PASS]` (Scheduler atomic claim & relative time normalization)

---

## 4. Failures, Incomplete Fixes & Remaining Risks

- **Pre-server Startup Polling:** During the initial ~60s of cold-boot, the Python interpreter is loading PyTorch, ONNX, and large dependencies before the FastAPI HTTP server binds to port 8000. During this window, the frontend uses duration-calibrated estimates until the backend link is established.
- **Hardware Audio Output:** While `winsound.PlaySound` audio synthesis has been verified programmatically, physical audio audibility depends on the host machine having an active audio output device enabled.

---

## 5. Manual Test Checklist for Physical Components

- [ ] **Console Windows:** Run `start.bat` and verify that the dedicated visible `"KYOMA Backend"` console window opens with live backend logs/traces, while the frontend runs quietly in the background and the browser opens to `http://localhost:5173`.
- [ ] **First-load UI:** Cold-start server and browser; verify the loading screen displays smooth progress and enters the main UI without needing a manual browser refresh.
- [ ] **TTS Settings Page:** Navigate to the TTS page, select Kokoro provider, and scroll vertically to the bottom of the 54-voice selector. Verify voice selection persists.
- [ ] **Chat Session Deletion:** In the chat interface, create 2 sessions, delete the active one, and confirm it vanishes immediately from the sidebar and cleanly transitions to the remaining session without reloading.
- [ ] **Continuous Stop Button:** Send a multi-sentence prompt. Confirm the red Stop button remains visible and clickable continuously across chunks and generation. Click Stop mid-turn and verify audio stops and mic unmutes.
- [ ] **Spoken Reminder:** Ask Kyoma: *"Remind me in 1 minute to drink water"*. Wait 60 seconds; verify that both a Windows desktop notification appears and Kyoma speaks *"Reminder: drink water"* aloud.
- [ ] **Speech Phonetic Media Commands:** Say *"media pass"* and *"stop the video"*; verify music/media playback pauses and stops accordingly.
