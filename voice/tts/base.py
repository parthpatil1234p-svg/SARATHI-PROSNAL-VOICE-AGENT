"""Abstract base class for Text-to-Speech engines."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator


class BaseTTS(ABC):
    """Abstract interface for voice synthesis."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Synthesizes text into complete audio bytes (e.g. WAV or MP3)."""

    @abstractmethod
    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        """Streams audio bytes chunk by chunk for minimal latency."""
