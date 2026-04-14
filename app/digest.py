"""
app/digest.py — Claude-powered daily parliament digest

Reads the day's statements from the DB and calls Claude to produce:
  - A readable news-style digest of the day's proceedings
  - A list of hot topics / key debates
  - Identified continuing threads (topics that have been debated over multiple days)

Usage:
    from app.digest import generate_digest_for_date, get_or_generate_digest

    # Get digest (from cache or generate fresh)
    digest = get_or_generate_digest("2025-03-19")

    # Force regenerate
    digest = generate_digest_for_date("2025-03-19", force=True)

Requires:
    ANTHROPIC_API_KEY environment variable
"""

import os
import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.db import get_connection

logger = logging.getLogger(__name__)

CLAUDE_MODEL       = "claude-sonnet-4-6"
MAX_STATEMENTS_IN  = 150    # cap statements sent to Claude (cost control)
MIN_WORD_COUNT     = 30     # skip very short statements in digest input


def _get_statements_for_date(date_str: str, limit: int = MAX_STATEMENTS_IN) -> list[dict]:
    """Fetch statements for a sitting date, sorted by page number."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT
            s.speaker_raw, s.statement_type, s.statement_text,
            s.word_count, s.page_number, s.topic,
            m.constituency, m.party
        FROM statements s
        JOIN members m ON s.member_id = m.id
        WHERE s.sitting_date = ?
          AND s.word_count >= ?
          AND s.statement_type IN ('speech', 'answer', 'question')
        ORDER BY s.page_number ASC
        LIMIT ?
    """, (date_str, MIN_WORD_COUNT, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _get_recent_topics(date_str: str, lookback_days: int = 21) -> list[str]:
    """Return the most discussed topics in the past N days (for thread detection)."""
    conn = get_connection()
    c    = conn.cursor()
    from_date = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    c.execute("""
        SELECT topic, COUNT(*) as n
        FROM statements
        WHERE topic IS NOT NULL
          AND sitting_date >= ?
          AND sitting_date < ?
        GROUP BY topic
        ORDER BY n DESC
        LIMIT 20
    """, (from_date, date_str))
    rows = c.fetchall()
    conn.close()
    return [r["topic"] for r in rows if r["topic"]]


def _format_statements_for_prompt(statements: list[dict]) -> str:
    """Format statements into a compact but informative prompt block."""
    lines = []
    for s in statements:
        speaker = s["speaker_raw"]
        if s.get("constituency"):
            speaker += f" ({s['constituency']})"
        if s.get("party"):
            speaker += f" [{s['party']}]"
        # Truncate very long statements to keep prompt manageable
        text = s["statement_text"]
        if len(text) > 600:
            text = text[:600] + "…"
        lines.append(f"[{s['statement_type'].upper()}] {speaker}:\n{text}\n")
    return "\n".join(lines)


def generate_digest_for_date(date_str: str, force: bool = False) -> dict | None:
    """
    Generate a news-style digest for a parliament sitting date using Claude.

    Returns dict with:
        sitting_date:  str
        digest_text:   str (markdown)
        hot_topics:    list[str]
        model_used:    str

    Returns None if no statements found for the date or API key not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — digest generation unavailable")
        return None

    # Check cache first
    if not force:
        cached = _get_cached_digest(date_str)
        if cached:
            logger.debug(f"Returning cached digest for {date_str}")
            return cached

    statements = _get_statements_for_date(date_str)
    if not statements:
        logger.info(f"No statements found for {date_str} — no digest generated")
        return None

    recent_topics = _get_recent_topics(date_str)
    statements_block = _format_statements_for_prompt(statements)

    # Format the date nicely
    try:
        display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except ValueError:
        display_date = date_str

    recent_topics_str = (
        "Recent ongoing topics: " + ", ".join(recent_topics[:10])
        if recent_topics else "No recent topic history available."
    )

    prompt = f"""You are a parliamentary correspondent covering the Indian Lok Sabha.
You have access to attributed statements from the parliament sitting on {display_date}.

{recent_topics_str}

Here are the key statements from today's sitting ({len(statements)} statements, capped at {MAX_STATEMENTS_IN}):

---
{statements_block}
---

Please produce a structured news digest in the following JSON format:

{{
  "headline": "One compelling headline for the day's proceedings (max 15 words)",
  "summary": "2-3 sentence overview of the day — what was the dominant mood, major business, key confrontations",
  "sections": [
    {{
      "title": "Section heading (e.g., 'Budget Debate Heats Up')",
      "body": "2-4 sentences covering this topic/debate with speaker attribution",
      "speakers": ["Speaker Name 1", "Speaker Name 2"],
      "is_continuing_thread": true/false
    }}
  ],
  "hot_topics": ["topic1", "topic2", "topic3"],
  "notable_quotes": [
    {{
      "speaker": "Full name as appears in debate",
      "quote": "Exact or near-exact memorable quote (max 30 words)",
      "context": "Brief context (max 10 words)"
    }}
  ],
  "tone": "one of: heated / productive / disrupted / ceremonial / ordinary"
}}

Rules:
- Write like a correspondent for a quality newspaper (The Hindu / Indian Express level)
- Be factual — only report what is in the statements above
- For is_continuing_thread: true if this topic appears in the recent_topics list
- Include 3-6 sections covering the main debates
- Include 2-3 notable quotes
- hot_topics should be 3-6 specific subject strings (e.g. "farmers' protests", "defence budget", "Manipur violence")
- Do NOT editorialize or add opinion — just report and synthesize
- Respond ONLY with valid JSON — no markdown fences, no preamble"""

    try:
        import anthropic
        client   = anthropic.Anthropic(api_key=api_key)
        message  = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_json = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        data = json.loads(raw_json)

        # Build a readable markdown version from the structured data
        digest_text = _render_digest_markdown(data, display_date)
        hot_topics  = data.get("hot_topics", [])

        # Cache in DB
        _save_digest(date_str, digest_text, hot_topics, CLAUDE_MODEL)

        return {
            "sitting_date": date_str,
            "digest_text":  digest_text,
            "hot_topics":   hot_topics,
            "model_used":   CLAUDE_MODEL,
            "structured":   data,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned non-JSON: {e}\nRaw: {raw_json[:300]}")
        return None
    except Exception as e:
        logger.error(f"Digest generation failed: {e}")
        return None


def _render_digest_markdown(data: dict, display_date: str) -> str:
    """Convert structured digest JSON to readable markdown."""
    lines = []

    headline = data.get("headline", "Parliament Sitting")
    lines.append(f"## {headline}")
    lines.append(f"*{display_date}*\n")

    summary = data.get("summary", "")
    if summary:
        lines.append(summary)
        lines.append("")

    tone = data.get("tone", "")
    if tone:
        tone_emoji = {
            "heated": "🔥", "productive": "✅", "disrupted": "⚠️",
            "ceremonial": "🏛️", "ordinary": "📋",
        }.get(tone, "")
        lines.append(f"**Tone:** {tone_emoji} {tone.title()}\n")

    for section in data.get("sections", []):
        title     = section.get("title", "")
        body      = section.get("body", "")
        thread    = section.get("is_continuing_thread", False)
        tag       = " *(continuing thread)*" if thread else ""
        lines.append(f"### {title}{tag}")
        lines.append(body)
        lines.append("")

    quotes = data.get("notable_quotes", [])
    if quotes:
        lines.append("### Notable Quotes")
        for q in quotes:
            speaker = q.get("speaker", "")
            quote   = q.get("quote", "")
            context = q.get("context", "")
            lines.append(f'> "{quote}"')
            lines.append(f'> — **{speaker}** _{context}_')
            lines.append("")

    return "\n".join(lines)


def _get_cached_digest(date_str: str) -> dict | None:
    conn = get_connection()
    c    = conn.cursor()
    c.execute(
        "SELECT digest_text, hot_topics, model_used FROM digests WHERE sitting_date = ?",
        (date_str,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "sitting_date": date_str,
        "digest_text":  row["digest_text"],
        "hot_topics":   json.loads(row["hot_topics"] or "[]"),
        "model_used":   row["model_used"],
    }


def _save_digest(date_str: str, digest_text: str, hot_topics: list, model: str):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO digests (sitting_date, digest_text, hot_topics, model_used)
        VALUES (?, ?, ?, ?)
    """, (date_str, digest_text, json.dumps(hot_topics), model))
    conn.commit()
    conn.close()


def get_or_generate_digest(date_str: str) -> dict | None:
    """Return cached digest or generate a fresh one."""
    cached = _get_cached_digest(date_str)
    if cached:
        return cached
    return generate_digest_for_date(date_str)


def get_latest_sitting_with_data() -> str | None:
    """Return the most recent sitting date that has parsed statements."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        SELECT sitting_date FROM statements
        GROUP BY sitting_date
        ORDER BY sitting_date DESC
        LIMIT 1
    """)
    row = c.fetchone()
    conn.close()
    return row["sitting_date"] if row else None


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Generate parliament digest")
    ap.add_argument("date",  nargs="?", help="Date (YYYY-MM-DD), defaults to latest")
    ap.add_argument("--force", action="store_true", help="Regenerate even if cached")
    args = ap.parse_args()

    date = args.date or get_latest_sitting_with_data()
    if not date:
        print("No sitting dates with data found in DB.")
        sys.exit(1)

    print(f"Generating digest for {date}...\n")
    result = generate_digest_for_date(date, force=args.force)
    if result:
        print(result["digest_text"])
        print(f"\n🏷  Hot topics: {', '.join(result['hot_topics'])}")
    else:
        print("Could not generate digest (no data or no API key).")
