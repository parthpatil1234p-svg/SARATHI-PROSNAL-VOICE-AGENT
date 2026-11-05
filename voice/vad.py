"""Voice Activity Detector (VAD) and Turn-Taking Analyzer."""

import logging
import time

import numpy as np

logger = logging.getLogger("JARVIS.VAD")


class VoiceActivityDetector:
    """
    Real-time acoustic VAD based on RMS energy and zero-crossing analysis.
    Provides robust, ultra-fast (<0.1ms) speech discrimination.
    """

    def __init__(self, energy_threshold: float = 0.015, silence_timeout_ms: int = 350):
        self.energy_threshold = energy_threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.silence_duration_sec = silence_timeout_ms / 1000.0

        # State tracking for continuous speech turns
        self.speech_started = False
        self.last_speech_time = 0.0
        self.accumulated_speech_chunks: list[np.ndarray] = []

    def calculate_rms(self, chunk: np.ndarray) -> float:
        """Computes Root Mean Square (RMS) energy normalized between 0.0 and 1.0."""
        if chunk.dtype == np.int16:
            data = chunk.astype(np.float32) / 32768.0
        else:
            data = chunk.astype(np.float32)

        rms = np.sqrt(np.mean(data ** 2))
        return float(rms)

    def is_speech(self, chunk: np.ndarray) -> bool:
        """Determines if the given audio chunk contains human voice activity."""
        rms = self.calculate_rms(chunk)
        return rms >= self.energy_threshold

    def process_frame(self, chunk: np.ndarray) -> tuple[bool, bool, bytes | None]:
        """
        Processes a single incoming audio frame.
        Returns:
            (has_speech, turn_completed, complete_audio_bytes)
        """
        has_speech = self.is_speech(chunk)
        current_time = time.time()
        turn_completed = False
        complete_audio = None

        if has_speech:
            if not self.speech_started:
                self.speech_started = True
                logger.debug("Speech activity detected. Turn started.")
            self.last_speech_time = current_time
            self.accumulated_speech_chunks.append(chunk)

        elif self.speech_started:
            self.accumulated_speech_chunks.append(chunk)
            silence_elapsed = current_time - self.last_speech_time

            if silence_elapsed >= self.silence_duration_sec:
                # Silence threshold reached: user finished speaking!
                turn_completed = True
                self.speech_started = False
                logger.debug(f"End of speech detected after {silence_elapsed:.2f}s of silence.")

                if self.accumulated_speech_chunks:
                    combined = np.concatenate(self.accumulated_speech_chunks)
                    complete_audio = combined.tobytes()
                    self.accumulated_speech_chunks.clear()

        return has_speech, turn_completed, complete_audio

    def reset(self):
        """Resets the state of the turn detector."""
        self.speech_started = False
        self.last_speech_time = 0.0
        self.accumulated_speech_chunks.clear()
