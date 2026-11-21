with open("backend/services/Input/Input.py", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Update WAKE_WORD_PATTERN
old_wake = '''WAKE_WORD_PATTERN = re.compile(
    r"\\b(?:hey|hi|ok|okay)\\s+(?:kyoma|coma|koma|kioma|keoma)\\b|"
    r"\\b(?:kyoma|kioma|keoma)(?:'s)?\\b",
    re.IGNORECASE,
)'''

new_wake = '''WAKE_WORD_PATTERN = re.compile(
    r"\\b(?:hey|hi|ok|okay|hello|your|you're)\\s+(?:kyoma|kiyoma|kioma|kyomah|coma|koma|keoma)\\b|"
    r"\\b(?:kyoma|kiyoma|kioma|kyomah|keoma)(?:'s)?\\b",
    re.IGNORECASE,
)'''

assert old_wake in text
text = text.replace(old_wake, new_wake)

# 2. Add MAX_UTTERANCE_SAMPLES
old_constants = '''    SPEECH_THRESHOLD = 0.3
    SILENCE_WAIT_TIME = 0.1 * SAMPLING_RATE   # original 0.1 s (kept as class attr)
    PRE_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    POST_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE'''

new_constants = '''    SPEECH_THRESHOLD = 0.3
    SILENCE_WAIT_TIME = 0.1 * SAMPLING_RATE   # original 0.1 s (kept as class attr)
    PRE_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    POST_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    MAX_UTTERANCE_SAMPLES = 15.0 * SAMPLING_RATE  # 15s max segment to prevent background audio accumulation'''

assert old_constants in text
text = text.replace(old_constants, new_constants)

# 3. Trigger processing on silence OR max utterance duration
old_vad_check = '''            if self.started_speaking and self.silent_samples > _silence_samples:
                post = self.tmp_audio_buffer[:int(self.POST_SPEECH_SAMPLES)]
                self.sentence_audio_buffer.extend(post)'''

new_vad_check = '''            is_max_len = len(self.sentence_audio_buffer) >= self.MAX_UTTERANCE_SAMPLES
            if self.started_speaking and (self.silent_samples > _silence_samples or is_max_len):
                if not is_max_len:
                    post = self.tmp_audio_buffer[:int(self.POST_SPEECH_SAMPLES)]
                    self.sentence_audio_buffer.extend(post)'''

assert old_vad_check in text
text = text.replace(old_vad_check, new_vad_check)

# 4. Update process_speech with wake-word aware confidence thresholds & hallucination checks
old_proc_speech = '''        # Conservative hallucination thresholds (faster-whisper metadata).
        # avg_logprob < -1.0: very low confidence (hallucinations typically -1.2 to -2.0)
        # no_speech_prob > 0.6: Whisper itself thinks this segment has no real speech
        if all_avg_logprob:
            mean_logprob = sum(all_avg_logprob) / len(all_avg_logprob)
            if mean_logprob < -1.0:
                logger.info(
                    f"[Whisper] Rejected low-confidence transcript "
                    f"(avg_logprob={mean_logprob:.3f} < -1.0): {transcribed_text!r}"
                )
                return None
        if all_no_speech_prob:
            mean_no_speech = sum(all_no_speech_prob) / len(all_no_speech_prob)
            if mean_no_speech > 0.6:
                logger.info(
                    f"[Whisper] Rejected no-speech transcript "
                    f"(no_speech_prob={mean_no_speech:.3f} > 0.6): {transcribed_text!r}"
                )
                return None'''

new_proc_speech = '''        # Confidence-aware thresholds: relaxed when likely wake phrase is detected
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
                return None'''

assert old_proc_speech in text
text = text.replace(old_proc_speech, new_proc_speech)

with open("backend/services/Input/Input.py", "w", encoding="utf-8") as f:
    f.write(text)

print("backend/services/Input/Input.py updated successfully!")
