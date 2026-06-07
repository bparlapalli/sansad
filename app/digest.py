"""
app/digest.py — Claude-powered daily parliament digest + politician profiles

Reads statements from the DB and calls Claude to produce:
  - Daily news-style digest for each sitting date
  - Politician profile bios for each MP with parsed statements

Usage:
    from app.digest import generate_digest_for_date, get_or_generate_digest
    from app.digest import generate_politician_profile, get_cached_profile

    digest  = get_or_generate_digest("2025-03-19")
    profile = get_cached_profile(member_id)

CLI:
    python app/digest.py 2025-03-19           # one date
    python app/digest.py --all-dates          # all missing digests
    python app/digest.py --all-profiles       # all missing profiles
    python app/digest.py --member <slug>      # one politician profile

Requires: ANTHROPIC_API_KEY environment variable
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
MAX_STATEMENTS_IN  = 150
MIN_WORD_COUNT     = 30


# ══════════════════════════════════════════════════════════════════════════════
#  Daily Digest
# ══════════════════════════════════════════════════════════════════════════════

def _get_statements_for_date(date_str: str, limit: int = MAX_STATEMENTS_IN) -> list[dict]:
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
    lines = []
    for s in statements:
        speaker = s["speaker_raw"]
        if s.get("constituency"):
            speaker += f" ({s['constituency']})"
        if s.get("party"):
            speaker += f" [{s['party']}]"
        text = s["statement_text"]
        if len(text) > 600:
            text = text[:600] + "…"
        lines.append(f"[{s['statement_type'].upper()}] {speaker}:\n{text}\n")
    return "\n".join(lines)


def generate_digest_for_date(date_str: str, force: bool = False) -> dict | None:
    """
    Generate a news-style digest for a sitting date using Claude.
    Returns dict with sitting_date, digest_text, hot_topics, model_used.
    Returns None if no data or no API key.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — digest generation unavailable")
        return None

    if not force:
        cached = _get_cached_digest(date_str)
        if cached:
            return cached

    statements = _get_statements_for_date(date_str)
    if not statements:
        return None

    recent_topics = _get_recent_topics(date_str)
    statements_block = _format_statements_for_prompt(statements)

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
- hot_topics should be 3-6 specific subject strings
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

        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        data = json.loads(raw_json)
        digest_text = _render_digest_markdown(data, display_date)
        hot_topics  = data.get("hot_topics", [])

        _save_digest(date_str, digest_text, hot_topics, CLAUDE_MODEL)

        return {
            "sitting_date": date_str,
            "digest_text":  digest_text,
            "hot_topics":   hot_topics,
            "model_used":   CLAUDE_MODEL,
            "structured":   data,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned non-JSON for digest {date_str}: {e}")
        return None
    except Exception as e:
        logger.error(f"Digest generation failed for {date_str}: {e}")
        return None


def _render_digest_markdown(data: dict, display_date: str) -> str:
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
        title  = section.get("title", "")
        body   = section.get("body", "")
        thread = section.get("is_continuing_thread", False)
        tag    = " *(continuing thread)*" if thread else ""
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
    cached = _get_cached_digest(date_str)
    if cached:
        return cached
    return generate_digest_for_date(date_str)


def get_latest_sitting_with_data() -> str | None:
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


# ══════════════════════════════════════════════════════════════════════════════
#  Politician Profiles
# ══════════════════════════════════════════════════════════════════════════════

def get_cached_profile(member_id: int) -> dict | None:
    """Return cached politician profile or None."""
    conn = get_connection()
    c    = conn.cursor()
    c.execute(
        "SELECT * FROM politician_profiles WHERE member_id = ?",
        (member_id,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    try:
        result["key_topics"] = json.loads(result.get("key_topics") or "[]")
    except Exception:
        result["key_topics"] = []
    return result


def _save_profile(member_id: int, profile_text: str, key_topics: list, model: str):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO politician_profiles
            (member_id, profile_text, key_topics, model_used)
        VALUES (?, ?, ?, ?)
    """, (member_id, profile_text, json.dumps(key_topics), model))
    conn.commit()
    conn.close()


def generate_politician_profile(member_id: int, force: bool = False) -> dict | None:
    """
    Generate and cache an AI-written profile for one MP.
    Returns dict with member_id, profile_text, key_topics, model_used.
    Returns None if no statements found or no API key.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set")
        return None

    if not force:
        cached = get_cached_profile(member_id)
        if cached:
            return cached

    conn = get_connection()
    c    = conn.cursor()

    c.execute("SELECT * FROM members WHERE id = ?", (member_id,))
    member = c.fetchone()
    if not member:
        conn.close()
        return None
    member = dict(member)

    c.execute("""
        SELECT statement_type, statement_text, sitting_date, topic, word_count, page_number
        FROM statements
        WHERE member_id = ?
        ORDER BY sitting_date, page_number
        LIMIT 200
    """, (member_id,))
    statements = [dict(r) for r in c.fetchall()]

    c.execute("""
        SELECT DISTINCT sitting_date FROM statements
        WHERE member_id = ? ORDER BY sitting_date
    """, (member_id,))
    dates = [r["sitting_date"] for r in c.fetchall()]

    c.execute("""
        SELECT topic, COUNT(*) as n FROM statements
        WHERE member_id = ? AND topic IS NOT NULL
        GROUP BY topic ORDER BY n DESC LIMIT 10
    """, (member_id,))
    top_topics = [r["topic"] for r in c.fetchall()]

    conn.close()

    if not statements:
        return None

    # Build statements block (cap at 100, max 400 chars each)
    stmts_text = "\n".join([
        f"[{s['sitting_date']} / {s['statement_type'].upper()}] {s['statement_text'][:400]}"
        for s in statements[:100]
    ])

    prompt = f"""You are writing a profile for an Indian Lok Sabha Member of Parliament.

Name: {member['name']}
Party: {member.get('party') or 'Unknown'}
Constituency: {member.get('constituency') or 'Unknown'}
Sitting dates active: {', '.join(dates)}
Top topics raised: {', '.join(top_topics)}
Total statements in database: {len(statements)}

Sample statements (up to 100):
---
{stmts_text}
---

Write a JSON profile:
{{
  "summary": "2-3 sentences describing who this MP is, their role, and their parliamentary style — based only on the statements above",
  "key_positions": ["specific position 1", "specific position 2", "specific position 3"],
  "key_topics": ["topic 1", "topic 2", "topic 3", "topic 4"],
  "notable_quote": "most memorable or representative line they said (max 25 words, exact wording)",
  "parliamentary_style": "one of: confrontational / collaborative / technical / rhetorical / procedural / inquisitive"
}}

Rules:
- Only use facts derived from the statements above
- Be concise and factual, no speculation
- If there are too few statements to characterise the MP, say so briefly in summary
- Respond ONLY with valid JSON — no markdown fences, no preamble"""

    try:
        import anthropic
        client  = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_json = message.content[0].text.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        data = json.loads(raw_json)

        # Render profile as markdown
        lines = []
        summary = data.get("summary", "")
        if summary:
            lines.append(summary)
            lines.append("")

        positions = data.get("key_positions", [])
        if positions:
            lines.append("**Key positions:** " + " · ".join(positions))
            lines.append("")

        style = data.get("parliamentary_style", "")
        if style:
            lines.append(f"**Parliamentary style:** {style.title()}")
            lines.append("")

        quote = data.get("notable_quote", "")
        if quote:
            lines.append(f'> "{quote}"')

        profile_text = "\n".join(lines).strip()
        key_topics   = data.get("key_topics", [])

        _save_profile(member_id, profile_text, key_topics, CLAUDE_MODEL)

        return {
            "member_id":    member_id,
            "profile_text": profile_text,
            "key_topics":   key_topics,
            "model_used":   CLAUDE_MODEL,
        }

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned non-JSON for profile {member_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Profile generation failed for member {member_id}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Bulk generation (called from CLI / admin subprocess)
# ══════════════════════════════════════════════════════════════════════════════

def bulk_generate_digests(force: bool = False):
    """Generate digests for all sitting dates that have statements but no digest."""
    conn = get_connection()
    c    = conn.cursor()
    if force:
        c.execute("""
            SELECT DISTINCT sitting_date FROM statements
            ORDER BY sitting_date
        """)
    else:
        c.execute("""
            SELECT DISTINCT s.sitting_date FROM statements s
            LEFT JOIN digests d ON d.sitting_date = s.sitting_date
            WHERE d.id IS NULL
            ORDER BY s.sitting_date
        """)
    dates = [r["sitting_date"] for r in c.fetchall()]
    conn.close()

    print(f"Dates needing digest: {len(dates)}")
    for i, date_str in enumerate(dates, 1):
        print(f"[{i}/{len(dates)}] Generating digest for {date_str}…")
        result = generate_digest_for_date(date_str, force=force)
        if result:
            print(f"  ✓ Done — {len(result.get('hot_topics', []))} topics")
        else:
            print(f"  ✗ Failed or no data")
    print("Bulk digest generation complete.")


def bulk_generate_profiles(force: bool = False):
    """Generate politician profiles for all MPs with statements but no profile."""
    conn = get_connection()
    c    = conn.cursor()
    if force:
        c.execute("""
            SELECT DISTINCT m.id, m.name FROM members m
            JOIN statements s ON s.member_id = m.id
            ORDER BY m.name
        """)
    else:
        c.execute("""
            SELECT DISTINCT m.id, m.name FROM members m
            JOIN statements s ON s.member_id = m.id
            LEFT JOIN politician_profiles p ON p.member_id = m.id
            WHERE p.id IS NULL
            ORDER BY m.name
        """)
    members = [dict(r) for r in c.fetchall()]
    conn.close()

    print(f"MPs needing profile: {len(members)}")
    for i, m in enumerate(members, 1):
        print(f"[{i}/{len(members)}] Generating profile for {m['name']}…")
        result = generate_politician_profile(m["id"], force=force)
        if result:
            print(f"  ✓ Done — {len(result.get('key_topics', []))} topics")
        else:
            print(f"  ✗ Failed or no data")
    print("Bulk profile generation complete.")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(description="Generate parliament digests and politician profiles")
    ap.add_argument("date",          nargs="?",        help="Date (YYYY-MM-DD) for single digest")
    ap.add_argument("--force",       action="store_true", help="Regenerate even if cached")
    ap.add_argument("--all-dates",   action="store_true", help="Generate digests for all sitting dates")
    ap.add_argument("--all-profiles",action="store_true", help="Generate profiles for all MPs")
    ap.add_argument("--member",      help="Generate profile for one MP by name_normalized slug")
    args = ap.parse_args()

    if args.all_dates:
        bulk_generate_digests(force=args.force)
        sys.exit(0)

    if args.all_profiles:
        bulk_generate_profiles(force=args.force)
        sys.exit(0)

    if args.member:
        conn = get_connection()
        c    = conn.cursor()
        c.execute("SELECT id, name FROM members WHERE name_normalized = ?", (args.member,))
        row = c.fetchone()
        conn.close()
        if not row:
            print(f"Member not found: {args.member}")
            sys.exit(1)
        print(f"Generating profile for {row['name']}…")
        result = generate_politician_profile(row["id"], force=args.force)
        if result:
            print(result["profile_text"])
            print(f"\n🏷  Topics: {', '.join(result['key_topics'])}")
        else:
            print("Could not generate profile.")
        sys.exit(0)

    # Single date digest
    date = args.date or get_latest_sitting_with_data()
    if not date:
        print("No sitting dates with data found in DB.")
        sys.exit(1)

    print(f"Generating digest for {date}…\n")
    result = generate_digest_for_date(date, force=args.force)
    if result:
        print(result["digest_text"])
        print(f"\n🏷  Hot topics: {', '.join(result['hot_topics'])}")
    else:
        print("Could not generate digest (no data or no API key).")
