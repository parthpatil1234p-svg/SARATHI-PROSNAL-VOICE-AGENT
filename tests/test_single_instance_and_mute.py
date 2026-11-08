"""Tests for Single Instance Lock and Microphone Mute/Unmute Functionality."""

import pytest
import numpy as np
from core.single_instance import SingleInstanceLock
from voice.audio_stream import AudioInputStream


def test_single_instance_lock():
    """Verifies that primary instance acquires lock and second instance is rejected."""
    # Use distinct test port to avoid collision with running servers
    test_port = 49199
    lock1 = SingleInstanceLock(port=test_port)
    lock2 = SingleInstanceLock(port=test_port)

    assert lock1.try_acquire() is True
    assert lock1.is_master is True

    # Second instance attempting to acquire the same lock must return False
    restored = []
    lock1.start_listener(on_restore_callback=lambda: restored.append(True))
    assert lock2.try_acquire() is False

    # Clean up
    lock1.release()


def test_audio_stream_mute_logic():
    """Verifies that AudioInputStream feeds silence when muted."""
    stream = AudioInputStream(sample_rate=16000, chunk_size=1280)
    stream.is_running = True
    stream.is_muted = True

    # Simulate an incoming audio frame with high amplitude
    loud_data = np.full((1280, 1), 0.8, dtype=np.float32)
    stream._audio_callback(loud_data, 1280, None, None)

    # Queue should contain a silent chunk of zeros, and latest_rms/level must be 0
    assert stream.latest_rms == 0.0
    assert stream.latest_level == 0
    assert not stream.audio_queue.empty()
    chunk = stream.audio_queue.get_nowait()
    assert np.all(chunk == 0)

    # Now unmute and test that real amplitude passes through
    stream.is_muted = False
    stream._audio_callback(loud_data, 1280, None, None)
    assert stream.latest_rms > 0.0
    assert stream.latest_level > 0
    chunk2 = stream.audio_queue.get_nowait()
    assert not np.all(chunk2 == 0)


@pytest.mark.asyncio
async def test_process_text_turn_no_name_error():
    """Ensure process_text_turn does not raise NameError for effective_text."""
    from unittest.mock import AsyncMock, patch
    from core.orchestrator import AssistantOrchestrator

    orchestrator = AssistantOrchestrator()
    orchestrator.speak_direct = AsyncMock()

    # Test mute command via text
    await orchestrator.process_text_turn("mute mic")
    assert orchestrator.audio_stream.is_muted is True

    # Test unmute command via text
    await orchestrator.process_text_turn("unmute")
    assert orchestrator.audio_stream.is_muted is False

    # Test arbitrary text (e.g. Hinglish / Hindi queries) without NameError
    orchestrator.tts.synthesize = AsyncMock(return_value=b"fake_audio")

    async def mock_stream(*args, **kwargs):
        yield "Namaste "
        yield "Parth."

    orchestrator.llm.stream_response = mock_stream
    with patch("core.orchestrator.player.play_bytes", return_value=True):
        await orchestrator.process_text_turn("Hinglish")
        await orchestrator.process_text_turn("Can you speak in Hindi?")

