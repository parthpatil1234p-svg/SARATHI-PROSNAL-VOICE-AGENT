"""TTS package factory."""

from config.settings import settings
from voice.tts.base import BaseTTS
from voice.tts.edge_tts_client import EdgeTTSClient
from voice.tts.elevenlabs_tts import ElevenLabsTTSClient


def get_tts_engine(provider: str | None = None) -> BaseTTS:
    """Returns the configured TTS engine instance."""
    provider = (provider or settings.TTS_PROVIDER).lower()
    if provider == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        return ElevenLabsTTSClient()
    # Default to Edge-TTS (100% free British neural voice)
    return EdgeTTSClient()


__all__ = ["BaseTTS", "EdgeTTSClient", "ElevenLabsTTSClient", "get_tts_engine"]
