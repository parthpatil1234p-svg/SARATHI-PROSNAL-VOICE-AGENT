"""Central S.A.R.A.T.H.I. Conversational Orchestrator."""

import asyncio
import logging
import sys
import time
from typing import Any

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
from core.filler_manager import filler_manager
from core.latency_tracker import TurnLatencyTracker
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

logger = logging.getLogger("SARATHI.Orchestrator")
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
        self.idle_vad = VoiceActivityDetector(silence_timeout_ms=450, min_speech_duration_sec=0.3)
        self.wake_detector = WakeWordDetector()
        self.sentence_chunker = SentenceChunker(min_clause_words=4 if settings.ENABLE_PIPELINED_TTS_QUEUE else 2)
        self.audio_stream = AudioInputStream(
            sample_rate=settings.SAMPLE_RATE,
            chunk_size=settings.CHUNK_SIZE
        )
        self.is_running = False
        self.active_conversation_timeout: float = 0.0
        self.last_spoken_text: str = ""
        self.last_spoken_time: float = 0.0
        self.state_machine.add_listener(self._notify_state_change)

        # Speculative STT state tracking
        self.speculative_stt_task: asyncio.Task | None = None
        self.speculative_call_count: int = 0
        self.speculative_discard_count: int = 0
        self.speculative_hit_count: int = 0
        self.speculative_triggered_this_turn: bool = False
        self.filler_manager = filler_manager

    def _notify_state_change(self, old_state: AssistantState, new_state: AssistantState):
        try:
            loop = getattr(self, "loop", None)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(event_bus.publish("state_changed", new_state.name), loop)
            else:
                running = asyncio.get_running_loop()
                running.create_task(event_bus.publish("state_changed", new_state.name))
        except RuntimeError:
            pass

    async def start_voice_loop(self):
        """Main asynchronous event loop for real-time voice interaction."""
        self.is_running = True
        self.audio_stream.start()
        console.print(f"[bold cyan]⚡ {settings.ASSISTANT_NAME} initialized and listening...[/bold cyan]")

        # Warm persistent connections in background if enabled
        if settings.ENABLE_PERSISTENT_HTTP_CLIENT:
            try:
                from core.http_client import warmup_groq_connections
                asyncio.create_task(warmup_groq_connections())
            except Exception as e:
                logger.debug(f"Warmup invocation notice: {e}")

        # Warm early conversational fillers in background if enabled
        if settings.ENABLE_EARLY_FILLERS:
            try:
                asyncio.create_task(self.filler_manager.warm_fillers(self.tts))
            except Exception as e:
                logger.debug(f"Filler pre-cache notice: {e}")

        # Spoken confirmation that audio output is operational
        try:
            greeting_text = "All systems online, sir. Sārathi is at your command."
            self.last_spoken_text = greeting_text
            self.last_spoken_time = time.time()
            greeting = await self.tts.synthesize(greeting_text)
            player.play_bytes(greeting)
            # Drain speaker audio from microphone buffer immediately after greeting
            await asyncio.sleep(0.4)
            while not self.audio_stream.audio_queue.empty():
                try:
                    self.audio_stream.audio_queue.get_nowait()
                except Exception:
                    break
            self.vad.reset()
            self.idle_vad.reset()
        except Exception as e:
            logger.warning(f"Initial greeting audio warning: {e}")

        try:
            while self.is_running:
                # 1. State: IDLE - Strictly listening for Wake Word ("Hey Sarathi") or active dialogue window
                if self.state_machine.current_state == AssistantState.IDLE:
                    # Ignore incoming audio during post-speech acoustic cooldown to prevent speaker echo
                    if time.time() - self.last_spoken_time < 0.6:
                        while not self.audio_stream.audio_queue.empty():
                            try:
                                self.audio_stream.audio_queue.get_nowait()
                            except Exception:
                                break
                        await asyncio.sleep(0.02)
                        continue

                    chunk = self.audio_stream.read_chunk(timeout=0.1)
                    if chunk is not None:
                        # Fast-path A: Active dialogue follow-up window
                        in_dialogue_window = time.time() < self.active_conversation_timeout
                        if in_dialogue_window and self.vad.is_speech(chunk):
                            self.state_machine.transition_to(AssistantState.LISTENING)
                            self.vad.speech_started = True
                            self.vad.accumulated_speech_chunks.append(chunk)
                            continue

                        # Fast-path B: OpenWakeWord acoustic model trigger
                        if self.wake_detector.process_chunk(chunk):
                            console.print("[bold green]🔔 OpenWakeWord trigger detected![/bold green]")
                            self.active_conversation_timeout = time.time() + 15.0
                            self.state_machine.transition_to(AssistantState.WAKE_DETECTED)
                            await event_bus.publish("wake_detected", {})
                            await self._play_wake_chime()
                            self.state_machine.transition_to(AssistantState.LISTENING)
                            self.vad.reset()
                            self.idle_vad.reset()
                            continue

                        # Robust Path C: Acoustic Speech Activity in IDLE for "Hey Sarathi" / "Sarathi"
                        has_speech, wake_turn_completed, wake_audio = self.idle_vad.process_frame(chunk)
                        if wake_turn_completed and wake_audio:
                            try:
                                transcript = await self.stt.transcribe(wake_audio)
                                cleaned = transcript.strip().lower()
                                wake_keywords = (
                                    "sarathi", "sarthi", "sarathy", "sarath", "sarti",
                                    "surathi", "सारथी", "hey sarathi", "hey sarthi", "hey jarvis"
                                )
                                if any(kw in cleaned for kw in wake_keywords):
                                    console.print(f"[bold green]🔔 Wake word matched: '{transcript}'[/bold green]")
                                    self.active_conversation_timeout = time.time() + 15.0
                                    self.state_machine.transition_to(AssistantState.WAKE_DETECTED)
                                    await event_bus.publish("wake_detected", {"transcript": transcript})
                                    await self._play_wake_chime()

                                    # Check if user spoke a command directly after the wake phrase
                                    post_cmd = self._extract_post_wake_command(transcript)
                                    if post_cmd:
                                        console.print(f"[cyan]Executing direct command: '{post_cmd}'[/cyan]")
                                        self.state_machine.transition_to(AssistantState.PROCESSING)
                                        await self.process_text_turn(post_cmd)
                                    else:
                                        self.state_machine.transition_to(AssistantState.LISTENING)
                                        self.vad.reset()
                            except Exception as e:
                                logger.error(f"Error evaluating idle wake audio: {e}")
                            finally:
                                self.idle_vad.reset()

                # 2. State: LISTENING - Capturing user speech
                elif self.state_machine.current_state == AssistantState.LISTENING:
                    chunk = self.audio_stream.read_chunk(timeout=0.1)
                    if chunk is not None:
                        has_speech, turn_completed, audio_bytes = self.vad.process_frame(chunk)

                        # Speculative STT: at ~220ms of silence in an active turn, trigger early transcription
                        if settings.ENABLE_SPECULATIVE_STT and self.vad.speech_started:
                            silence_sec = self.vad.silence_elapsed_sec
                            if silence_sec >= 0.220 and not self.speculative_triggered_this_turn:
                                snapshot = self.vad.get_current_audio_snapshot()
                                if snapshot and len(snapshot) > int(settings.SAMPLE_RATE * 0.3 * 2):
                                    self.speculative_triggered_this_turn = True
                                    self.speculative_call_count += 1
                                    logger.info(
                                        f"🚀 [Speculative STT] Initiating early transcription at {silence_sec*1000:.0f}ms silence "
                                        f"(Total Calls: {self.speculative_call_count}, Hits: {self.speculative_hit_count})"
                                    )
                                    self.speculative_stt_task = asyncio.create_task(
                                        self.stt.transcribe(snapshot)
                                    )

                        # If speech resumes before 450ms cut, discard speculative task
                        if has_speech and self.speculative_stt_task is not None:
                            if not self.speculative_stt_task.done():
                                self.speculative_stt_task.cancel()
                            self.speculative_stt_task = None
                            self.speculative_discard_count += 1
                            logger.info(
                                f"🗑️ [Speculative STT] Speech resumed before cutoff. Discarded speculative call "
                                f"(Total Discards: {self.speculative_discard_count})"
                            )

                        if turn_completed and audio_bytes:
                            console.print("[dim]🎤 Speech turn completed. Transcribing...[/dim]")
                            last_voice_t = self.vad.last_voice_timestamp
                            vad_fire_t = time.time()
                            spec_task = self.speculative_stt_task
                            self.speculative_stt_task = None
                            self.speculative_triggered_this_turn = False

                            self.state_machine.transition_to(AssistantState.PROCESSING)
                            await self._handle_speech_turn(
                                audio_bytes,
                                last_voice_t=last_voice_t,
                                vad_fire_t=vad_fire_t,
                                speculative_task=spec_task
                            )

                # 3. State: SPEAKING - Drain microphone buffer so speaker output is not captured as user speech
                elif self.state_machine.current_state == AssistantState.SPEAKING:
                    while not self.audio_stream.audio_queue.empty():
                        try:
                            self.audio_stream.audio_queue.get_nowait()
                        except Exception:
                            break

                await asyncio.sleep(0.005)

        except asyncio.CancelledError:
            logger.info("Voice loop cancelled.")
        finally:
            self.stop()

    async def _handle_speech_turn(
        self,
        audio_bytes: bytes,
        last_voice_t: float | None = None,
        vad_fire_t: float | None = None,
        speculative_task: asyncio.Task | None = None
    ):
        """Transcribes speech and initiates LLM response pipeline."""
        tracker = TurnLatencyTracker(last_voice_timestamp=last_voice_t)
        tracker.mark_vad_fire(vad_fire_t)

        audio_started_event = asyncio.Event()
        filler_task = None
        if settings.ENABLE_EARLY_FILLERS:
            filler_task = asyncio.create_task(
                self.filler_manager.watch_and_play_filler(
                    vad_fire_t or time.time(),
                    audio_started_event,
                    threshold_sec=0.700
                )
            )

        try:
            start_time = time.time()
            transcript = ""
            if speculative_task is not None:
                try:
                    transcript = await speculative_task
                    self.speculative_hit_count += 1
                    logger.info(
                        f"🎯 [Speculative STT Hit] Used early speculative transcription! "
                        f"(Total Hits: {self.speculative_hit_count})"
                    )
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"Speculative STT execution notice ({e}), falling back to fresh STT.")

            if not transcript.strip():
                transcript = await self.stt.transcribe(audio_bytes)

            stt_latency = (time.time() - start_time) * 1000
            tracker.mark_stt_done(transcript=transcript)

            if not transcript.strip():
                console.print("[dim]No audible speech transcribed.[/dim]")
                self.state_machine.transition_to(AssistantState.IDLE)
                return

            cleaned = transcript.strip().lower().rstrip(".,!?")

            # Blacklist background hiss artifacts and common Whisper hallucinations
            common_hallucinations = {
                "", "you", "thanks for watching", "thank you for watching",
                "subtitles", "subtitles by", "subtitle", ".", "...", "[music]", "[applause]"
            }
            if cleaned in common_hallucinations or len(cleaned) < 2:
                console.print(f"[dim]Filtered out acoustic noise artifact: '{transcript}'[/dim]")
                self.state_machine.transition_to(AssistantState.IDLE)
                return

            # Check against acoustic self-echo
            if self.last_spoken_text and (time.time() - self.last_spoken_time < 6.0):
                recent_lower = self.last_spoken_text.lower()
                clean_words = set(cleaned.split())
                recent_words = set(recent_lower.split())
                overlap = clean_words.intersection(recent_words)
                overlap_ratio = len(overlap) / max(len(clean_words), 1)

                if (cleaned in recent_lower or overlap_ratio >= 0.4) and len(clean_words) >= 2:
                    console.print(f"[dim yellow]🛡️ Acoustic self-echo suppressed ({overlap_ratio:.0%} match): '{transcript}'[/dim yellow]")
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

            # Check for direct shutdown / exit commands
            cleaned_cmd = transcript.lower().strip().rstrip(".,!?")
            if any(term in cleaned_cmd for term in ("shut down", "power off", "shutdown", "exit sarathi", "sarathi exit", "sarathi quit")):
                console.print("[bold red]🛑 Voice shutdown command received.[/bold red]")
                audio_started_event.set()
                await self.speak_direct("Shutting down systems. Goodbye, sir.")
                await asyncio.sleep(0.4)
                self.stop()
                import os
                os._exit(0)
                return

            # Check for rule/intent fast path (bypasses LLM for deterministic queries)
            if settings.ENABLE_RULE_FAST_PATH:
                from core.fast_path import check_fast_path
                fp = check_fast_path(transcript)
                if fp.matched:
                    audio_started_event.set()
                    tracker.mark_llm_first_token()
                    tracker.mark_first_clause_ready(fp.spoken_text)
                    await self.speak_direct(
                        text=fp.spoken_text,
                        tool_name=fp.tool_name,
                        tool_result=fp.tool_result,
                        tracker=tracker
                    )
                    self.state_machine.transition_to(AssistantState.IDLE)
                    return

            await self.process_text_turn(transcript, tracker=tracker, audio_started_event=audio_started_event)
        finally:
            audio_started_event.set()
            if filler_task and not filler_task.done():
                filler_task.cancel()

    @staticmethod
    def _extract_post_wake_command(text: str) -> str | None:
        """Extracts follow-up command if user spoke wake word and command in one breath."""
        cleaned = text.strip().rstrip(".,!?")
        lower = cleaned.lower()
        wake_phrases = [
            "hey sarathi", "hey sarthi", "hey jarvis",
            "sarathi", "sarthi", "sarathy", "sarath", "sarti", "surathi", "सारथी", "jarvis"
        ]
        for wp in wake_phrases:
            if lower.startswith(wp):
                rem = cleaned[len(wp):].strip(" ,:;-")
                return rem if len(rem) >= 2 else None
            elif wp in lower:
                idx = lower.find(wp)
                rem = cleaned[idx + len(wp):].strip(" ,:;-")
                return rem if len(rem) >= 2 else None
        return None

    async def process_text_turn(
        self,
        user_text: str,
        tracker: TurnLatencyTracker | None = None,
        audio_started_event: asyncio.Event | None = None
    ):
        """Processes a textual user prompt through LLM and streams spoken response with parallel pipelining."""
        try:
            if tracker is None:
                tracker = TurnLatencyTracker(last_voice_timestamp=time.time())
                tracker.mark_vad_fire()
                tracker.mark_stt_done(user_text)

            self.state_machine.transition_to(AssistantState.PROCESSING)
            self.memory.add_user_message(user_text)
            await event_bus.publish("user_speech", {"text": user_text, "latency_ms": 0})

            console.print(f"[bold cyan]{settings.ASSISTANT_NAME}:[/bold cyan] ", end="")

            async def tracked_token_stream():
                async for token in self.llm.stream_response(self.memory):
                    if tracker:
                        tracker.mark_llm_first_token()
                    yield token

            async def tracked_sentence_stream():
                async for sentence in self.sentence_chunker.chunk_stream(tracked_token_stream()):
                    if tracker:
                        tracker.mark_first_clause_ready(sentence)
                    yield sentence

            sentence_stream = tracked_sentence_stream()

            self.state_machine.transition_to(AssistantState.SPEAKING)
            start_time = time.time()
            audio_queue: asyncio.Queue[tuple[str, bytes] | None] = asyncio.Queue(maxsize=5)

            async def synthesizer_producer():
                """Synthesizes incoming sentence clauses in parallel in the background."""
                first_synth = True
                try:
                    async for sentence in sentence_stream:
                        if self.state_machine.current_state == AssistantState.INTERRUPTED:
                            break
                        audio_bytes = await self.tts.synthesize(sentence)
                        if first_synth and tracker:
                            tracker.mark_tts_first_audio()
                            first_synth = False
                        if audio_bytes:
                            await audio_queue.put((sentence, audio_bytes))
                except Exception as e:
                    logger.error(f"Error in parallel TTS synthesizer: {e}")
                finally:
                    await audio_queue.put(None)  # Sentinel to mark completion

            spoken_sentences: list[str] = []

            async def playback_consumer():
                """Plays synthesized audio as soon as each clause is ready."""
                first_audio_played = False
                last_clause_end_time: float | None = None
                while True:
                    item = await audio_queue.get()
                    if item is None or self.state_machine.current_state == AssistantState.INTERRUPTED:
                        break

                    sentence, audio_bytes = item

                    # Inter-clause gap logging (>150ms flagged)
                    now = time.perf_counter()
                    if last_clause_end_time is not None:
                        gap_ms = (now - last_clause_end_time) * 1000
                        if gap_ms > 150.0:
                            logger.warning(
                                f"⚠️ [Clause Gap Exceeded] Inter-clause gap was {gap_ms:.1f}ms (>150ms) before clause: '{sentence[:30]}...'"
                            )
                        else:
                            logger.debug(f"Inter-clause playback gap: {gap_ms:.1f}ms")

                    spoken_sentences.append(sentence)
                    console.print(f"[cyan]{sentence}[/cyan] ", end="")

                    if not first_audio_played:
                        if audio_started_event:
                            audio_started_event.set()
                        if tracker:
                            tracker.mark_playback_start()
                            if settings.ENABLE_LATENCY_METRICS:
                                tracker.print_table()
                                await event_bus.publish("turn_latency", tracker.get_metrics())
                        ttfa = (time.time() - start_time) * 1000
                        logger.info(f"Time-to-First-Audio (TTFA): {ttfa:.1f}ms")
                        first_audio_played = True
                        await event_bus.publish("assistant_speech", {"text": sentence, "ttfa_ms": round(ttfa, 1)})
                    else:
                        await event_bus.publish("assistant_speech", {"text": sentence, "ttfa_ms": 0})

                    success = await asyncio.to_thread(player.play_bytes, audio_bytes)
                    last_clause_end_time = time.perf_counter()
                    if not success:
                        break

            try:
                # Run parallel producer (TTS synthesis) and consumer (audio playback) concurrently
                await asyncio.gather(synthesizer_producer(), playback_consumer())
                console.print()
            finally:
                if self.state_machine.current_state != AssistantState.INTERRUPTED:
                    full_text = " ".join(spoken_sentences) if spoken_sentences else ""
                    self.last_spoken_text = full_text
                    self.last_spoken_time = time.time()
                    # Grant 8-second continuous conversational follow-up window
                    self.active_conversation_timeout = time.time() + 8.0

                    # Acoustic self-audio suppression: wait 400ms and drain any speaker feedback from buffer
                    await asyncio.sleep(0.4)
                    while not self.audio_stream.audio_queue.empty():
                        try:
                            self.audio_stream.audio_queue.get_nowait()
                        except Exception:
                            break
                    self.vad.reset()
                    self.idle_vad.reset()

                    self.state_machine.transition_to(AssistantState.IDLE)
        except Exception as e:
            logger.error(f"Error processing text turn: {e}", exc_info=True)
            self.state_machine.transition_to(AssistantState.IDLE)
            try:
                await self.speak_direct(f"Apologies, sir. An error occurred: {e}")
            except Exception:
                pass

    async def speak_direct(
        self,
        text: str,
        tool_name: str | None = None,
        tool_result: Any = None,
        tracker: TurnLatencyTracker | None = None,
        audio_started_event: asyncio.Event | None = None
    ):
        """
        Direct vocalization for quick local actions and notifications.
        Bypasses cloud LLM inference completely (<150ms TTFA) and ensures clean transcript reporting.
        """
        start = time.time()
        self.state_machine.transition_to(AssistantState.PROCESSING)

        if tool_name and tool_result is not None:
            await event_bus.publish("tool_executed", {
                "name": tool_name,
                "args": {},
                "result": tool_result,
                "latency_ms": 15
            })

        self.state_machine.transition_to(AssistantState.SPEAKING)
        audio_bytes = await self.tts.synthesize(text)
        if tracker:
            tracker.mark_tts_first_audio()

        if audio_started_event:
            audio_started_event.set()

        ttfa = round((time.time() - start) * 1000, 1)
        console.print(f"[bold cyan]{settings.ASSISTANT_NAME}:[/bold cyan] [cyan]{text}[/cyan] [dim]({ttfa:.0f}ms)[/dim]")
        await event_bus.publish("assistant_speech", {"text": text, "ttfa_ms": ttfa})

        if audio_bytes:
            if tracker:
                tracker.mark_playback_start()
                if settings.ENABLE_LATENCY_METRICS:
                    tracker.print_table()
                    await event_bus.publish("turn_latency", tracker.get_metrics())
            await asyncio.to_thread(player.play_bytes, audio_bytes)

        self.last_spoken_text = text
        self.last_spoken_time = time.time()
        self.active_conversation_timeout = time.time() + 6.0

        # Allow 400ms acoustic drain to prevent microphone echo
        await asyncio.sleep(0.4)
        while not self.audio_stream.audio_queue.empty():
            try:
                self.audio_stream.audio_queue.get_nowait()
            except Exception:
                break
        self.vad.reset()
        self.idle_vad.reset()
        self.state_machine.transition_to(AssistantState.IDLE)

    async def _play_wake_chime(self):
        """Synthesizes or plays an acoustic activation cue."""
        try:
            cue = "Yes, sir?"
            self.last_spoken_text = cue
            self.last_spoken_time = time.time()
            audio = await self.tts.synthesize(cue)
            player.play_bytes(audio)
            await asyncio.sleep(0.3)
            while not self.audio_stream.audio_queue.empty():
                try:
                    self.audio_stream.audio_queue.get_nowait()
                except Exception:
                    break
            self.vad.reset()
            self.idle_vad.reset()
        except Exception as e:
            logger.error(f"Error playing wake chime: {e}")

    def stop(self):
        """Stops the orchestrator and cleans up resources."""
        self.is_running = False
        player.interrupt()
        self.audio_stream.stop()
        logger.info("Assistant orchestrator terminated.")
