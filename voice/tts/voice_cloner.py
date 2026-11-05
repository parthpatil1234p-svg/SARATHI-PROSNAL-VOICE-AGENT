"""Voice Cloning manager supporting Instant Voice Cloning via ElevenLabs and local voice references."""

import logging
import os
import shutil
from pathlib import Path

import httpx

from config.settings import settings

logger = logging.getLogger("JARVIS.VoiceCloner")


class VoiceCloner:
    """
    Manages custom voice cloning for J.A.R.V.I.S.
    Uploads user-provided audio samples to create instant voice clones,
    and updates the active assistant voice configuration.
    """

    def __init__(self):
        self.voices_dir = settings.ASSETS_DIR / "voices"
        self.voices_dir.mkdir(parents=True, exist_ok=True)

    async def clone_from_audio_file(
        self,
        audio_file_path: str | Path,
        voice_name: str = "PersonalJarvisVoice",
        description: str = "Custom cloned voice for personal AI assistant"
    ) -> dict:
        """
        Takes an audio sample file (.wav, .mp3, .m4a), registers a voice clone,
        and binds it to the J.A.R.V.I.S. TTS engine.
        """
        source_path = Path(audio_file_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Audio file '{audio_file_path}' not found.")

        # 1. Save reference copy locally
        target_path = self.voices_dir / f"personal_voice{source_path.suffix}"
        shutil.copy(source_path, target_path)
        logger.info(f"Saved local voice reference to: {target_path}")

        # 2. If ElevenLabs API Key is available, create instant voice clone via API
        if settings.ELEVENLABS_API_KEY:
            try:
                voice_id = await self._upload_to_elevenlabs(source_path, voice_name, description)
                self._update_env_voice_id(voice_id)
                return {
                    "status": "success",
                    "provider": "elevenlabs",
                    "voice_id": voice_id,
                    "voice_name": voice_name,
                    "local_path": str(target_path),
                    "message": f"Successfully created custom voice clone '{voice_name}' (ID: {voice_id})!"
                }
            except Exception as e:
                logger.error(f"ElevenLabs voice cloning failed: {e}")
                return {
                    "status": "partial_success",
                    "provider": "local_reference",
                    "local_path": str(target_path),
                    "message": f"Local audio saved to {target_path.name}. ElevenLabs clone error: {e}"
                }

        return {
            "status": "success",
            "provider": "local_reference",
            "local_path": str(target_path),
            "message": f"Voice reference stored at '{target_path}'. Configure ELEVENLABS_API_KEY to activate cloud cloning."
        }

    async def _upload_to_elevenlabs(
        self, audio_path: Path, voice_name: str, description: str
    ) -> str:
        """Uploads the voice sample to ElevenLabs Instant Voice Cloning endpoint."""
        url = "https://api.elevenlabs.io/v1/voices/add"
        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(audio_path, "rb") as f:
                files = {
                    "files": (audio_path.name, f, "audio/mpeg" if audio_path.suffix == ".mp3" else "audio/wav")
                }
                data = {
                    "name": voice_name,
                    "description": description
                }
                resp = await client.post(url, headers=headers, data=data, files=files)
                resp.raise_for_status()
                result = resp.json()
                voice_id = result.get("voice_id")
                if not voice_id:
                    raise ValueError(f"No voice_id returned: {result}")
                return voice_id

    def _update_env_voice_id(self, voice_id: str):
        """Updates .env file with the newly generated voice ID."""
        env_path = settings.ASSETS_DIR.parent / ".env"
        lines = []
        found_id = False
        found_provider = False

        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = []
        for line in lines:
            if line.startswith("ELEVENLABS_VOICE_ID="):
                new_lines.append(f'ELEVENLABS_VOICE_ID="{voice_id}"\n')
                found_id = True
            elif line.startswith("TTS_PROVIDER="):
                new_lines.append('TTS_PROVIDER="elevenlabs"\n')
                found_provider = True
            else:
                new_lines.append(line)

        if not found_id:
            new_lines.append(f'ELEVENLABS_VOICE_ID="{voice_id}"\n')
        if not found_provider:
            new_lines.append('TTS_PROVIDER="elevenlabs"\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # Update in-memory settings
        settings.ELEVENLABS_VOICE_ID = voice_id
        settings.TTS_PROVIDER = "elevenlabs"
        logger.info(f"Updated .env with active ELEVENLABS_VOICE_ID='{voice_id}'")


voice_cloner = VoiceCloner()
