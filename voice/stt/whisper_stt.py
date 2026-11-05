"""Local and Groq-accelerated Whisper STT implementations."""

import io
import logging
import wave

from config.settings import settings
from voice.stt.base import BaseSTT

logger = logging.getLogger("JARVIS.WhisperSTT")


class WhisperSTT(BaseSTT):
    """
    High-speed Whisper STT.
    Prioritizes Groq Whisper Large v3 Turbo (ultra-low latency ~120ms) when GROQ_API_KEY is present,
    falling back to local faster-whisper on GPU/CPU.
    """

    def __init__(self, model_size: str = "base.en"):
        self.model_size = model_size
        self._local_model = None

    def _get_wav_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> io.BytesIO:
        """Encodes raw PCM bytes into an in-memory WAV file."""
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)
        wav_io.seek(0)
        wav_io.name = "speech.wav"
        return wav_io

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not audio_bytes:
            return ""

        # Option 1: Fast Groq Whisper Cloud if GROQ_API_KEY is configured
        if settings.GROQ_API_KEY:
            try:
                from groq import Groq
                client = Groq(api_key=settings.GROQ_API_KEY)
                wav_file = self._get_wav_bytes(audio_bytes, sample_rate)

                transcription = client.audio.transcriptions.create(
                    file=wav_file,
                    model="whisper-large-v3-turbo",
                    prompt="Conversation with Tony Stark's personal assistant Jarvis.",
                    response_format="text",
                    language="en",
                    temperature=0.0
                )
                text = str(transcription).strip()
                logger.info(f"Groq Whisper transcription: '{text}'")
                return text
            except Exception as e:
                logger.warning(f"Groq Whisper failed ({e}), falling back to local faster-whisper.")

        # Option 2: Local faster-whisper
        try:
            from faster_whisper import WhisperModel
            if self._local_model is None:
                logger.info(f"Loading local faster-whisper model '{self.model_size}'...")
                self._local_model = WhisperModel(
                    self.model_size,
                    device="auto",
                    compute_type="float16"
                )

            wav_file = self._get_wav_bytes(audio_bytes, sample_rate)
            segments, _ = self._local_model.transcribe(wav_file, beam_size=1)
            text = " ".join([seg.text for seg in segments]).strip()
            logger.info(f"Local Whisper transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"Local Whisper transcription error: {e}")
            return ""
