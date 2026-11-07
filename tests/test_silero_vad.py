"""Unit tests for Step 3: Silero VAD, pre-roll buffer, and split turn detection."""

import time
import logging
import numpy as np
import pytest

from config.settings import settings
from voice.vad import RMSVAD, SileroVAD, VoiceActivityDetector


def test_silero_vad_initialization():
    """Verifies SileroVAD loads the ONNX model and initializes recurrent states."""
    vad = SileroVAD()
    assert vad.session is not None
    assert vad.h.shape == (2, 1, 64)
    assert vad.c.shape == (2, 1, 64)
    assert vad.preroll_samples == int(16000 * 0.2)  # 3200 samples = 200ms


def test_silero_ambient_rejection():
    """Verifies SileroVAD rejects low ambient microphone noise."""
    vad = SileroVAD()
    noise = (np.random.randn(1280) * 150).astype(np.int16)
    assert vad.is_speech(noise) is False


def test_silero_preroll_buffer_inclusion():
    """Verifies that ~200ms of pre-roll audio is prepended when speech starts."""
    vad = SileroVAD(preroll_ms=200, silence_timeout_ms=300)

    # 1. Feed low noise to fill pre-roll buffer
    preroll_noise = (np.ones(1600, dtype=np.int16) * 123)
    vad.process_frame(preroll_noise)
    vad.process_frame(preroll_noise)
    assert len(vad.preroll_buffer) > 0

    # 2. Simulate speech frames
    # Load genuine speech from test_speech.wav
    import soundfile as sf
    speech_data, _ = sf.read(str(settings.ASSETS_DIR / "test_speech.wav"))
    pcm_all = (speech_data * 32767).astype(np.int16)

    # Feed active speech frames to trigger speech_started
    for i in range(7, 12):
        chunk = pcm_all[i * 1280 : (i + 1) * 1280]
        has_sp, turn_done, _ = vad.process_frame(chunk)
        if vad.speech_started:
            break

    assert vad.speech_started is True
    # The first element in accumulated_chunks must contain the pre-roll buffer
    first_accum = vad.accumulated_chunks[0]
    assert 123 in first_accum


def test_silero_split_turn_detection(caplog):
    """Verifies split-turn warning when speech resumes < 1.0s after cutoff."""
    vad = SileroVAD(silence_timeout_ms=100, min_speech_duration_sec=0.1)

    import soundfile as sf
    speech_data, _ = sf.read(str(settings.ASSETS_DIR / "test_speech.wav"))
    pcm_all = (speech_data * 32767).astype(np.int16)

    # 1. Utterance 1: feed sustained speech frames (chunks 7 and 8)
    chunk_a = pcm_all[7 * 1280 : 8 * 1280]
    chunk_b = pcm_all[8 * 1280 : 9 * 1280]
    vad.process_frame(chunk_a)
    vad.process_frame(chunk_b)
    assert vad.speech_started is True

    # End utterance with silence
    silence = np.zeros(1280, dtype=np.int16)
    vad.process_frame(silence)
    time.sleep(0.12)
    _, turn_done, audio = vad.process_frame(silence)
    assert turn_done is True
    assert vad.last_cut_time > 0

    # 2. User resumes speech quickly (< 1.0s gap)
    with caplog.at_level(logging.WARNING):
        vad.process_frame(chunk_a)
        vad.process_frame(chunk_b)

    assert any("Split Turn Detected" in r.message for r in caplog.records)


def test_vad_factory_engine_switching():
    """Verifies dynamic engine selection between 'rms' and 'silero'."""
    v_rms = VoiceActivityDetector(engine="rms")
    assert isinstance(v_rms._engine, RMSVAD)

    v_silero = VoiceActivityDetector(engine="silero")
    assert isinstance(v_silero._engine, SileroVAD)
