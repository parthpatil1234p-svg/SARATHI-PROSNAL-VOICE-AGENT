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
from core.event_bus import event_bus
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
        self.active_conversation_timeout: float = 0.0
        self.state_machine.add_listener(self._notify_state_change)

    def _notify_state_change(self, old_state: AssistantState, new_state: AssistantState):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(event_bus.publish("state_changed", new_state.name))
        except Exception:
            pass

    async def start_voice_loop(self):
        """Main asynchronous event loop for real-time voice interaction."""
        self.is_running = True
        self.audio_stream.start()
        console.print(f"[bold cyan]⚡ {settings.ASSISTANT_NAME} initialized and listening...[/bold cyan]")

        # Spoken confirmation that audio output is operational
        try:
            greeting = await self.tts.synthesize("All systems online, sir. I am listening.")
            player.play_bytes(greeting)
        except Exception as e:
            logger.warning(f"Initial greeting audio warning: {e}")

        try:
            while self.is_running:
                # 1. State: IDLE - Strictly listening for Wake Word ("Hey Jarvis") or active dialogue window
                if self.state_machine.current_state == AssistantState.IDLE:
                    chunk = self.audio_stream.read_chunk(timeout=0.1)
                    if chunk is not None:
                        wake_triggered = self.wake_detector.process_chunk(chunk)
                        in_dialogue_window = time.time() < self.active_conversation_timeout
                        # When outside dialogue window, strictly require wake word to prevent noise false triggers
                        has_speech = self.vad.is_speech(chunk) if in_dialogue_window else False

                        if wake_triggered:
                            console.print("[bold green]🔔 Wake word detected![/bold green]")
                            self.active_conversation_timeout = time.time() + 12.0
                            self.state_machine.transition_to(AssistantState.WAKE_DETECTED)
                            await self._play_wake_chime()
                            self.state_machine.transition_to(AssistantState.LISTENING)
                            self.vad.reset()
                        elif has_speech:
                            # User continued speaking naturally within the active conversation window
                            self.state_machine.transition_to(AssistantState.LISTENING)
                            self.vad.speech_started = True
                            self.vad.accumulated_speech_chunks.append(chunk)

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
                            asyncio.create_task(event_bus.publish("barge_in", {}))
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
        cleaned = transcript.strip().lower().rstrip(".,!?")

        # Blacklist background hiss artifacts and common Whisper hallucinations
        common_hallucinations = {
            "", "you", "thank you", "thank you.", "thanks", "thanks for watching",
            "bye", "subtitles", "subtitle", "hello", "hi", "yes", "no", "um", "uh", ".", "..."
        }
        if cleaned in common_hallucinations or len(cleaned) < 2:
            console.print(f"[dim]Filtered out acoustic noise artifact: '{transcript}'[/dim]")
            self.state_machine.transition_to(AssistantState.IDLE)
            return

        console.print(f"[bold white]User:[/bold white] {transcript} [dim]({stt_latency:.0f}ms STT)[/dim]")
        await event_bus.publish("user_speech", {"text": transcript, "latency_ms": round(stt_latency, 1)})

        # Check for direct stop commands
        if transcript.lower().strip() in ("stop", "quiet", "cancel", "nevermind", "shut up"):
            player.interrupt()
            await event_bus.publish("barge_in", {})
            self.state_machine.transition_to(AssistantState.IDLE)
            return

        await self.process_text_turn(transcript)

    async def process_text_turn(self, user_text: str):
        """Processes a textual user prompt through LLM and streams spoken response with parallel pipelining."""
        self.state_machine.transition_to(AssistantState.PROCESSING)
        self.memory.add_user_message(user_text)
        await event_bus.publish("user_speech", {"text": user_text, "latency_ms": 0})

        console.print(f"[bold cyan]{settings.ASSISTANT_NAME}:[/bold cyan] ", end="")
        token_stream = self.llm.stream_response(self.memory)
        sentence_stream = self.sentence_chunker.chunk_stream(token_stream)

        self.state_machine.transition_to(AssistantState.SPEAKING)
        start_time = time.time()
        audio_queue: asyncio.Queue[tuple[str, bytes] | None] = asyncio.Queue(maxsize=5)

        async def synthesizer_producer():
            """Synthesizes incoming sentence clauses in parallel in the background."""
            try:
                async for sentence in sentence_stream:
                    if self.state_machine.current_state == AssistantState.INTERRUPTED:
                        break
                    audio_bytes = await self.tts.synthesize(sentence)
                    if audio_bytes:
                        await audio_queue.put((sentence, audio_bytes))
            except Exception as e:
                logger.error(f"Error in parallel TTS synthesizer: {e}")
            finally:
                await audio_queue.put(None)  # Sentinel to mark completion

        async def playback_consumer():
            """Plays synthesized audio as soon as each clause is ready."""
            first_audio_played = False
            while True:
                item = await audio_queue.get()
                if item is None or self.state_machine.current_state == AssistantState.INTERRUPTED:
                    break

                sentence, audio_bytes = item
                console.print(f"[cyan]{sentence}[/cyan] ", end="")

                if not first_audio_played:
                    ttfa = (time.time() - start_time) * 1000
                    logger.info(f"Time-to-First-Audio (TTFA): {ttfa:.1f}ms")
                    first_audio_played = True
                    await event_bus.publish("assistant_speech", {"text": sentence, "ttfa_ms": round(ttfa, 1)})
                else:
                    await event_bus.publish("assistant_speech", {"text": sentence, "ttfa_ms": 0})

                success = await asyncio.to_thread(player.play_bytes, audio_bytes)
                if not success:
                    break

        try:
            # Run parallel producer (TTS synthesis) and consumer (audio playback) concurrently
            await asyncio.gather(synthesizer_producer(), playback_consumer())
            console.print()
        finally:
            if self.state_machine.current_state != AssistantState.INTERRUPTED:
                # Grant 8-second continuous conversational follow-up window
                self.active_conversation_timeout = time.time() + 8.0

                # Acoustic self-audio suppression: wait 300ms and drain any speaker feedback from buffer
                await asyncio.sleep(0.3)
                while not self.audio_stream.audio_queue.empty():
                    try:
                        self.audio_stream.audio_queue.get_nowait()
                    except Exception:
                        break
                self.vad.reset()

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
