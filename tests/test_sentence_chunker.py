"""Unit tests for the SentenceChunker."""

import pytest

from voice.sentence_chunker import SentenceChunker


@pytest.mark.asyncio
async def test_sentence_chunker_splitting():
    chunker = SentenceChunker(min_chunk_chars=10)

    async def token_generator():
        tokens = ["Good ", "morning, ", "sir. ", "All ", "systems ", "are ", "operational! ", "How ", "may ", "I ", "assist?"]
        for t in tokens:
            yield t

    chunks = []
    async for chunk in chunker.chunk_stream(token_generator()):
        chunks.append(chunk)

    assert len(chunks) == 4
    assert chunks[0] == "Good morning,"
    assert chunks[1] == "sir."
    assert chunks[2] == "All systems are operational!"
    assert chunks[3] == "How may I assist?"


def test_markdown_cleaning():
    text = "Here is **bold**, *italic*, and `code` with [link]."
    cleaned = SentenceChunker._clean_for_speech(text)
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "`" not in cleaned
    assert "[" not in cleaned
    assert cleaned == "Here is bold, italic, and code with ."
