"""
Kokoro TTS backend service — fully offline, ONNX-based.

Model files are expected at:
  backend/services/TTS/Kokoro/models/kokoro-v1.0.onnx
  backend/services/TTS/Kokoro/models/voices-v1.0.bin

Download with download_kokoro_weights.py (auto-created next to this file),
or run:
  wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
  wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
"""

from io import BytesIO
import os
import numpy as np
import soundfile as sf

from services.lib.LAV_logger import logger

BASE_DIR      = os.path.dirname(__file__)
MODELS_DIR    = os.path.join(BASE_DIR, "models")
MODEL_PATH    = os.path.join(MODELS_DIR, "kokoro-v1.0.onnx")
VOICES_PATH   = os.path.join(MODELS_DIR, "voices-v1.0.bin")

# Download URLs for first-time setup
MODEL_URL  = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

# Map voice prefix → language/accent label shown in the UI
VOICE_LANG_MAP = {
    "af_": "🇺🇸 American Female",
    "am_": "🇺🇸 American Male",
    "bf_": "🇬🇧 British Female",
    "bm_": "🇬🇧 British Male",
    "ef_": "🇪🇸 Spanish Female",
    "em_": "🇪🇸 Spanish Male",
    "ff_": "🇫🇷 French Female",
    "hf_": "🇮🇳 Hindi Female",
    "hm_": "🇮🇳 Hindi Male",
    "if_": "🇮🇹 Italian Female",
    "im_": "🇮🇹 Italian Male",
    "jf_": "🇯🇵 Japanese Female",
    "jm_": "🇯🇵 Japanese Male",
    "pf_": "🇧🇷 Portuguese Female",
    "pm_": "🇧🇷 Portuguese Male",
    "zf_": "🇨🇳 Chinese Female",
    "zm_": "🇨🇳 Chinese Male",
}

DEFAULT_VOICE = "af_heart"


class KokoroTTS:
    """Offline Kokoro TTS via kokoro-onnx."""

    def __init__(self):
        self.kokoro = None
        self.available = False
        self.current_voice: str = DEFAULT_VOICE
        self.speed: float = 1.0

        self._try_load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _try_load(self):
        """Attempt to load the Kokoro ONNX model."""
        if not os.path.exists(MODEL_PATH) or not os.path.exists(VOICES_PATH):
            logger.warning(
                "[Kokoro] Model files not found. "
                f"Expected:\n  {MODEL_PATH}\n  {VOICES_PATH}\n"
                "Run 'python download_kokoro_weights.py' to download them."
            )
            return

        try:
            from kokoro_onnx import Kokoro
            logger.info("[Kokoro] Loading ONNX model…")
            self.kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
            self.available = True
            logger.info(f"[Kokoro] Ready. {len(self.get_available_voices())} voices loaded.")
        except ImportError:
            logger.error("[Kokoro] kokoro-onnx not installed. Run: pip install kokoro-onnx")
        except Exception as e:
            logger.error(f"[Kokoro] Failed to load model: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Public API — mirrors GPT-SoVITS interface expected by TTS.py
    # ------------------------------------------------------------------

    def get_available_voices(self) -> list[str]:
        """Return list of voice IDs."""
        if not self.available or self.kokoro is None:
            return []
        return list(self.kokoro.get_voices())

    def change_voice(self, voice_name: str) -> dict:
        """Set the active voice."""
        available = self.get_available_voices()
        if voice_name not in available:
            if DEFAULT_VOICE in available:
                self.current_voice = DEFAULT_VOICE
            elif available:
                self.current_voice = available[0]
            logger.warning(f"[Kokoro] Voice '{voice_name}' not in available voices, defaulted to '{self.current_voice}'")
            return {"message": f"Kokoro voice defaulted to {self.current_voice}"}
        self.current_voice = voice_name
        return {"message": f"Kokoro voice changed to {voice_name}"}

    def synthesize(self, text: str) -> bytes | dict:
        """
        Synthesise *text* and return raw WAV bytes, or an error dict if
        Kokoro is unavailable.
        """
        if not self.available or self.kokoro is None:
            return {
                "message": "Kokoro TTS is unavailable (model files missing or not loaded)."
            }

        try:
            samples, sample_rate = self.kokoro.create(
                text,
                voice=self.current_voice,
                speed=self.speed,
                lang="en-us",
            )

            # Encode to WAV bytes
            buf = BytesIO()
            sf.write(buf, samples, sample_rate, format="wav")
            buf.seek(0)
            return buf.read()

        except Exception as e:
            logger.error(f"[Kokoro] Synthesis error: {e}", exc_info=True)
            return {"message": "Kokoro synthesis failed", "Exception": str(e)}

    def set_speed(self, speed: float):
        """Adjust speech speed (0.5 – 2.0)."""
        self.speed = max(0.5, min(2.0, speed))

    # These are no-ops for Kokoro (voices are built-in, not uploaded)
    def upload_voice(self, *args, **kwargs):
        raise NotImplementedError("Kokoro does not support custom voice upload.")

    def delete_voice(self, *args, **kwargs):
        raise NotImplementedError("Kokoro does not support voice deletion.")
