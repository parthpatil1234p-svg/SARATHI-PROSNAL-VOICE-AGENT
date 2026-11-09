"""Application settings using Pydantic Settings."""

import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory: handles both live development and PyInstaller frozen executable
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLE_DIR = Path(sys._MEIPASS)
    EXE_DIR = Path(sys.executable).parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent.parent
    EXE_DIR = BUNDLE_DIR

BASE_DIR = BUNDLE_DIR

# Determine .env location: prefer .env next to executable if present, else bundled
_env_candidate = EXE_DIR / ".env"
ENV_FILE_PATH = str(_env_candidate if _env_candidate.exists() else (BUNDLE_DIR / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Assistant Persona
    ASSISTANT_NAME: str = "SARATHI"
    USER_NAME: str = "Parth"

    # LLM Configuration
    GROQ_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    OPENAI_API_KEY: str = Field(default="")
    DEFAULT_LLM_PROVIDER: str = "groq"  # "groq" or "gemini"
    DEFAULT_LLM_MODEL: str = "qwen/qwen3.8-27b"
    FALLBACK_LLM_MODEL: str = "openai/gpt-oss-20b"
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
    WAKE_WORD_THRESHOLD: float = 0.50

    # Audio Stream Parameters
    SAMPLE_RATE: int = 16000
    CHANNELS: int = 1
    CHUNK_SIZE: int = 1280  # 80ms chunk at 16kHz
    MIC_INPUT_GAIN: float = 2.5  # Software pre-amp boost for laptop / quiet microphones
    AUDIO_INPUT_DEVICE_INDEX: str | None = None
    AUDIO_OUTPUT_DEVICE_INDEX: str | None = None

    # VAD & Turn-Taking (Calibrated for high accuracy and natural conversational pauses)
    VOICE_ACTIVITY_THRESHOLD: float = 0.028
    SILENCE_TIMEOUT_MS: int = 1400  # 1400ms natural conversational pause allowing multi-clause thoughts without cutoffs

    # Latency Optimization & Metric Flags
    ENABLE_LATENCY_METRICS: bool = True
    GROQ_REASONING_EFFORT: str = "low"  # "low", "medium", "high"
    ENABLE_LLM_LOW_LATENCY: bool = True
    ENABLE_RULE_FAST_PATH: bool = False  # Set to False so conversational queries and greetings hit Groq LLM
    CONTINUOUS_VOICE_MODE: bool = False  # Waits strictly for 'Hey Sarathi' wake word in IDLE before capturing voice turns
    MOBILE_NOTIFY_TOPIC: str = "sarathi_parth_alerts"
    ENABLE_PERSISTENT_HTTP_CLIENT: bool = True
    ENABLE_FLAC_COMPRESSION: bool = True
    GROQ_TIMEOUT_SEC: float = 8.0
    VAD_ENGINE: str = "silero"  # "rms" or "silero"
    ENABLE_SPECULATIVE_STT: bool = False
    ENABLE_PIPELINED_TTS_QUEUE: bool = True
    ENABLE_EARLY_FILLERS: bool = False  # Avoid interrupting user pauses with generic filler phrases

    # Supabase Cloud Sync
    SUPABASE_URL: str = Field(default="")
    SUPABASE_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")
    ENABLE_SUPABASE_SYNC: bool = True

    # Vision & Screen Analysis
    VISION_MODEL: str = "llama-3.2-11b-vision-preview"

    # Paths
    ASSETS_DIR: Path = BASE_DIR / "assets"
    SOUNDS_DIR: Path = BASE_DIR / "assets" / "sounds"
    MODELS_DIR: Path = BASE_DIR / "assets" / "models"


settings = Settings()
