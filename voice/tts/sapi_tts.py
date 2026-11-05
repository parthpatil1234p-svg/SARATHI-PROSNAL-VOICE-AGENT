"""Ultra-low latency offline Text-to-Speech using Windows SAPI5 / pyttsx3."""

import asyncio
import io
import logging
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pyttsx3
import soundfile as sf

from voice.tts.base import BaseTTS

logger = logging.getLogger("JARVIS.SapiTTS")


class SapiTTSClient(BaseTTS):
    """
    Windows SAPI5 offline speech synthesizer.
    Delivers instantaneous (~150ms) audio with zero network latency.
    """

    def __init__(self, rate: int = 190):
        self.rate = rate
        self._engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            # Prefer a British or clean English voice if available
            voices = self._engine.getProperty("voices")
            for v in voices:
                if "british" in v.name.lower() or "george" in v.name.lower() or "hazel" in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    break
        except Exception as e:
            logger.warning(f"SAPI TTS engine initialization error: {e}")

    async def synthesize(self, text: str) -> bytes:
        if not text.strip() or not self._engine:
            return b""

        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name

            self._engine.save_to_file(text, temp_path)
            self._engine.runAndWait()

            with open(temp_path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"SAPI synthesis error: {e}")
            return b""
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        audio = await self.synthesize(text)
        if audio:
            yield audio
