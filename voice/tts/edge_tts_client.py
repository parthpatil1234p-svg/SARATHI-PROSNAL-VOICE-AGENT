"""Free, high-fidelity British Text-to-Speech using Microsoft Edge Neural TTS."""

import io
import logging
from collections.abc import AsyncGenerator

import edge_tts

from config.settings import settings
from voice.tts.base import BaseTTS

logger = logging.getLogger("SARATHI.EdgeTTS")


class EdgeTTSClient(BaseTTS):
    """
    Microsoft Edge Neural TTS Client.
    Provides natural-sounding British male voice (en-GB-RyanNeural) with 0 API key cost.
    Automatically falls back to local offline Windows SAPI5 COM engine when offline.
    """

    def __init__(self, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice or settings.EDGE_TTS_VOICE
        self.rate = rate
        self.pitch = pitch

    async def synthesize(self, text: str) -> bytes:
        """Synthesizes text into complete audio bytes in MP3 format with local offline SAPI fallback."""
        if not text.strip():
            return b""

        try:
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
        except Exception as e:
            logger.warning(f"Edge-TTS network synthesis unavailable ({e}), falling back to offline Windows SAPI5...")
            try:
                from voice.tts.sapi_tts import SapiTTSClient
                sapi = SapiTTSClient()
                return await sapi.synthesize(text)
            except Exception as se:
                logger.error(f"Offline SAPI fallback failed: {se}")
                return b""

    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        """Yields audio binary chunks as they arrive over the WebSocket with offline fallback."""
        if not text.strip():
            return

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as e:
            logger.warning(f"Edge-TTS stream error ({e}), falling back to offline Windows SAPI5...")
            try:
                from voice.tts.sapi_tts import SapiTTSClient
                sapi = SapiTTSClient()
                async for chunk in sapi.stream_audio_chunks(text):
                    yield chunk
            except Exception as se:
                logger.error(f"Offline SAPI streaming failed: {se}")
