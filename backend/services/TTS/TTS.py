from services.lib.LAV_logger import logger
from .Kokoro.KokoroTTS import KokoroTTS

PROVIDERS = {
    "kokoro": KokoroTTS,
}

def _get_provider_cls(provider_key: str):
    if provider_key == "kokoro":
        return KokoroTTS
    if provider_key == "gpt-sovits":
        try:
            from .GPTsovits.GptSovits import GptSovits
            return GptSovits
        except Exception as e:
            logger.error(f"[TTS] Failed to import GptSovits: {e}")
            raise e
    raise ValueError(f"Unknown TTS provider: {provider_key}")

import json
import os

class TTS:
    def __init__(self):
        # Lazily-instantiated provider cache
        self._instances: dict = {}
        
        # Read saved provider from settings.json so we ONLY load the configured engine
        saved_provider = "kokoro"
        try:
            settings_path = os.path.join(os.path.dirname(__file__), "..", "..", "settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    p = data.get("tts.provider")
                    if p:
                        saved_provider = p
        except Exception as e:
            logger.warning(f"[TTS] Could not read saved provider from settings.json: {e}")

        self._active_provider: str = saved_provider
        self._engine: GptSovits | KokoroTTS = self._get_instance(saved_provider)

    @property
    def provider(self) -> str:
        return self._active_provider

    @property
    def kokoro(self):
        """Direct access to underlying Kokoro model for health checks and status."""
        if self._active_provider == "kokoro" and hasattr(self._engine, "kokoro"):
            return self._engine.kokoro
        return None

    # ------------------------------------------------------------------
    # Provider switching
    # ------------------------------------------------------------------

    def _get_instance(self, provider_key: str):
        """Return a cached instance for the given provider key."""
        if provider_key not in self._instances:
            cls = _get_provider_cls(provider_key)
            if cls is None:
                raise ValueError(f"Unknown TTS provider: {provider_key}")
            logger.info(f"[TTS] Initialising provider: {provider_key}")
            self._instances[provider_key] = cls()
        return self._instances[provider_key]

    def set_provider(self, provider_key: str) -> dict:
        """Switch the active TTS provider at runtime."""
        # Demo mode protection: lock to Kokoro
        try:
            from demo_safety import is_demo_mode_active
            if is_demo_mode_active() and provider_key != "kokoro":
                logger.info(f"[TTS] Demo mode active: rejecting provider switch to '{provider_key}'. Locked to kokoro.")
                return {"message": "TTS provider switching is disabled in demo mode. Provider locked to kokoro."}
        except Exception:
            pass

        if provider_key == "rvc":
            self._active_provider = "rvc"
            logger.info("[TTS] Active provider set to: rvc")
            return {"message": "TTS provider switched to rvc"}
        if provider_key not in ("kokoro", "gpt-sovits"):
            raise ValueError(f"Unknown TTS provider: {provider_key}. Choose from: ['kokoro', 'gpt-sovits']")
        self._active_provider = provider_key
        self._engine = self._get_instance(provider_key)
        logger.info(f"[TTS] Active provider set to: {provider_key}")
        return {"message": f"TTS provider switched to {provider_key}"}

    def get_provider(self) -> str:
        return self._active_provider

    # ------------------------------------------------------------------
    # Voice management — delegate to the active engine
    # ------------------------------------------------------------------

    @property
    def current_voice(self) -> str | None:
        return getattr(self._engine, "current_voice", None)

    def get_available_voices(self) -> list[str]:
        """Get list of available voices from the active provider."""
        return self._engine.get_available_voices()

    def change_voice(self, voice_name: str) -> dict:
        """Change the current voice (active provider only)."""
        return self._engine.change_voice(voice_name)

    def synthesize(self, text: str):
        """Synthesize text to speech using the active provider."""
        try:
            from Kyoma.tts_sanitizer import sanitize_for_tts
            text = sanitize_for_tts(text)
        except Exception:
            pass
        return self._engine.synthesize(text)

    def upload_voice(self, name, reference_audio, reference_text, reference_language):
        return self._engine.upload_voice(name, reference_audio, reference_text, reference_language)

    def delete_voice(self, name: str) -> dict:
        return self._engine.delete_voice(name)