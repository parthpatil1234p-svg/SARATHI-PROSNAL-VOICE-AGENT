# SARATHI-PERSONAL-VOICE-AGENT

Autonomous desktop AI voice assistant built for Windows 11 with a tactical HUD, ultra-low latency audio pipeline, Groq LLM inference, Groq Whisper STT, native SAPI5 / ElevenLabs TTS, and real-time mobile push notifications.

---

## ⚡ Key Capabilities

- **Ultra-Fast Voice Pipeline**: Continuous hands-free listening with real-time Silero VAD, streaming Whisper transcription, and pipelined clause synthesis (~600–900ms response).
- **Cognitive Brain**: Powered by Groq LLM inference (`openai/gpt-oss-20b` and `llama-3.3-70b-versatile`) with automated tool calling and memory.
- **Tactical Sci-Fi HUD**: High-tech desktop interface featuring real-time audio visualizers, CPU/RAM telemetry, quick trigger buttons, and a dedicated **Conversation Log** tracking all user inputs, assistant outputs, tool executions, and latency metrics.
- **Instant Barge-In**: Sub-10ms vocal interruption allowing the user to halt spoken responses naturally.
- **Zero-Deadlock Local TTS**: Native Windows COM SAPI voice fallback guaranteeing reliable speech output without freezing.
- **Instant Mobile Push Notifications**: Zero-auth push notification integration via the open `ntfy` protocol directly to your phone.
- **Standalone Portable Executable**: Self-contained background launcher compiled via PyInstaller (`Sarathi.exe`).

---

## 🛠️ Tech Stack

- **Runtime**: Python 3.13 (Windows 11 x64)
- **Frontend / GUI**: PyWebView (Microsoft Edge WebView2), Tailwind CSS, Lucide Icons
- **STT**: Groq Whisper Large v3 Turbo (with local `faster-whisper` CPU fallback)
- **LLM**: Groq Cloud API (`openai/gpt-oss-20b` / `llama-3.3-70b`) & Google Gemini Flash
- **TTS**: Windows SAPI COM (offline ~50ms) & ElevenLabs Neural Voice
- **VAD**: Silero VAD (ONNX Runtime) & Acoustic Energy Analyzer

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/parthpatil1234p-svg/SARATHI-PROSNAL-VOICE-AGENT.git
cd SARATHI-PROSNAL-VOICE-AGENT
```

### 2. Set Up Virtual Environment & Dependencies
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and insert your API keys:
```powershell
cp .env.example .env
```
Ensure your `GROQ_API_KEY` is set:
```ini
GROQ_API_KEY="gsk_your-groq-key-here"
DEFAULT_LLM_PROVIDER="groq"
STT_PROVIDER="whisper"
CONTINUOUS_VOICE_MODE="true"
ENABLE_RULE_FAST_PATH="false"
```

### 4. Run the Application
```powershell
.venv\Scripts\python main.py
```

### 5. Build Standalone Executable
```powershell
.venv\Scripts\pyinstaller Sarathi.spec --noconfirm
```
The compiled application will be generated in `dist/Sarathi/Sarathi.exe`.

---

## 📱 Mobile Notifications Setup

To receive real-time alerts on your mobile phone:
1. Open [https://ntfy.sh/sarathi_parth_alerts](https://ntfy.sh/sarathi_parth_alerts) on your phone browser, or install the free **ntfy** app (Android/iOS) and subscribe to `sarathi_parth_alerts`.
2. Any notification triggered by Sarathi will alert your device immediately.

---

## 📜 License
MIT License. Built with passion by Parth Patil.
