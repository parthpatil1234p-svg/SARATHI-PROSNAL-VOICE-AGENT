"""J.A.R.V.I.S. Desktop AI Voice Assistant - Windows 11 Entry Point."""

import argparse
import asyncio
import logging
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel

from config.settings import settings
from core.orchestrator import AssistantOrchestrator
from tools.registry import get_all_tool_schemas
from voice.audio_stream import AudioInputStream

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
# Silence chatty external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

console = Console(force_terminal=True)


def display_banner():
    """Prints the SARATHI futuristic console header."""
    header = (
        "[bold cyan]"
        "  === S.A.R.A.T.H.I. ===\n"
        "  Autonomous Desktop AI Voice Assistant (Windows 11)\n"
        "[/bold cyan]\n"
        f"[bold white]Your Loyal Navigator & Desktop Companion[/bold white]\n"
        f"[dim]Model: {settings.DEFAULT_LLM_MODEL} | TTS: {settings.TTS_PROVIDER} | Persona: {settings.ASSISTANT_NAME}[/dim]"
    )
    console.print(Panel(header, border_style="cyan", expand=False))


async def run_interactive_cli(orchestrator: AssistantOrchestrator):
    """Interactive text prompt mode with real-time TTS audio generation and tool calling."""
    console.print("[bold green]Mode: Interactive CLI (Voice Output Enabled)[/bold green]")
    console.print("[dim]Type your command (e.g., 'What is my CPU usage?', 'Set volume to 50%', 'quit'):[/dim]\n")

    while True:
        try:
            user_input = await asyncio.to_thread(input, "\nSir > ")
            cleaned = user_input.strip()

            if not cleaned:
                continue

            if cleaned.lower() in ("exit", "quit", "q"):
                console.print("[cyan]SARATHI: Shutting down systems. Goodbye, sir.[/cyan]")
                break

            await orchestrator.process_text_turn(cleaned)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[cyan]SARATHI: Standing down. Good day, sir.[/cyan]")
            break


async def main():
    parser = argparse.ArgumentParser(description="S.A.R.A.T.H.I. AI Voice Assistant")
    parser.add_argument("--gui", "--hud", action="store_true", help="Launch the Mark VII Tactical Desktop HUD")
    parser.add_argument("--tk", action="store_true", help="Launch the CustomTkinter GUI instead of the Web HUD")
    parser.add_argument("--cli", action="store_true", help="Run in interactive CLI mode (Type prompt, hear voice)")
    parser.add_argument("--voice", action="store_true", help="Run headless in continuous background voice mode")
    parser.add_argument("--devices", action="store_true", help="List all audio input and output devices")
    parser.add_argument("--tools", action="store_true", help="List all registered OS and diagnostic tools")
    args = parser.parse_args()

    # If --tk passed, launch CustomTkinter app
    if args.tk:
        from gui.app import run_gui
        run_gui()
        return

    # If --gui/--hud or no arguments passed, launch the Mark VII Tactical Desktop HUD
    if args.gui or (not args.cli and not args.voice and not args.devices and not args.tools):
        try:
            from gui.hud import run_tactical_hud
            run_tactical_hud()
            return
        except Exception as e:
            console.print(f"[yellow]Tactical HUD encountered: {e}. Falling back to standard Tkinter GUI.[/yellow]")
            from gui.app import run_gui
            run_gui()
            return

    display_banner()

    if args.devices:
        devices = AudioInputStream.list_audio_devices()
        console.print("\n[bold cyan]Detected Audio Devices:[/bold cyan]")
        for dev in devices:
            io_info = []
            if dev["max_inputs"] > 0:
                io_info.append(f"IN: {dev['max_inputs']}ch")
            if dev["max_outputs"] > 0:
                io_info.append(f"OUT: {dev['max_outputs']}ch")
            console.print(f"  [{dev['index']}] {dev['name']} ({', '.join(io_info)})")
        return

    if args.tools:
        tools = get_all_tool_schemas()
        console.print(f"\n[bold cyan]Registered Tools ({len(tools)}):[/bold cyan]")
        for t in tools:
            fn = t["function"]
            console.print(f"  • [bold green]{fn['name']}[/bold green]: {fn['description']}")
        return

    orchestrator = AssistantOrchestrator()

    if args.cli:
        await run_interactive_cli(orchestrator)
    else:
        # Default to voice loop, fallback to CLI if mic unavailable
        try:
            await orchestrator.start_voice_loop()
        except Exception as e:
            console.print(f"[yellow]Voice stream initialization encountered: {e}. Falling back to CLI mode.[/yellow]")
            await run_interactive_cli(orchestrator)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
