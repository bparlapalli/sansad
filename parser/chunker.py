"""
parser/chunker.py — Split a statement's text into paragraph-sized search chunks.

A single statements row is one speaker turn, which for a floor speech can run
to several hundred words covering multiple subjects. Full-text search over
the whole row buries the matching phrase somewhere inside a wall of text.
This module groups sentences into ~word-target windows so a search match is
visible in the snippet, without splitting mid-sentence.

Sentence boundary covers English (. ! ?) and Hindi Devanagari (।).
"""

import re

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?।])\s+')

TARGET_WORDS = 60
MAX_WORDS    = 100


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def chunk_statement_text(text: str, target_words: int = TARGET_WORDS,
                         max_words: int = MAX_WORDS) -> list[str]:
    """
    Group a statement's sentences into chunks of roughly `target_words`,
    never exceeding `max_words` unless a single sentence is already longer
    (in which case that sentence becomes its own chunk).
    Returns a list of chunk strings; empty input returns [].
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks = []
    current = []
    current_words = 0

    for sentence in sentences:
        sentence_words = len(sentence.split())

        if current and current_words + sentence_words > max_words:
            chunks.append(" ".join(current))
            current = []
            current_words = 0

        current.append(sentence)
        current_words += sentence_words

        if current_words >= target_words:
            chunks.append(" ".join(current))
            current = []
            current_words = 0

    if current:
        chunks.append(" ".join(current))

    return chunks


def store_chunks(conn, statement_id: int, statement_text: str) -> int:
    """
    Chunk a statement's text and insert into statement_chunks. Returns count.
    Assumes no chunks already exist for this statement_id (plain INSERT, so
    the chunks_ai trigger keeps chunks_fts in sync). Callers re-chunking an
    existing statement must DELETE its rows from statement_chunks first —
    that fires chunks_ad, which keeps the FTS index consistent.
    """
    chunks = chunk_statement_text(statement_text)
    c = conn.cursor()
    for i, chunk_text in enumerate(chunks):
        c.execute("""
            INSERT INTO statement_chunks (statement_id, chunk_index, chunk_text, word_count)
            VALUES (?, ?, ?, ?)
        """, (statement_id, i, chunk_text, len(chunk_text.split())))
    return len(chunks)
