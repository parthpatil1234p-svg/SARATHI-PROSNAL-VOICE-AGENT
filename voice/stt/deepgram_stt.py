"""Deepgram Nova-2 low-latency streaming STT implementation."""

import logging

import httpx

from config.settings import settings
from voice.stt.base import BaseSTT

logger = logging.getLogger("SARATHI.DeepgramSTT")


class DeepgramSTT(BaseSTT):
    """
    Deepgram Nova-2 STT implementation.
    Transcribes audio payloads with ~150ms cloud latency.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self.endpoint = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&punctuate=true"

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not self.api_key:
            logger.warning("DEEPGRAM_API_KEY not set.")
            return ""

        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": f"audio/raw;encoding=linear16;rate={sample_rate};channels=1"
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(self.endpoint, content=audio_bytes, headers=headers)
                response.raise_for_status()
                data = response.json()
                transcript = (
                    data.get("results", {})
                    .get("channels", [{}])[0]
                    .get("alternatives", [{}])[0]
                    .get("transcript", "")
                )
                return transcript.strip()
        except Exception as e:
            logger.error(f"Deepgram transcription error: {e}. Falling back to Whisper STT.")
            try:
                from voice.stt.whisper_stt import WhisperSTT
                fallback = WhisperSTT()
                return await fallback.transcribe(audio_bytes, sample_rate)
            except Exception as fe:
                logger.error(f"STT fallback error: {fe}")
                return ""
