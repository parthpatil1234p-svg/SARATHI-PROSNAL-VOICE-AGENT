"""STT factory module."""

from config.settings import settings
from voice.stt.base import BaseSTT
from voice.stt.deepgram_stt import DeepgramSTT
from voice.stt.whisper_stt import WhisperSTT


def get_stt_engine(provider: str | None = None) -> BaseSTT:
    """Returns the configured STT engine."""
    provider = (provider or settings.STT_PROVIDER).lower()
    if provider == "deepgram" and settings.DEEPGRAM_API_KEY:
        return DeepgramSTT()
    return WhisperSTT()


__all__ = ["BaseSTT", "DeepgramSTT", "WhisperSTT", "get_stt_engine"]
