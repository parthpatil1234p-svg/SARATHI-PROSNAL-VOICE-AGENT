"""J.A.R.V.I.S. Modern Desktop GUI Application (Iron Man HUD Theme)."""

import asyncio
import math
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config.settings import settings
from core.orchestrator import AssistantOrchestrator
from core.state_machine import AssistantState
from tools.system_tools import get_system_diagnostics
from voice.tts.voice_cloner import voice_cloner

# Configure CustomTkinter Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Theme Palette (Stark Industries Cyberpunk Cyan)
COLOR_BG = "#0B0E14"
COLOR_SIDEBAR = "#111722"
COLOR_CARD = "#161F30"
COLOR_CYAN = "#00E5FF"
COLOR_CYAN_DIM = "#007B8A"
COLOR_ACCENT = "#00ADB5"
COLOR_RED = "#FF3366"
COLOR_GREEN = "#00FF99"
COLOR_TEXT = "#E0F7FA"


class JarvisDesktopApp(ctk.CTk):
    """
    Production-grade Windows 11 GUI for J.A.R.V.I.S.
    Features:
    - Real-time animated Arc Reactor & Audio Waveform HUD
    - One-click Voice Mode (Background wake-word & VAD listening)
    - Live Conversation Stream & Tool Execution Cards
    - Live System Diagnostics (CPU, RAM, Battery, Disk)
    - Embedded Settings Modal for Groq & Gemini API Keys and Voice Cloning
    """

    def __init__(self):
        super().__init__()

        self.title("SARATHI // Autonomous Desktop AI Assistant")
        self.geometry("1120x760")
        self.minsize(980, 680)
        self.configure(fg_color=COLOR_BG)

        # Core Backend
        self.orchestrator = AssistantOrchestrator()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.voice_thread: threading.Thread | None = None
        self.is_voice_mode_active = False

        # State machine hook
        self.orchestrator.state_machine.add_listener(self._on_state_change)

        # Arc Reactor Animation Variables
        self.anim_angle = 0
        self.wave_pulse = 0

        self._build_ui()
        self._start_telemetry_loop()
        self._animate_arc_reactor()

    def _build_ui(self):
        # Grid layout: 2 columns (Sidebar: 280px, Main: flexible)
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ----------------------------------------------------
        # 1. LEFT SIDEBAR: Telemetry & Status
        # ----------------------------------------------------
        sidebar = ctk.CTkFrame(self, fg_color=COLOR_SIDEBAR, corner_radius=0, width=280)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        sidebar.grid_propagate(False)

        # Logo / Title
        logo_label = ctk.CTkLabel(
            sidebar,
            text="SARATHI",
            font=ctk.CTkFont(family="Consolas", size=26, weight="bold"),
            text_color=COLOR_CYAN
        )
        logo_label.pack(pady=(25, 2))

        sub_label = ctk.CTkLabel(
            sidebar,
            text="MARK VII // DESKTOP CORE",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#64748B"
        )
        sub_label.pack(pady=(0, 15))

        # Status Pill Badge
        self.status_badge = ctk.CTkLabel(
            sidebar,
            text="● SYSTEM STANDBY",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color=COLOR_CYAN,
            fg_color="#082A3A",
            corner_radius=12,
            width=200,
            height=30
        )
        self.status_badge.pack(pady=10)

        # Voice Mode Toggle Button
        self.btn_voice_mode = ctk.CTkButton(
            sidebar,
            text="⚡ START VOICE MODE",
            command=self.toggle_voice_mode,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=COLOR_CYAN_DIM,
            hover_color=COLOR_CYAN,
            text_color="#FFFFFF",
            corner_radius=8,
            height=42
        )
        self.btn_voice_mode.pack(padx=20, pady=(15, 15), fill="x")

        # Telemetry Frame
        telem_frame = ctk.CTkFrame(sidebar, fg_color=COLOR_CARD, corner_radius=10)
        telem_frame.pack(padx=18, pady=10, fill="x")

        ctk.CTkLabel(
            telem_frame,
            text="SYSTEM TELEMETRY",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=COLOR_CYAN
        ).pack(anchor="w", padx=12, pady=(10, 8))

        self.lbl_cpu = ctk.CTkLabel(telem_frame, text="CPU: Loading...", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT)
        self.lbl_cpu.pack(anchor="w", padx=12, pady=2)
        self.prog_cpu = ctk.CTkProgressBar(telem_frame, height=6, progress_color=COLOR_CYAN, fg_color="#1E293B")
        self.prog_cpu.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_ram = ctk.CTkLabel(telem_frame, text="RAM: Loading...", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT)
        self.lbl_ram.pack(anchor="w", padx=12, pady=2)
        self.prog_ram = ctk.CTkProgressBar(telem_frame, height=6, progress_color=COLOR_ACCENT, fg_color="#1E293B")
        self.prog_ram.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_battery = ctk.CTkLabel(telem_frame, text="Battery: --", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT)
        self.lbl_battery.pack(anchor="w", padx=12, pady=2)

        self.lbl_disk = ctk.CTkLabel(telem_frame, text="Disk C: --", font=ctk.CTkFont(size=11), text_color=COLOR_TEXT)
        self.lbl_disk.pack(anchor="w", padx=12, pady=(2, 10))

        # Bottom Sidebar: Settings Button
        btn_settings = ctk.CTkButton(
            sidebar,
            text="⚙ SETTINGS & API KEYS",
            command=self.open_settings_modal,
            font=ctk.CTkFont(size=12),
            fg_color="#1E293B",
            hover_color="#334155",
            corner_radius=8,
            height=34
        )
        btn_settings.pack(side="bottom", padx=20, pady=20, fill="x")

        # ----------------------------------------------------
        # 2. MAIN WORKSPACE: Arc Reactor HUD + Live Transcript
        # ----------------------------------------------------
        main_frame = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=0)
        main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        # Top Header & Arc Reactor Canvas
        top_hud = ctk.CTkFrame(main_frame, fg_color=COLOR_CARD, corner_radius=12, height=180)
        top_hud.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 15))
        top_hud.grid_columnconfigure(0, weight=1)

        # Canvas for Animated Arc Reactor Visualizer
        self.canvas_reactor = tk.Canvas(
            top_hud,
            width=220,
            height=140,
            bg=COLOR_CARD,
            highlightthickness=0
        )
        self.canvas_reactor.pack(pady=10)

        # Conversation History Box
        self.transcript_box = ctk.CTkTextbox(
            main_frame,
            fg_color=COLOR_CARD,
            text_color=COLOR_TEXT,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
            corner_radius=12
        )
        self.transcript_box.grid(row=1, column=0, sticky="nsew", padx=0, pady=(0, 15))
        self.append_log("SYSTEM", "S.A.R.A.T.H.I. Core operational. Ready for voice interaction or command prompt.")

        # Bottom Input Bar (Command Prompt)
        bottom_bar = ctk.CTkFrame(main_frame, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew")
        bottom_bar.grid_columnconfigure(0, weight=1)

        self.entry_cmd = ctk.CTkEntry(
            bottom_bar,
            placeholder_text="Speak or type a command (e.g. 'Check diagnostics', 'Set volume to 50%')...",
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_CARD,
            border_color="#1E293B",
            corner_radius=8,
            height=42
        )
        self.entry_cmd.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.entry_cmd.bind("<Return>", lambda e: self.send_text_command())

        btn_send = ctk.CTkButton(
            bottom_bar,
            text="EXECUTE",
            command=self.send_text_command,
            width=100,
            height=42,
            font=ctk.CTkFont(weight="bold"),
            fg_color=COLOR_CYAN_DIM,
            hover_color=COLOR_CYAN
        )
        btn_send.grid(row=0, column=1)

    # ----------------------------------------------------
    # State & Visualizer Animations
    # ----------------------------------------------------
    def _on_state_change(self, old_state: AssistantState, new_state: AssistantState):
        """Dispatched on state change from core state machine."""
        state_map = {
            AssistantState.IDLE: ("● LISTENING ('Hey Sarathi')", COLOR_CYAN, "#082A3A"),
            AssistantState.WAKE_DETECTED: ("🔔 WAKE DETECTED", COLOR_GREEN, "#063A22"),
            AssistantState.LISTENING: ("🎤 CAPTURING SPEECH", COLOR_GREEN, "#063A22"),
            AssistantState.PROCESSING: ("⚡ PROCESSING...", "#FFB703", "#3D2B00"),
            AssistantState.EXECUTING_TOOL: ("⚙ EXECUTING TOOL", "#00B4D8", "#032830"),
            AssistantState.SPEAKING: ("🔊 J.A.R.V.I.S. SPEAKING", COLOR_CYAN, "#082A3A"),
            AssistantState.INTERRUPTED: ("🛑 USER BARGE-IN", COLOR_RED, "#3D0814"),
        }
        text, text_color, fg_color = state_map.get(
            new_state, (f"● {new_state.name}", COLOR_CYAN, "#082A3A")
        )
        self.after(0, lambda: self.status_badge.configure(text=text, text_color=text_color, fg_color=fg_color))

    def _animate_arc_reactor(self):
        """Draws concentric glowing futuristic rings and animated ticks on canvas."""
        canvas = self.canvas_reactor
        canvas.delete("all")

        cx, cy = 110, 70
        r_outer = 48
        r_inner = 28

        self.anim_angle = (self.anim_angle + 2) % 360
        state = self.orchestrator.state_machine.current_state

        pulse_color = COLOR_CYAN
        if state == AssistantState.SPEAKING:
            r_outer += int(math.sin(time.time() * 8) * 4)
            pulse_color = "#38EF7D"
        elif state == AssistantState.PROCESSING:
            pulse_color = "#FFB703"

        # Outer glowing circle
        canvas.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer, outline=pulse_color, width=2)
        # Inner core
        canvas.create_oval(cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner, outline=COLOR_CYAN_DIM, width=2)

        # Rotating tick marks (HUD feel)
        for i in range(0, 360, 30):
            rad = math.radians(i + self.anim_angle)
            x1 = cx + (r_outer - 6) * math.cos(rad)
            y1 = cy + (r_outer - 6) * math.sin(rad)
            x2 = cx + r_outer * math.cos(rad)
            y2 = cy + r_outer * math.sin(rad)
            canvas.create_line(x1, y1, x2, y2, fill=pulse_color, width=2)

        # Core center glow
        canvas.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, fill=pulse_color, outline="")

        self.after(40, self._animate_arc_reactor)

    # ----------------------------------------------------
    # Voice Mode & Turn Handlers
    # ----------------------------------------------------
    def toggle_voice_mode(self):
        """Starts or stops the continuous background voice loop."""
        if not self.is_voice_mode_active:
            self.is_voice_mode_active = True
            self.btn_voice_mode.configure(text="🛑 STOP VOICE MODE", fg_color=COLOR_RED, hover_color="#D90429")
            self.append_log("VOICE", "Voice Mode Activated. Listening for wake word 'Hey Sarathi'...")

            def run_async():
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
                self.loop.run_until_complete(self.orchestrator.start_voice_loop())

            self.voice_thread = threading.Thread(target=run_async, daemon=True)
            self.voice_thread.start()
        else:
            self.is_voice_mode_active = False
            self.btn_voice_mode.configure(text="⚡ START VOICE MODE", fg_color=COLOR_CYAN_DIM, hover_color=COLOR_CYAN)
            self.orchestrator.stop()
            self.append_log("VOICE", "Voice Mode Deactivated.")

    def send_text_command(self):
        """Processes manual text prompt through orchestrator."""
        cmd = self.entry_cmd.get().strip()
        if not cmd:
            return

        self.entry_cmd.delete(0, "end")
        self.append_log("USER", cmd)

        def run_turn():
            asyncio.run(self._async_text_turn(cmd))

        threading.Thread(target=run_turn, daemon=True).start()

    async def _async_text_turn(self, cmd: str):
        # Intercept output to display in transcript
        class LogCapturer:
            def __init__(self, app):
                self.app = app
                self.full_response = ""

            def append(self, token):
                self.full_response += token

        await self.orchestrator.process_text_turn(cmd)
        # Display the assistant's memory last turn
        if self.orchestrator.memory.messages:
            last_resp = self.orchestrator.memory.messages[-1].get("content", "")
            if last_resp:
                self.after(0, lambda: self.append_log("SARATHI", last_resp))

    def append_log(self, sender: str, message: str):
        """Appends formatted message to the live transcript textbox."""
        timestamp = time.strftime("%H:%M:%S")
        prefix = f"[{timestamp}] {sender}: "
        self.transcript_box.insert("end", prefix, "header")
        self.transcript_box.insert("end", f"{message}\n\n", "body")
        self.transcript_box.see("end")

    # ----------------------------------------------------
    # Telemetry Background Poller
    # ----------------------------------------------------
    def _start_telemetry_loop(self):
        def poll():
            while True:
                try:
                    diag = get_system_diagnostics()
                    cpu_raw = float(diag["cpu_usage_percent"].replace("%", ""))
                    ram_split = diag["ram_usage"].split("(")[-1].replace("%)", "")
                    ram_raw = float(ram_split)

                    self.after(0, lambda: self._update_telem_ui(diag, cpu_raw, ram_raw))
                except Exception:
                    pass
                time.sleep(2.5)

        threading.Thread(target=poll, daemon=True).start()

    def _update_telem_ui(self, diag: dict, cpu: float, ram: float):
        self.lbl_cpu.configure(text=f"CPU: {diag['cpu_usage_percent']} ({diag['cpu_cores']} Cores)")
        self.prog_cpu.set(cpu / 100.0)

        self.lbl_ram.configure(text=f"RAM: {diag['ram_usage']}")
        self.prog_ram.set(ram / 100.0)

        self.lbl_battery.configure(text=f"Battery: {diag['battery_status']}")
        self.lbl_disk.configure(text=f"Disk C: {diag['disk_free_c_drive']}")

    # ----------------------------------------------------
    # Settings & Voice Cloning Modal
    # ----------------------------------------------------
    def open_settings_modal(self):
        """Opens settings dialog for API Keys & Voice Cloning."""
        modal = ctk.CTkToplevel(self)
        modal.title("J.A.R.V.I.S. // System Configuration & Voice Cloning")
        modal.geometry("640x620")
        modal.configure(fg_color=COLOR_SIDEBAR)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(
            modal,
            text="API KEYS & BRAIN PROVIDER",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color=COLOR_CYAN
        ).pack(anchor="w", padx=25, pady=(20, 10))

        # Groq API Key
        ctk.CTkLabel(modal, text="Groq API Key (Ultra-fast LLM & Whisper):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=25)
        entry_groq = ctk.CTkEntry(modal, width=580, show="•", fg_color=COLOR_CARD)
        entry_groq.insert(0, settings.GROQ_API_KEY)
        entry_groq.pack(padx=25, pady=(2, 10))

        # Gemini API Key
        ctk.CTkLabel(modal, text="Gemini API Key (Google GenAI Gemini 2.0 Flash):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=25)
        entry_gemini = ctk.CTkEntry(modal, width=580, show="•", fg_color=COLOR_CARD)
        entry_gemini.insert(0, settings.GEMINI_API_KEY)
        entry_gemini.pack(padx=25, pady=(2, 10))

        # Active Provider Selector
        ctk.CTkLabel(modal, text="Primary LLM Provider:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=25)
        opt_provider = ctk.CTkOptionMenu(
            modal,
            values=["Groq", "Gemini"],
            fg_color=COLOR_CYAN_DIM,
            button_color=COLOR_CYAN
        )
        opt_provider.set("Gemini" if settings.DEFAULT_LLM_PROVIDER == "gemini" else "Groq")
        opt_provider.pack(anchor="w", padx=25, pady=(2, 10))

        # Voice Engine / Latency Mode Selector
        ctk.CTkLabel(modal, text="TTS Voice Engine (Latency vs Quality):", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=25)
        opt_tts = ctk.CTkOptionMenu(
            modal,
            values=["Edge-TTS British (Natural)", "Ultra-Fast Local SAPI (<150ms)", "ElevenLabs Custom Voice"],
            fg_color=COLOR_CYAN_DIM,
            button_color=COLOR_CYAN,
            width=320
        )
        if settings.TTS_PROVIDER in ("sapi", "local", "fast"):
            opt_tts.set("Ultra-Fast Local SAPI (<150ms)")
        elif settings.TTS_PROVIDER == "elevenlabs":
            opt_tts.set("ElevenLabs Custom Voice")
        else:
            opt_tts.set("Edge-TTS British (Natural)")
        opt_tts.pack(anchor="w", padx=25, pady=(2, 10))

        # Audio Output Device Selector & Test
        import sounddevice as sd
        output_devices = ["Default"]
        device_map = {"Default": ""}
        try:
            for idx, dev in enumerate(sd.query_devices()):
                if dev.get("max_output_channels", 0) > 0:
                    label = f"[{idx}] {dev['name'][:30]}"
                    output_devices.append(label)
                    device_map[label] = str(idx)
        except Exception:
            pass

        ctk.CTkLabel(modal, text="Audio Output Speaker / Device:", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=25)
        dev_frame = ctk.CTkFrame(modal, fg_color="transparent")
        dev_frame.pack(fill="x", padx=25, pady=(2, 12))

        opt_device = ctk.CTkOptionMenu(
            dev_frame,
            values=output_devices,
            fg_color="#1E293B",
            button_color="#334155",
            width=320
        )
        current_dev_str = str(settings.AUDIO_OUTPUT_DEVICE_INDEX) if settings.AUDIO_OUTPUT_DEVICE_INDEX else ""
        matched_label = "Default"
        for lbl, d_idx in device_map.items():
            if d_idx == current_dev_str:
                matched_label = lbl
                break
        opt_device.set(matched_label)
        opt_device.pack(side="left")

        def test_audio_output():
            chosen = opt_device.get()
            dev_idx = device_map.get(chosen, "")
            settings.AUDIO_OUTPUT_DEVICE_INDEX = dev_idx or None

            def run_test():
                try:
                    audio = asyncio.run(self.orchestrator.tts.synthesize("Voice output test successful, sir. All audio systems operational."))
                    from voice.player import player
                    player.play_bytes(audio)
                except Exception as exc:
                    err = str(exc)
                    self.after(0, lambda: messagebox.showerror("Audio Test Error", err))

            threading.Thread(target=run_test, daemon=True).start()

        btn_test_audio = ctk.CTkButton(
            dev_frame,
            text="🔊 TEST VOICE",
            command=test_audio_output,
            fg_color=COLOR_CYAN_DIM,
            hover_color=COLOR_CYAN,
            width=130
        )
        btn_test_audio.pack(side="left", padx=10)

        # Divider
        ctk.CTkFrame(modal, height=1, fg_color="#334155").pack(fill="x", padx=25, pady=10)

        # Voice Cloning Studio
        ctk.CTkLabel(
            modal,
            text="CUSTOM VOICE CLONING STUDIO",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            text_color=COLOR_CYAN
        ).pack(anchor="w", padx=25, pady=(10, 5))

        ctk.CTkLabel(
            modal,
            text="Upload an audio sample (.mp3 / .wav) of your voice to clone it for J.A.R.V.I.S.:",
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8"
        ).pack(anchor="w", padx=25, pady=(0, 10))

        selected_audio_path = tk.StringVar(value="")

        def choose_file():
            path = filedialog.askopenfilename(
                title="Select Voice Sample Audio File",
                filetypes=[("Audio Files", "*.mp3 *.wav *.m4a"), ("All Files", "*.*")]
            )
            if path:
                selected_audio_path.set(path)
                lbl_file.configure(text=f"Selected: {path.split('/')[-1]}")

        file_frame = ctk.CTkFrame(modal, fg_color="transparent")
        file_frame.pack(fill="x", padx=25, pady=5)

        btn_browse = ctk.CTkButton(file_frame, text="Browse Audio File...", command=choose_file, width=160)
        btn_browse.pack(side="left")

        lbl_file = ctk.CTkLabel(file_frame, text="No file selected", font=ctk.CTkFont(size=11), text_color="#64748B")
        lbl_file.pack(side="left", padx=10)

        # Clone button
        def perform_clone():
            path = selected_audio_path.get()
            if not path:
                messagebox.showwarning("No File", "Please select an audio sample file first!")
                return

            def run_clone():
                try:
                    res = asyncio.run(voice_cloner.clone_from_audio_file(path))
                    msg = res.get("message", "Voice cloned successfully.")
                    self.after(0, lambda: messagebox.showinfo("Voice Cloned", msg))
                except Exception as exc:
                    err_msg = str(exc)
                    self.after(0, lambda: messagebox.showerror("Clone Failed", err_msg))

            threading.Thread(target=run_clone, daemon=True).start()

        btn_clone = ctk.CTkButton(
            modal,
            text="🧬 CLONE PERSONAL VOICE",
            command=perform_clone,
            fg_color="#00A86B",
            hover_color="#00C853"
        )
        btn_clone.pack(anchor="w", padx=25, pady=10)

        # Save Settings Action
        def save_settings():
            new_groq = entry_groq.get().strip()
            new_gemini = entry_gemini.get().strip()
            new_provider = opt_provider.get().lower()
            chosen_dev = opt_device.get()
            new_dev_idx = device_map.get(chosen_dev, "")

            tts_choice = opt_tts.get()
            if "SAPI" in tts_choice:
                new_tts = "sapi"
            elif "ElevenLabs" in tts_choice:
                new_tts = "elevenlabs"
            else:
                new_tts = "edge_tts"

            env_path = settings.ASSETS_DIR.parent / ".env"
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f'GROQ_API_KEY="{new_groq}"\n')
                f.write(f'GEMINI_API_KEY="{new_gemini}"\n')
                f.write(f'DEFAULT_LLM_PROVIDER="{new_provider}"\n')
                f.write(f'TTS_PROVIDER="{new_tts}"\n')
                f.write(f'ELEVENLABS_VOICE_ID="{settings.ELEVENLABS_VOICE_ID}"\n')
                f.write(f'AUDIO_OUTPUT_DEVICE_INDEX="{new_dev_idx}"\n')

            settings.GROQ_API_KEY = new_groq
            settings.GEMINI_API_KEY = new_gemini
            settings.DEFAULT_LLM_PROVIDER = new_provider
            settings.TTS_PROVIDER = new_tts
            settings.AUDIO_OUTPUT_DEVICE_INDEX = new_dev_idx or None

            from voice.tts import get_tts_engine
            self.orchestrator.tts = get_tts_engine(new_tts)
            self.orchestrator.llm._init_client()

            messagebox.showinfo("Saved", "Configuration updated successfully!")
            modal.destroy()

        btn_save = ctk.CTkButton(
            modal,
            text="SAVE & APPLY CONFIGURATION",
            command=save_settings,
            font=ctk.CTkFont(weight="bold"),
            fg_color=COLOR_CYAN_DIM,
            hover_color=COLOR_CYAN,
            height=40
        )
        btn_save.pack(side="bottom", padx=25, pady=20, fill="x")


def run_gui():
    """Desktop Application entrypoint."""
    app = JarvisDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
