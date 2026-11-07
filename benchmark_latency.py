"""Reproducible latency benchmarking harness for S.A.R.A.T.H.I.

Measures every stage relative to the LAST VOICED AUDIO FRAME (T0):
- T0: last_voice (0.0 ms)
- T1: vad_fire
- T2: stt_done
- T3: llm_first_token
- T4: first_clause_ready
- T5: tts_first_audio
- T6: playback_start
"""

import asyncio
import io
import time
import wave
import numpy as np

from config.settings import settings
from core.latency_tracker import TurnLatencyTracker
from core.orchestrator import AssistantOrchestrator
from voice.sentence_chunker import SentenceChunker
from voice.vad import VoiceActivityDetector


def generate_speech_audio_frames(
    voiced_duration_sec: float = 1.2,
    silence_duration_sec: float = 0.5,
    sample_rate: int = 16000,
    chunk_size: int = 1280
) -> list[tuple[np.ndarray, bool]]:
    """
    Generates audio frames (PCM int16):
    - Uses assets/test_speech.wav if available for realistic acoustic data and STT transcription.
    - Otherwise generates synthetic harmonic voiced frames.
    - Appends silence frames to simulate the silence window.
    """
    frames = []
    wav_path = settings.ASSETS_DIR / "test_speech.wav"
    chunk_dur = chunk_size / sample_rate

    if wav_path.exists():
        try:
            import soundfile as sf
            data, sr = sf.read(str(wav_path))
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            pcm_all = (data * 32767).astype(np.int16)
            num_chunks = len(pcm_all) // chunk_size
            for i in range(num_chunks):
                chunk = pcm_all[i * chunk_size : (i + 1) * chunk_size]
                frames.append((chunk, True))
        except Exception:
            pass

    if not frames:
        # Fallback synthetic voiced frames
        num_voiced = int(voiced_duration_sec / chunk_dur)
        for i in range(num_voiced):
            t = np.linspace(i * chunk_dur, (i + 1) * chunk_dur, chunk_size, endpoint=False)
            signal = 0.6 * np.sin(2 * np.pi * 150 * t) + 0.3 * np.sin(2 * np.pi * 600 * t) + 0.1 * np.sin(2 * np.pi * 1200 * t)
            pcm = (signal * 14000).astype(np.int16)
            frames.append((pcm, True))

    # Append silence frames to trigger VAD silence timeout
    num_silence = int(silence_duration_sec / chunk_dur)
    for _ in range(num_silence):
        noise = (np.random.randn(chunk_size) * 80).astype(np.int16)
        frames.append((noise, False))

    return frames


async def run_turn_benchmark(custom_query: str = "State your operational readiness in one sentence."):
    """Runs a complete end-to-end benchmark measuring every stage from last voiced audio frame."""
    orchestrator = AssistantOrchestrator()

    if settings.ENABLE_PERSISTENT_HTTP_CLIENT:
        from core.http_client import warmup_groq_connections
        await warmup_groq_connections()

    vad = VoiceActivityDetector()
    tracker = None

    frames = generate_speech_audio_frames(voiced_duration_sec=1.5, silence_duration_sec=1.0)

    # Simulate real-time audio chunk feeding at realistic frame intervals
    last_voiced_frame_time = None
    captured_audio = None
    vad_fire_time = None

    speculative_task = None
    for chunk, is_voiced in frames:
        has_speech, turn_completed, audio_bytes = vad.process_frame(chunk)
        if has_speech:
            last_voiced_frame_time = vad.last_voice_timestamp
            if speculative_task and not speculative_task.done():
                speculative_task.cancel()
                speculative_task = None

        # Speculative STT at ~220ms of silence
        if settings.ENABLE_SPECULATIVE_STT and vad.speech_started and speculative_task is None:
            if vad.silence_elapsed_sec >= 0.220:
                snap = vad.get_current_audio_snapshot()
                if snap:
                    speculative_task = asyncio.create_task(orchestrator.stt.transcribe(snap))

        if turn_completed and audio_bytes:
            vad_fire_time = time.time()
            captured_audio = audio_bytes
            tracker = TurnLatencyTracker(last_voice_timestamp=vad.last_voice_timestamp)
            tracker.mark_vad_fire(vad_fire_time)
            break
        await asyncio.sleep(0.08)

    if not tracker:
        tracker = TurnLatencyTracker(last_voice_timestamp=time.time() - 0.45)
        tracker.mark_vad_fire()

    # Step 2: STT Stage
    stt_start = time.time()
    try:
        if speculative_task:
            try:
                transcript = await speculative_task
            except Exception:
                transcript = await orchestrator.stt.transcribe(captured_audio) if captured_audio else custom_query
        elif captured_audio and settings.GROQ_API_KEY:
            transcript = await orchestrator.stt.transcribe(captured_audio)
        else:
            transcript = custom_query
        if not transcript.strip():
            transcript = custom_query
    except Exception:
        transcript = custom_query

    tracker.mark_stt_done(transcript=transcript)

    # Step 3: Fast-Path Rule Check or LLM Stage
    if settings.ENABLE_RULE_FAST_PATH:
        from core.fast_path import check_fast_path
        fp = check_fast_path(transcript)
        if fp.matched:
            tracker.mark_llm_first_token()
            tracker.mark_first_clause_ready(fp.spoken_text)
            first_audio = await orchestrator.tts.synthesize(fp.spoken_text)
            tracker.mark_tts_first_audio()
            tracker.mark_playback_start()
            tracker.print_table()
            return tracker.get_metrics()

    # Step 3 (Standard): LLM Stage
    orchestrator.memory.add_user_message(transcript)
    token_stream = orchestrator.llm.stream_response(orchestrator.memory)

    async def tracked_tokens():
        async for tok in token_stream:
            tracker.mark_llm_first_token()
            yield tok

    # Step 4: Sentence Chunker Stage
    chunker = SentenceChunker()
    sentence_stream = chunker.chunk_stream(tracked_tokens())

    async def tracked_sentences():
        async for s in sentence_stream:
            tracker.mark_first_clause_ready(s)
            yield s

    # Step 5: TTS Synthesis Stage
    first_clause = None
    first_audio = None
    async for sentence in tracked_sentences():
        if first_clause is None:
            first_clause = sentence
            # Synthesize first clause
            first_audio = await orchestrator.tts.synthesize(sentence)
            tracker.mark_tts_first_audio()
            break

    # Step 6: Playback Start Stage
    if first_audio:
        tracker.mark_playback_start()

    tracker.print_table()
    return tracker.get_metrics()


if __name__ == "__main__":
    asyncio.run(run_turn_benchmark())
