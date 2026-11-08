"""Ultra-fast LLM client with streaming and recursive tool calling."""

import logging
import time
from collections.abc import AsyncGenerator

from config.settings import settings
from core.event_bus import event_bus
from llm.memory import ConversationMemory
from tools.registry import execute_tool, get_all_tool_schemas

logger = logging.getLogger("SARATHI.LLMClient")


class LLMClient:
    """
    LLM Client powered by Groq (default) or OpenAI.
    Handles streaming token delivery, JSON tool calling, and recursive observation responses.
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

    async def stream_response(
        self, memory: ConversationMemory
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens.
        If the LLM decides to call a tool, accumulates the tool parameters,
        executes the tool, appends the result to memory, and streams the final voice confirmation.
        """
        tools = get_all_tool_schemas()
        messages = memory.get_messages()

        if self.provider == "gemini" and self._gemini_client:
            async for token in self._stream_gemini(memory):
                yield token
        elif self._groq_client:
            async for token in self._stream_groq(memory, messages, tools):
                yield token
        elif self._gemini_client:
            async for token in self._stream_gemini(memory):
                yield token
        elif self._openai_client:
            async for token in self._stream_openai(memory, messages, tools):
                yield token
        else:
            # Sane local offline fallback for development without keys
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
                    "Provide a crisp, formal spoken response in character as J.A.R.V.I.S. No markdown."
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
            yield "Apologies, sir. I encountered a communication error with my Gemini cognitive service."

    async def _stream_groq(
        self,
        memory: ConversationMemory,
        messages: list[dict],
        tools: list[dict],
        model_idx: int = 0
    ) -> AsyncGenerator[str, None]:
        # Mark-LVI inspired Model Ladder: smoothly steps down to fast reliable fallbacks on rate-limit/error
        ladder = [self.model]
        for fallback in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
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
                    fallback_text = "I am listening, sir. How may I assist you?"
                    memory.add_assistant_message(fallback_text)
                    yield fallback_text

        except Exception as e:
            err_str = str(e).lower()
            logger.warning(f"Groq model '{current_model}' encountered error: {e}")
            # If rate limited (429) or model issue and next rung on ladder exists, step down
            if model_idx + 1 < len(ladder):
                next_model = ladder[model_idx + 1]
                logger.info(f"Stepping down model ladder: {current_model} ➔ {next_model}")
                async for token in self._stream_groq(memory, messages, tools, model_idx=model_idx + 1):
                    yield token
            elif self._gemini_client:
                logger.info("All Groq ladder rungs exhausted. Stepping to Google Gemini fallback.")
                async for token in self._stream_gemini(memory):
                    yield token
            else:
                logger.error(f"Groq streaming ladder exhausted: {e}", exc_info=True)
                yield "Apologies, sir. All cognitive processing rungs encountered an error."

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
            yield "Apologies, sir. Cognitive processing error."

    def _offline_fallback_generator(self, memory: ConversationMemory):
        """Offline fallback response generator."""
        last_message = memory.messages[-1].get("content", "").lower() if memory.messages else ""
        if "cpu" in last_message or "diagnostic" in last_message or "system" in last_message:
            from tools.system_tools import get_system_diagnostics
            diag = get_system_diagnostics()
            reply = f"Diagnostics indicate CPU usage is at {diag['cpu_usage_percent']}, and battery is {diag['battery_status']}."
        elif "volume" in last_message:
            reply = "Master audio volume adjusted as requested, sir."
        else:
            reply = "I am online and functioning, sir. For full autonomous intelligence, please provide a GROQ_API_KEY in your configuration."

        memory.add_assistant_message(reply)
        for word in reply.split(" "):
            yield word + " "
