import asyncio
import os
import wave
from fastapi import WebSocket
import sounddevice as sd
import numpy as np
import torch
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad, VADIterator
from ..lib.LAV_logger import logger


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
    SPEECH_THRESHOLD = 0.3
    SILENCE_WAIT_TIME = 0.1 * SAMPLING_RATE
    PRE_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    POST_SPEECH_SAMPLES = 0.5 * SAMPLING_RATE
    
    running = False

    def __init__(self):
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

    def _reset_buffers(self):
        self.sentence_audio_buffer = []
        self.tmp_audio_buffer = []
        self.silent_samples = 0
        self.started_speaking = False

    async def start_streaming(self, clients):
        if self.running:
            return
        self.running = True
        logger.info("Started recording")

        loop = asyncio.get_event_loop()

        def audio_callback(indata, frames, time, status):
            if self.esp32_mode:
                return  # Ignore local mic if ESP32 is connected
            audio_np = indata.flatten().astype(np.float32) / 32768.0
            asyncio.run_coroutine_threadsafe(
                self._process_audio(audio_np, clients), loop
            )

        with sd.InputStream(samplerate=self.SAMPLING_RATE, channels=1, dtype='int16', callback=audio_callback):
            while self.running:
                await asyncio.sleep(0.1)

        logger.info("Stopped recording")

    def stop_streaming(self):
        self.running = False

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
        if not self.running:
            return
            
        self.tmp_audio_buffer.extend(audio_np)

        while len(self.tmp_audio_buffer) >= 512:
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

            if speech_prob < self.SPEECH_THRESHOLD:
                if self.silent_samples <= self.SILENCE_WAIT_TIME:
                    self.silent_samples += 512
            else:
                self.silent_samples = 0
                if not self.started_speaking:
                    pre = self.sentence_audio_buffer[-int(self.PRE_SPEECH_SAMPLES):]
                    self.sentence_audio_buffer = list(pre)
                self.started_speaking = True

            if self.started_speaking:
                self.sentence_audio_buffer.extend(chunk)

            if self.started_speaking and self.silent_samples > self.SILENCE_WAIT_TIME:
                post = self.tmp_audio_buffer[:int(self.POST_SPEECH_SAMPLES)]
                self.sentence_audio_buffer.extend(post)

                async with self.processing_lock:
                    # Capture the current buffer and reset immediately to prevent concurrent calls
                    # on the same buffer
                    audio_array = np.array(self.sentence_audio_buffer)
                    self.vad_iterator.reset_states()
                    self._reset_buffers()
                    
                    # Run Whisper in a thread so it doesn't block the event loop
                    loop = asyncio.get_event_loop()
                    transcribed_text = await loop.run_in_executor(
                        None, self.process_speech, audio_array
                    )

                    if transcribed_text and transcribed_text not in self.whisper_filter_list:
                        if transcribed_text != self.last_transcription:
                            self.last_transcription = transcribed_text
                            logger.info(f"[STT] Transcribed: {transcribed_text}")
                            # Notify frontend WebSocket clients (if any are connected)
                            dead_clients = set()
                            for client in list(clients):
                                try:
                                    await client.send_json({"type": "transcription", "text": transcribed_text})
                                except Exception:
                                    dead_clients.add(client)
                            clients -= dead_clients
                            # In ESP32 mode, also trigger the autonomous LLM→TTS pipeline
                            if self.esp32_mode and self.esp32_pipeline_callback:
                                asyncio.create_task(self.esp32_pipeline_callback(transcribed_text))

    def process_speech(self, audio_data):
        with wave.open(self.MIC_OUTPUT_PATH, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes((audio_data * 32768.0).astype(np.int16).tobytes())

        transcribed_text = ''
        segments, _ = self.whisper_model.transcribe(self.MIC_OUTPUT_PATH, language=self.input_language)
        for segment in segments:
            transcribed_text += segment.text

        if not transcribed_text:
            return
            
        import re
        clean_text = re.sub(r'[^\w\s]', '', transcribed_text).strip().lower()
        if clean_text in self.whisper_filter_list:
            return
            
        return transcribed_text

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

            if speech_prob < self.SPEECH_THRESHOLD:
                if self.silent_samples <= self.SILENCE_WAIT_TIME:
                    self.silent_samples += 512
            else:
                self.silent_samples = 0
                if not self.started_speaking:
                    pre = self.sentence_audio_buffer[-int(self.PRE_SPEECH_SAMPLES):]
                    self.sentence_audio_buffer = list(pre)
                self.started_speaking = True

            if self.started_speaking:
                self.sentence_audio_buffer.extend(chunk)

            if self.started_speaking and self.silent_samples > self.SILENCE_WAIT_TIME:
                post = self.tmp_audio_buffer[:int(self.POST_SPEECH_SAMPLES)]
                self.sentence_audio_buffer.extend(post)

                transcribed_text = self.process_speech(np.array(self.sentence_audio_buffer))
                if transcribed_text:
                    print(f"📝 Transcription: {transcribed_text}")

                self.vad_iterator.reset_states()
                self._reset_buffers()


if __name__ == "__main__":
    vi = VoiceInput()
    vi.run_cli()
