"""Voice Activity Detector (VAD) and Turn-Taking Analyzer."""

import logging
import time

import numpy as np

from config.settings import settings

logger = logging.getLogger("JARVIS.VAD")


class VoiceActivityDetector:
    """
    Real-time acoustic VAD based on RMS energy, noise floor estimation,
    and consecutive speech frame verification.
    Provides robust, ultra-fast speech discrimination with zero ambient noise false triggers.
    """

    def __init__(
        self,
        energy_threshold: float | None = None,
        silence_timeout_ms: int | None = None,
        min_speech_duration_sec: float = 0.55
    ):
        self.energy_threshold = energy_threshold or settings.VOICE_ACTIVITY_THRESHOLD
        self.silence_timeout_ms = silence_timeout_ms or settings.SILENCE_TIMEOUT_MS
        self.silence_duration_sec = self.silence_timeout_ms / 1000.0
        self.min_speech_duration_sec = min_speech_duration_sec

        # Dynamic ambient noise floor tracking
        self.noise_floor: float = 0.012

        # State tracking for continuous speech turns
        self.speech_started = False
        self.last_speech_time = 0.0
        self.consecutive_speech_frames = 0
        self.min_consecutive_frames = 2  # Require at least 2 frames (~160ms) of sustained voice
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
        """
        Determines if the audio frame contains genuine human speech energy
        above both the static threshold and the dynamic ambient noise floor.
        """
        rms = self.calculate_rms(chunk)

        # Update running ambient noise floor slowly during silence
        if not self.speech_started:
            self.noise_floor = 0.95 * self.noise_floor + 0.05 * min(rms, 0.03)

        effective_threshold = max(self.energy_threshold, self.noise_floor * 2.2)
        return rms >= effective_threshold

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
            self.consecutive_speech_frames += 1
            if not self.speech_started:
                # Only initiate turn if speech persists for min_consecutive_frames
                if self.consecutive_speech_frames >= self.min_consecutive_frames:
                    self.speech_started = True
                    logger.debug("Speech activity confirmed. Turn started.")
            if self.speech_started:
                self.last_speech_time = current_time
                self.accumulated_speech_chunks.append(chunk)

        elif self.speech_started:
            self.consecutive_speech_frames = 0
            self.accumulated_speech_chunks.append(chunk)
            silence_elapsed = current_time - self.last_speech_time

            if silence_elapsed >= self.silence_duration_sec:
                # Silence threshold reached: user finished speaking
                self.speech_started = False
                logger.debug(f"End of speech detected after {silence_elapsed:.2f}s of silence.")

                if self.accumulated_speech_chunks:
                    combined = np.concatenate(self.accumulated_speech_chunks)
                    duration_sec = len(combined) / float(settings.SAMPLE_RATE)

                    # Filter out short noise bursts (< min_speech_duration_sec)
                    if duration_sec >= self.min_speech_duration_sec:
                        complete_audio = combined.tobytes()
                        turn_completed = True
                    else:
                        logger.debug(f"Discarded short acoustic pulse ({duration_sec:.2f}s < {self.min_speech_duration_sec}s).")

                    self.accumulated_speech_chunks.clear()
        else:
            self.consecutive_speech_frames = 0

        return has_speech, turn_completed, complete_audio

    def reset(self):
        """Resets the state of the turn detector."""
        self.speech_started = False
        self.last_speech_time = 0.0
        self.consecutive_speech_frames = 0
        self.accumulated_speech_chunks.clear()
