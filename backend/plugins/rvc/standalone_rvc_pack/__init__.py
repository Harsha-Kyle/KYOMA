"""
Standalone RVC Voice Converter

A simplified, self-contained version of RVC (Retrieval-based Voice Conversion)
that can be used independently without the full RVC environment.
"""

from .voice_converter import StandaloneVoiceConverter
from .config import StandaloneConfig

__version__ = "1.0.0"
__all__ = ["StandaloneVoiceConverter", "StandaloneConfig"] 