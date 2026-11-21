import sys
import os
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

        try:
            kyoma_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Kyoma'))
            if kyoma_path not in sys.path:
                sys.path.append(kyoma_path)
            from demo_safety import is_demo_mode_active
            demo_mode = is_demo_mode_active()
        except Exception:
            demo_mode = False

        if demo_mode:
            saved_provider = 'kokoro'
            logger.info('[TTS] Demo mode active at startup: locked to Kokoro TTS')

        self._active_provider: str = saved_provider
        self._engine: GptSovits | KokoroTTS = self._get_instance(saved_provider)
        if demo_mode and hasattr(self._engine, 'change_voice'):
            try:
                self._engine.change_voice('af_heart')
            except Exception:
                pass

    @property
    def provider(self) -> str:
        return self._active_provider

    @property
    def kokoro(self):
        """Direct access to underlying Kokoro model for health checks and status."""
        if self._active_provider == "kokoro":
            if hasattr(self._engine, "kokoro") and self._engine.kokoro is not None:
                return self._engine.kokoro
            if getattr(self._engine, "available", False):
                return self._engine
        return None
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
        available = self.get_available_voices()
        if available and voice_name not in available:
            logger.warning(f"[TTS] Voice '{voice_name}' not available for provider '{self._active_provider}'. Available: {available[:5]}...")
            if self.current_voice in available:
                return {"message": f"Voice '{voice_name}' not supported by current provider. Kept current voice '{self.current_voice}'."}
            fallback = available[0]
            res = self._engine.change_voice(fallback)
            return {"message": f"Voice '{voice_name}' not supported. Defaulted to '{fallback}'."}
        return self._engine.change_voice(voice_name)

    def synthesize(self, text: str):
        """Synthesize text to speech using the active provider."""
        try:
            from Kyoma.tts_sanitizer import sanitize_for_tts
            text = sanitize_for_tts(text)
        except Exception:
            pass
        if not text or not any(c.isalnum() for c in text):
            return None
        return self._engine.synthesize(text)

    def upload_voice(self, name, reference_audio, reference_text, reference_language):
        return self._engine.upload_voice(name, reference_audio, reference_text, reference_language)

    def delete_voice(self, name: str) -> dict:
        return self._engine.delete_voice(name)