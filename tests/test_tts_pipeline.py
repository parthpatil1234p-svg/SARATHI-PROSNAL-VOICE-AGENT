"""Unit tests for Step 5: TTS Producer/Consumer pipelining, clause minimum word thresholds, and filler manager."""

import asyncio
import time
import pytest

from config.settings import settings
from core.filler_manager import FillerManager
from voice.sentence_chunker import SentenceChunker


@pytest.mark.asyncio
async def test_chunker_enforces_minimum_clause_length():
    """Verifies that comma splitting requires at least 4 words when pipelining is enabled."""
    chunker = SentenceChunker(min_chunk_chars=10, min_clause_words=4)

    async def token_gen():
        # "Yes, sir, I am ready to help."
        # "Yes," (1 word) and "sir," (1 word) must NOT split!
        # "I am ready to help." (5 words) -> splits on final period
        tokens = ["Yes, ", "sir, ", "I am ready to help. ", "Everything is online."]
        for t in tokens:
            yield t

    chunks = []
    async for chunk in chunker.chunk_stream(token_gen()):
        chunks.append(chunk)

    # First chunk should have accumulated "Yes, sir, I am ready to help." (not chopped at "Yes," or "sir,")
    assert len(chunks) == 2
    assert chunks[0] == "Yes, sir, I am ready to help."
    assert chunks[1] == "Everything is online."


@pytest.mark.asyncio
async def test_filler_manager_watchdog_cancellation():
    """Verifies filler does not play if real audio starts before 700ms threshold."""
    filler_mgr = FillerManager()
    # Mock a cached filler
    filler_mgr.cached_fillers = [b"mock_audio_filler"]

    prev_flag = settings.ENABLE_EARLY_FILLERS
    settings.ENABLE_EARLY_FILLERS = True
    try:
        cancel_event = asyncio.Event()

        # Simulate real audio starting at 100ms (< 700ms)
        async def real_audio_worker():
            await asyncio.sleep(0.1)
            cancel_event.set()

        asyncio.create_task(real_audio_worker())
        vad_fire_t = time.time()
        played = await filler_mgr.watch_and_play_filler(
            vad_fire_t=vad_fire_t,
            cancel_event=cancel_event,
            threshold_sec=0.400
        )
        # Should NOT play filler because real audio started at 100ms
        assert played is False
    finally:
        settings.ENABLE_EARLY_FILLERS = prev_flag
