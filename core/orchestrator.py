"""Central J.A.R.V.I.S. Conversational Orchestrator."""

import asyncio
import logging
import sys
import time

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console

from config.settings import settings
from core.state_machine import AssistantState, StateMachine
from llm.client import LLMClient
from llm.memory import ConversationMemory
from voice.audio_stream import AudioInputStream
from voice.player import player
from voice.sentence_chunker import SentenceChunker
from voice.stt import get_stt_engine
from voice.tts import get_tts_engine
from voice.vad import VoiceActivityDetector
from voice.wake_word import WakeWordDetector

logger = logging.getLogger("JARVIS.Orchestrator")
console = Console(force_terminal=True, legacy_windows=False)


class AssistantOrchestrator:
    """
    Central nervous system for J.A.R.V.I.S.
    Coordinates audio capture, wake word spotting, VAD, STT, LLM streaming,
    sentence chunking, TTS synthesis, and barge-in interruption.
    """

    def __init__(self):
        self.state_machine = StateMachine(AssistantState.IDLE)
        self.memory = ConversationMemory()
        self.llm = LLMClient()
        self.tts = get_tts_engine()
        self.stt = get_stt_engine()
        self.vad = VoiceActivityDetector(silence_timeout_ms=settings.SILENCE_TIMEOUT_MS)
        self.wake_detector = WakeWordDetector()
        self.sentence_chunker = SentenceChunker()
        self.audio_stream = AudioInputStream(
            sample_rate=settings.SAMPLE_RATE,
            chunk_size=settings.CHUNK_SIZE
        )
        self.is_running = False

    async def start_voice_loop(self):
        """Main asynchronous event loop for real-time voice interaction."""
        self.is_running = True
        self.audio_stream.start()
        console.print(f"[bold cyan]⚡ {settings.ASSISTANT_NAME} initialized and listening for 'Hey Jarvis'...[/bold cyan]")

        try:
            while self.is_running:
                # 1. State: IDLE - Listening for Wake Word
                if self.state_machine.current_state == AssistantState.IDLE:
                    chunk = self.audio_stream.read_chunk(timeout=0.1)
                    if chunk is not None and self.wake_detector.process_chunk(chunk):
                        console.print("[bold green]🔔 Wake word detected![/bold green]")
                        self.state_machine.transition_to(AssistantState.WAKE_DETECTED)
                        await self._play_wake_chime()
                        self.state_machine.transition_to(AssistantState.LISTENING)
                        self.vad.reset()

                # 2. State: LISTENING - Capturing user speech
                elif self.state_machine.current_state == AssistantState.LISTENING:
                    chunk = self.audio_stream.read_chunk(timeout=0.1)
                    if chunk is not None:
                        has_speech, turn_completed, audio_bytes = self.vad.process_frame(chunk)
                        if turn_completed and audio_bytes:
                            console.print("[dim]🎤 Speech turn completed. Transcribing...[/dim]")
                            self.state_machine.transition_to(AssistantState.PROCESSING)
                            await self._handle_speech_turn(audio_bytes)

                # 3. State: SPEAKING - Monitoring for user barge-in
                elif self.state_machine.current_state == AssistantState.SPEAKING:
                    chunk = self.audio_stream.read_chunk(timeout=0.05)
                    if chunk is not None:
                        # If user speaks loudly during playback, trigger instant interruption
                        if self.vad.is_speech(chunk):
                            console.print("[bold yellow]🛑 User barge-in detected! Halting speech output.[/bold yellow]")
                            player.interrupt()
                            self.state_machine.transition_to(AssistantState.INTERRUPTED)
                            await asyncio.sleep(0.1)
                            self.state_machine.transition_to(AssistantState.LISTENING)
                            self.vad.reset()

                await asyncio.sleep(0.005)

        except asyncio.CancelledError:
            logger.info("Voice loop cancelled.")
        finally:
            self.stop()

    async def _handle_speech_turn(self, audio_bytes: bytes):
        """Transcribes speech and initiates LLM response pipeline."""
        start_time = time.time()
        transcript = await self.stt.transcribe(audio_bytes)

        if not transcript.strip():
            console.print("[dim]No audible speech transcribed.[/dim]")
            self.state_machine.transition_to(AssistantState.IDLE)
            return

        stt_latency = (time.time() - start_time) * 1000
        console.print(f"[bold white]User:[/bold white] {transcript} [dim]({stt_latency:.0f}ms STT)[/dim]")

        # Check for direct stop commands
        if transcript.lower().strip() in ("stop", "quiet", "cancel", "nevermind", "shut up"):
            player.interrupt()
            self.state_machine.transition_to(AssistantState.IDLE)
            return

        await self.process_text_turn(transcript)

    async def process_text_turn(self, user_text: str):
        """Processes a textual user prompt through LLM and streams spoken response."""
        self.state_machine.transition_to(AssistantState.PROCESSING)
        self.memory.add_user_message(user_text)

        console.print(f"[bold cyan]{settings.ASSISTANT_NAME}:[/bold cyan] ", end="")
        token_stream = self.llm.stream_response(self.memory)
        sentence_stream = self.sentence_chunker.chunk_stream(token_stream)

        self.state_machine.transition_to(AssistantState.SPEAKING)
        first_audio_played = False
        start_time = time.time()

        try:
            async for sentence in sentence_stream:
                if self.state_machine.current_state == AssistantState.INTERRUPTED:
                    console.print("\n[yellow][Interrupted][/yellow]")
                    break

                console.print(f"[cyan]{sentence}[/cyan] ", end="")

                # Synthesize sentence audio
                audio_bytes = await self.tts.synthesize(sentence)
                if not first_audio_played:
                    ttfa = (time.time() - start_time) * 1000
                    logger.info(f"Time-to-First-Audio (TTFA): {ttfa:.1f}ms")
                    first_audio_played = True

                # Play audio chunk (aborts if interrupted)
                success = player.play_bytes(audio_bytes)
                if not success:
                    break

            console.print()
        finally:
            if self.state_machine.current_state != AssistantState.INTERRUPTED:
                self.state_machine.transition_to(AssistantState.IDLE)

    async def _play_wake_chime(self):
        """Synthesizes or plays an acoustic activation cue."""
        try:
            # Generate a quick audio cue
            audio = await self.tts.synthesize("Yes, sir?")
            player.play_bytes(audio)
        except Exception as e:
            logger.error(f"Error playing wake chime: {e}")

    def stop(self):
        """Stops the orchestrator and cleans up resources."""
        self.is_running = False
        player.interrupt()
        self.audio_stream.stop()
        logger.info("Assistant orchestrator terminated.")
