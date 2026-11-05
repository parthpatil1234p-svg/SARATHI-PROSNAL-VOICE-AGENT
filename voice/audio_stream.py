"""Audio stream capture using sounddevice with thread-safe ring buffering."""

import logging
import queue
from collections.abc import Generator

import numpy as np
import sounddevice as sd

logger = logging.getLogger("JARVIS.AudioStream")


class AudioInputStream:
    """
    Continuous microphone stream manager.
    Captures 16kHz 16-bit mono audio into an asynchronous queue/ring buffer.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1280,  # 80ms chunk
        channels: int = 1,
        device_index: int | str | None = None
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.device_index = int(device_index) if device_index is not None and str(device_index).isdigit() else None

        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=100)
        self.stream: sd.InputStream | None = None
        self.is_running = False
        self.latest_rms: float = 0.0
        self.latest_level: int = 0

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """sounddevice callback invoked for every incoming audio block."""
        if status:
            logger.warning(f"Audio buffer status warning: {status}")

        if not self.is_running:
            return

        try:
            rms = float(np.sqrt(np.mean(indata ** 2)))
            self.latest_rms = rms
            self.latest_level = max(0, min(100, int(rms * 450)))
        except Exception:
            pass

        # Clone and convert to 16-bit PCM integer or float array
        pcm_chunk = (indata.copy() * 32767).astype(np.int16)
        try:
            self.audio_queue.put_nowait(pcm_chunk)
        except queue.Full:
            # Drop oldest frame to keep latency real-time
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                pass
            self.audio_queue.put_nowait(pcm_chunk)

    def start(self):
        """Starts the background audio stream."""
        if self.is_running:
            return

        self.is_running = True
        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.chunk_size,
            device=self.device_index,
            callback=self._audio_callback
        )
        self.stream.start()
        logger.info(f"Audio stream started (SampleRate: {self.sample_rate}Hz, Chunk: {self.chunk_size} frames)")

    def stop(self):
        """Stops and closes the audio stream."""
        if not self.is_running:
            return

        self.is_running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        # Drain queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        logger.info("Audio stream stopped.")

    def read_chunk(self, timeout: float = 0.5) -> np.ndarray | None:
        """Reads a single audio chunk from the queue with timeout."""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stream_chunks(self) -> Generator[np.ndarray, None, None]:
        """Generator yielding audio frames continuously."""
        while self.is_running:
            chunk = self.read_chunk()
            if chunk is not None:
                yield chunk

    @staticmethod
    def list_audio_devices() -> list[dict]:
        """Returns all host audio devices."""
        devices = sd.query_devices()
        return [
            {
                "index": i,
                "name": dev["name"],
                "max_inputs": dev["max_input_channels"],
                "max_outputs": dev["max_output_channels"],
                "default_samplerate": dev["default_samplerate"]
            }
            for i, dev in enumerate(devices)
        ]
