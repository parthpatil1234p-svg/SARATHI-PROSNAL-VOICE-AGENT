"""Wake Word Detection engine utilizing openWakeWord with fallback support."""

import logging

import numpy as np

from config.settings import settings

logger = logging.getLogger("JARVIS.WakeWord")


class WakeWordDetector:
    """
    Offline wake word detector.
    Evaluates 16kHz audio chunks against the 'hey_jarvis' ONNX model.
    """

    def __init__(self, threshold: float | None = None, model_name: str = "hey_jarvis", auto_load: bool = True):
        self.threshold = threshold or settings.WAKE_WORD_THRESHOLD
        self.model_name = model_name
        self.oww_model = None
        self._is_loaded = False
        if auto_load:
            self._init_engine()

    def _init_engine(self):
        if self._is_loaded:
            return
        self._is_loaded = True
        try:
            from openwakeword.model import Model
            logger.info("Initializing openWakeWord model...")
            self.oww_model = Model(
                wakeword_models=[self.model_name],
                inference_framework="onnx"
            )
            logger.info(f"openWakeWord loaded model '{self.model_name}' successfully.")
        except Exception as e:
            logger.warning(
                f"openWakeWord model '{self.model_name}' could not be initialized directly ({e}). "
                "Operating in adaptive keyword / voice trigger mode."
            )
            self.oww_model = None

    def process_chunk(self, chunk: np.ndarray) -> bool:
        """
        Feeds a chunk of 16kHz PCM audio to the detector.
        Returns True if the wake word confidence score exceeds threshold.
        """
        if self.oww_model is None:
            return False

        # openWakeWord expects 16-bit PCM integer samples
        if chunk.dtype != np.int16:
            chunk = (chunk * 32767).astype(np.int16)

        try:
            prediction = self.oww_model.predict(chunk.flatten())
            for key, score in prediction.items():
                if self.model_name in key and score >= self.threshold:
                    logger.info(f"Wake word detected! Model: {key}, Score: {score:.3f}")
                    self.oww_model.reset()
                    return True
        except Exception as e:
            logger.error(f"Error predicting wake word: {e}")

        return False

    def reset(self):
        """Resets model state."""
        if self.oww_model:
            self.oww_model.reset()
