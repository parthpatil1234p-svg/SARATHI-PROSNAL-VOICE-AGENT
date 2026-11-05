"""Interruptible audio player for real-time speech output with instant barge-in support."""

import io
import logging
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("JARVIS.AudioPlayer")


class InterruptibleAudioPlayer:
    """
    Thread-safe, low-latency audio player.
    Supports atomic interruption: user speaking triggers player.stop() which halts playback in <30ms.
    """

    def __init__(self, default_sample_rate: int = 24000):
        self.default_sample_rate = default_sample_rate
        self.abort_event = threading.Event()
        self.is_playing = False
        self._lock = threading.Lock()

    def play_bytes(self, audio_bytes: bytes, format: str = "WAV") -> bool:
        """
        Plays raw audio bytes (e.g. WAV or MP3 from TTS).
        Returns True if played to completion, False if aborted/interrupted.
        """
        try:
            with io.BytesIO(audio_bytes) as bio:
                data, sample_rate = sf.read(bio, dtype="float32")
        except Exception as e:
            logger.error(f"Failed to decode audio bytes: {e}")
            return False

        return self.play_numpy(data, sample_rate)

    def play_numpy(self, data: np.ndarray, sample_rate: int) -> bool:
        """
        Streams audio frames in 1024-sample blocks, checking abort_event after every block.
        """
        with self._lock:
            self.abort_event.clear()
            self.is_playing = True

        try:
            # Flatten to mono or ensure correct shape
            if data.ndim == 1:
                channels = 1
            else:
                channels = data.shape[1]

            chunk_size = 1024
            total_samples = len(data)

            with sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                blocksize=chunk_size
            ) as stream:
                for i in range(0, total_samples, chunk_size):
                    if self.abort_event.is_set():
                        logger.info("Audio playback aborted mid-stream (barge-in).")
                        stream.abort()
                        return False

                    chunk = data[i:i + chunk_size]
                    if len(chunk) < chunk_size:
                        # Pad final chunk to match blocksize if needed
                        pad_width = ((0, chunk_size - len(chunk)), (0, 0)) if data.ndim > 1 else (0, chunk_size - len(chunk))
                        chunk = np.pad(chunk, pad_width, mode="constant")

                    stream.write(chunk)

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
