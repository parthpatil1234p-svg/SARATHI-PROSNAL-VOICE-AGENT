"""Persistent HTTP/2 client and Groq connection pooling for S.A.R.A.T.H.I."""

import asyncio
import io
import logging
import soundfile as sf
import numpy as np
import httpx
from groq import AsyncGroq

from config.settings import settings

logger = logging.getLogger("SARATHI.HTTPClient")

_shared_httpx_client: httpx.AsyncClient | None = None
_shared_groq_async_client: AsyncGroq | None = None
_warmup_completed: bool = False
_warmup_lock = asyncio.Lock()


def get_shared_httpx_client() -> httpx.AsyncClient:
    """Returns a shared HTTPX AsyncClient configured for HTTP/2 and persistent keep-alive."""
    global _shared_httpx_client
    if _shared_httpx_client is None or _shared_httpx_client.is_closed:
        try:
            _shared_httpx_client = httpx.AsyncClient(
                http2=True,
                timeout=settings.GROQ_TIMEOUT_SEC,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=60.0
                )
            )
            logger.info("Initialized shared HTTP/2 async client with connection pooling.")
        except Exception as e:
            logger.warning(f"HTTP/2 initialization failed ({e}); falling back to HTTP/1.1 pool.")
            _shared_httpx_client = httpx.AsyncClient(
                http2=False,
                timeout=settings.GROQ_TIMEOUT_SEC,
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=60.0
                )
            )
    return _shared_httpx_client


def get_shared_groq_async_client() -> AsyncGroq | None:
    """
    Returns an AsyncGroq instance.
    If ENABLE_PERSISTENT_HTTP_CLIENT is True, reuses the shared HTTP/2 connection pool.
    """
    global _shared_groq_async_client
    if not settings.GROQ_API_KEY:
        return None

    if not settings.ENABLE_PERSISTENT_HTTP_CLIENT:
        return AsyncGroq(api_key=settings.GROQ_API_KEY)

    if _shared_groq_async_client is None:
        client = get_shared_httpx_client()
        _shared_groq_async_client = AsyncGroq(
            api_key=settings.GROQ_API_KEY,
            http_client=client
        )
        logger.info("Persistent AsyncGroq client initialized with shared HTTP/2 pool.")
    return _shared_groq_async_client


def reset_shared_clients() -> None:
    """Resets shared client instances so new API keys or credentials take effect immediately."""
    global _shared_groq_async_client, _warmup_completed
    _shared_groq_async_client = None
    _warmup_completed = False
    logger.info("Shared Groq client singleton reset for updated credentials.")


async def warmup_groq_connections() -> None:
    """
    Sends tiny dummy requests to warm TLS handshakes and HTTP/2 sockets for both LLM and STT endpoints.
    Fails silently without raising exceptions so startup is never blocked.
    """
    global _warmup_completed
    if _warmup_completed or not settings.GROQ_API_KEY:
        return

    async with _warmup_lock:
        if _warmup_completed:
            return

        groq = get_shared_groq_async_client()
        if not groq:
            return

        logger.info("Warming persistent Groq connections for STT and LLM...")

        # 1. Warmup LLM socket (tiny dummy stream)
        async def _warm_llm():
            try:
                stream = await groq.chat.completions.create(
                    model=settings.DEFAULT_LLM_MODEL,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                    stream=True
                )
                async for _ in stream:
                    pass
                logger.info("Groq LLM socket warmed.")
            except Exception as e:
                logger.debug(f"LLM socket warmup notice: {e}")

        # 2. Warmup STT socket (tiny 0.2s silence FLAC)
        async def _warm_stt():
            try:
                bio = io.BytesIO()
                silence = np.zeros(3200, dtype=np.int16)
                sf.write(bio, silence, 16000, format="FLAC", subtype="PCM_16")
                bio.seek(0)
                bio.name = "warmup.flac"
                await groq.audio.transcriptions.create(
                    file=bio,
                    model="whisper-large-v3-turbo",
                    response_format="text"
                )
                logger.info("Groq STT socket warmed.")
            except Exception as e:
                logger.debug(f"STT socket warmup notice: {e}")

        await asyncio.gather(_warm_llm(), _warm_stt(), return_exceptions=True)
        _warmup_completed = True
        logger.info("Groq persistent connection warmup complete.")


async def close_shared_http_client() -> None:
    """Gracefully closes the shared HTTP client connection pool on shutdown."""
    global _shared_httpx_client, _shared_groq_async_client, _warmup_completed
    if _shared_httpx_client and not _shared_httpx_client.is_closed:
        try:
            await _shared_httpx_client.aclose()
            logger.info("Shared HTTP/2 client closed cleanly.")
        except Exception:
            pass
    _shared_httpx_client = None
    _shared_groq_async_client = None
    _warmup_completed = False
