"""
scrapers/youtube/youtube_scraper.py — Party & leader YouTube channels → media_items.

Who and where to listen is defined in core/party_registry.py (parties, people,
time-bounded party affiliations, accounts). No API key needed:

  1. LIST  — for each active YouTube account, walk the channel's /streams and
             /videos tabs newest-first (yt-dlp, flat — no video downloaded)
             back to the cutoff date, work out who is speaking, and record
             the videos worth keeping as 'listed' rows in media_items.
               · a leader's own channel → every video, speaker = the owner
               · a party channel        → only videos whose title names a
                 tracked leader, or that are press conferences / briefings
               · a search account       → YouTube search results (news
                 channels) whose title names the owner; for people with no
                 official channel, e.g. CJP's Abhijeet Dipke
  2. FETCH — for each 'listed' row: exact publish time + description
             (yt-dlp) and the caption track from that same call, split into
             ~60-word timed chunks in media_chunks (each one deep-links to
             its moment in the video). The row is tagged with the speaker's
             party *on the publish date* via party_on(), so a leader who
             later switches parties keeps their old quotes under the old party.

Captions are mostly Hindi auto-generated. --english also stores YouTube's
machine translation in media_chunks.text_en (one extra request per video);
otherwise text_en is left for a later Sarvam translation pass.

TLS: like PIB, needs `truststore` on machines whose Python bundle can't
verify Google's chain. Never switch verification off instead.

YouTube rate-limits caption downloads per IP (HTTP 429). The scraper runs
sequentially with a jittered pause between videos, backs off on 429, and
stops cleanly if it persists (rows stay 'listed' — rerun with --fetch-only).
Don't parallelise it: more processes on one IP just hit the limit sooner.

Usage:
    python scrapers/youtube/youtube_scraper.py --seed                # load registry into DB
    python scrapers/youtube/youtube_scraper.py --days 30             # list + fetch, all accounts
    python scrapers/youtube/youtube_scraper.py --days 30 --party inc
    python scrapers/youtube/youtube_scraper.py --account @RahulGandhi --days 7
    python scrapers/youtube/youtube_scraper.py --list-only --days 30
    python scrapers/youtube/youtube_scraper.py --fetch-only --limit 50
    python scrapers/youtube/youtube_scraper.py --status
"""

import argparse
import json
import random
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Devanagari titles on Windows consoles

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    print("⚠ truststore not installed — YouTube requests may fail TLS verification.\n"
          "  Install it with: python -m pip install --use-feature=truststore truststore")

import yt_dlp

from core.db import get_connection, init_db
from core.party_registry import party_on, seed_registry

TABS           = ("streams", "videos")    # press conferences are livestreams
MIN_DURATION   = 60                       # skip Shorts
MAX_WALK       = 1500                     # hard stop per tab if dates are missing
SEARCH_RESULTS = 60
PAUSE_SEC      = 4                        # between videos (plus up to 4s jitter)
BACKOFF        = (120, 300, 900)          # seconds to wait on successive 429s
CHUNK_WORDS    = 60
CAPTION_LANGS  = ["hi", "en", "en-IN", "en-US"]

_PRESS     = ["briefing", "press conference", "press conf", "press meet", "media interaction",
              "addresses the media", "interacts with media", "media byte",
              "प्रेस वार्ता", "प्रेस कॉन्फ्रेंस", "पत्रकार वार्ता", "पत्रकार परिषद"]
_INTERVIEW = ["interview", "podcast", "in conversation", "exclusive", "साक्षात्कार"]
_SPEECH    = ["addresses", "address", "speech", "rally", "public meeting", "jansabha",
              "जनसभा", "संबोधन", "sabha", "parliament", "lok sabha", "rajya sabha"]


class Blocked(Exception):
    """YouTube is refusing transcript requests from this IP — stop, retry later."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def content_kind(title: str) -> str:
    t = title.lower()
    for kind, words in (("press_conference", _PRESS), ("interview", _INTERVIEW),
                        ("speech", _SPEECH)):
        if any(w in t for w in words):
            return kind
    return "other"


def load_people(conn):
    """[(person_id, [lowercased aliases])] for title matching."""
    return [(r["id"], [a.lower() for a in json.loads(r["aliases"] or "[]")])
            for r in conn.execute("SELECT id, aliases FROM people")]


def match_person(title: str, people):
    """The tracked person named earliest in the title, or None."""
    t, best = title.lower(), None
    for pid, aliases in people:
        for a in aliases:
            pos = t.find(a)
            if pos >= 0 and (best is None or pos < best[0]):
                best = (pos, pid)
    return best[1] if best else None


COOKIES_FROM = None   # set by --cookies-from-browser (e.g. "firefox")


def _ydl(**extra):
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if COOKIES_FROM:
        # Logged-in requests get far looser caption rate limits than anonymous ones.
        opts["cookiesfrombrowser"] = (COOKIES_FROM,)
    opts.update(extra)
    return yt_dlp.YoutubeDL(opts)


def _iso_day(ts):
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat() if ts else None


def select_accounts(conn, party=None, handle=None):
    sql = """SELECT a.*, p.slug AS party_slug FROM source_accounts a
             LEFT JOIN parties p ON a.owner_party_id = p.id
             WHERE a.platform = 'youtube' AND a.active = 1"""
    rows = conn.execute(sql).fetchall()
    if handle:
        rows = [r for r in rows if r["handle"].lower() == handle.lower()]
    if party:
        today = date.today().isoformat()
        pid = conn.execute("SELECT id FROM parties WHERE slug = ?", (party,)).fetchone()
        pid = pid[0] if pid else -1
        rows = [r for r in rows
                if r["owner_party_id"] == pid
                or (r["owner_person_id"] and party_on(conn, r["owner_person_id"], today) == pid)]
    return rows


# ── Phase 1: LIST ─────────────────────────────────────────────────────────────

def _channel_entries(acc, cutoff: str):
    """Yield flat entries from each tab, newest first, until older than cutoff."""
    base = acc["url"] or f"https://www.youtube.com/{acc['handle']}"
    for tab in TABS:
        with _ydl(extract_flat=True,
                  extractor_args={"youtubetab": {"approximate_date": [""]}}) as y:
            try:
                # process=False keeps `entries` a lazy page-by-page generator,
                # so breaking at the cutoff stops the walk — otherwise yt-dlp
                # pages through the channel's entire history first.
                info = y.extract_info(f"{base}/{tab}", download=False, process=False)
            except yt_dlp.utils.DownloadError as e:
                if "does not have a" in str(e):      # channel has no such tab
                    continue
                raise
            for n, e in enumerate(info.get("entries") or []):
                if n >= MAX_WALK:
                    print(f"      {tab}: stopped at {MAX_WALK} entries without reaching the cutoff")
                    break
                if e.get("live_status") == "is_upcoming":
                    continue
                day = _iso_day(e.get("timestamp"))
                # approximate dates are day-granular ("3 days ago"); one day
                # of slack so we don't stop early on the boundary
                if day and day < (date.fromisoformat(cutoff) - timedelta(days=1)).isoformat():
                    break
                yield e, day


def _search_entries(acc):
    # YouTube's own results page sorted by upload date (sp=CAI%3D) — this
    # yt-dlp build doesn't accept the `ytsearchdate` prefix.
    url = ("https://www.youtube.com/results?sp=CAI%253D&search_query="
           + urllib.parse.quote_plus(acc["handle"]))
    with _ydl(extract_flat=True, playlistend=SEARCH_RESULTS) as y:
        info = y.extract_info(url, download=False)
    for e in info.get("entries") or []:
        yield e, _iso_day(e.get("timestamp"))


def list_account(conn, acc, cutoff: str, people) -> int:
    added = seen = 0
    entries = _search_entries(acc) if acc["kind"] == "search" else _channel_entries(acc, cutoff)
    for e, approx_day in entries:
        vid, title = e.get("id"), e.get("title") or ""
        if not vid or (e.get("duration") and e["duration"] < MIN_DURATION):
            continue
        seen += 1
        kind = content_kind(title)
        if acc["owner_person_id"] and acc["kind"] == "channel":
            person, how = acc["owner_person_id"], "owner"
        else:
            person = match_person(title, people)
            how = "title_match" if person else "none"
            if acc["kind"] == "search":
                # Search results are full of videos *about* someone (critics,
                # roasts, reaction clips). Keep only formats where they're the
                # one talking: their press conferences and interviews.
                if (person != acc["owner_person_id"]
                        or kind not in ("press_conference", "interview")
                        or "#shorts" in title.lower()):
                    continue
                how = "search"
            elif not person and kind != "press_conference":
                continue                        # party channel: not a leader, not a presser
        cur = conn.execute("""
            INSERT OR IGNORE INTO media_items
              (platform, external_id, account_id, title, url, published_date,
               duration_sec, content_kind, person_id, attribution)
            VALUES ('youtube', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (vid, acc["id"], title, f"https://www.youtube.com/watch?v={vid}", approx_day,
             e.get("duration"), kind, person, how))
        added += cur.rowcount
    conn.commit()
    print(f"  {acc['handle']:<36} scanned {seen:>4}  new {added}", flush=True)
    return added


# ── Phase 2: FETCH ────────────────────────────────────────────────────────────

def _json3_segments(data):
    """[(start_sec, text)] from YouTube's json3 caption format."""
    out = []
    for ev in data.get("events", []):
        text = " ".join("".join(s.get("utf8", "") for s in ev.get("segs") or []).split())
        if text:
            out.append((ev.get("tStartMs", 0) / 1000, text))
    return out


def _chunks(segments):
    """Group caption segments into ~CHUNK_WORDS-word timed chunks."""
    out, buf, start = [], [], None
    for sec, text in segments:
        if text.startswith("["):                 # [संगीत], [Music], [Applause]
            continue
        if start is None:
            start = sec
        buf.append(text)
        if sum(len(b.split()) for b in buf) >= CHUNK_WORDS:
            out.append((start, " ".join(buf)))
            buf, start = [], None
    if buf:
        out.append((start, " ".join(buf)))
    return out


def _pick_track(info):
    """(lang, is_auto, json3_url) — manual captions first, then the original-language
    auto track ('hi-orig' is YouTube's name for untranslated Hindi ASR)."""
    manual, auto = info.get("subtitles") or {}, info.get("automatic_captions") or {}
    orig = info.get("language") or "hi"
    for tracks, is_auto, langs in (
        (manual, False, [orig, *CAPTION_LANGS]),
        (auto, True, [f"{orig}-orig", orig, *CAPTION_LANGS]),
    ):
        for lang in langs:
            for f in tracks.get(lang) or []:
                if f.get("ext") == "json3":
                    return lang.removesuffix("-orig"), is_auto, f["url"]
    return None


def _get_json(ydl, url):
    """GET a caption URL, sleeping through YouTube's 429s with backoff."""
    for wait in BACKOFF:
        try:
            return json.loads(ydl.urlopen(url).read())
        except yt_dlp.networking.exceptions.HTTPError as e:
            if e.status != 429:
                raise
            print(f"      429 from YouTube — waiting {wait // 60} min")
            time.sleep(wait)
    raise Blocked("still rate-limited after backing off")


def fetch_item(conn, row, cutoff: str, owner_party_id, english=False):
    with _ydl() as y:
        info = y.extract_info(row["url"], download=False)
        ts = info.get("release_timestamp") or info.get("timestamp")
        published_at = (datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M")
                        if ts else None)
        ud = info.get("upload_date")
        day = _iso_day(ts) or (f"{ud[:4]}-{ud[4:6]}-{ud[6:]}" if ud else None)

        # The speaker's party on the day — not today's party.
        party = party_on(conn, row["person_id"], day) if row["person_id"] and day else None
        common = dict(published_at=published_at, published_date=day,
                      description=(info.get("description") or "")[:5000],
                      duration_sec=info.get("duration"), party_id=party or owner_party_id)

        if day and day < cutoff:
            # Search results aren't date-bounded like channel walks are.
            _update(conn, row["id"], fetch_status="out_of_range", **common)
            return "out_of_range"

        track = _pick_track(info)
        if not track:
            _update(conn, row["id"], fetch_status="no_transcript",
                    fetched_at=datetime.now().isoformat(timespec="seconds"), **common)
            return "no_transcript"
        lang, auto, url = track
        chunks = _chunks(_json3_segments(_get_json(y, url)))

        # Optional: YouTube's machine translation to English, aligned to the same
        # chunks by timestamp. Costs one more caption request per video.
        english_by_chunk = {}
        if english and lang != "en":
            en = next((f["url"] for f in (info.get("automatic_captions") or {}).get("en") or []
                       if f.get("ext") == "json3"), None)
            if en:
                starts = [c[0] for c in chunks]
                for sec, text in _json3_segments(_get_json(y, en)):
                    i = max((k for k, s0 in enumerate(starts) if s0 <= sec), default=0)
                    english_by_chunk.setdefault(i, []).append(text)

    text = " ".join(c[1] for c in chunks)
    conn.execute("DELETE FROM media_chunks WHERE item_id = ?", (row["id"],))
    conn.executemany(
        "INSERT INTO media_chunks (item_id, chunk_index, start_sec, text, text_en) VALUES (?,?,?,?,?)",
        [(row["id"], i, round(s or 0, 1), t,
          " ".join(english_by_chunk[i]) if i in english_by_chunk else None)
         for i, (s, t) in enumerate(chunks)])
    _update(conn, row["id"], fetch_status="fetched", transcript_lang=lang,
            transcript_auto=int(auto), transcript_text=text, word_count=len(text.split()),
            fetched_at=datetime.now().isoformat(timespec="seconds"), fetch_error=None, **common)
    return "fetched"


def _update(conn, item_id, **cols):
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE media_items SET {sets} WHERE id = ?", (*cols.values(), item_id))
    conn.commit()


def fetch_pending(conn, account_ids, cutoff: str, limit=None, english=False) -> dict:
    sql = f"""SELECT m.*, a.owner_party_id FROM media_items m
              JOIN source_accounts a ON m.account_id = a.id
              WHERE m.platform = 'youtube' AND m.fetch_status IN ('listed', 'error')
                AND m.account_id IN ({','.join('?' * len(account_ids))})
              -- Most valuable first, so a rate-limit stop still leaves the
              -- pressers and full speeches in: party-channel short clips are
              -- mostly excerpts of the full livestreams anyway.
              ORDER BY m.content_kind = 'press_conference' DESC,
                       COALESCE(m.duration_sec, 0) DESC, m.published_date DESC"""
    rows = conn.execute(sql, account_ids).fetchall()
    if limit:
        rows = rows[:limit]
    tally = {}
    print(f"\nFetching {len(rows)} video(s)…")
    for i, r in enumerate(rows, 1):
        try:
            status = fetch_item(conn, r, cutoff, r["owner_party_id"], english)
        except Blocked as e:
            print(f"\n⛔ YouTube is blocking caption requests from this IP — stopping ({e}).\n"
                  f"   Remaining rows stay 'listed'; rerun with --fetch-only later.")
            tally["blocked"] = len(rows) - i + 1
            break
        except Exception as e:
            status = "error"
            _update(conn, r["id"], fetch_status="error", fetch_error=str(e)[:500])
        tally[status] = tally.get(status, 0) + 1
        print(f"  [{i}/{len(rows)}] {status:<13} {r['title'][:80]}", flush=True)
        time.sleep(PAUSE_SEC + random.random() * PAUSE_SEC)
    return tally


# ── Status ────────────────────────────────────────────────────────────────────

def status(conn):
    print("\nBy account:")
    for r in conn.execute("""
        SELECT a.handle, a.kind, a.verified,
               COUNT(m.id) n,
               SUM(m.fetch_status = 'fetched') f,
               SUM(m.fetch_status = 'listed') l,
               SUM(m.fetch_status = 'no_transcript') nt,
               SUM(m.fetch_status = 'error') err,
               MIN(m.published_date) d0, MAX(m.published_date) d1
        FROM source_accounts a LEFT JOIN media_items m ON m.account_id = a.id
        WHERE a.platform = 'youtube' GROUP BY a.id ORDER BY a.id"""):
        print(f"  {r['handle']:<36} {'✓' if r['verified'] else '?'} items={r['n']:<4} "
              f"fetched={r['f'] or 0:<4} listed={r['l'] or 0:<4} no_captions={r['nt'] or 0:<3} "
              f"errors={r['err'] or 0:<3} {r['d0'] or ''}…{r['d1'] or ''}")
    print("\nBy speaker (fetched, with party on the day):")
    for r in conn.execute("""
        SELECT COALESCE(pe.name, '(party channel, unnamed)') who, pa.short_name party,
               COUNT(*) n, SUM(m.word_count) w
        FROM media_items m LEFT JOIN people pe ON m.person_id = pe.id
        LEFT JOIN parties pa ON m.party_id = pa.id
        WHERE m.fetch_status = 'fetched' GROUP BY who, party ORDER BY n DESC"""):
        print(f"  {r['who']:<32} {r['party'] or '-':<9} videos={r['n']:<4} words={r['w'] or 0:,}")
    n = conn.execute("SELECT COUNT(*) FROM media_chunks").fetchone()[0]
    print(f"\nQuote chunks: {n:,}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--seed", action="store_true", help="Load core/party_registry.py into the DB and exit")
    ap.add_argument("--days", type=int, default=3, help="How far back to go (default 3)")
    ap.add_argument("--party", help="Only accounts of this party slug (inc, bjp, cjp)")
    ap.add_argument("--account", help="Only this handle, e.g. @RahulGandhi")
    ap.add_argument("--list-only", action="store_true")
    ap.add_argument("--fetch-only", action="store_true")
    ap.add_argument("--limit", type=int, help="Max videos to fetch this run")
    ap.add_argument("--english", action="store_true",
                    help="Also store YouTube's English auto-translation (2x caption requests)")
    ap.add_argument("--cookies-from-browser", metavar="BROWSER",
                    help="Use this browser's YouTube login (firefox works best on Windows; "
                         "Chrome/Edge cookie encryption usually blocks this)")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    global COOKIES_FROM
    COOKIES_FROM = args.cookies_from_browser

    init_db()
    conn = get_connection()
    seed_registry(conn)          # cheap + idempotent; keeps the DB in step with the file
    if args.seed:
        print("Registry seeded:", {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                                   for t in ("parties", "people", "affiliations", "source_accounts")})
        return
    if args.status:
        status(conn)
        return

    accounts = select_accounts(conn, args.party, args.account)
    if not accounts:
        sys.exit("No matching active YouTube accounts.")
    cutoff = (date.today() - timedelta(days=args.days)).isoformat()
    print(f"YouTube: {len(accounts)} account(s), since {cutoff}")

    if not args.fetch_only:
        people = load_people(conn)
        for acc in accounts:
            try:
                list_account(conn, acc, cutoff, people)
            except Exception as e:
                print(f"  {acc['handle']:<36} LIST FAILED: {str(e)[:150]}")

    if not args.list_only:
        tally = fetch_pending(conn, [a["id"] for a in accounts], cutoff, args.limit,
                              args.english)
        print("\nDone:", tally)
    conn.close()


if __name__ == "__main__":
    main()
