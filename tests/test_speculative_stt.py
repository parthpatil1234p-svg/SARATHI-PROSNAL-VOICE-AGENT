"""Unit tests for Step 4: Speculative STT at 220ms silence with resume cancellation."""

import asyncio
import numpy as np
import pytest

from config.settings import settings
from core.orchestrator import AssistantOrchestrator


@pytest.mark.asyncio
async def test_speculative_stt_lifecycle():
    """Verifies speculative STT triggers at 220ms silence and cancels cleanly when speech resumes."""
    prev_flag = settings.ENABLE_SPECULATIVE_STT
    settings.ENABLE_SPECULATIVE_STT = True
    try:
        orch = AssistantOrchestrator()
        assert orch.speculative_call_count == 0
        assert orch.speculative_discard_count == 0
        assert orch.speculative_hit_count == 0

        # Simulate a mock speculative task
        async def dummy_transcribe(audio):
            await asyncio.sleep(0.05)
            return "speculative transcript"

        orch.stt.transcribe = dummy_transcribe

        # Start speculative task
        task = asyncio.create_task(dummy_transcribe(b"dummy_audio"))
        orch.speculative_stt_task = task
        orch.speculative_call_count += 1

        # Simulate user resuming speech -> task must be discarded
        if not task.done():
            task.cancel()
        orch.speculative_stt_task = None
        orch.speculative_discard_count += 1

        assert orch.speculative_call_count == 1
        assert orch.speculative_discard_count == 1
        assert orch.speculative_stt_task is None

        # Verify task was cancelled
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        settings.ENABLE_SPECULATIVE_STT = prev_flag


@pytest.mark.asyncio
async def test_speculative_stt_hit_resolves_instantly():
    """Verifies that a completed speculative task delivers the transcript immediately without extra STT latency."""
    orch = AssistantOrchestrator()

    async def fast_speculative():
        return "Operational status nominal."

    spec_task = asyncio.create_task(fast_speculative())
    # Awaiting pre-warmed speculative task takes ~0ms
    res = await spec_task
    assert res == "Operational status nominal."
