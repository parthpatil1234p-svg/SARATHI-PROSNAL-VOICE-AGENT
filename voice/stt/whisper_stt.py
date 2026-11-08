"""Local and Groq-accelerated Whisper STT implementations."""

import asyncio
import io
import logging
import wave
import numpy as np
import soundfile as sf

from config.settings import settings
from voice.stt.base import BaseSTT

logger = logging.getLogger("SARATHI.WhisperSTT")


class WhisperSTT(BaseSTT):
    """
    High-speed Whisper STT.
    Prioritizes Groq Whisper Large v3 Turbo (ultra-low latency ~120ms) when GROQ_API_KEY is present,
    with persistent HTTP/2 pooling, FLAC compression, silence trimming, and 3s fallback to local faster-whisper.
    """

    def __init__(self, model_size: str = "base.en"):
        self.model_size = model_size
        self._local_model = None
        self._groq_client = None
        self._init_groq_client()

    def _init_groq_client(self):
        if settings.GROQ_API_KEY:
            try:
                if settings.ENABLE_PERSISTENT_HTTP_CLIENT:
                    from core.http_client import get_shared_groq_async_client
                    self._groq_client = get_shared_groq_async_client()
                    logger.info("WhisperSTT initialized with persistent HTTP/2 Groq client.")
                else:
                    from groq import AsyncGroq
                    self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
                    logger.info("WhisperSTT initialized with standard AsyncGroq client.")
            except Exception as e:
                logger.warning(f"Failed to init Groq Whisper client: {e}")
        else:
            self._groq_client = None

    def _normalize_speech_peak(self, samples: np.ndarray, target_peak: float = 0.85) -> np.ndarray:
        """Normalizes vocal waveform peak so Whisper hears loud, crisp, articulate speech."""
        if len(samples) == 0:
            return samples
        float_samples = samples.astype(np.float32)
        max_amp = float(np.max(np.abs(float_samples)))
        if max_amp > 80.0:
            gain = (32767.0 * target_peak) / max_amp
            gain = min(max(gain, 1.0), 6.0)  # Bounded gain between 1.0x and 6.0x
            return np.clip(float_samples * gain, -32768, 32767).astype(np.int16)
        return samples

    def _trim_trailing_silence(
        self,
        samples: np.ndarray,
        sample_rate: int = 16000,
        keep_padding_ms: int = 180,
        threshold: float = 0.003
    ) -> np.ndarray:
        """
        Trims trailing dead air while preserving speech and final consonants.
        Scans backwards in 20ms frames and retains keep_padding_ms after the last active speech frame.
        """
        if len(samples) < sample_rate * 0.1:
            return samples

        frame_len = int(sample_rate * 0.02)  # 20ms frame
        num_frames = len(samples) // frame_len
        end_frame_idx = num_frames

        for i in range(num_frames - 1, -1, -1):
            frame = samples[i * frame_len : (i + 1) * frame_len]
            rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2)) / 32768.0
            if rms >= threshold:
                end_frame_idx = i + 1
                break

        padding_samples = int(sample_rate * (keep_padding_ms / 1000.0))
        cutoff = min(len(samples), end_frame_idx * frame_len + padding_samples)
        return samples[:cutoff]

    def _get_wav_bytes(self, audio_bytes: bytes, sample_rate: int = 16000) -> io.BytesIO:
        """Encodes raw PCM bytes into an in-memory WAV file with peak normalization."""
        samples = np.frombuffer(audio_bytes, dtype=np.int16)
        normalized = self._normalize_speech_peak(samples)
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(normalized.tobytes())
        wav_io.seek(0)
        wav_io.name = "speech.wav"
        return wav_io

    def _get_audio_payload(self, audio_bytes: bytes, sample_rate: int = 16000) -> io.BytesIO:
        """
        Prepares audio payload for STT upload.
        Normalizes peak, trims trailing silence, and compresses to 16kHz mono FLAC.
        """
        if not settings.ENABLE_FLAC_COMPRESSION:
            return self._get_wav_bytes(audio_bytes, sample_rate)

        try:
            raw_samples = np.frombuffer(audio_bytes, dtype=np.int16)
            normalized_samples = self._normalize_speech_peak(raw_samples)
            trimmed_samples = self._trim_trailing_silence(normalized_samples, sample_rate=sample_rate)

            flac_io = io.BytesIO()
            sf.write(flac_io, trimmed_samples, sample_rate, format="FLAC", subtype="PCM_16")
            flac_io.seek(0)
            flac_io.name = "speech.flac"
            return flac_io
        except Exception as e:
            logger.warning(f"FLAC compression/trim failed ({e}), falling back to WAV.")
            return self._get_wav_bytes(audio_bytes, sample_rate)

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not audio_bytes:
            return ""

        # Option 1: Fast Groq Whisper Cloud with persistent connection and timeout
        if self._groq_client:
            try:
                audio_file = self._get_audio_payload(audio_bytes, sample_rate)
                transcription_coro = self._groq_client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3-turbo",
                    prompt="Sarathi, Sarthi, Parth, AI desktop assistant voice commands and questions in English, Hindi, and Hinglish.",
                    response_format="text",
                    temperature=0.0
                )
                transcription = await asyncio.wait_for(
                    transcription_coro,
                    timeout=settings.GROQ_TIMEOUT_SEC
                )
                text = str(transcription).strip()
                # Suppress prompt reflection hallucinations on quiet frames
                if text.lower() in ("sarathi ai assistant conversation in english or hindi.", "sarathi ai assistant", "commands and conversation in english and hindi."):
                    return ""
                logger.info(f"Groq Whisper transcription: '{text}'")
                return text
            except asyncio.TimeoutError:
                logger.warning(
                    f"Groq Whisper call timed out after {settings.GROQ_TIMEOUT_SEC}s. Falling back to local faster-whisper."
                )
            except Exception as e:
                logger.warning(f"Groq Whisper failed ({e}), falling back to local faster-whisper.")

        # Option 2: Local faster-whisper with automatic CUDA/CPU acceleration
        try:
            import ctranslate2
            from faster_whisper import WhisperModel
            if self._local_model is None:
                use_cuda = False
                if ctranslate2.get_cuda_device_count() > 0:
                    try:
                        import ctypes
                        ctypes.cdll.LoadLibrary("cublas64_12.dll")
                        use_cuda = True
                    except Exception:
                        logger.info("cuBLAS 12 DLL not present on system; defaulting faster-whisper to CPU int8")
                        use_cuda = False

                device = "cuda" if use_cuda else "cpu"
                compute_type = "float16" if use_cuda else "int8"
                logger.info(f"Loading local faster-whisper model '{self.model_size}' on {device} ({compute_type})...")
                self._local_model = WhisperModel(
                    self.model_size,
                    device=device,
                    compute_type=compute_type
                )

            wav_file = self._get_wav_bytes(audio_bytes, sample_rate)

            def _transcribe_sync(model, f):
                segs, _ = model.transcribe(f, beam_size=1)
                return " ".join([seg.text for seg in segs]).strip()

            try:
                text = await asyncio.to_thread(_transcribe_sync, self._local_model, wav_file)
            except Exception as infer_err:
                logger.warning(f"Local faster-whisper inference failed ({infer_err}), retrying on CPU int8 fallback...")
                self._local_model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                wav_file.seek(0)
                text = await asyncio.to_thread(_transcribe_sync, self._local_model, wav_file)

            logger.info(f"Local Whisper transcription: '{text}'")
            return text
        except Exception as e:
            logger.error(f"Local Whisper transcription error: {e}")
            return ""
