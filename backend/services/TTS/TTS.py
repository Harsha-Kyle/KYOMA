from services.lib.LAV_logger import logger

from .GPTsovits.GptSovits import GptSovits
from .Kokoro.KokoroTTS import KokoroTTS

PROVIDERS = {
    "gpt-sovits": GptSovits,
    "kokoro":     KokoroTTS,
}

import json
import os

class TTS:
    def __init__(self):
        # Lazily-instantiated provider cache
        self._instances: dict = {}
        
        # Read saved provider from settings.json so we ONLY load the configured engine
        saved_provider = "gpt-sovits"
        try:
            settings_path = os.path.join(os.path.dirname(__file__), "..", "..", "settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    p = data.get("tts.provider")
                    if p in PROVIDERS:
                        saved_provider = p
        except Exception as e:
            logger.warning(f"[TTS] Could not read saved provider from settings.json: {e}")

        self._active_provider: str = saved_provider
        self._engine: GptSovits | KokoroTTS = self._get_instance(saved_provider)

    # ------------------------------------------------------------------
    # Provider switching
    # ------------------------------------------------------------------

    def _get_instance(self, provider_key: str):
        """Return a cached instance for the given provider key."""
        if provider_key not in self._instances:
            cls = PROVIDERS.get(provider_key)
            if cls is None:
                raise ValueError(f"Unknown TTS provider: {provider_key}")
            logger.info(f"[TTS] Initialising provider: {provider_key}")
            self._instances[provider_key] = cls()
        return self._instances[provider_key]

    def set_provider(self, provider_key: str) -> dict:
        """Switch the active TTS provider at runtime."""
        if provider_key == "rvc":
            self._active_provider = "rvc"
            logger.info("[TTS] Active provider set to: rvc")
            return {"message": "TTS provider switched to rvc"}
        if provider_key not in PROVIDERS:
            raise ValueError(f"Unknown TTS provider: {provider_key}. Choose from: {list(PROVIDERS)}")
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
        return self._engine.synthesize(text)

    def upload_voice(self, name, reference_audio, reference_text, reference_language):
        return self._engine.upload_voice(name, reference_audio, reference_text, reference_language)

    def delete_voice(self, name: str) -> dict:
        return self._engine.delete_voice(name)