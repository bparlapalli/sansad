"""
parser/test_sarvam.py — Quick Sarvam AI API connectivity + translation test.

Run this on your LOCAL machine (the Cowork sandbox has no internet):

    python parser/test_sarvam.py

Or with explicit key:
    SARVAM_API_KEY=sk_... python parser/test_sarvam.py

What it tests:
  1. API key is set
  2. Single short Hindi sentence → English translation (POST to api.sarvam.ai)
  3. Multi-sentence Hindi text → English (simulates a real statement)
  4. One of the actual Hindi PDFs we have registered (if statements exist in DB)

Exit code 0 = all tests passed, Sarvam is ready to use.
"""

import os
import sys
import json
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# ── Load .env manually (no python-dotenv needed) ──────────────────────────────
_env_file = _ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

try:
    import requests
except ImportError:
    print("✗  requests not installed. Run: pip install requests")
    sys.exit(1)

SARVAM_KEY  = os.getenv("SARVAM_API_KEY", "")
SARVAM_URL  = "https://api.sarvam.ai/translate"
SARVAM_MODEL = "mayura:v1"

# Test sentences (Hindi → English)
TEST_SENTENCES = [
    # Short sentence
    {
        "label": "Short sentence",
        "text":  "भारत एक महान देश है।",
        "expected_fragment": "India",
    },
    # Realistic parliamentary fragment
    {
        "label": "Parliamentary statement",
        "text":  (
            "सभापति महोदय, मैं इस प्रस्ताव का समर्थन करता हूं। "
            "हमें देश के किसानों की समस्याओं को गंभीरता से लेना होगा। "
            "सरकार को उचित कदम उठाने चाहिए।"
        ),
        "expected_fragment": "President",  # or 'Speaker' / 'Sir'
    },
]


def translate(text: str, source_lang: str = "hi", target_lang: str = "en-IN") -> dict:
    """Call Sarvam translate API. Returns full response JSON."""
    headers = {
        "api-subscription-key": SARVAM_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "input":       text,
        "source_language_code": source_lang,
        "target_language_code": target_lang,
        "speaker_gender": "Male",
        "mode": "formal",
        "model": SARVAM_MODEL,
        "enable_preprocessing": False,
    }
    resp = requests.post(SARVAM_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def run_tests():
    print("\n" + "="*60)
    print("Sarvam AI — Translation API Test")
    print("="*60)

    # ── 1. Key check ──────────────────────────────────────────────
    print("\n[1] API Key")
    if not SARVAM_KEY:
        print("    ✗  SARVAM_API_KEY not set in env or .env file")
        print("    Set it in .env:  SARVAM_API_KEY=sk_...")
        sys.exit(1)
    print(f"    ✓  Key present: {SARVAM_KEY[:12]}…")

    # ── 2. Translation tests ──────────────────────────────────────
    all_ok = True
    for i, tc in enumerate(TEST_SENTENCES, 2):
        print(f"\n[{i}] {tc['label']}")
        print(f"    IN  (hi): {tc['text'][:80]}{'…' if len(tc['text'])>80 else ''}")
        t0 = time.time()
        try:
            result = translate(tc["text"])
            elapsed = time.time() - t0
            translated = result.get("translated_text", "")
            print(f"    OUT (en): {translated[:120]}{'…' if len(translated)>120 else ''}")
            print(f"    Time: {elapsed:.2f}s")
            if translated:
                print(f"    ✓  Translation received")
            else:
                print(f"    ✗  Empty translation returned")
                all_ok = False
        except requests.HTTPError as e:
            print(f"    ✗  HTTP {e.response.status_code}: {e.response.text[:200]}")
            all_ok = False
        except requests.ConnectionError as e:
            print(f"    ✗  Connection error: {e}")
            print("       (Are you running on local machine? Sandbox has no internet.)")
            all_ok = False
        except Exception as e:
            print(f"    ✗  {type(e).__name__}: {e}")
            all_ok = False

    # ── 3. DB check — any Hindi statements to test? ───────────────
    print("\n[4] DB check — Hindi statements sample")
    try:
        from core.db import get_connection
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT id, speaker_raw, statement_text
            FROM statements
            WHERE language = 'hindi' OR original_language IS NOT NULL
            LIMIT 3
        """)
        rows = c.fetchall()
        conn.close()
        if rows:
            print(f"    Found {len(rows)} Hindi statement(s) in DB")
            for row in rows:
                print(f"    → [{row['id']}] {row['speaker_raw']}: {str(row['statement_text'])[:60]}…")
            print()
            print("    Testing translation of first Hindi statement from DB…")
            t0 = time.time()
            try:
                result = translate(str(rows[0]['statement_text'])[:500])
                elapsed = time.time() - t0
                print(f"    ✓  Translated in {elapsed:.2f}s")
                print(f"    OUT: {result.get('translated_text','')[:200]}")
            except Exception as e:
                print(f"    ✗  {e}")
                all_ok = False
        else:
            print("    (No Hindi statements in DB yet — parse a Hindi PDF first)")
    except Exception as e:
        print(f"    (DB check skipped: {e})")

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "="*60)
    if all_ok:
        print("✅  All tests passed — Sarvam AI is ready to use")
        print()
        print("   Run full translation pipeline:")
        print("   python main.py --parse-only --translate")
    else:
        print("❌  Some tests failed — check errors above")
    print("="*60 + "\n")
    return all_ok


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
