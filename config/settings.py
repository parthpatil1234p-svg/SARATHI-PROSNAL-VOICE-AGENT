"""Application settings using Pydantic Settings."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Assistant Persona
    ASSISTANT_NAME: str = "JARVIS"
    USER_NAME: str = "Sir"

    # LLM Configuration
    GROQ_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")
    DEFAULT_LLM_PROVIDER: str = "groq"  # "groq" or "gemini"
    DEFAULT_LLM_MODEL: str = "openai/gpt-oss-20b"
    FALLBACK_LLM_MODEL: str = "qwen/qwen3.8-27b"
    DEFAULT_GEMINI_MODEL: str = "gemini-flash-latest"

    # STT Configuration
    STT_PROVIDER: str = Field(default="whisper")  # "deepgram" or "whisper"
    DEEPGRAM_API_KEY: str = Field(default="")
    LOCAL_WHISPER_MODEL: str = "base.en"

    # TTS Configuration
    TTS_PROVIDER: str = Field(default="edge_tts")  # "edge_tts", "sapi" (ultra-fast 150ms), or "elevenlabs"
    EDGE_TTS_VOICE: str = "en-GB-RyanNeural"  # Crisp, formal British male accent
    ELEVENLABS_API_KEY: str = Field(default="")
    ELEVENLABS_VOICE_ID: str = Field(default="")

    # Wake Word Configuration
    WAKE_WORD_ENGINE: str = "openwakeword"
    WAKE_WORD_NAME: str = "hey_jarvis"
    PICOVOICE_ACCESS_KEY: str = Field(default="")
    WAKE_WORD_THRESHOLD: float = 0.60

    # Audio Stream Parameters
    SAMPLE_RATE: int = 16000
    CHANNELS: int = 1
    CHUNK_SIZE: int = 1280  # 80ms chunk at 16kHz
    AUDIO_INPUT_DEVICE_INDEX: str | None = None
    AUDIO_OUTPUT_DEVICE_INDEX: str | None = None

    # VAD & Turn-Taking (Aggressive 220ms silence timeout for minimal latency)
    VOICE_ACTIVITY_THRESHOLD: float = 0.015
    SILENCE_TIMEOUT_MS: int = 220  # milliseconds of silence to trigger end-of-speech

    # Vision & Screen Analysis
    VISION_MODEL: str = "llama-3.2-11b-vision-preview"

    # Paths
    ASSETS_DIR: Path = BASE_DIR / "assets"
    SOUNDS_DIR: Path = BASE_DIR / "assets" / "sounds"
    MODELS_DIR: Path = BASE_DIR / "assets" / "models"


settings = Settings()
