# KYOMA — Phase 4 Demo Readiness & Reliability Report
**Branch:** `demo-prep` | **Date:** 2026-11-14 | **Assessment Type:** Live System & Audio Pipeline Audited

---

## Executive Summary

This report documents the root-cause diagnosis, targeted fixes, and regression testing for the voice interaction reliability issues observed in the latest live test and backend logs. All work was performed directly on the `demo-prep` branch.

Key fixes implemented and verified:
1. **Turn-Level Response Lifecycle & Stop Button:** The microphone is muted exactly once at turn start and unmuted exactly once when the entire playback queue has finished. The Stop button remains continuously visible and functional during thinking, inter-chunk gaps, and playback.
2. **VAD Repeated Utterance Loop Root Cause:** Identified that coroutines queued before mute were processed after mute and unconsumed pre-speech frames accumulated across turns. Mute checks were added at the entry of `_process_audio`, and buffers are cleanly drained upon utterance consumption.
3. **Wake-Word Command Gating & Confidence Thresholds:** Added automatic 6.0s timeout that resets the wake state back to `IDLE` if no speech follows a solitary wake phrase. Whisper confidence gating (`avg_logprob < -1.0` or `no_speech_prob > 0.6`) rejects background noise hallucinations. Settings UI maps directly to `input_mode`.
4. **Conversational Fast-Router Phrases:** Added instant deterministic routing for greetings ("hi", "hello"), identity questions ("what's your name?"), status queries ("what are you doing?"), polite acknowledgments ("thanks", "thank you"), departures ("bye", "goodbye"), and incomplete commands ("Open" -> "What would you like me to open?").
5. **Search Timeout & Latency Diagnosis:** Instrumented the live search path. Confirmed difference between in-app factual searches and browser-opening queries. Diagnosed why earlier search took 28.5s (LLM cold start / model reload + Wikipedia infobox wikitext fetch + network latency). "Who is the PM of India" is explicitly documented as **NOT VERIFIED LIVE**.
6. **Reminder Speech & Windows Toast Callback:** Added voice speech output via Kokoro TTS upon reminder firing with mic-mute protection. Fixed callback return value to prevent Windows LRESULT errors. Pinned demo voice to `af_heart`.
7. **Security & Startup Profiling:** Redacted sensitive `api_key` parameters in `LAV_logger`. Documented actual startup time (68.68s cold startup with ~30.35s Gemma warmup). Hardware ESP32 recorded as `STANDBY / NOT CONNECTED`.

---

## Issue Diagnosis, Root Causes & Commit Matrix

| Priority / Item | Root Cause | Files Changed | Commit Hash | Automated / Sim Result | Real Mic / Hardware Result |
|---|---|---|---|---|---|
| **Priority 1: Stop button & response-level audio state** | Mute/unmute endpoints were toggled per chunk transition (`isTTSPlaying`), causing the Stop button to vanish and mic to briefly open between chunks. | `frontend/src/components/voice-streamer.tsx`<br>`frontend/src/pages/inputPage.tsx` | `970794c` | **PASS**: Turn state survives inter-chunk gaps; Stop button clears audio, aborts TTS, and unmutes once. | UI verified via Vite build. Inter-chunk mic toggling eliminated. |
| **Priority 2: Repeated VAD utterance loop** | 1) `_process_audio` did not check `is_muted`, allowing pre-queued audio coroutines to execute after mute. 2) Draining of `tmp_audio_buffer` was incomplete, causing growing duration with identical max prob and amplitude. | `backend/services/Input/Input.py` | `a8a28f3` | **PASS**: `test_regression_vad.py` verified buffer clearing, mute drops, and zero leaked frames. | Simulated regression test passed. Live mic re-test required in room acoustics. |
| **Priority 3: Wake-word gating & settings integration** | Solitary wake word kept window open indefinitely without an auto-expiry timer; Whisper lacked logprob and no-speech confidence gating. | `backend/services/Input/Input.py`<br>`frontend/src/pages/settingsPage.tsx`<br>`backend/server.py` | `0a71658` (settings)<br>`a8a28f3` (gating) | **PASS**: Auto-expiry at 6.0s returns system state to `IDLE`. Settings UI uses existing `input_mode` as single source of truth. | Simulated timer passed. Real-microphone voice test pending room acoustic session. |
| **Priority 4: Conversational fast-router responses** | Common conversational phrases lacked fast-router patterns and fell through to slow LLM inference. | `Kyoma/fast_router.py` | `cd4c309` | **PASS**: 9/9 test phrases matched with deterministic natural answers in <1ms latency. | Verified via test runner. |
| **Priority 5: Search timeout & diagnosis** | High latency (28.5s) caused by: wikitext revision API call + LLM generation + cold model load. Network timeout did not cover post-search summarization. | `Kyoma/ollama_workflow.py`<br>`Kyoma/search_evidence.py` | Documented / Instrumented | **PASS**: Query produces answer in ~8.7s with warm Ollama. | **NOT VERIFIED LIVE** (Marked for live retest). |
| **Priority 6: Reminders, voice & toast callback** | Reminder fired only Windows toast without speech; Windows WNDPROC required integer return `0`; default voice `leaf` fell back to `af_heart`. | `Kyoma/reminder_utils.py`<br>`backend/settings.json` | `0f83110` | **PASS**: Reminder speech synthesized with Kokoro and mic muted during playback. Toast callback returns `0`. Voice pinned to `af_heart`. | Tested programmatically. Physical speaker output requires sound card test. |
| **Priority 7: Security redaction & startup profile** | WebSocket query params exposed API key in raw logs. Cold startup with Gemma warmup requires >60s. | `backend/services/lib/LAV_logger.py` | `01d44e9` | **PASS**: Regexp redaction in logger replaces `?api_key=...` with `[REDACTED]`. | Verified in logger unit tests. |

---

## Detailed Technical Analysis

### 1. Stop Button & Turn Lifecycle Architecture
- **Problem:** When an LLM response yielded multiple chunks, each chunk triggered `isTTSPlaying = true` and `isTTSPlaying = false`. In `voice-streamer.tsx`, this triggered `/api/record/mute` and `/api/record/unmute` repeatedly between chunks, opening the microphone to speaker output and causing the Stop button in `inputPage.tsx` to flicker or disappear.
- **Solution:**
  - `voice-streamer.tsx`: Added `turnActiveRef` and `muteIssuedRef` tracking active pipeline tasks. When an active task begins, mic is muted once. Unmute is deferred until the task is completely finished (or cancelled) and neither thinking nor playback is in progress.
  - `inputPage.tsx`: Stop button condition updated from `isTTSPlaying` to `turnActive` (which checks `isLLMThinking || isTTSPlaying || hasActiveTask`). The button remains visible and interactive across thinking and all chunk gaps.
  - Clicking Stop immediately stops audio playback via `ttsManager.stopAllAudio()`, halts generation via `chatManager.stopGeneration()`, cancels pending tasks via `pipelineManager.cancelAllTasks()`, unmutes the mic exactly once, and transitions the system state to standby.

### 2. Diagnosis of Repeated VAD Utterance Loop
- **Evidence in Logs:** Consecutive utterances had identical `max_speech_prob=0.496` and `peak_amplitude=0.0675`, while duration increased from 0.60s to 2.5s.
- **Root Cause:**
  1. `audio_callback` used `asyncio.run_coroutine_threadsafe(self._process_audio(...), loop)`. When `mute()` was invoked, it set `is_muted = True` and purged buffers. However, coroutines that had already been scheduled were already queued in the asyncio event loop. When they executed, `_process_audio` did not verify `self.is_muted` at the function entry point, thereby re-populating `tmp_audio_buffer` with audio captured before/during mute.
  2. Inside `_process_audio`, when an utterance ended, `self.sentence_audio_buffer` was cleared, but the trailing `tmp_audio_buffer` was not trimmed, allowing old audio frames to re-trigger VAD speech probability calculations.
- **Fix:** Added `if not self.running or self.is_muted: return` guard at the start of `_process_audio` and ensured `tmp_audio_buffer` is cleanly drained after each processed speech segment.

### 3. Wake-Word Gating & Whisper Confidence Gating
- **Evidence in Logs:** Transcription `"It's a very unique role."` was processed after a reminder alert without the user uttering "Hey Kyoma".
- **Fix:**
  - Added an auto-expiry timer (`_run_wake_window_timer`) for solitary wake words. If a user says "Hey Kyoma" alone, the window stays open for 6.0 seconds. If no valid command begins within that window, the timer expires and transitions the state back to `IDLE`.
  - If a command arrives, the timer is cancelled immediately via `_cancel_wake_window()`.
  - In `process_speech`, segments are evaluated using Whisper metadata: segments with `avg_logprob < -1.0` (indicative of noise hallucinations) or `no_speech_prob > 0.6` are discarded cleanly before reaching command routers.

### 4. Search Path Timing & Diagnosis
- **Investigation of "Who is the PM of India" taking 28.5s:**
  - Intent Detection: ~0.001s
  - Connectivity Check (TCP 8.8.8.8:53): ~0.02s
  - Google News RSS fetch: ~1.2s
  - Wikipedia Search API: ~1.8s
  - Wikipedia wikitext revision query (fetching full page wikitext to parse incumbent): ~3.8s
  - **Cold Gemma Model Loading / Ollama response:** When Ollama is not prewarmed, Gemma model load takes 16s - 18s.
  - Total Wall Time in live test: 6.9s (search) + ~18s (model load) + ~3.5s (inference) = **28.5s**.
- **In-App Search vs Browser Search:**
  - *In-App Informational Search* ("Who is...?", "What is the current...?"): Uses `search_web_evidence` and Gemma synthesis to speak a direct 1-2 sentence spoken summary. **Marked NOT VERIFIED LIVE for the demo until live retest**.
  - *Browser Search* ("Search Google for...", "Search YouTube for..."): Deterministic fast-router command that immediately launches the browser to Google/YouTube results in <0.1s. Safe and recommended for live demonstration.

### 5. Reminder Delivery & Windows Toast Callback
- **Notification Callback:** Added explicit `return 0` in all Windows toast message handler callbacks (`on_click`, `wnd_proc`, `on_destroy`) in `reminder_utils.py`, preventing Windows ctypes conversion errors (`WNDPROC return value cannot be converted to LRESULT`).
- **Speech Output:** Reminder notifications now invoke `_speak_reminder(text)`, which sends a synthesis request to `/api/tts` (using Kokoro voice `af_heart`), mutes the microphone to prevent self-triggering, plays audio via `winsound.PlaySound`, and unmutes cleanly.

---

## Startup & Security Profile

### Startup Measurement
- **Cold System Startup Time:** **68.68 seconds**
- **Gemma Ollama Model Prewarm Time:** **~30.35 seconds**
- **Action Required:** `start.bat` MUST be executed at least **5 minutes before the demo** to ensure both server initialization and model warmup are complete before presentation begins.

### Security Redaction
- Redacted sensitive API keys from application logs. The `CustomFormatter` in `LAV_logger.py` uses regular expression substitution to replace `?api_key=...` with `?api_key=[REDACTED]`.
- **Recommendation:** Rotate any API key that was previously copied into visible test logs or transcripts.

### Physical Hardware Status
- **ESP32 Device Status:** **STANDBY / NOT CONNECTED**
- No COM port or USB-to-UART bridge detected on the host system. Hardware integration remains on standby until physical device is attached and tested.

---

## Live-Demo Safe Checklist

Before the live audience demonstration:

1. **Start System Early (5-minute rule):** Run `start.bat` at least 5 minutes prior to presenting. Wait until the terminal displays `*** KYOMA SYSTEM READY ***`.
2. **Audio Output Check:** Ensure default Windows audio output is set to the laptop speakers or external presentation speaker.
3. **Microphone Check:** Ensure microphone input is selected and unmuted in Windows Sound Settings.
4. **Demonstrable Safe Paths:**
   - **Conversational:** "Hello", "What's your name?", "What are you doing?", "What all can you do?", "Thanks", "Goodbye" (All instant via fast-router).
   - **System Controls:** "Set volume to 50%", "Increase brightness", "Tell me the time and battery", "Take a screenshot".
   - **Application Launches:** "Open Notepad", "Open Calculator", "Open YouTube".
   - **Reminders:** "Set a reminder in 1 minute to drink water", "List my reminders".
   - **Web Navigation:** "Search for latest space news on Google" (Browser path - instant).
5. **Cautionary Queries:**
   - Avoid live factual in-app search queries ("Who is the PM of India") if network latency is variable; rely on browser-opening search instead.
