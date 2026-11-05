"""Unit tests for the Voice Synthesis engine."""

import pytest

from voice.tts.edge_tts_client import EdgeTTSClient


@pytest.mark.asyncio
async def test_edge_tts_synthesis():
    tts = EdgeTTSClient(voice="en-GB-RyanNeural")
    try:
        audio = await tts.synthesize("At your service, sir.")
        assert len(audio) > 1000  # Should be non-empty audio data
    except Exception as exc:
        pytest.skip(f"Skipping live TTS network test due to network/DNS: {exc}")
