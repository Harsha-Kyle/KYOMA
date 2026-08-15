from services.lib.LAV_logger import logger

from .GPTsovits.GptSovits import GptSovits

class TTS:
    def __init__(self):
        self.tts_engine = GptSovits()
        self.current_voice = "leaf"

    def get_available_voices(self):
        """Get list of available voices from the models directory"""
        return self.tts_engine.get_available_voices()

    def change_voice(self, voice_name):
        """Change the current voice to the specified one"""
        return self.tts_engine.change_voice(voice_name)

    def synthesize(self, text):
        """Synthesize text to speech using the current voice"""
        return self.tts_engine.synthesize(text)
    
    def upload_voice(self, name, reference_audio, reference_text, reference_language):
        return self.tts_engine.upload_voice(name, reference_audio, reference_text, reference_language)
    
    def delete_voice(self, name):
        return self.tts_engine.delete_voice(name)
    