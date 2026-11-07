"""Abstract base class interface for Voice Activity Detectors."""

from abc import ABC, abstractmethod
import numpy as np


class BaseVAD(ABC):
    """Abstract interface for Voice Activity Detection engines."""

    @abstractmethod
    def process_frame(self, chunk: np.ndarray) -> tuple[bool, bool, bytes | None]:
        """
        Processes a single incoming audio frame.

        Args:
            chunk: Numpy array of audio samples (PCM int16 or float32).

        Returns:
            (has_speech, turn_completed, complete_audio_bytes)
        """
        pass

    @property
    @abstractmethod
    def last_voice_timestamp(self) -> float:
        """Returns the epoch timestamp of the last voiced audio frame before silence."""
        pass

    @property
    @abstractmethod
    def silence_elapsed_sec(self) -> float:
        """Returns elapsed seconds of continuous silence in the current speech turn."""
        pass

    @abstractmethod
    def get_current_audio_snapshot(self) -> bytes | None:
        """Returns a snapshot of audio bytes accumulated so far in the active turn."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets internal state, accumulator buffers, and speech timestamps."""
        pass

    def start_speech(self, chunk: np.ndarray | None = None) -> None:
        """Forces speech_started state and appends optional initial chunk."""
        pass
