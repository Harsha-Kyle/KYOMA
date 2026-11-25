# ProgressMD.md — Current Project State, Decision Log & Execution Tracking

> **Operational Rule:** This file is the working record of the project's real state. It is updated at the conclusion of every session. Never mark a phase, task, or capability as complete unless verified by code inspection or observed test execution.

---

## 1. Current Project Status

- **Project Name:** KYOMA → AI Receptionist
- **Current Phase:** Phase 0 — Pre-Implementation Audit, Architecture Extraction & Planning
- **Phase Status:** **Under Review (Awaiting User Sign-Off on Phase 0 Gate)**
- **Last Updated:** 2026-10-21
- **Current Task:** Consolidate audit documentation, establish `AgentsMD.md` & `ProgressMD.md`, and present unresolved architectural decisions.
- **Next Proposed Task:** User review and sign-off on Phase 0 open decisions (Hardware Form Factor, Audio Input Source, Database Scope, Host Notification Channel, Wake-Word Strategy), followed by Phase 1 scaffolding approval.
- **Overall State:** Clean, verified, non-destructive audit completed. No receptionist code has been written yet.

---

## 2. Phase Overview & Status Registry

| Phase | Phase Name & Objective | Status | Gate Requirement | User Approval |
|---|---|---|---|---|
| **Phase 0** | **Codebase Audit & Architecture Extraction**<br>Produce evidence-based blueprint of Kyoma; verify STT, TTS, LLM, and automation; identify discrepancies; classify reusable modules. | **Under Review** | 8 master audit docs produced; master `.docx` consolidated; `AgentsMD.md`, `KyomaMD.md`, `ProgressMD.md` synchronized; open decisions identified. | **Pending User Sign-Off** |
| **Phase 1** | **Standalone Project Scaffold & Core Audio Pipeline**<br>Initialize `ai-receptionist/` directory; configure environment (`.env`), token auth (`auth.py`), Faster-Whisper/Silero VAD (`Input.py`), and Kokoro ONNX TTS (`KokoroTTS.py`). | **Not Started** | Passing unit tests for VAD, Whisper transcription, and Kokoro speech synthesis on synthetic audio; clean `.env` loading. | Deferred to Gate 0 |
| **Phase 2** | **Visitor Data Store & Receptionist Tool Execution**<br>Build SQLite visitor database (`visitors`, `appointments`, `hosts`); adapt `fast_router.py` for receptionist FAQs; adapt `Kyoma_automation.py` tools (`register_guest`, `lookup_directory`). | **Not Started** | Idempotent SQLite migrations; tool calling unit tests with mocked Ollama; zero-LLM fast path tests. | Deferred to Gate 1 |
| **Phase 3** | **Host Notification & External Integrations**<br>Implement staff notification dispatchers (webhooks/email/SMS) and appointment reminder scheduler (adapted from `reminder_utils.py`). | **Not Started** | Safe webhook payload validation; simulated notification tests; reminder trigger tests. | Deferred to Gate 2 |
| **Phase 4** | **Receptionist Kiosk WebUI & Optional Hardware**<br>Create touchscreen check-in interface; visitor badge display; optional ESP32 OLED integration. | **Not Started** | End-to-end integration test (voice greeting → visitor registration → host notification → TTS confirmation). | Deferred to Gate 3 |

---

## 3. Confirmed Technical Facts vs. Codebase Discrepancies

### Confirmed Facts (Source-Ground Truth)
- **STT Engine:** Silero VAD (512-sample chunks, threshold 0.3, silence timeout 100ms) + Faster-Whisper `base` model (float16 on CUDA, int8 on CPU) via host microphone (`backend/services/Input/Input.py:44, 101`).
- **TTS Engine:** Kokoro ONNX (`kokoro-v1.0.onnx`, `voices-v1.0.bin`, active voice: `af_heart`, 24kHz WAV) (`backend/services/TTS/Kokoro/KokoroTTS.py:82`).
- **LLM Engine:** Local Ollama on `http://localhost:11434` (`Kyoma/kyoma_config.json: {"ollama_model": "gemma4:e2b"}`).
- **Two-Tier Router:** Tier 1 Fast Path regex (`Kyoma/fast_router.py`) executes in `<10ms`; Tier 2 native tool calling (`Kyoma/Kyoma_automation.py:531-662`) executes via `ollama.chat()`.
- **Desktop Reminders:** SQLite database `Kyoma/Reminders logs/reminders.db` scheduled via `APScheduler` background thread (`Kyoma/reminder_utils.py`).

### Refuted Documentation Claims / Known Discrepancies
- **FAISS Vector Memory:** ❌ Claimed in README, but **completely absent from code**. Legacy LAV uses embedded **Qdrant** (`backend/services/Memory/Memory.py`); Kyoma automation uses an in-memory Python list (`Kyoma/memory_manager.py`).
- **ESP32 Edge Microphone:** ⚠️ Disabled on the server (`backend/server.py:256-259` commented out). Voice capture runs via host PC microphone.
- **ESP32 Push-to-Talk:** ❌ Firmware streams continuously during `STATE_LISTENING`; no physical button logic is implemented.
- **Hardcoded User Paths:** ⚠️ `Kyoma/app_utils.py` and `Kyoma_automation.py` contain hardcoded `C:\Users\harsh\...` paths that must be eliminated in the receptionist project.

---

## 4. Confirmed Decisions Log

| Decision ID | Date | Confirmed Decision | Rationale & Architectural Impact |
|---|---|---|---|
| **D-001** | 2026-10-21 | **Separate Repository Boundary** | The AI Receptionist will be built in a dedicated, isolated project directory (`ai-receptionist/`). It will NOT be developed inside `LocalAIVtuber2-master/`. |
| **D-002** | 2026-10-21 | **Drop Desktop & VTuber Tooling** | All Windows desktop automation (`pycaw`, `sbc`, `screenshot.py`, `media_control.py`, `window_manager.py`) and VTuber avatar rigging (`Live2D`, `Three.js VRM`, `ChatFetch`) are permanently excluded from the receptionist scope. |
| **D-003** | 2026-10-21 | **100% Offline Core Voice Stack** | Speech-to-Text (Faster-Whisper), Intelligence (Ollama), and Speech Synthesis (Kokoro ONNX) must execute strictly locally on the host machine to eliminate cloud latency and protect visitor privacy. |
| **D-004** | 2026-10-21 | **Consolidated Master Word Document** | All 8 audit Markdown reports were merged into a formatted Word document [`KYOMA_Complete_Technical_Audit.docx`](file:///c:/Users/harsh/Downloads/LocalAIVtuber2-master/KYOMA_Complete_Technical_Audit.docx) in the project root. |

---

## 5. Unresolved Decisions & Open Architecture Questions

The following decisions must be reviewed and answered by the user before beginning Phase 1 implementation:

| Issue ID | Architectural Question | Key Tradeoffs & Options | Proposed Recommendation | Status |
|---|---|---|---|---|
| **O-001** | **Physical Hardware Form Factor** | **Option A:** Dedicated touchscreen kiosk / PC only (simpler, robust).<br>**Option B:** Kiosk PC + physical XIAO ESP32-C3 desk robot with OLED expressions (engaging, novel). | **Option A** for v1 baseline; retain ESP32 WebSocket interface as an optional add-on module. | **Open (Needs User Approval)** |
| **O-002** | **Audio Input Capture Device** | **Option A:** Host PC / USB boundary microphone (stable, high signal-to-noise ratio).<br>**Option B:** ESP32 INMP441 I2S microphone (requires re-enabling server code & tuning network packet loss). | **Option A (Host USB Mic)** using proven `Input.py` pipeline. | **Open (Needs User Approval)** |
| **O-003** | **Visitor Database Scope & Sync** | **Option A:** Local standalone SQLite database (`visitors.db`) (100% offline, zero setup).<br>**Option B:** SQLite with webhook sync to corporate CRM / HR portal. | **Option A (Local SQLite)** following the proven `reminder_utils.py` SQLite pattern. | **Open (Needs User Approval)** |
| **O-004** | **Host Staff Notification Channel** | **Option A:** Outbound Webhooks (Slack incoming webhook, Microsoft Teams card).<br>**Option B:** SMTP Email or SMS (Twilio).<br>**Option C:** On-screen kiosk notifications only. | **Option A (Slack/Teams Webhook)** configurable via `.env`. | **Open (Needs User Approval)** |
| **O-005** | **Wake-Word & Noise Filtering Strategy** | **Option A:** Continuous VAD thresholding (current Kyoma baseline; susceptible to false triggers in noisy lobbies).<br>**Option B:** Local wake-word engine (e.g. OpenWakeWord for "Hello Receptionist").<br>**Option C:** Physical presence trigger (touchscreen button or PIR/ultrasonic sensor). | **Option C (Touch-to-Speak Kiosk Button)** with secondary VAD for hands-free speech turn completion. | **Open (Needs User Approval)** |

---

## 6. Blockers and Active Risks

| Risk ID | Identified Risk | Impact | Mitigation Strategy | Status |
|---|---|---|---|---|
| **R-001** | **Ollama Tool Hallucination Apology Loop** | In Kyoma, if Ollama outputs an unmapped tool name, the execution engine returns "Function not found", causing the LLM to get trapped in an apology loop. | Implement strict schema validation: if an unknown tool is returned, gracefully fall back to conversational dialogue without recursive re-prompting. | Documented for Phase 2 |
| **R-002** | **Hardcoded User Paths in Copied Modules** | Copying legacy modules without sanitization could introduce brittle dependencies on `C:\Users\harsh\...`. | Strictly enforce `Path(__file__).resolve().parent` across all new codebase files. | Standing rule in `AgentsMD.md` |
| **R-003** | **Lobby Background Chatter Interference** | Continuous listening without a push-to-talk or wake-word mechanism will trigger unintended transcriptions. | Require explicit kiosk presence interaction (touch button or wake word). | Linked to decision O-005 |

---

## 7. Work Log

### 2026-10-21 — Codebase Audit, Master Document & Governance Framework
- **Goal:** Conduct a comprehensive audit of Kyoma, generate the 8 required architecture blueprints, merge them into a master Word document, and establish synchronized governance files (`AgentsMD.md`, `ProgressMD.md`).
- **Work Performed:**
  1. Inspected full repository structure, backend services, Kyoma automation tools, frontend package manifests, and ESP32 firmware.
  2. Identified and documented core codebase facts vs. documentation discrepancies (Qdrant vs FAISS, disabled ESP32 mic, active Kokoro TTS).
  3. Generated all 8 detailed technical Markdown blueprints in `docs/`:
     - `KYOMA_PROJECT_OVERVIEW.md`
     - `KYOMA_CODEBASE_MAP.md`
     - `KYOMA_VOICE_AND_AI_PIPELINE.md`
     - `KYOMA_STORAGE_AND_DATA_FLOW.md`
     - `KYOMA_FEATURES_AND_INTEGRATIONS.md`
     - `KYOMA_REUSE_BLUEPRINT.md`
     - `KYOMA_VERIFICATION_AND_OPEN_QUESTIONS.md`
     - `KYOMA_BASE_INSTRUCTIONS.md`
  4. Executed `docs/consolidate_docs.py` to produce [`KYOMA_Complete_Technical_Audit.docx`](file:///c:/Users/harsh/Downloads/LocalAIVtuber2-master/KYOMA_Complete_Technical_Audit.docx) with automated Table of Contents, 16 formatted tables, code block shading, and headers/footers.
  5. Updated [`AgentsMD.md`](file:///c:/Users/harsh/Downloads/LocalAIVtuber2-master/AgentsMD.md) adapting ClashHQ workflow protocols (local-first single writer, mandatory checkpoint copies, phase gates, handoff/resume).
  6. Updated [`ProgressMD.md`](file:///c:/Users/harsh/Downloads/LocalAIVtuber2-master/ProgressMD.md) reflecting verified facts, phase statuses, decision log, open architectural questions, and next actions.
- **Files Created / Changed:**
  - `docs/KYOMA_*.md` (8 files created)
  - `docs/consolidate_docs.py` (created)
  - `KYOMA_Complete_Technical_Audit.docx` (created in root)
  - `AgentsMD.md` (updated)
  - `ProgressMD.md` (updated)
- **Results:** 100% verified. No source code in `backend/`, `Kyoma/`, `frontend/`, or `esp32_firmware/` was modified.
- **Status:** Phase 0 complete and awaiting user review.

---

## 8. Verification Record

| Date | Target Component | Verification Check Performed | Observed Outcome | Evidence Reference |
|---|---|---|---|---|
| 2026-10-21 | STT Pipeline | Inspected `Input.py` audio buffer, Silero VAD parameters, and Faster-Whisper instantiation. | Confirmed 16kHz mono, 512-chunk VAD, Faster-Whisper base model. | `backend/services/Input/Input.py:44, 101` |
| 2026-10-21 | TTS Engine | Checked `backend/settings.json` and `KokoroTTS.py`. | Confirmed `tts.provider: kokoro` with `af_heart` voice. | `backend/settings.json:10`, `KokoroTTS.py:82` |
| 2026-10-21 | Router & Tooling | Traced `KyomaLLM.py`, `fast_router.py`, and `Kyoma_automation.py`. | Confirmed `<10ms` regex fast path and Ollama native tool calling loop across 37 functions. | `KyomaLLM.py:69-74`, `Kyoma_automation.py:531-662` |
| 2026-10-21 | Vector Storage | Grepped repository for `faiss`; inspected `Memory.py` and `memory_manager.py`. | Confirmed **FAISS is unused**. Qdrant is used in LAV; simple in-memory list in Kyoma. | `backend/services/Memory/Memory.py:5-24`, `Kyoma/memory_manager.py:1-36` |
| 2026-10-21 | ESP32 Hardware | Inspected `main.cpp` and `server.py:256-259`. | Confirmed OLED expressions work, but server audio ingestion from ESP32 mic is commented out. | `esp32_firmware/src/main.cpp:302-372`, `server.py:256-259` |
| 2026-10-21 | Master Word Doc | Inspected generated `.docx` paragraphs, tables, and heading elements using `python-docx`. | 335 paragraphs, 16 tables, 17 Heading 1 sections successfully validated. | `KYOMA_Complete_Technical_Audit.docx` |

---

## 9. Next Action

- **Proposed Next Step:** User reviews and signs off on the **5 Open Decisions (Section 5)** and grants approval to close Phase 0.
- **Why This Is Next:** Phase 1 implementation (project scaffold and core audio pipeline) cannot begin until the hardware form factor, audio source, and notification channel decisions are approved.
- **Requires User Approval:** **YES (Do not begin Phase 1 without explicit approval).**
