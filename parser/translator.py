"""
parser/translator.py — Sarvam AI translation module

Translates Hindi and regional-language parliament statements to English
using the Sarvam AI API (https://www.sarvam.ai).

Sarvam AI specialises in Indian languages and supports:
  hi (Hindi), bn (Bengali), te (Telugu), mr (Marathi), ta (Tamil),
  gu (Gujarati), kn (Kannada), ml (Malayalam), pa (Punjabi), or (Odia)

Setup:
  1. Get an API key from https://www.sarvam.ai
  2. Set environment variable: export SARVAM_API_KEY="your-key-here"
     Or add to a .env file at the project root.

When SARVAM_API_KEY is not set, all functions return the original text
unchanged and log a warning. No crashes — the pipeline degrades gracefully.

Usage:
    from parser.translator import translate_to_english, batch_translate

    english, was_translated = translate_to_english(hindi_text, source_language="hi")
    results = batch_translate(statements_list)
"""

import os
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Supported languages ───────────────────────────────────────────────────────

SARVAM_SUPPORTED = {
    "hi": "Hindi",
    "bn": "Bengali",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "or": "Odia",
}

SARVAM_API_URL   = "https://api.sarvam.ai/translate"
SARVAM_MODEL     = "mayura:v1"
MAX_CHUNK_CHARS  = 900    # Sarvam API limit per request (≈ 1000 chars; leave headroom)
RETRY_DELAY      = 2.0    # seconds between retries on rate-limit


# ── Core translation function ─────────────────────────────────────────────────

def translate_to_english(text: str, source_language: str = "hi") -> tuple[str, bool]:
    """
    Translate `text` from `source_language` to English using Sarvam AI.

    Returns:
        (translated_text, was_translated)
        was_translated = False when:
          - SARVAM_API_KEY is not set (graceful stub mode)
          - source_language is not supported
          - API call fails after retries

    Args:
        text:            Input text in source language
        source_language: ISO 639-1 code ('hi', 'bn', 'ta', etc.)
    """
    if not text or not text.strip():
        return text, False

    if source_language not in SARVAM_SUPPORTED:
        logger.debug(f"Language '{source_language}' not in Sarvam supported set — skipping")
        return text, False

    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        logger.warning(
            "SARVAM_API_KEY not set — translation skipped. "
            "Set it to enable Hindi/regional → English translation."
        )
        return text, False

    # Sarvam has a per-request character limit — split if needed
    if len(text) > MAX_CHUNK_CHARS:
        return _translate_chunked(text, source_language, api_key)

    return _call_sarvam(text, source_language, api_key)


def _call_sarvam(text: str, source_language: str, api_key: str,
                 retries: int = 3) -> tuple[str, bool]:
    """
    Single API call to Sarvam translate endpoint.
    Retries on 429 (rate limit) and 5xx errors.
    """
    import requests

    headers = {
        "API-Subscription-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "input":                text,
        "source_language_code": f"{source_language}-IN",
        "target_language_code": "en-IN",
        "model":                SARVAM_MODEL,
        "speaker_gender":       "Male",
        "mode":                 "formal",
        "enable_preprocessing": True,
    }

    for attempt in range(retries):
        try:
            resp = requests.post(
                SARVAM_API_URL,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if resp.status_code == 200:
                translated = resp.json().get("translated_text", text)
                return translated, True

            elif resp.status_code == 429:
                wait = RETRY_DELAY * (attempt + 1)
                logger.warning(f"Sarvam rate limit — waiting {wait:.0f}s (attempt {attempt+1})")
                time.sleep(wait)
                continue

            else:
                logger.error(f"Sarvam API error {resp.status_code}: {resp.text[:200]}")
                return text, False

        except Exception as e:
            logger.error(f"Sarvam request error: {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)
            else:
                return text, False

    return text, False


def _translate_chunked(text: str, source_language: str, api_key: str) -> tuple[str, bool]:
    """
    Split long text into sentence-chunks, translate each, rejoin.
    Tries to split on sentence boundaries (।  for Hindi, . for others).
    """
    # Split on Hindi danda (।) or period followed by space
    import re
    sentences = re.split(r'([।.!?])\s+', text)

    chunks  = []
    current = ""
    for part in sentences:
        if len(current) + len(part) < MAX_CHUNK_CHARS:
            current += part
        else:
            if current:
                chunks.append(current.strip())
            current = part

    if current:
        chunks.append(current.strip())

    if not chunks:
        return text, False

    translated_parts = []
    any_success      = False

    for chunk in chunks:
        if not chunk:
            continue
        t, ok = _call_sarvam(chunk, source_language, api_key)
        translated_parts.append(t)
        if ok:
            any_success = True
        time.sleep(0.2)  # small pause between chunk requests

    return " ".join(translated_parts), any_success


# ── Batch translation ─────────────────────────────────────────────────────────

def batch_translate(statements: list[dict]) -> list[dict]:
    """
    Translate all non-English statements in a list in place.

    Each statement dict is expected to have:
        statement_text:  str
        language:        str (ISO code)

    On return, statements with language != 'en' will have:
        statement_text:  English translation (or original if no API key)
        original_text:   original text preserved here
        translated:      bool — True if Sarvam was called successfully

    Returns the modified list.
    """
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        logger.warning(
            "SARVAM_API_KEY not set — batch_translate is a no-op. "
            "Hindi statements will remain in Hindi."
        )
        for stmt in statements:
            stmt["translated"] = False
        return statements

    non_english = [s for s in statements if s.get("language", "en") != "en"]
    logger.info(f"Translating {len(non_english)} / {len(statements)} non-English statements")

    for i, stmt in enumerate(non_english):
        lang = stmt.get("language", "hi")
        text = stmt["statement_text"]

        translated, ok = translate_to_english(text, source_language=lang)
        stmt["original_text"]  = text
        stmt["statement_text"] = translated
        stmt["translated"]     = ok

        if (i + 1) % 10 == 0:
            logger.info(f"  Translated {i+1} / {len(non_english)}")

        time.sleep(0.1)  # gentle rate-limiting

    for stmt in statements:
        if "translated" not in stmt:
            stmt["translated"] = False

    return statements


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_text = (
        "माननीय अध्यक्ष महोदय, मैं इस सदन में यह कहना चाहता हूं कि "
        "हमारी सरकार शिक्षा और स्वास्थ्य के क्षेत्र में महत्वपूर्ण कार्य कर रही है।"
    )
    print("Input (Hindi):", test_text)
    result, ok = translate_to_english(test_text, source_language="hi")
    print(f"Output (translated={ok}): {result}")

    if not os.getenv("SARVAM_API_KEY"):
        print("\n⚠  Set SARVAM_API_KEY to enable real translation.")
        print("   export SARVAM_API_KEY='your-key-here'")
