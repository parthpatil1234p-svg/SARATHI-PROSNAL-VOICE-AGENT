"""Interruptible audio player for real-time speech output with instant barge-in support."""

import io
import logging
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

from config.settings import settings

logger = logging.getLogger("SARATHI.AudioPlayer")


class InterruptibleAudioPlayer:
    """
    Thread-safe, robust audio player for voice assistant output.
    Plays audio via sounddevice with support for custom output device routing
    and instantaneous (<30ms) barge-in interruption.
    """

    def __init__(self, default_sample_rate: int = 24000):
        self.default_sample_rate = default_sample_rate
        self.abort_event = threading.Event()
        self.is_playing = False
        self._lock = threading.Lock()

    def _get_output_device(self) -> int | None:
        """Determines the best output device (configured or default speakers)."""
        if settings.AUDIO_OUTPUT_DEVICE_INDEX is not None and str(settings.AUDIO_OUTPUT_DEVICE_INDEX).isdigit():
            return int(settings.AUDIO_OUTPUT_DEVICE_INDEX)

        # Look for default output device or fallback to Speakers if Headphones is default and disconnected
        try:
            default_out = sd.default.device[1]
            if default_out is not None and default_out >= 0:
                return default_out
        except Exception:
            pass

        return None

    def play_bytes(self, audio_bytes: bytes, format: str = "WAV") -> bool:
        """
        Decodes raw audio bytes (MP3/WAV from TTS) and plays through speaker.
        Returns True if played to completion, False if aborted/interrupted.
        """
        if not audio_bytes:
            return False

        try:
            with io.BytesIO(audio_bytes) as bio:
                data, sample_rate = sf.read(bio, dtype="float32")
        except Exception as e:
            logger.error(f"Failed to decode audio bytes: {e}")
            return False

        return self.play_numpy(data, sample_rate)

    def play_numpy(self, data: np.ndarray, sample_rate: int) -> bool:
        """
        Plays numpy audio array and monitors abort_event for instant barge-in.
        """
        with self._lock:
            self.abort_event.clear()
            self.is_playing = True

        device = self._get_output_device()
        try:
            logger.debug(f"Playing audio: {len(data)} samples at {sample_rate}Hz on device {device}")
            sd.play(data, samplerate=sample_rate, device=device)

            # Poll while playing to allow instant interruption without busy-waiting
            duration_sec = len(data) / float(sample_rate)
            start_time = time.time()

            while time.time() - start_time < duration_sec:
                if self.abort_event.is_set():
                    logger.info("Audio playback aborted mid-stream (barge-in).")
                    sd.stop()
                    return False
                time.sleep(0.015)

            # Wait for final samples to clear hardware buffer
            sd.wait()
            return True

        except Exception as e:
            logger.error(f"Error during audio stream playback: {e}")
            return False
        finally:
            with self._lock:
                self.is_playing = False

    def interrupt(self):
        """Immediately halts active audio output."""
        if self.is_playing:
            logger.info("Interrupt signal dispatched to player.")
            self.abort_event.set()
            try:
                sd.stop()
            except Exception:
                pass
            with self._lock:
                self.is_playing = False


# Global player instance
player = InterruptibleAudioPlayer()
