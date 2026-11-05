"""Abstract base class for Speech-to-Text (STT) engines."""

from abc import ABC, abstractmethod


class BaseSTT(ABC):
    """Abstract interface for transcribing speech audio."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Transcribes complete audio bytes into text."""
