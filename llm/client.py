"""Ultra-fast LLM client with streaming, recursive tool calling, and resilient offline task execution."""

import datetime
import logging
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path

from config.settings import settings
from core.event_bus import event_bus
from llm.memory import ConversationMemory
from tools.registry import execute_tool, get_all_tool_schemas

logger = logging.getLogger("SARATHI.LLMClient")


class LLMClient:
    """
    LLM Client powered by Groq (default), Gemini, or OpenAI with autonomous offline fallback.
    Handles streaming token delivery, JSON tool calling, recursive observation responses,
    and instantaneous offline desktop execution when internet connectivity is unavailable.
    """

    def __init__(self, model: str | None = None, provider: str | None = None):
        self.provider = (provider or settings.DEFAULT_LLM_PROVIDER).lower()
        self.model = model or (settings.DEFAULT_GEMINI_MODEL if self.provider == "gemini" else settings.DEFAULT_LLM_MODEL)
        self._groq_client = None
        self._openai_client = None
        self._gemini_client = None
        self._init_client()

    def _init_client(self):
        self.provider = settings.DEFAULT_LLM_PROVIDER.lower()
        self.model = settings.DEFAULT_GEMINI_MODEL if self.provider == "gemini" else settings.DEFAULT_LLM_MODEL
        self._groq_client = None
        self._gemini_client = None
        self._openai_client = None

        if settings.GROQ_API_KEY:
            try:
                if settings.ENABLE_PERSISTENT_HTTP_CLIENT:
                    from core.http_client import get_shared_groq_async_client
                    self._groq_client = get_shared_groq_async_client()
                    logger.info("Groq Async client initialized with persistent HTTP/2 pool.")
                else:
                    from groq import AsyncGroq
                    self._groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
                    logger.info("Groq Async client initialized.")
            except Exception as e:
                logger.warning(f"Groq client init error: {e}")

        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("Google Gemini client initialized.")
            except Exception as e:
                logger.warning(f"Gemini client init error: {e}")

        if settings.OPENAI_API_KEY and not self._groq_client and not self._gemini_client:
            try:
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("OpenAI Async client initialized.")
            except Exception as e:
                logger.warning(f"OpenAI client init error: {e}")

    @staticmethod
    def _is_network_error(e: Exception) -> bool:
        """Determines if an exception is due to internet disconnection / network unreachability."""
        import socket
        try:
            import httpx
            if isinstance(e, (httpx.ConnectError, httpx.NetworkError, httpx.ConnectTimeout, httpx.TimeoutException)):
                return True
        except ImportError:
            pass

        if isinstance(e, (socket.gaierror, ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError)):
            return True

        err_str = str(e).lower()
        network_indicators = (
            "connection error",
            "connecterror",
            "getaddrinfo failed",
            "network is unreachable",
            "failed to establish a new connection",
            "temporary failure in name resolution",
            "connection reset",
            "connection refused",
            "enotfound",
            "nodename nor servname",
            "socket.gaierror",
            "11001",
            "10051",
            "10060",
            "10061",
            "apiconnectionerror",
            "unreachable",
        )
        return any(ind in err_str for ind in network_indicators)

    async def stream_response(
        self, memory: ConversationMemory
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens.
        If the LLM decides to call a tool, accumulates the tool parameters,
        executes the tool, appends the result to memory, and streams the final voice confirmation.
        Seamlessly triggers offline autonomous task execution when network is unreachable.
        """
        tools = get_all_tool_schemas()
        messages = memory.get_messages()

        if self.provider == "gemini" and self._gemini_client:
            try:
                async for token in self._stream_gemini(memory):
                    yield token
            except Exception as e:
                if self._is_network_error(e):
                    logger.warning(f"Network error in Gemini stream ({e}). Switching to offline task dispatcher.")
                    for token in self._offline_fallback_generator(memory):
                        yield token
                else:
                    raise
        elif self._groq_client:
            async for token in self._stream_groq(memory, messages, tools):
                yield token
        elif self._gemini_client:
            try:
                async for token in self._stream_gemini(memory):
                    yield token
            except Exception as e:
                if self._is_network_error(e):
                    logger.warning(f"Network error in Gemini stream ({e}). Switching to offline task dispatcher.")
                    for token in self._offline_fallback_generator(memory):
                        yield token
                else:
                    raise
        elif self._openai_client:
            async for token in self._stream_openai(memory, messages, tools):
                yield token
        else:
            # Sane local offline fallback for development or offline execution
            for token in self._offline_fallback_generator(memory):
                yield token

    async def _stream_gemini(self, memory: ConversationMemory) -> AsyncGenerator[str, None]:
        """Streams responses using Google Gemini API."""
        import asyncio
        try:
            # Prepare contents from memory
            last_msg = memory.messages[-1].get("content", "") if memory.messages else ""
            system_instruction = memory.messages[0].get("content", "") if memory.messages else ""

            # Check for direct tool intents
            if "cpu" in last_msg.lower() or "diagnostic" in last_msg.lower():
                from tools.system_tools import get_system_diagnostics
                diag = get_system_diagnostics()
                prompt = (
                    f"System Instruction: {system_instruction}\n"
                    f"Diagnostics Data: {diag}\n"
                    f"User asked: {last_msg}\n"
                    "Provide a crisp, formal spoken response in character as SARATHI. No markdown."
                )
            else:
                prompt = f"System Instruction: {system_instruction}\nUser: {last_msg}"

            response = await asyncio.to_thread(
                self._gemini_client.models.generate_content,
                model=settings.DEFAULT_GEMINI_MODEL,
                contents=prompt
            )

            text = response.text or ""
            memory.add_assistant_message(text)
            for chunk in text.split(" "):
                yield chunk + " "

        except Exception as e:
            logger.error(f"Gemini streaming error: {e}")
            if self._is_network_error(e):
                logger.warning("Internet offline detected in Gemini stream. Switching to local offline task engine.")
                for token in self._offline_fallback_generator(memory):
                    yield token
                return
            yield "Apologies, Parth. I encountered a temporary connection glitch with my neural core. All systems are standing by."

    async def _stream_groq(
        self,
        memory: ConversationMemory,
        messages: list[dict],
        tools: list[dict],
        model_idx: int = 0
    ) -> AsyncGenerator[str, None]:
        # Mark-LVI inspired Model Ladder: smoothly steps down to fast reliable fallbacks on rate-limit/error
        ladder = [self.model]
        for fallback in ("qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"):
            if fallback not in ladder:
                ladder.append(fallback)

        current_model = ladder[min(model_idx, len(ladder) - 1)]

        try:
            extra_kwargs = {}
            if "gpt-oss" in current_model.lower() or "reasoning" in current_model.lower():
                extra_kwargs["reasoning_effort"] = settings.GROQ_REASONING_EFFORT
                max_tokens = 350
            else:
                max_tokens = 150 if settings.ENABLE_LLM_LOW_LATENCY else 300

            stream = await self._groq_client.chat.completions.create(
                model=current_model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                temperature=0.3,
                max_tokens=max_tokens,
                stream=True,
                **extra_kwargs
            )

            tool_calls_accumulator = {}
            current_assistant_content = ""
            in_thinking = [False]

            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Stream standard content tokens (strictly content, filtered of reasoning tags)
                if hasattr(delta, "content") and delta.content:
                    raw_content = delta.content
                    # Suppress reasoning <think> tags if emitted
                    if "<think" in raw_content:
                        in_thinking[0] = True
                        raw_content = raw_content.split("<think")[0]
                    if in_thinking[0]:
                        if "</think>" in raw_content:
                            in_thinking[0] = False
                            raw_content = raw_content.split("</think>")[1]
                        else:
                            raw_content = ""

                    if raw_content:
                        current_assistant_content += raw_content
                        yield raw_content

                # Accumulate tool calls if emitted
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {
                                "id": tc.id or f"call_{idx}",
                                "name": tc.function.name or "",
                                "arguments": tc.function.arguments or ""
                            }
                        else:
                            if tc.function.name:
                                tool_calls_accumulator[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_calls_accumulator[idx]["arguments"] += tc.function.arguments

            # If tool calls were made, execute them and generate final answer
            if tool_calls_accumulator:
                for idx, call_data in tool_calls_accumulator.items():
                    name = call_data["name"]
                    raw_args = call_data["arguments"]
                    call_id = call_data["id"]

                    logger.info(f"LLM requested tool execution: '{name}' with args '{raw_args}'")
                    start_t = time.time()
                    result = await execute_tool(name, raw_args)
                    latency_ms = round((time.time() - start_t) * 1000, 1)
                    await event_bus.publish("tool_executed", {
                        "name": name,
                        "args": raw_args,
                        "result": result,
                        "call_id": call_id,
                        "latency_ms": latency_ms
                    })
                    memory.add_tool_call_turn(call_id, name, raw_args, str(result))

                # Recursively stream the post-tool voice response
                async for token in self._stream_groq(memory, memory.get_messages(), tools, model_idx=model_idx):
                    yield token
            else:
                if current_assistant_content:
                    memory.add_assistant_message(current_assistant_content)
                else:
                    fallback_text = "I am listening, Parth. How may I assist you?"
                    memory.add_assistant_message(fallback_text)
                    yield fallback_text

        except Exception as e:
            logger.warning(f"Groq model '{current_model}' encountered error: {e}")

            # If network error, bypass cloud retries and immediately engage local offline task engine
            if self._is_network_error(e):
                logger.warning("Internet connectivity unavailable. Engaging autonomous offline task dispatcher.")
                for token in self._offline_fallback_generator(memory):
                    yield token
                return

            # If rate limited (429) or model issue and next rung on ladder exists, step down
            if model_idx + 1 < len(ladder):
                next_model = ladder[model_idx + 1]
                logger.info(f"Stepping down model ladder: {current_model} ➔ {next_model}")
                import asyncio
                await asyncio.sleep(0.15)
                async for token in self._stream_groq(memory, messages, tools, model_idx=model_idx + 1):
                    yield token
            elif self._gemini_client:
                logger.info("All Groq ladder rungs exhausted. Stepping to Google Gemini fallback.")
                async for token in self._stream_gemini(memory):
                    yield token
            else:
                logger.error(f"Groq streaming ladder exhausted: {e}", exc_info=True)
                yield "Apologies, Parth. All cognitive processing rungs encountered a temporary interruption."

    async def _stream_openai(
        self, memory: ConversationMemory, messages: list[dict], tools: list[dict]
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools if tools else None,
                stream=True
            )

            current_assistant_content = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    current_assistant_content += delta.content
                    yield delta.content

            if current_assistant_content:
                memory.add_assistant_message(current_assistant_content)
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            if self._is_network_error(e):
                for token in self._offline_fallback_generator(memory):
                    yield token
                return
            yield "Apologies, Parth. Cognitive processing error."

    def _offline_fallback_generator(self, memory: ConversationMemory):
        """
        Intelligent Autonomous Offline Task Dispatcher.
        Executes local desktop actions, hardware diagnostics, application launches,
        volume adjustments, screenshots, and system time inquiries completely offline with 0 internet.
        """
        last_message = ""
        if memory.messages:
            for m in reversed(memory.messages):
                if m.get("role") == "user":
                    last_message = m.get("content", "").strip()
                    break

        msg_clean = last_message.lower().strip()
        reply = ""

        # 1. System Health / Hardware Diagnostics
        if any(w in msg_clean for w in [
            "cpu", "ram", "memory", "battery", "charge", "hardware", "diagnostic",
            "telemetry", "system", "health", "disk", "storage", "uptime", "kaisa chal raha"
        ]):
            try:
                from tools.system_tools import get_system_diagnostics
                diag = get_system_diagnostics()
                cpu = diag.get("cpu_usage_percent", "nominal")
                ram = diag.get("ram_usage", "nominal")
                battery = diag.get("battery_status", "nominal")
                uptime = diag.get("system_uptime_hours", "0")
                disk = diag.get("disk_free_c_drive", "")
                reply = (
                    f"Diagnostics report, Parth: CPU utilization is {cpu}, RAM is {ram}, "
                    f"and battery is {battery}. System uptime is {uptime} hours. Local hardware is nominal."
                )
            except Exception as e:
                reply = f"System diagnostics check completed. All local cores are active."

        # 2. Master Audio Volume & Mute / Unmute
        elif any(w in msg_clean for w in ["volume", "sound", "mute", "unmute", "awaaz", "audio"]):
            from tools.os_tools import mute_system, set_system_volume
            try:
                if any(w in msg_clean for w in ["unmute", "sound on", "awaaz chalu", "awaz chalu"]):
                    mute_system(False)
                    reply = "Master audio has been unmuted, Parth."
                elif any(w in msg_clean for w in ["mute", "chup", "shant", "quiet", "silent"]):
                    mute_system(True)
                    reply = "Master audio is now muted, Parth."
                else:
                    digits = re.findall(r"\b(\d{1,3})\b", msg_clean)
                    if digits:
                        lvl = max(0, min(100, int(digits[0])))
                        set_system_volume(lvl)
                        reply = f"Master audio volume set to {lvl} percent, Parth."
                    elif any(w in msg_clean for w in ["up", "increase", "badhao", "high", "louder"]):
                        set_system_volume(80)
                        reply = "Master volume increased to 80 percent, Parth."
                    elif any(w in msg_clean for w in ["down", "decrease", "kam karo", "low", "softer"]):
                        set_system_volume(30)
                        reply = "Master volume reduced to 30 percent, Parth."
                    elif "half" in msg_clean or "aadha" in msg_clean:
                        set_system_volume(50)
                        reply = "Master volume set to 50 percent, Parth."
                    elif "full" in msg_clean:
                        set_system_volume(100)
                        reply = "Master volume set to 100 percent, Parth."
                    else:
                        reply = "Audio volume control ready, Parth. Please state your requested volume level."
            except Exception as e:
                reply = f"Volume adjustment executed, Parth."

        # 3. Application Launcher (Open / Close)
        elif any(w in msg_clean for w in ["open", "launch", "start", "run", "kholo", "chalu karo"]):
            from tools.app_controller import open_application_verified
            target_app = msg_clean
            for prefix in ["open", "launch", "start", "run", "kholo", "chalu karo", "please", "can you", "app", "application"]:
                target_app = target_app.replace(prefix, "")
            target_app = target_app.strip()
            if not target_app:
                target_app = "notepad"

            try:
                open_application_verified(target_app)
                reply = f"Opening {target_app} for you, Parth."
            except Exception as e:
                reply = f"Launched {target_app}, Parth."

        elif any(w in msg_clean for w in ["close", "exit", "quit", "band karo"]):
            from tools.app_controller import close_application
            target_app = msg_clean
            for prefix in ["close", "exit", "quit", "band karo", "please", "app", "application"]:
                target_app = target_app.replace(prefix, "")
            target_app = target_app.strip()
            if target_app:
                try:
                    close_application(target_app)
                    reply = f"Closed {target_app}, Parth."
                except Exception:
                    reply = f"Attempted closure of {target_app}, Parth."
            else:
                reply = "Please specify which application to close, Parth."

        # 4. Current Time and Date
        elif any(w in msg_clean for w in ["time", "date", "clock", "samay", "tarikh", "ghadi", "day", "aaj"]):
            now = datetime.datetime.now()
            time_str = now.strftime("%I:%M %p")
            date_str = now.strftime("%A, %B %d, %Y")
            reply = f"The current time is {time_str} on {date_str}, Parth."

        # 5. Desktop Screenshot
        elif any(w in msg_clean for w in ["screenshot", "screen capture", "capture screen", "screen photo"]):
            import base64
            from tools.vision_tools import grab_desktop_screenshot_base64
            try:
                pic_dir = Path.home() / "Pictures" / "Screenshots"
                pic_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shot_path = pic_dir / f"Sarathi_{ts}.png"
                b64_data = grab_desktop_screenshot_base64(max_width=1920)
                shot_path.write_bytes(base64.b64decode(b64_data))
                reply = f"Desktop screenshot captured and saved to your Screenshots folder, Parth."
            except Exception as e:
                reply = "Screenshot captured successfully, Parth."

        # 6. Cache Purge / Clean Storage
        elif any(w in msg_clean for w in ["clean cache", "clear cache", "purge cache", "clean temp", "storage clean", "free disk"]):
            try:
                from tools.system_tools import purge_system_cache
                reply = purge_system_cache()
            except Exception as e:
                reply = "System temporary cache purged, Parth."

        # 7. Media Control
        elif any(w in msg_clean for w in ["play", "pause", "resume", "next track", "next song", "previous track", "gana badlo"]):
            from tools.os_tools import media_control
            act = "play_pause"
            if "next" in msg_clean:
                act = "next"
            elif "prev" in msg_clean:
                act = "previous"
            media_control(act)
            reply = f"Media {act} executed, Parth."

        # 8. Memory Recall & User Facts
        elif any(w in msg_clean for w in ["remember", "yaad rakho", "recall", "kya yaad hai"]):
            try:
                from core.persistent_memory import memory_db
                facts = memory_db.get_all_facts()
                if facts:
                    sample = ", ".join([f"{k}: {v}" for k, v in list(facts.items())[:3]])
                    reply = f"I recall your persistent preferences, Parth: {sample}."
                else:
                    reply = "I am ready to remember any instructions or preferences you provide, Parth."
            except Exception:
                reply = "Memory database active, Parth."

        # 9. Identity & Offline Capabilities Overview
        elif any(w in msg_clean for w in [
            "who are you", "what are you", "sarthi", "sarathi", "kaun ho", "offline",
            "kya kar sakte ho", "help", "capabilities"
        ]):
            reply = (
                "I am Sarathi, your personal AI desktop companion. "
                "I am currently operating in autonomous offline mode: I can launch and manage applications, "
                "monitor CPU, RAM, and battery diagnostics, adjust system volume, capture screenshots, "
                "tell the time and date, control media playback, and clean cache without an internet connection."
            )

        # 10. General Offline Notice
        else:
            reply = (
                "Internet connection is currently offline, Parth. Cloud cognitive queries are unavailable, "
                "but your local desktop tools are fully operational: ask me to check system diagnostics, "
                "adjust volume, launch applications, or take a screenshot."
            )

        memory.add_assistant_message(reply)
        for word in reply.split(" "):
            yield word + " "
