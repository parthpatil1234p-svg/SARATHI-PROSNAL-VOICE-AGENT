"""Voice Activity Detector (VAD) and Turn-Taking Analyzers.

Provides:
- SileroVAD: Deep-learning neural VAD (ONNX Runtime, 20-30ms frames, ~200ms pre-roll, split-turn logging).
- RMSVAD: Lightweight acoustic energy VAD (calibrated fallback).
- VoiceActivityDetector: Unified interface dynamically selecting the engine configured in settings.
"""

import collections
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from config.settings import BASE_DIR, settings
from voice.vad_interface import BaseVAD

logger = logging.getLogger("SARATHI.VAD")


class RMSVAD(BaseVAD):
    """
    Real-time acoustic VAD based on RMS energy, noise floor estimation,
    and consecutive speech frame verification. Preserved as a robust zero-dependency fallback.
    """

    def __init__(
        self,
        energy_threshold: float | None = None,
        silence_timeout_ms: int | None = None,
        min_speech_duration_sec: float = 0.20
    ):
        self.energy_threshold = energy_threshold or settings.VOICE_ACTIVITY_THRESHOLD
        self.silence_timeout_ms = silence_timeout_ms or settings.SILENCE_TIMEOUT_MS
        self.silence_duration_sec = self.silence_timeout_ms / 1000.0
        self.min_speech_duration_sec = min_speech_duration_sec

        # Dynamic ambient noise floor tracking
        self.noise_floor: float = 0.012

        # State tracking for continuous speech turns
        self.speech_started = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self.consecutive_speech_frames = 0
        self.min_consecutive_frames = 2  # Require at least 2 frames (~160ms) of sustained voice
        self.accumulated_speech_chunks: list[np.ndarray] = []
        self._saved_last_voice_time = 0.0

    def calculate_rms(self, chunk: np.ndarray) -> float:
        """Computes Root Mean Square (RMS) energy normalized between 0.0 and 1.0."""
        if chunk.dtype == np.int16:
            data = chunk.astype(np.float32) / 32768.0
        else:
            data = chunk.astype(np.float32)

        rms = np.sqrt(np.mean(data ** 2))
        return float(rms)

    def is_speech(self, chunk: np.ndarray) -> bool:
        """Determines if the audio frame contains energy above the dynamic noise floor."""
        rms = self.calculate_rms(chunk)
        if not self.speech_started:
            self.noise_floor = 0.95 * self.noise_floor + 0.05 * min(rms, 0.03)

        effective_threshold = max(self.energy_threshold, self.noise_floor * 2.2)
        return rms >= effective_threshold

    def process_frame(self, chunk: np.ndarray) -> tuple[bool, bool, bytes | None]:
        has_speech = self.is_speech(chunk)
        current_time = time.time()
        turn_completed = False
        complete_audio = None

        if has_speech:
            self.consecutive_speech_frames += 1
            if not self.speech_started:
                if self.consecutive_speech_frames >= self.min_consecutive_frames:
                    self.speech_started = True
                    self.speech_start_time = current_time
                    logger.debug("RMS VAD confirmed speech start.")
            if self.speech_started:
                self.last_speech_time = current_time
                self.accumulated_speech_chunks.append(chunk)

        elif self.speech_started:
            self.consecutive_speech_frames = 0
            self.accumulated_speech_chunks.append(chunk)
            silence_elapsed = current_time - self.last_speech_time

            if silence_elapsed >= self.silence_duration_sec:
                self.speech_started = False
                if self.accumulated_speech_chunks:
                    combined = np.concatenate(self.accumulated_speech_chunks)
                    duration_sec = len(combined) / float(settings.SAMPLE_RATE)
                    if duration_sec >= self.min_speech_duration_sec:
                        complete_audio = combined.tobytes()
                        turn_completed = True
                        self._saved_last_voice_time = self.last_speech_time
                    self.accumulated_speech_chunks.clear()
        else:
            self.consecutive_speech_frames = 0

        return has_speech, turn_completed, complete_audio

    @property
    def last_voice_timestamp(self) -> float:
        return getattr(self, "_saved_last_voice_time", self.last_speech_time)

    @property
    def silence_elapsed_sec(self) -> float:
        if not self.speech_started or self.last_speech_time == 0.0:
            return 0.0
        return max(0.0, time.time() - self.last_speech_time)

    def get_current_audio_snapshot(self) -> bytes | None:
        if not self.speech_started or not self.accumulated_speech_chunks:
            return None
        return np.concatenate(self.accumulated_speech_chunks).tobytes()

    def reset(self):
        self.speech_started = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self.consecutive_speech_frames = 0
        self.accumulated_speech_chunks.clear()

    def start_speech(self, chunk: np.ndarray | None = None):
        self.speech_started = True
        self.speech_start_time = time.time()
        self.last_speech_time = time.time()
        self.consecutive_speech_frames = self.min_consecutive_frames
        if chunk is not None:
            self.accumulated_speech_chunks.append(chunk)


class SileroVAD(BaseVAD):
    """
    Neural Voice Activity Detector powered by Silero VAD (ONNX Runtime).
    Features:
    - 20-30ms sub-framing (320-480 samples).
    - ~200ms pre-roll FIFO ring buffer to prevent clipping of soft initial phonemes.
    - Preserves calibrated 450ms silence timeout window.
    - Split-turn logger: detects and logs speech resuming within 1000ms of a cutoff.
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        silence_timeout_ms: int | None = None,
        speech_threshold: float = 0.16,
        preroll_ms: int = 200,
        min_speech_duration_sec: float = 0.20,
        sample_rate: int = 16000
    ):
        self.sample_rate = sample_rate
        self.silence_timeout_ms = silence_timeout_ms or settings.SILENCE_TIMEOUT_MS
        self.silence_duration_sec = self.silence_timeout_ms / 1000.0
        self.speech_threshold = speech_threshold
        self.min_speech_duration_sec = min_speech_duration_sec

        # Locate ONNX model
        resolved_path = self._resolve_model_path(model_path)
        import onnxruntime as ort
        # Suppress ONNX runtime logging
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(str(resolved_path), sess_options=opts)

        # Model hidden states
        self.h = np.zeros((2, 1, 64), dtype=np.float32)
        self.c = np.zeros((2, 1, 64), dtype=np.float32)
        self.sr_tensor = np.array(self.sample_rate, dtype=np.int64)

        # Pre-roll ring buffer (~200ms at 16kHz = 3200 samples)
        self.preroll_samples = int(self.sample_rate * (preroll_ms / 1000.0))
        self.preroll_buffer: collections.deque[np.int16] = collections.deque(maxlen=self.preroll_samples)

        # Sub-framing: 320 samples = 20ms at 16kHz
        self.frame_size = 320

        # State tracking
        self.speech_started = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self._saved_last_voice_time = 0.0
        self.last_cut_time = 0.0
        self.accumulated_chunks: list[np.ndarray] = []
        self.consecutive_speech_frames = 0
        self.min_consecutive_frames = 2

    def _resolve_model_path(self, model_path: Path | str | None) -> Path:
        candidates = [
            Path(model_path) if model_path else None,
            settings.MODELS_DIR / "silero_vad.onnx",
            BASE_DIR / "assets" / "models" / "silero_vad.onnx",
        ]
        for c in candidates:
            if c and c.exists():
                return c
        # Search site-packages fallback
        import faster_whisper
        fw_model = Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"
        if fw_model.exists():
            return fw_model

        raise FileNotFoundError("Silero VAD ONNX model not found in assets or dependencies.")

    def _infer_probability(self, frame_float: np.ndarray) -> float:
        """Runs one sub-frame through Silero ONNX and updates hidden recurrent states."""
        # Ensure shape [1, N]
        inp = frame_float.reshape(1, -1)
        out, self.h, self.c = self.session.run(
            None,
            {
                "input": inp,
                "sr": self.sr_tensor,
                "h": self.h,
                "c": self.c
            }
        )
        return float(out[0][0])

    def is_speech(self, chunk: np.ndarray) -> bool:
        """Evaluates speech probability across the incoming audio chunk using hybrid neural + acoustic energy."""
        pcm = chunk.astype(np.float32)
        if chunk.dtype == np.int16:
            pcm = pcm / 32768.0

        rms = float(np.sqrt(np.mean(pcm ** 2)))
        # Strictly reject ambient background hiss and digital silence below speech floor
        if rms < 0.006:
            return False

        num_subframes = max(1, len(pcm) // self.frame_size)
        probs = []
        for i in range(num_subframes):
            sub = pcm[i * self.frame_size : (i + 1) * self.frame_size]
            if len(sub) < self.frame_size:
                sub = np.pad(sub, (0, self.frame_size - len(sub)))
            prob = self._infer_probability(sub)
            probs.append(prob)

        # Hybrid check: neural probability OR clear vocal acoustic energy
        neural_speech = max(probs) >= self.speech_threshold
        energy_speech = rms >= 0.025
        return neural_speech or energy_speech

    def process_frame(self, chunk: np.ndarray) -> tuple[bool, bool, bytes | None]:
        """
        Processes frame with neural speech evaluation, pre-roll buffer, and split turn check.
        """
        # Always feed raw samples into pre-roll ring buffer when speech has not started
        pcm_int16 = chunk if chunk.dtype == np.int16 else (chunk * 32767).astype(np.int16)
        if not self.speech_started:
            self.preroll_buffer.extend(pcm_int16.tolist())

        has_speech = self.is_speech(chunk)
        current_time = time.time()
        turn_completed = False
        complete_audio = None

        if has_speech:
            self.consecutive_speech_frames += 1
            if not self.speech_started:
                if self.consecutive_speech_frames >= self.min_consecutive_frames:
                    self.speech_started = True
                    self.speech_start_time = current_time

                    # Split-turn logging check: did user resume within 1000ms of last cutoff?
                    if self.last_cut_time > 0:
                        split_gap = current_time - self.last_cut_time
                        if split_gap < 1.0:
                            logger.warning(
                                f"[Split Turn Detected] User speech resumed {split_gap * 1000:.1f}ms after cut (gap < 1.0s)."
                            )

                    # Prepend ~200ms pre-roll so initial syllable / consonant is never clipped
                    if self.preroll_buffer:
                        preroll_arr = np.array(self.preroll_buffer, dtype=np.int16)
                        self.accumulated_chunks.append(preroll_arr)
                        self.preroll_buffer.clear()
                    logger.debug("Silero VAD confirmed speech. Turn started with pre-roll.")

            if self.speech_started:
                self.last_speech_time = current_time
                self.accumulated_chunks.append(pcm_int16)

        elif self.speech_started:
            self.consecutive_speech_frames = 0
            self.accumulated_chunks.append(pcm_int16)
            silence_elapsed = current_time - self.last_speech_time

            # Preserved exact 450ms silence timeout
            if silence_elapsed >= self.silence_duration_sec:
                self.speech_started = False
                logger.debug(f"Silero VAD detected end of speech ({silence_elapsed:.2f}s silence).")

                if self.accumulated_chunks:
                    combined = np.concatenate(self.accumulated_chunks)
                    duration_sec = len(combined) / float(self.sample_rate)

                    if duration_sec >= self.min_speech_duration_sec:
                        complete_audio = combined.tobytes()
                        turn_completed = True
                        self._saved_last_voice_time = self.last_speech_time
                        self.last_cut_time = current_time  # Mark cutoff time for split turn detection
                    else:
                        logger.debug(f"Discarded acoustic artifact ({duration_sec:.2f}s).")

                    self.accumulated_chunks.clear()
        else:
            self.consecutive_speech_frames = 0

        return has_speech, turn_completed, complete_audio

    @property
    def last_voice_timestamp(self) -> float:
        return getattr(self, "_saved_last_voice_time", self.last_speech_time)

    @property
    def silence_elapsed_sec(self) -> float:
        if not self.speech_started or self.last_speech_time == 0.0:
            return 0.0
        return max(0.0, time.time() - self.last_speech_time)

    def get_current_audio_snapshot(self) -> bytes | None:
        if not self.speech_started or not self.accumulated_chunks:
            return None
        return np.concatenate(self.accumulated_chunks).tobytes()

    def reset(self):
        self.speech_started = False
        self.speech_start_time = 0.0
        self.last_speech_time = 0.0
        self.consecutive_speech_frames = 0
        self.accumulated_chunks.clear()
        self.preroll_buffer.clear()
        self.h.fill(0)
        self.c.fill(0)

    def start_speech(self, chunk: np.ndarray | None = None):
        self.speech_started = True
        self.speech_start_time = time.time()
        self.last_speech_time = time.time()
        self.consecutive_speech_frames = self.min_consecutive_frames
        if chunk is not None:
            pcm_int16 = chunk if chunk.dtype == np.int16 else (chunk * 32767).astype(np.int16)
            self.accumulated_chunks.append(pcm_int16)


class VoiceActivityDetector(BaseVAD):
    """
    Unified Voice Activity Detector adapter.
    Instantiates SileroVAD when settings.VAD_ENGINE == 'silero' (with automatic RMS fallback),
    or RMSVAD when settings.VAD_ENGINE == 'rms'.
    """

    def __init__(
        self,
        energy_threshold: float | None = None,
        silence_timeout_ms: int | None = None,
        min_speech_duration_sec: float = 0.20,
        engine: str | None = None,
        **kwargs: Any
    ):
        if engine is not None:
            chosen_engine = engine.lower()
        elif energy_threshold is not None:
            chosen_engine = "rms"
        else:
            chosen_engine = settings.VAD_ENGINE.lower()

        if chosen_engine == "silero":
            try:
                self._engine: BaseVAD = SileroVAD(
                    silence_timeout_ms=silence_timeout_ms,
                    min_speech_duration_sec=min_speech_duration_sec,
                    **kwargs
                )
                logger.info("Initialized Silero neural VAD engine with pre-roll.")
                return
            except Exception as e:
                logger.warning(f"Failed to initialize Silero VAD ({e}); falling back to RMS VAD.")

        self._engine = RMSVAD(
            energy_threshold=energy_threshold,
            silence_timeout_ms=silence_timeout_ms,
            min_speech_duration_sec=min_speech_duration_sec
        )
        logger.info("Initialized RMS acoustic VAD engine.")

    def is_speech(self, chunk: np.ndarray) -> bool:
        return self._engine.is_speech(chunk)

    def process_frame(self, chunk: np.ndarray) -> tuple[bool, bool, bytes | None]:
        return self._engine.process_frame(chunk)

    @property
    def speech_started(self) -> bool:
        return getattr(self._engine, "speech_started", False)

    @property
    def speech_start_time(self) -> float:
        return getattr(self._engine, "speech_start_time", 0.0)

    @property
    def last_speech_time(self) -> float:
        return getattr(self._engine, "last_speech_time", 0.0)

    @property
    def last_voice_timestamp(self) -> float:
        return self._engine.last_voice_timestamp

    @property
    def silence_elapsed_sec(self) -> float:
        return self._engine.silence_elapsed_sec

    def get_current_audio_snapshot(self) -> bytes | None:
        return self._engine.get_current_audio_snapshot()

    def reset(self):
        self._engine.reset()

    def start_speech(self, chunk: np.ndarray | None = None):
        if hasattr(self._engine, "start_speech"):
            self._engine.start_speech(chunk)
        else:
            self._engine.speech_started = True


__all__ = ["BaseVAD", "RMSVAD", "SileroVAD", "VoiceActivityDetector"]
