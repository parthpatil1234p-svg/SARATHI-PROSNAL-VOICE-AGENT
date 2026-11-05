"""ElevenLabs Voice Synthesis engine for cinematic Paul Bettany voice cloning."""

import logging
from collections.abc import AsyncGenerator

import httpx

from config.settings import settings
from voice.tts.base import BaseTTS

logger = logging.getLogger("JARVIS.ElevenLabsTTS")


class ElevenLabsTTSClient(BaseTTS):
    """
    ElevenLabs API client.
    Supports low-latency streaming audio with turbo/flash models and custom voice IDs.
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = "eleven_turbo_v2_5"
    ):
        self.api_key = api_key or settings.ELEVENLABS_API_KEY
        self.voice_id = voice_id or settings.ELEVENLABS_VOICE_ID or "21m00Tcm4TlvDq8ikWAM"
        self.model_id = model_id
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"

    async def synthesize(self, text: str) -> bytes:
        """Calls ElevenLabs REST endpoint to get complete audio."""
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured in settings or environment.")

        url = f"{self.base_url}/{self.voice_id}?output_format=mp3_44100_128"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.85,
                "style": 0.15,
                "use_speaker_boost": True
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content

    async def stream_audio_chunks(self, text: str) -> AsyncGenerator[bytes, None]:
        """Streams raw MP3 chunks directly from the ElevenLabs HTTP stream."""
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured.")

        url = f"{self.base_url}/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.85
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=1024):
                    if chunk:
                        yield chunk
