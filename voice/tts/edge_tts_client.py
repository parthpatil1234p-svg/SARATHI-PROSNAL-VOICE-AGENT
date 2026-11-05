"""Free, high-fidelity British Text-to-Speech using Microsoft Edge Neural TTS."""

import io
import logging
from collections.abc import AsyncGenerator

import edge_tts

from config.settings import settings
from voice.tts.base import BaseTTS

logger = logging.getLogger("JARVIS.EdgeTTS")


class EdgeTTSClient(BaseTTS):
    """
    Microsoft Edge Neural TTS Client.
    Provides natural-sounding British male voice (en-GB-RyanNeural) with 0 API key cost.
    """

    def __init__(self, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice or settings.EDGE_TTS_VOICE
        self.rate = rate
        self.pitch = pitch

    async def synthesize(self, text: str) -> bytes:
        """Synthesizes text into complete audio bytes in MP3 format."""
        if not text.strip():
            return b""

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch
        )

        audio_buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.write(chunk["data"])

        return audio_buffer.getvalue()

    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        """Yields audio binary chunks as they arrive over the WebSocket."""
        if not text.strip():
            return

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch
        )

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
