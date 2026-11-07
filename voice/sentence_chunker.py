"""Punctuation-based streaming sentence chunker for ultra-low latency TTS pipelines."""

import re
from collections.abc import AsyncGenerator

from config.settings import settings


class SentenceChunker:
    """
    Accumulates streaming LLM tokens and yields ready-to-speak sentence clauses.
    Features:
    - Minimum clause length threshold (~4 words when ENABLE_PIPELINED_TTS_QUEUE is active)
      on commas to prevent choppy playback pauses.
    - Full sentence punctuation (.?!:\n) splits naturally even for concise phrases.
    - Cleans markdown formatting, emojis, brackets, and symbols before TTS delivery.
    """

    def __init__(self, min_chunk_chars: int = 15, min_clause_words: int = 2):
        self.buffer = ""
        self.min_chunk_chars = min_chunk_chars
        self.min_clause_words = min_clause_words
        self.sentence_pattern = re.compile(r'([.?!:\n]+(?:\s+|$))')
        self.clause_pattern = re.compile(r'([,;]+(?:\s+|$))')

    async def chunk_stream(
        self, token_generator: AsyncGenerator[str, None]
    ) -> AsyncGenerator[str, None]:
        """Reads tokens from an async generator and yields ready-to-speak sentences."""
        is_first_chunk = True

        async for token in token_generator:
            self.buffer += token

            # 1. Check for eager first-clause boundary with minimum word length constraint
            if is_first_chunk and len(self.buffer) >= 8:
                clause_match = self.clause_pattern.search(self.buffer)
                if clause_match:
                    end_idx = clause_match.end()
                    candidate = self.buffer[:end_idx].strip()
                    if len(candidate.split()) >= self.min_clause_words:
                        self.buffer = self.buffer[end_idx:]
                        is_first_chunk = False
                        cleaned = self._clean_for_speech(candidate)
                        if cleaned:
                            yield cleaned
                        continue

            # 2. Check for sentence-terminating punctuation (.?!:\n)
            sent_match = self.sentence_pattern.search(self.buffer)
            if sent_match and len(self.buffer) >= self.min_chunk_chars:
                end_idx = sent_match.end()
                sentence = self.buffer[:end_idx].strip()
                self.buffer = self.buffer[end_idx:]
                is_first_chunk = False
                cleaned = self._clean_for_speech(sentence)
                if cleaned:
                    yield cleaned
                continue

            # 3. Check for mid-sentence comma/semicolon clause splits with word threshold
            if len(self.buffer) >= self.min_chunk_chars:
                clause_match = self.clause_pattern.search(self.buffer)
                if clause_match:
                    end_idx = clause_match.end()
                    candidate = self.buffer[:end_idx].strip()
                    if len(candidate.split()) >= self.min_clause_words:
                        self.buffer = self.buffer[end_idx:]
                        is_first_chunk = False
                        cleaned = self._clean_for_speech(candidate)
                        if cleaned:
                            yield cleaned
                        continue

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
        # Remove markdown link formatting and brackets [link] -> ""
        text = re.sub(r'\[.*?\]', '', text)
        # Remove backticks / code fences
        text = re.sub(r'`+', '', text)
        # Collapse extra whitespaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
