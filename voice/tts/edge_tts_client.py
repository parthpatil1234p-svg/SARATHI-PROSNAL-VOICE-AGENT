"""Free, high-fidelity neural Text-to-Speech using Microsoft Edge Neural TTS."""

import io
import logging
import re
from collections.abc import AsyncGenerator

import edge_tts

from config.settings import settings
from voice.tts.base import BaseTTS

logger = logging.getLogger("SARATHI.EdgeTTS")


class EdgeTTSClient(BaseTTS):
    """
    Microsoft Edge Neural TTS Client.
    Provides natural-sounding Hindi neural voice (hi-IN-MadhurNeural) and English voice.
    Automatically detects Hindi / Hinglish text and dynamically routes to MadhurNeural
    for crystal-clear, articulate, human-like voice output with zero creepy distortion.
    Automatically falls back to local offline Windows SAPI5 COM engine when offline.
    """

    def __init__(self, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz"):
        self.default_voice = voice or settings.EDGE_TTS_VOICE or "hi-IN-MadhurNeural"
        self.rate = rate
        self.pitch = pitch

    def _select_voice_for_text(self, text: str) -> str:
        """Dynamically picks the best neural voice for Hindi vs English text."""
        if not text:
            return self.default_voice
        # Devanagari Unicode block: \u0900-\u097F
        has_devanagari = bool(re.search(r'[\u0900-\u097F]', text))
        hindi_keywords = (
            "namaste", "suno", "sarathi", "sarthi", "theek", "kaise", "kya", "kahan", "kab",
            "karo", "dhanyawad", "shukriya", "batao", "chalu", "band", "dekho", "hai", "hain",
            "main", "aap", "tum", "mera", "meri", "hum"
        )
        words = set(re.findall(r'\b\w+\b', text.lower()))
        has_hindi_keyword = bool(words.intersection(hindi_keywords))

        if has_devanagari or has_hindi_keyword:
            return "hi-IN-MadhurNeural"

        return self.default_voice

    async def synthesize(self, text: str) -> bytes:
        """Synthesizes text into complete audio bytes in MP3 format with local offline SAPI fallback."""
        if not text.strip():
            return b""

        target_voice = self._select_voice_for_text(text)
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=target_voice,
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

        target_voice = self._select_voice_for_text(text)
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=target_voice,
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
