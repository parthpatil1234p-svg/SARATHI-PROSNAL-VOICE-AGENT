"""Per-turn end-to-end latency tracking and stage benchmarking."""

import logging
import time
from typing import Any
from rich.console import Console
from rich.table import Table

logger = logging.getLogger("SARATHI.LatencyTracker")
console = Console()


class TurnLatencyTracker:
    """
    Measures and logs timestamps for each stage of an assistant turn.
    All stages are measured strictly relative to T0: the LAST VOICED AUDIO FRAME.
    """

    def __init__(self, last_voice_timestamp: float | None = None):
        self.t0_last_voice: float = last_voice_timestamp or time.time()
        self.vad_fire: float | None = None
        self.stt_done: float | None = None
        self.llm_first_token: float | None = None
        self.first_clause_ready: float | None = None
        self.tts_first_audio: float | None = None
        self.playback_start: float | None = None

        # Text metadata
        self.user_transcript: str = ""
        self.assistant_first_clause: str = ""
        self.full_response: str = ""

    def mark_vad_fire(self, timestamp: float | None = None):
        self.vad_fire = timestamp or time.time()

    def mark_stt_done(self, transcript: str = "", timestamp: float | None = None):
        self.stt_done = timestamp or time.time()
        self.user_transcript = transcript

    def mark_llm_first_token(self, timestamp: float | None = None):
        if self.llm_first_token is None:
            self.llm_first_token = timestamp or time.time()

    def mark_first_clause_ready(self, clause: str = "", timestamp: float | None = None):
        if self.first_clause_ready is None:
            self.first_clause_ready = timestamp or time.time()
            self.assistant_first_clause = clause

    def mark_tts_first_audio(self, timestamp: float | None = None):
        if self.tts_first_audio is None:
            self.tts_first_audio = timestamp or time.time()

    def mark_playback_start(self, timestamp: float | None = None):
        if self.playback_start is None:
            self.playback_start = timestamp or time.time()

    def get_metrics(self) -> dict[str, Any]:
        """Calculates stage durations and cumulative latency from last_voice (T0)."""
        t0 = self.t0_last_voice
        vad_ms = round((self.vad_fire - t0) * 1000, 1) if self.vad_fire else None
        stt_ms = round((self.stt_done - t0) * 1000, 1) if self.stt_done else None
        llm_ms = round((self.llm_first_token - t0) * 1000, 1) if self.llm_first_token else None
        clause_ms = round((self.first_clause_ready - t0) * 1000, 1) if self.first_clause_ready else None
        tts_ms = round((self.tts_first_audio - t0) * 1000, 1) if self.tts_first_audio else None
        playback_ms = round((self.playback_start - t0) * 1000, 1) if self.playback_start else None

        # Delta stage durations
        vad_delta = vad_ms if vad_ms is not None else 0.0
        stt_delta = round((self.stt_done - self.vad_fire) * 1000, 1) if (self.stt_done and self.vad_fire) else 0.0
        llm_delta = round((self.llm_first_token - self.stt_done) * 1000, 1) if (self.llm_first_token and self.stt_done) else 0.0
        clause_delta = round((self.first_clause_ready - self.llm_first_token) * 1000, 1) if (self.first_clause_ready and self.llm_first_token) else 0.0
        tts_delta = round((self.tts_first_audio - self.first_clause_ready) * 1000, 1) if (self.tts_first_audio and self.first_clause_ready) else 0.0
        playback_delta = round((self.playback_start - self.tts_first_audio) * 1000, 1) if (self.playback_start and self.tts_first_audio) else 0.0

        return {
            "last_voice_t0": 0.0,
            "vad_fire": vad_ms,
            "stt_done": stt_ms,
            "llm_first_token": llm_ms,
            "first_clause_ready": clause_ms,
            "tts_first_audio": tts_ms,
            "playback_start": playback_ms,
            "deltas": {
                "vad_silence": vad_delta,
                "stt": stt_delta,
                "llm_ttft": llm_delta,
                "clause_chunk": clause_delta,
                "tts_synth": tts_delta,
                "playback_init": playback_delta,
            },
            "total_e2e_ms": playback_ms or tts_ms or 0.0,
            "user_transcript": self.user_transcript,
            "first_clause": self.assistant_first_clause
        }

    def print_table(self):
        """Prints a per-turn latency breakdown table using Rich."""
        m = self.get_metrics()
        deltas = m["deltas"]

        table = Table(title="⏱️ SARATHI PER-TURN LATENCY BREAKDOWN (from Last Voiced Frame)", title_style="bold cyan")
        table.add_column("Stage", style="bold white", width=22)
        table.add_column("Stage Latency", justify="right", style="yellow")
        table.add_column("Cumulative (from T0)", justify="right", style="green")
        table.add_column("Details / Notes", style="dim")

        table.add_row("0. last_voice (T0)", "-", "0.0 ms", "User finishes vocal utterance")
        table.add_row("1. vad_fire", f"{deltas['vad_silence']:.1f} ms", f"{m['vad_fire'] or 0.0:.1f} ms", "VAD silence timeout window")
        table.add_row("2. stt_done", f"{deltas['stt']:.1f} ms", f"{m['stt_done'] or 0.0:.1f} ms", f"STT: '{m['user_transcript']}'")
        table.add_row("3. llm_first_token", f"{deltas['llm_ttft']:.1f} ms", f"{m['llm_first_token'] or 0.0:.1f} ms", "Groq LPU first token (TTFT)")
        table.add_row("4. first_clause_ready", f"{deltas['clause_chunk']:.1f} ms", f"{m['first_clause_ready'] or 0.0:.1f} ms", f"Clause: '{m['first_clause']}'")
        table.add_row("5. tts_first_audio", f"{deltas['tts_synth']:.1f} ms", f"{m['tts_first_audio'] or 0.0:.1f} ms", "First audio chunk synthesized")
        table.add_row("6. playback_start", f"{deltas['playback_init']:.1f} ms", f"{m['playback_start'] or 0.0:.1f} ms", "Speaker hardware audio begins")

        console.print(table)
        console.print(f"[bold green]▶ TOTAL E2E LATENCY (End-of-Speech ➔ Audio Out): {m['total_e2e_ms']:.1f} ms[/bold green]\n")
