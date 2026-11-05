"""Tests for VoiceActivityDetector noise rejection and turn-taking."""

import numpy as np
import pytest

from voice.vad import VoiceActivityDetector


def test_vad_rejects_ambient_noise():
    vad = VoiceActivityDetector(energy_threshold=0.030)
    # Ambient noise: low amplitude random noise (~0.01 RMS)
    noise_frame = (np.random.randn(1280) * 300).astype(np.int16)
    assert not vad.is_speech(noise_frame)


def test_vad_detects_genuine_voice():
    vad = VoiceActivityDetector(energy_threshold=0.030)
    # Loud sine wave simulating human voice (~0.15 RMS)
    t = np.linspace(0, 0.08, 1280)
    voice_frame = (np.sin(2 * np.pi * 300 * t) * 15000).astype(np.int16)
    assert vad.is_speech(voice_frame)


def test_vad_requires_consecutive_frames_to_start():
    vad = VoiceActivityDetector(energy_threshold=0.030)
    t = np.linspace(0, 0.08, 1280)
    loud_frame = (np.sin(2 * np.pi * 300 * t) * 15000).astype(np.int16)

    # 1 single frame should NOT start speech turn yet (min_consecutive_frames = 2)
    has_speech, turn_done, _ = vad.process_frame(loud_frame)
    assert has_speech is True
    assert vad.speech_started is False

    # Second consecutive frame confirms speech
    has_speech, turn_done, _ = vad.process_frame(loud_frame)
    assert has_speech is True
    assert vad.speech_started is True


def test_vad_discards_short_bursts():
    vad = VoiceActivityDetector(
        energy_threshold=0.030,
        silence_timeout_ms=100,
        min_speech_duration_sec=0.5
    )
    t = np.linspace(0, 0.08, 1280)
    loud_frame = (np.sin(2 * np.pi * 300 * t) * 15000).astype(np.int16)
    silent_frame = np.zeros(1280, dtype=np.int16)

    # 2 speech frames = ~160ms of audio (< 500ms min duration)
    vad.process_frame(loud_frame)
    vad.process_frame(loud_frame)

    # 3 silent frames to trigger timeout
    vad.process_frame(silent_frame)
    vad.process_frame(silent_frame)
    import time
    time.sleep(0.12)
    _, turn_done, audio_bytes = vad.process_frame(silent_frame)

    # Audio should be discarded as too short
    assert turn_done is False
    assert audio_bytes is None
