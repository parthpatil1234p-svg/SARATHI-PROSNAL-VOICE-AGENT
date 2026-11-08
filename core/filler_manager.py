"""Filler manager for pre-generating and playing low-latency acoustic cues."""

import asyncio
import hashlib
import logging
import random
import time
from pathlib import Path

from config.settings import settings
from voice.player import player
from voice.tts.base import BaseTTS

logger = logging.getLogger("SARATHI.FillerManager")

DEFAULT_FILLER_PHRASES = [
    "Right away, sir.",
    "On it, sir.",
    "One moment, sir."
]


class FillerManager:
    """
    Manages short spoken conversational acknowledgements.
    Pre-generates clips in the active TTS voice at startup, cached to disk.
    Plays a clip only if real audio synthesis has not commenced within ~700ms of VAD cutoff.
    """

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (settings.ASSETS_DIR / "cache" / "fillers")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cached_fillers: list[bytes] = []
        self._is_playing_filler = False
        self._filler_lock = asyncio.Lock()

    def _get_cache_path(self, phrase: str, provider: str, voice: str) -> Path:
        key = f"{provider}_{voice}_{phrase.strip().lower()}"
        name_hash = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / f"filler_{name_hash}.wav"

    async def warm_fillers(self, tts: BaseTTS) -> None:
        """Pre-synthesizes and caches acknowledgment clips to disk and memory."""
        if not settings.ENABLE_EARLY_FILLERS:
            return

        provider = getattr(settings, "TTS_PROVIDER", "default")
        voice = getattr(settings, "EDGE_TTS_VOICE", "default")
        self.cached_fillers.clear()

        for phrase in DEFAULT_FILLER_PHRASES:
            target_file = self._get_cache_path(phrase, provider, voice)
            try:
                if target_file.exists():
                    audio_bytes = target_file.read_bytes()
                    if audio_bytes:
                        self.cached_fillers.append(audio_bytes)
                        continue

                audio_bytes = await tts.synthesize(phrase)
                if audio_bytes:
                    target_file.write_bytes(audio_bytes)
                    self.cached_fillers.append(audio_bytes)
                    logger.debug(f"Pre-cached filler: '{phrase}' ({len(audio_bytes)} bytes)")
            except Exception as e:
                logger.debug(f"Could not pre-synthesize filler '{phrase}': {e}")

        logger.info(f"Loaded {len(self.cached_fillers)} pre-generated conversational fillers.")

    def get_filler(self) -> bytes | None:
        """Returns a random pre-synthesized acknowledgement audio clip."""
        if not self.cached_fillers:
            return None
        return random.choice(self.cached_fillers)

    async def watch_and_play_filler(
        self,
        vad_fire_t: float,
        cancel_event: asyncio.Event,
        threshold_sec: float = 0.700
    ) -> bool:
        """
        Sleeps until ~700ms after vad_fire_t.
        Plays a short filler ONLY if real audio has not yet started and turn is still in-flight.
        Never talks over real audio.
        """
        if not settings.ENABLE_EARLY_FILLERS or not self.cached_fillers:
            return False

        delay = max(0.0, (vad_fire_t + threshold_sec) - time.time())
        try:
            # Wait for 700ms threshold or cancellation event
            await asyncio.wait_for(cancel_event.wait(), timeout=delay)
            # If wait_for returns without TimeoutError, real audio already started!
            return False
        except asyncio.TimeoutError:
            # Threshold reached! Real audio has not started yet.
            pass

        if cancel_event.is_set():
            return False

        filler_bytes = self.get_filler()
        if not filler_bytes:
            return False

        async with self._filler_lock:
            # Re-check cancellation after lock acquisition
            if cancel_event.is_set():
                return False

            self._is_playing_filler = True
            logger.info("[Early Filler] Playing acknowledgement clip (700ms latency threshold reached).")
            try:
                await asyncio.to_thread(player.play_bytes, filler_bytes)
                return True
            finally:
                self._is_playing_filler = False


filler_manager = FillerManager()
