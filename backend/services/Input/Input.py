import asyncio
import json
import os
import re
import time
import wave
from fastapi import WebSocket
import sounddevice as sd
import numpy as np
import torch
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad, VADIterator
from ..lib.LAV_logger import logger

# ---------------------------------------------------------------------------
# Pre-compiled wake-word pattern (module-level to avoid re-compiling per chunk)
# Covers common Whisper mis-transcriptions of "Kyoma": coma, koma, kioma, keoma
# and possessive artifacts like "kyoma's".
# ---------------------------------------------------------------------------
WAKE_WORD_PATTERN = re.compile(
    r"\b(?:hey|hi|ok|okay|hello|your|you're)\s+(?:kyoma|kiyoma|kioma|kyomah|coma|koma|keoma)\b|"
    r"\b(?:kyoma|kiyoma|kioma|kyomah|keoma)(?:'s)?\b",
    re.IGNORECASE,
)

# Timeout (seconds) for a single Whisper transcription before the watchdog
# cancels it.
_WHISPER_WATCHDOG_TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# VAD configuration helpers
# ---------------------------------------------------------------------------

def _load_vad_config() -> dict:
    """
    Load VAD and input-mode settings from kyoma_config.json (Kyoma/ directory).
    Falls back to safe defaults if the file is absent or malformed.

    Supported keys:
        vad_silence_duration  (float, seconds)  — Default: 0.45 s.
        vad_speech_threshold  (float, 0–1)      — Default: 0.3.
        input_mode            (str)             — 'always_listening' | 'wake_word' | 'push_to_talk'.
                                                  Default: 'always_listening'.
        wake_word_timeout     (float, seconds)  — Command window after wake chime. Default: 6.0 s.
    """
    defaults = {
        "vad_silence_duration": 0.45,
        "vad_speech_threshold": 0.3,
        "input_mode": "always_listening",
        "wake_word_timeout": 6.0,
        "whisper_initial_prompt": "",
    }
    try:
        base = os.path.dirname(__file__)
        cfg_path = os.path.abspath(
            os.path.join(base, "..", "..", "..", "Kyoma", "kyoma_config.json")
        )
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if "vad_silence_duration" in user_cfg:
                defaults["vad_silence_duration"] = float(user_cfg["vad_silence_duration"])
            if "vad_speech_threshold" in user_cfg:
                defaults["vad_speech_threshold"] = float(user_cfg["vad_speech_threshold"])
            if "input_mode" in user_cfg:
                defaults["input_mode"] = str(user_cfg["input_mode"]).lower().strip()
            if "wake_word_timeout" in user_cfg:
                defaults["wake_word_timeout"] = float(user_cfg["wake_word_timeout"])
            if "whisper_initial_prompt" in user_cfg:
                defaults["whisper_initial_prompt"] = str(user_cfg["whisper_initial_prompt"]).strip()
    except Exception as e:
        logger.warning(f"[VAD] Could not load kyoma_config.json for VAD settings: {e}")
    return defaults


class VoiceInput:
    current_module_directory = os.path.dirname(__file__)
    MIC_OUTPUT_PATH = os.path.join(current_module_directory, "voice_recording.wav")

    SAMPLING_RATE = 16000
    input_language = "en"
    whisper_filter_list = [
        "you", "thank you", "thanks for watching", "thank you for watching",
        "thank you very much", "there is no message", "on the top of the door",
        "15%", "im going to put it in the fridge", "i", "okay", "bye", "so", "im sorry", "there are no messages"
    ]
    # Class-level defaults (preserved for backward compatibility).
    # Effective runtime values are set per-instance from kyoma_config.json.
    SPEECH_THRESHOLD = 0.3
    SILENCE_WAIT_TIME = 0.1 * SAMPLING_RATE   # original 0.1 s (kept as class attr)
    PRE_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    POST_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    MAX_UTTERANCE_SAMPLES = 15.0 * SAMPLING_RATE  # 15s max segment to prevent background audio accumulation

    running = False

    def __init__(self):
        # ── Load configurable VAD parameters ───────────────────────────────
        _vad_cfg = _load_vad_config()
        # Instance-level overrides so they can differ per config without
        # touching the class-level constants (which stay at original 0.1 s).
        self._vad_silence_duration: float = _vad_cfg["vad_silence_duration"]  # seconds
        self._vad_speech_threshold: float = _vad_cfg["vad_speech_threshold"]
        self._silence_wait_samples: int = int(self._vad_silence_duration * self.SAMPLING_RATE)
        self.input_mode: str = _vad_cfg.get("input_mode", "always_listening")
        self.wake_word_timeout: float = _vad_cfg.get("wake_word_timeout", 6.0)
        self.whisper_initial_prompt: str = _vad_cfg.get("whisper_initial_prompt", "")
        self.system_state: str = "IDLE"  # IDLE | LISTENING | THINKING | SPEAKING
        self._wake_active_until: float = 0.0
        self.state_callback = None  # async def callback(state: str) -> None
        self.barge_in_callback = None  # callable to interrupt active TTS/speaking
        self._last_state_broadcast = (None, 0.0)  # (state, timestamp) debounce guard

        logger.info(
            f"[VAD] silence_duration={self._vad_silence_duration:.3f}s "
            f"({self._silence_wait_samples} samples) | "
            f"speech_threshold={self._vad_speech_threshold:.2f} | "
            f"input_mode={self.input_mode}"
        )

        # ── Per-utterance diagnostic accumulators ───────────────────────────
        # Cleared at the start of each speech event; logged when it ends.
        self._utt_probs: list = []       # all speech_prob values during utterance
        self._utt_peak: float = 0.0      # peak absolute amplitude in utterance

        self._reset_buffers()
        self.last_transcription = None
        self.esp32_mode = False
        # Optional async callback (set by server) called with transcribed text in ESP32 mode.
        # Signature: async def callback(text: str) -> None
        self.esp32_pipeline_callback = None

        # Initialize AI models lazily/at instance level to avoid sys.meta_path issues on 3.13
        try:
            self.vad_model = load_silero_vad()
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            _compute_type = "float16" if self.device == "cuda" else "int8"
            self.whisper_model = WhisperModel("base", device=self.device, compute_type=_compute_type)
            self.vad_iterator = VADIterator(self.vad_model, sampling_rate=self.SAMPLING_RATE)
            self.stt_available = True
        except Exception as e:
            logger.error(f"Failed to initialize STT models: {e}")
            self.stt_available = False
            self.whisper_model = None
            self.vad_model = None
        self.processing_lock = asyncio.Lock()
        self.is_muted = False
        self.transcription_in_flight = False  # Guard against overlapping transcription jobs
        self._transcription_generation: int = 0  # Bumped on mute/unmute to discard stale Whisper results
        self._wake_window_task: asyncio.Task | None = None  # auto-close wake window on timeout

    def _reset_buffers(self):
        self.sentence_audio_buffer = []
        self.tmp_audio_buffer = []
        self.silent_samples = 0
        self.started_speaking = False
        # Reset per-utterance diagnostics
        self._utt_probs = []
        self._utt_peak = 0.0

    def mute(self):
        """Immediately discard incoming audio and purge all buffers."""
        self.is_muted = True
        self._reset_buffers()
        self._transcription_generation += 1  # invalidate any in-flight Whisper result
        self.transcription_in_flight = False
        if hasattr(self, 'vad_iterator') and self.vad_iterator:
            try:
                self.vad_iterator.reset_states()
            except Exception:
                pass
        logger.info("[STT] VoiceInput muted and buffers purged")

    def unmute(self):
        """Resume accepting audio and reset state cleanly."""
        self._reset_buffers()
        self._transcription_generation += 1  # invalidate any in-flight Whisper result
        self.transcription_in_flight = False
        if hasattr(self, 'vad_iterator') and self.vad_iterator:
            try:
                self.vad_iterator.reset_states()
            except Exception:
                pass
        self.is_muted = False
        logger.info("[STT] VoiceInput unmuted")

    async def start_streaming(self, clients):
        if self.running:
            return
        self.running = True
        self.is_muted = False
        self._reset_buffers()
        logger.info("Started recording")

        loop = asyncio.get_event_loop()

        def audio_callback(indata, frames, time, status):
            if not self.running or self.is_muted or self.esp32_mode:
                return  # Drop audio immediately when stopped, muted, or in ESP32 mode
            audio_np = indata.flatten().astype(np.float32) / 32768.0
            asyncio.run_coroutine_threadsafe(
                self._process_audio(audio_np, clients), loop
            )

        with sd.InputStream(samplerate=self.SAMPLING_RATE, channels=1, dtype='int16', callback=audio_callback):
            while self.running:
                await asyncio.sleep(0.1)

        self._reset_buffers()
        logger.info("Stopped recording")

    def stop_streaming(self):
        self.running = False
        self._reset_buffers()


    def set_esp32_mode(self, mode: bool):
        self.esp32_mode = mode
        if mode:
            logger.info("VoiceInput switched to ESP32 mode")
        else:
            logger.info("VoiceInput switched to Local mode")

    def process_esp32_audio(self, audio_bytes: bytes, clients):
        # Always accept audio from ESP32 regardless of self.running, so the
        # ESP32-only pipeline works without requiring the frontend to be open.
        if not self.esp32_mode:
            return
        if len(audio_bytes) == 0:
            return
        # Convert 16-bit PCM bytes to float32 numpy array
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            self._process_audio(audio_np, clients), loop
        )

    async def _process_audio(self, audio_np, clients):
        # Guard: drop stale coroutines that were queued before mute was set,
        # or if a transcription job is already in flight.
        # Discard them so old frames cannot leak into the next utterance.
        if not self.running or self.is_muted or self.transcription_in_flight:
            return

        self.tmp_audio_buffer.extend(audio_np)

        while len(self.tmp_audio_buffer) >= 512:
            # Re-check guards inside chunk loop
            if self.is_muted or self.transcription_in_flight:
                self.tmp_audio_buffer.clear()
                break

            chunk = np.array(self.tmp_audio_buffer[:512])
            self.tmp_audio_buffer = self.tmp_audio_buffer[512:]

            speech_prob = self.vad_model(torch.from_numpy(chunk), self.SAMPLING_RATE).item()

            # Broadcast to all connected clients — skip dead ones silently
            dead_clients = set()
            for client in list(clients):
                try:
                    await client.send_json({"type": "probability", "probability": speech_prob})
                except Exception:
                    dead_clients.add(client)
            clients -= dead_clients

            # Use instance-level configurable threshold and silence duration
            _threshold = self._vad_speech_threshold
            _silence_samples = self._silence_wait_samples

            if speech_prob < _threshold:
                if self.silent_samples <= _silence_samples:
                    self.silent_samples += 512
            else:
                self.silent_samples = 0
                if not self.started_speaking:
                    pre = self.sentence_audio_buffer[-int(self.PRE_SPEECH_SAMPLES):]
                    self.sentence_audio_buffer = list(pre)
                self.started_speaking = True

            # Accumulate per-utterance diagnostics during active speech
            if self.started_speaking:
                self.sentence_audio_buffer.extend(chunk)
                self._utt_probs.append(speech_prob)
                chunk_peak = float(np.max(np.abs(chunk)))
                if chunk_peak > self._utt_peak:
                    self._utt_peak = chunk_peak

            is_max_len = len(self.sentence_audio_buffer) >= self.MAX_UTTERANCE_SAMPLES
            if self.started_speaking and (self.silent_samples > _silence_samples or is_max_len):
                if not is_max_len:
                    post = self.tmp_audio_buffer[:int(self.POST_SPEECH_SAMPLES)]
                    self.sentence_audio_buffer.extend(post)

                async with self.processing_lock:
                    if self.transcription_in_flight:
                        self.vad_iterator.reset_states()
                        self._reset_buffers()
                        self.tmp_audio_buffer.clear()
                        continue

                    # ── Per-utterance diagnostics ──────────────────────────────
                    _all_samples = np.array(self.sentence_audio_buffer, dtype=np.float32)
                    _utt_dur_s = len(_all_samples) / self.SAMPLING_RATE
                    if self._utt_probs:
                        _rms = float(np.sqrt(np.mean(_all_samples ** 2))) if len(_all_samples) else 0.0
                        _avg_prob = float(np.mean(self._utt_probs))
                        _max_prob = float(np.max(self._utt_probs))
                        logger.info(
                            f"[VAD_DIAG] utterance_end | "
                            f"avg_speech_prob={_avg_prob:.3f} | max_speech_prob={_max_prob:.3f} | "
                            f"peak_amplitude={self._utt_peak:.4f} | rms={_rms:.4f} | "
                            f"duration_s={_utt_dur_s:.2f} | "
                            f"silence_dur_s={self._vad_silence_duration:.3f} | "
                            f"threshold={self._vad_speech_threshold:.2f}"
                        )

                    # ── Barge-in check ──────────────────────────────────────────
                    if self.system_state == "SPEAKING" and _utt_dur_s >= 0.3:
                        logger.info("[VoiceInput] Barge-in detected during SPEAKING! Interrupting audio.")
                        if self.barge_in_callback:
                            try:
                                self.barge_in_callback()
                            except Exception as _bie:
                                logger.debug(f"[VoiceInput] Barge-in callback error: {_bie}")
                        self.system_state = "LISTENING"
                        asyncio.create_task(self._safe_broadcast_state("LISTENING"))

                    # Ignore utterances shorter than 0.4 seconds per spec
                    if _utt_dur_s < 0.4:
                        self.vad_iterator.reset_states()
                        self._reset_buffers()
                        continue

                    # Capture the current buffer and reset immediately to prevent concurrent calls
                    # on the same buffer
                    audio_array = np.array(self.sentence_audio_buffer)
                    self.vad_iterator.reset_states()
                    self._reset_buffers()
                    # Also drain the tmp_audio_buffer so stale pre-speech frames
                    # from this utterance cannot bleed into the next detection cycle.
                    if len(self.tmp_audio_buffer) > int(self.PRE_SPEECH_SAMPLES):
                        self.tmp_audio_buffer = self.tmp_audio_buffer[-int(self.PRE_SPEECH_SAMPLES):]
                    else:
                        self.tmp_audio_buffer.clear()
                    
                    self.transcription_in_flight = True
                    # Capture generation BEFORE the Whisper call so we can
                    # detect if mute()/unmute() fired while we were blocked.
                    my_gen = self._transcription_generation
                    try:
                        # Run Whisper in a thread with a watchdog timeout so a
                        # stuck model cannot permanently block audio processing.
                        loop = asyncio.get_event_loop()
                        try:
                            transcribed_text = await asyncio.wait_for(
                                loop.run_in_executor(
                                    None, self.process_speech, audio_array
                                ),
                                timeout=_WHISPER_WATCHDOG_TIMEOUT,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"[STT] Whisper watchdog: transcription timed out "
                                f"after {_WHISPER_WATCHDOG_TIMEOUT}s — discarding"
                            )
                            transcribed_text = None

                        # ── Stale-result guard ─────────────────────────────
                        # If mute() or unmute() bumped the generation while
                        # Whisper was running, this result is stale — discard.
                        if self._transcription_generation != my_gen:
                            logger.info(
                                "[STT] Discarding stale transcription "
                                f"(gen {my_gen} → {self._transcription_generation})"
                            )
                            continue

                        if transcribed_text:
                            # ── Wake Word & State Flow ─────────────────────────
                            active_text = transcribed_text
                            now = time.time()

                            if self.input_mode == "wake_word":
                                # Use pre-compiled module-level pattern
                                m = WAKE_WORD_PATTERN.search(transcribed_text)
                                if m:
                                    logger.info(f"[WakeWord] Detected: {transcribed_text!r}")
                                    remainder = re.sub(r"^[,\.\?!;:\s\-]+", "", transcribed_text[m.end():]).strip()
                                    if remainder:
                                        # Wake word and command in same utterance -> accept command, enter THINKING, mute mic
                                        active_text = remainder
                                        self.system_state = "THINKING"
                                        self.mute()
                                        asyncio.create_task(self._safe_broadcast_state("THINKING"))
                                    else:
                                        # Wake word alone: open command window, transition to LISTENING.
                                        # Audio capture continues — new speech arriving during this
                                        # window is NOT discarded (transcription_in_flight is reset
                                        # in finally). The next completed utterance enters the
                                        # "now < _wake_active_until" branch and is accepted as a command.
                                        self._wake_active_until = now + self.wake_word_timeout
                                        self.system_state = "LISTENING"
                                        logger.info(f"[WakeWord] Wake word detected alone. Window open for {self.wake_word_timeout}s.")
                                        asyncio.create_task(self._safe_broadcast_state("LISTENING"))
                                        self._cancel_wake_window()
                                        self._wake_window_task = asyncio.create_task(
                                            self._run_wake_window_timer(self.wake_word_timeout)
                                        )
                                        continue
                                elif now < self._wake_active_until:
                                    # Within open 6-second command window -> accept command, enter THINKING, mute mic
                                    self._wake_active_until = 0.0
                                    self._cancel_wake_window()
                                    active_text = transcribed_text
                                    self.system_state = "THINKING"
                                    self.mute()
                                    asyncio.create_task(self._safe_broadcast_state("THINKING"))
                                else:
                                    # Wake-word mode active but wake word not detected; ignore
                                    logger.debug(f"[WakeWord] Utterance ignored (no wake word, outside window): {transcribed_text!r}")
                                    continue
                            elif self.input_mode == "always_listening":
                                # Always listening mode accepts speech directly
                                self.system_state = "THINKING"
                                self.mute()
                                asyncio.create_task(self._safe_broadcast_state("THINKING"))
                            elif self.input_mode == "push_to_talk":
                                # In PTT mode, standard background mic capture is bypassed unless triggered
                                pass

                            # Duplicate guard: reject the exact same text as the last accepted
                            # utterance. This prevents double-processing when VAD fires twice
                            # on the same speech, but does NOT prevent re-issuing a command
                            # after a different command in between (by design — the user may
                            # genuinely repeat a command).
                            if active_text != self.last_transcription:
                                self.last_transcription = active_text
                                logger.info(f"[STT] Transcribed: {active_text}")
                                # Notify frontend WebSocket clients (if any are connected)
                                dead_clients = set()
                                for client in list(clients):
                                    try:
                                        await client.send_json({"type": "transcription", "text": active_text})
                                    except Exception:
                                        dead_clients.add(client)
                                clients -= dead_clients
                                # In ESP32 mode, trigger the autonomous LLM→TTS pipeline ONLY if no frontend WebUI client is connected.
                                # If frontend is connected, the frontend will handle it via its WebSocket event.
                                if self.esp32_mode and self.esp32_pipeline_callback and len(clients) == 0:
                                    asyncio.create_task(self.esp32_pipeline_callback(active_text))
                    finally:
                        self.transcription_in_flight = False

    def _cancel_wake_window(self):
        """Cancel any pending wake-window expiry task."""
        if self._wake_window_task and not self._wake_window_task.done():
            self._wake_window_task.cancel()
        self._wake_window_task = None

    async def _run_wake_window_timer(self, timeout: float):
        """Auto-close the wake-word command window after timeout seconds if no command arrives."""
        try:
            await asyncio.sleep(timeout)
            # If window is still open (not consumed by a command), close it and return to IDLE
            if self._wake_active_until > 0.0:
                self._wake_active_until = 0.0
                self.system_state = "IDLE"
                logger.info("[WakeWord] Command window expired with no command — returning to IDLE.")
                asyncio.create_task(self._safe_broadcast_state("IDLE"))
        except asyncio.CancelledError:
            pass  # Window was consumed by a command — normal path

    async def _safe_broadcast_state(self, state: str):
        """Debounced state broadcast to prevent rapid UI toggling."""
        if not self.state_callback:
            return
        import time
        now = time.time()
        last_state, last_time = self._last_state_broadcast
        # Allow state change immediately, but debounce identical state re-broadcasts within 1.0s
        if state == last_state and (now - last_time) < 1.0:
            return
        self._last_state_broadcast = (state, now)
        try:
            await self.state_callback(state)
        except Exception as e:
            logger.debug(f"[VoiceInput] State broadcast error: {e}")

    def process_speech(self, audio_data):
        with wave.open(self.MIC_OUTPUT_PATH, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes((audio_data * 32768.0).astype(np.int16).tobytes())

        transcribed_text = ""
        # Collect per-segment confidence for hallucination rejection.
        # faster-whisper exposes avg_logprob and no_speech_prob per segment.
        all_avg_logprob: list = []
        all_no_speech_prob: list = []

        prompt = self.whisper_initial_prompt if self.whisper_initial_prompt else "Kyoma"
        segments, _ = self.whisper_model.transcribe(
            self.MIC_OUTPUT_PATH,
            language=self.input_language,
            initial_prompt=prompt
        )
        for segment in segments:
            transcribed_text += segment.text
            # faster-whisper NamedTuple exposes avg_logprob and no_speech_prob
            if hasattr(segment, "avg_logprob"):
                all_avg_logprob.append(float(segment.avg_logprob))
            if hasattr(segment, "no_speech_prob"):
                all_no_speech_prob.append(float(segment.no_speech_prob))

        if not transcribed_text:
            return None

        # Confidence-aware thresholds: relaxed when likely wake phrase is detected
        has_wake = bool(WAKE_WORD_PATTERN.search(transcribed_text))
        min_logprob = -1.45 if has_wake else -1.0
        max_no_speech = 0.75 if has_wake else 0.60

        if all_avg_logprob:
            mean_logprob = sum(all_avg_logprob) / len(all_avg_logprob)
            if mean_logprob < min_logprob:
                logger.info(
                    f"[Whisper] Rejected low-confidence transcript "
                    f"(avg_logprob={mean_logprob:.3f} < {min_logprob}): {transcribed_text!r}"
                )
                return None
        if all_no_speech_prob:
            mean_no_speech = sum(all_no_speech_prob) / len(all_no_speech_prob)
            if mean_no_speech > max_no_speech:
                logger.info(
                    f"[Whisper] Rejected no-speech transcript "
                    f"(no_speech_prob={mean_no_speech:.3f} > {max_no_speech}): {transcribed_text!r}"
                )
                return None

        import re as _re
        clean_text = _re.sub(r"[^\w\s]", "", transcribed_text).strip().lower()
        # Drop if only punctuation/noise remains
        if not clean_text or clean_text in self.whisper_filter_list:
            return None

        # Reject obvious repeated-word noise (e.g. "No, no, no, no")
        words_only = clean_text.split()
        if len(words_only) >= 3 and len(set(words_only)) == 1:
            logger.info(f"[Whisper] Rejected repeated-word noise: {transcribed_text!r}")
            return None

        return transcribed_text.strip()


    def run_cli(self):
        print("🎙️ Running in CLI mode. Press Ctrl+C to stop.")
        loop = asyncio.get_event_loop()

        def audio_callback(indata, frames, time, status):
            audio_np = indata.flatten().astype(np.float32) / 32768.0
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self._process_audio_cli(audio_np)))

        with sd.InputStream(samplerate=self.SAMPLING_RATE, channels=1, dtype='int16', callback=audio_callback):
            try:
                loop.run_forever()
            except KeyboardInterrupt:
                print("🛑 Stopped recording.")

    async def _process_audio_cli(self, audio_np):
        self.tmp_audio_buffer.extend(audio_np)

        while len(self.tmp_audio_buffer) >= 512:
            chunk = np.array(self.tmp_audio_buffer[:512])
            self.tmp_audio_buffer = self.tmp_audio_buffer[512:]

            speech_prob = self.vad_model(torch.from_numpy(chunk), self.SAMPLING_RATE).item()
            print(f"Speech probability: {speech_prob:.2f}")

            _threshold = self._vad_speech_threshold
            _silence_samples = self._silence_wait_samples

            if speech_prob < _threshold:
                if self.silent_samples <= _silence_samples:
                    self.silent_samples += 512
            else:
                self.silent_samples = 0
                if not self.started_speaking:
                    pre = self.sentence_audio_buffer[-int(self.PRE_SPEECH_SAMPLES):]
                    self.sentence_audio_buffer = list(pre)
                self.started_speaking = True

            if self.started_speaking:
                self.sentence_audio_buffer.extend(chunk)
                self._utt_probs.append(speech_prob)
                chunk_peak = float(np.max(np.abs(chunk)))
                if chunk_peak > self._utt_peak:
                    self._utt_peak = chunk_peak

            is_max_len = len(self.sentence_audio_buffer) >= self.MAX_UTTERANCE_SAMPLES
            if self.started_speaking and (self.silent_samples > _silence_samples or is_max_len):
                if not is_max_len:
                    post = self.tmp_audio_buffer[:int(self.POST_SPEECH_SAMPLES)]
                    self.sentence_audio_buffer.extend(post)

                # ── Per-utterance diagnostics ──────────────────────────────
                if self._utt_probs:
                    _all_samples = np.array(self.sentence_audio_buffer, dtype=np.float32)
                    _rms = float(np.sqrt(np.mean(_all_samples ** 2))) if len(_all_samples) else 0.0
                    _avg_prob = float(np.mean(self._utt_probs))
                    _max_prob = float(np.max(self._utt_probs))
                    print(
                        f"[VAD_DIAG] avg_prob={_avg_prob:.3f} max_prob={_max_prob:.3f} "
                        f"peak={self._utt_peak:.4f} rms={_rms:.4f} "
                        f"dur_s={len(_all_samples)/self.SAMPLING_RATE:.2f}"
                    )

                transcribed_text = self.process_speech(np.array(self.sentence_audio_buffer))
                if transcribed_text:
                    print(f"📝 Transcription: {transcribed_text}")

                self.vad_iterator.reset_states()
                self._reset_buffers()


if __name__ == "__main__":
    vi = VoiceInput()
    vi.run_cli()
