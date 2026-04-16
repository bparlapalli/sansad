"""
parser/translator.py — Sarvam AI translation module

Translates Hindi and regional-language parliament statements to English
using the Sarvam AI API (https://www.sarvam.ai).

Sarvam AI specialises in Indian languages and supports:
  hi (Hindi), bn (Bengali), te (Telugu), mr (Marathi), ta (Tamil),
  gu (Gujarati), kn (Kannada), ml (Malayalam), pa (Punjabi), or (Odia)

LID (Language Identification) approach:
  - For each statement, detect language via Sarvam's /text-lid endpoint
  - English statements are skipped — no translation needed
  - Non-English statements are translated and original text preserved
  - Both original_text (native script) and statement_text (English) are stored

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

# 2-letter codes accepted by the Sarvam translate API
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

# Maps Sarvam LID codes (e.g. "hi-IN") → 2-letter ISO used by translate API
LID_CODE_TO_ISO = {
    "hi-IN": "hi", "bn-IN": "bn", "te-IN": "te", "mr-IN": "mr",
    "ta-IN": "ta", "gu-IN": "gu", "kn-IN": "kn", "ml-IN": "ml",
    "pa-IN": "pa", "or-IN": "or", "en-IN": "en",
}

SARVAM_API_URL   = "https://api.sarvam.ai/translate"
SARVAM_LID_URL   = "https://api.sarvam.ai/text-lid"
SARVAM_MODEL     = "mayura:v1"
MAX_CHUNK_CHARS  = 900    # Sarvam API limit per request (≈ 1000 chars; leave headroom)
RETRY_DELAY      = 2.0    # seconds between retries on rate-limit


# ── Language Identification (LID) ────────────────────────────────────────────

def detect_language_lid(text: str, api_key: str) -> tuple[str, str]:
    """
    Detect the language of `text` using Sarvam's /text-lid endpoint.

    Returns:
        (language_code, script)
        e.g. ("hi-IN", "Devanagari") or ("en-IN", "Latin")
        Falls back to ("en-IN", "Latin") on any error.

    Args:
        text:    Input text (first 800 chars used; LID limit is 1000)
        api_key: Sarvam API key
    """
    import requests

    snippet = text[:800].strip()
    if not snippet:
        return "en-IN", "Latin"

    try:
        resp = requests.post(
            SARVAM_LID_URL,
            headers={
                "API-Subscription-Key": api_key,
                "Content-Type": "application/json",
            },
            json={"input": snippet},   # Sarvam LID uses "input", not "text"
            timeout=10,
        )
        if resp.status_code == 200:
            data      = resp.json()
            lang_code = data.get("language_code", "en-IN")
            script    = data.get("script", "Latin")
            logger.debug(f"LID: {lang_code} ({script}) — '{snippet[:40]}…'")
            return lang_code, script
        else:
            logger.warning(f"LID API error {resp.status_code}: {resp.text[:120]}")
            return "en-IN", "Latin"

    except Exception as e:
        logger.warning(f"LID request failed: {e}")
        return "en-IN", "Latin"


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


# ── Batch translation (LID approach) ─────────────────────────────────────────

def batch_translate(statements: list[dict]) -> list[dict]:
    """
    Detect language via Sarvam LID, then translate all non-English statements.

    LID approach — for EVERY statement:
      1. Call /text-lid to get the true source language
      2. English (en-IN) → skip translation; clear original_text
      3. Non-English supported → translate to English; store original text
      4. Non-English unsupported → keep as-is; mark language + original_language

    Each statement dict is expected to have:
        statement_text:  str
        language:        str (ISO code from pdf_parser heuristic)

    On return every statement has:
        statement_text:    English (if translated) or original (if not)
        original_text:     Native-script text — set ONLY when translation succeeded
                           (so the pair always has both English + original available)
        original_language: Sarvam LID code e.g. "hi-IN" — set for any non-English stmt
        lid_script:        Detected script e.g. "Devanagari", "Latin"
        translated:        bool — True only if Sarvam translate call succeeded
        language:          "english" if translated, else original ISO code

    Returns the modified list.
    """
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        logger.warning(
            "SARVAM_API_KEY not set — batch_translate is a no-op. "
            "Statements will remain in their original language."
        )
        for stmt in statements:
            stmt["translated"] = False
        return statements

    logger.info(f"LID + translation: processing {len(statements)} statements…")
    en_count   = 0
    trans_ok   = 0
    trans_fail = 0

    for i, stmt in enumerate(statements):
        text = stmt["statement_text"]

        # ── Step 1: Language Identification ──────────────────────────────────
        lid_code, script = detect_language_lid(text, api_key)
        iso_lang = LID_CODE_TO_ISO.get(lid_code, "")  # e.g. "hi", "en", ""

        stmt["lid_language_code"] = lid_code   # e.g. "hi-IN"
        stmt["lid_script"]        = script     # e.g. "Devanagari"

        # ── Step 2: English — no translation needed ───────────────────────────
        if iso_lang == "en" or lid_code == "en-IN":
            stmt["translated"]      = False
            stmt["original_text"]   = None
            stmt["language"]        = "en"
            en_count += 1
            time.sleep(0.05)
            if (i + 1) % 20 == 0:
                logger.info(f"  [{i+1}/{len(statements)}] en={en_count} ok={trans_ok} fail={trans_fail}")
            continue

        # ── Step 3: Non-English — store original, attempt translation ─────────
        stmt["original_language"] = lid_code   # always record detected language

        if iso_lang not in SARVAM_SUPPORTED:
            # Detected language not yet supported for translation (e.g. future codes)
            logger.debug(f"LID code {lid_code} not in translate supported set — keeping original")
            stmt["translated"]    = False
            stmt["original_text"] = None  # no translation available; stmt_text IS the original
            time.sleep(0.05)
            continue

        # ── Step 4: Translate ────────────────────────────────────────────────
        translated_text, ok = translate_to_english(text, source_language=iso_lang)
        if ok:
            stmt["original_text"]   = text            # preserve native script
            stmt["statement_text"]  = translated_text  # replace with English
            stmt["language"]        = "english"
            stmt["translated"]      = True
            trans_ok += 1
        else:
            stmt["original_text"]   = None  # translation failed; stmt_text stays as original
            stmt["translated"]      = False
            trans_fail += 1

        if (i + 1) % 10 == 0:
            logger.info(f"  [{i+1}/{len(statements)}] en={en_count} ok={trans_ok} fail={trans_fail}")

        time.sleep(0.15)  # 2 API calls per stmt — slightly gentler pacing

    logger.info(
        f"  Done — English: {en_count}, Translated: {trans_ok}, "
        f"Failed/unsupported: {trans_fail}"
    )
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
