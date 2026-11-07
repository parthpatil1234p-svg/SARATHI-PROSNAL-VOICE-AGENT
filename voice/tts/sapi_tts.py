"""Ultra-low latency offline Text-to-Speech using native Windows SAPI5 COM interface."""

import asyncio
import io
import logging
import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

from voice.tts.base import BaseTTS

logger = logging.getLogger("SARATHI.SapiTTS")


class SapiTTSClient(BaseTTS):
    """
    Native Windows SAPI5 offline speech synthesizer via direct COM dispatch.
    Delivers instantaneous (~50ms) audio with zero network latency and thread-safe execution.
    """

    def __init__(self, rate: int = 190):
        self.rate = rate

    async def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            return b""

        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        temp_path = None
        co_init = False
        try:
            import pythoncom
            import win32com.client

            pythoncom.CoInitialize()
            co_init = True

            voice = win32com.client.Dispatch("SAPI.SpVoice")
            stream = win32com.client.Dispatch("SAPI.SpFileStream")

            # Map rate to SAPI5 range (-10 to 10)
            sapi_rate = max(-10, min(10, int((self.rate - 200) / 20)))
            voice.Rate = sapi_rate

            # Prefer modern clean English voices (George, Hazel, David, Mark, Zira)
            try:
                voices = voice.GetVoices()
                for v in voices:
                    desc = v.GetDescription().lower()
                    if any(name in desc for name in ("george", "hazel", "david", "mark", "zira")):
                        voice.Voice = v
                        break
            except Exception:
                pass

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name

            # 3 = SSFMCreateForWrite (overwrite if existing)
            stream.Open(temp_path, 3)
            voice.AudioOutputStream = stream
            voice.Speak(text)
            stream.Close()

            with open(temp_path, "rb") as f:
                return f.read()

        except Exception as e:
            logger.error(f"Native SAPI synthesis error: {e}")
            # Fallback to pyttsx3 in case win32com COM stream is blocked
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", self.rate)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as pf:
                    ptemp = pf.name
                engine.save_to_file(text, ptemp)
                engine.runAndWait()
                with open(ptemp, "rb") as pf:
                    res = pf.read()
                os.unlink(ptemp)
                return res
            except Exception as pe:
                logger.error(f"pyttsx3 secondary fallback error: {pe}")
                return b""

        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            if co_init:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        audio = await self.synthesize(text)
        if audio:
            yield audio
