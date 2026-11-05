"""TTS package factory."""

from config.settings import settings
from voice.tts.base import BaseTTS
from voice.tts.edge_tts_client import EdgeTTSClient
from voice.tts.elevenlabs_tts import ElevenLabsTTSClient
from voice.tts.sapi_tts import SapiTTSClient


def get_tts_engine(provider: str | None = None) -> BaseTTS:
    """Returns the configured TTS engine instance."""
    provider = (provider or settings.TTS_PROVIDER).lower()
    if provider == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        return ElevenLabsTTSClient()
    elif provider in ("sapi", "local", "fast"):
        return SapiTTSClient()
    # Default to Edge-TTS (Crisp British neural voice)
    return EdgeTTSClient()


__all__ = ["BaseTTS", "EdgeTTSClient", "ElevenLabsTTSClient", "SapiTTSClient", "get_tts_engine"]
