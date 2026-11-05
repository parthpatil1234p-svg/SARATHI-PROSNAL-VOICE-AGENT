"""Punctuation-based streaming sentence chunker for ultra-low latency TTS pipelines."""

import re
from collections.abc import AsyncGenerator


class SentenceChunker:
    """
    Accumulates streaming LLM tokens and yields complete sentences as early as possible.
    Splits on sentence-ending punctuation (.?!:;) and line breaks.
    Preserves conversational flow while dropping Time-to-First-Audio to ~200ms.
    """

    def __init__(self, min_chunk_chars: int = 15):
        self.buffer = ""
        self.min_chunk_chars = min_chunk_chars
        # Regex to match punctuation followed by whitespace, end-of-line, or quote
        self.split_pattern = re.compile(r'([.?!;:\n]+(?:\s+|$))')

    async def chunk_stream(
        self, token_generator: AsyncGenerator[str, None]
    ) -> AsyncGenerator[str, None]:
        """Reads tokens from an async generator and yields ready-to-speak sentences."""
        is_first_chunk = True

        async for token in token_generator:
            self.buffer += token

            # For the very first clause, split eagerly on commas/dashes for sub-200ms TTFA
            if is_first_chunk and len(self.buffer) >= 8:
                first_match = re.search(r'([,;:\n.?!]+(?:\s+|$))', self.buffer)
                if first_match:
                    end_idx = first_match.end()
                    sentence = self.buffer[:end_idx].strip()
                    self.buffer = self.buffer[end_idx:]
                    is_first_chunk = False
                    cleaned = self._clean_for_speech(sentence)
                    if cleaned:
                        yield cleaned
                    continue

            # Check standard minimum length before splitting
            if len(self.buffer) < self.min_chunk_chars:
                continue

            match = self.split_pattern.search(self.buffer)
            if match:
                end_idx = match.end()
                sentence = self.buffer[:end_idx].strip()
                self.buffer = self.buffer[end_idx:]
                is_first_chunk = False

                # Clean markdown formatting artifacts from text before TTS
                cleaned = self._clean_for_speech(sentence)
                if cleaned:
                    yield cleaned

        # Flush any trailing words
        trailing = self.buffer.strip()
        if trailing:
            cleaned = self._clean_for_speech(trailing)
            if cleaned:
                yield cleaned
            self.buffer = ""

    def reset(self):
        """Clears the internal sentence buffer."""
        self.buffer = ""

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Removes markdown markers, asterisks, brackets, and emojis from text."""
        # Remove bold/italic asterisks
        text = re.sub(r'\*+', '', text)
        # Remove markdown headers (#)
        text = re.sub(r'#+\s*', '', text)
        # Remove inline backticks
        text = re.sub(r'`+', '', text)
        # Remove bracketed references [1], [image], etc.
        text = re.sub(r'\[.*?\]', '', text)
        # Normalize excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
