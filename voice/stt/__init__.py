"""STT factory module."""

from config.settings import settings
from voice.stt.base import BaseSTT
from voice.stt.deepgram_stt import DeepgramSTT
from voice.stt.whisper_stt import WhisperSTT


def get_stt_engine(provider: str | None = None) -> BaseSTT:
    """Returns the configured STT engine."""
    provider = (provider or settings.STT_PROVIDER).lower()
    dg_key = (settings.DEEPGRAM_API_KEY or "").strip()
    is_placeholder = any(p in dg_key.lower() for p in ("your-", "placeholder", "key-here", "xxx"))
    if provider == "deepgram" and dg_key and not is_placeholder:
        return DeepgramSTT()
    return WhisperSTT()


__all__ = ["BaseSTT", "DeepgramSTT", "WhisperSTT", "get_stt_engine"]
