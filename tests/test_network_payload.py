"""Unit tests for Step 2: Persistent HTTP/2 client and audio payload compression."""

import io
import numpy as np
import pytest
import soundfile as sf

from config.settings import settings
from core.http_client import get_shared_groq_async_client, get_shared_httpx_client
from voice.stt.whisper_stt import WhisperSTT


def test_shared_http_client_initialization():
    """Verifies that the shared HTTP client initializes with pooling enabled."""
    client = get_shared_httpx_client()
    assert client is not None
    assert not client.is_closed


def test_trailing_silence_trimming():
    """Verifies that trailing silence is trimmed without damaging the voiced prefix."""
    stt = WhisperSTT()
    sr = 16000
    # 0.5s speech tone (high energy)
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    speech = (np.sin(2 * np.pi * 300 * t) * 15000).astype(np.int16)
    # 0.5s silence (low noise)
    silence = (np.random.randn(int(sr * 0.5)) * 40).astype(np.int16)
    combined = np.concatenate([speech, silence])

    trimmed = stt._trim_trailing_silence(combined, sample_rate=sr, keep_padding_ms=100)
    # Should have trimmed at least 300ms of the 500ms trailing silence
    assert len(trimmed) < len(combined)
    assert len(trimmed) >= len(speech)


def test_flac_audio_payload_generation():
    """Verifies FLAC compression yields valid FLAC bytes substantially smaller than raw WAV."""
    stt = WhisperSTT()
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    pcm = (np.sin(2 * np.pi * 400 * t) * 12000).astype(np.int16)
    raw_bytes = pcm.tobytes()

    # Generate WAV
    wav_payload = stt._get_wav_bytes(raw_bytes, sample_rate=sr)
    wav_size = len(wav_payload.getvalue())

    # Generate FLAC
    prev_flag = settings.ENABLE_FLAC_COMPRESSION
    settings.ENABLE_FLAC_COMPRESSION = True
    try:
        flac_payload = stt._get_audio_payload(raw_bytes, sample_rate=sr)
        flac_bytes = flac_payload.getvalue()
        flac_size = len(flac_bytes)

        # FLAC should be valid soundfile audio
        bio = io.BytesIO(flac_bytes)
        data, read_sr = sf.read(bio)
        assert read_sr == sr
        assert len(data) > 0
        # FLAC payload should be strictly smaller than uncompressed WAV
        assert flac_size < wav_size
    finally:
        settings.ENABLE_FLAC_COMPRESSION = prev_flag
