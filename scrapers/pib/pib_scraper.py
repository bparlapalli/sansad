"""
scrapers/pib/pib_scraper.py — Press Information Bureau (pib.gov.in) press releases.

Unlike eparlib, PIB answers plain HTTP requests, so no browser is needed.
Two phases, both resumable and idempotent (keyed by PIB's release ID, PRID):

  1. LIST  — for each date, POST the ASP.NET listing form at allRel.aspx
             (region + language + day/month/year) and record every release
             it shows as a 'listed' row in pib_releases (title + ministry).
  2. FETCH — for each 'listed' row, load PressReleasePage.aspx?PRID=...
             and fill in posted time, body text and the translation links.

TLS note: pib.gov.in doesn't send its intermediate certificate, so Python's
default cert bundle rejects it. We use `truststore` (the OS certificate
store, same as curl/browsers on Windows) instead of disabling verification.

Usage:
    python scrapers/pib/pib_scraper.py                         # today
    python scrapers/pib/pib_scraper.py --days 7                # last 7 days
    python scrapers/pib/pib_scraper.py --date 2026-09-25
    python scrapers/pib/pib_scraper.py --from 2026-09-01 --to 2026-09-28
    python scrapers/pib/pib_scraper.py --list-only --days 30   # index only, no bodies
    python scrapers/pib/pib_scraper.py --fetch-only --limit 200
    python scrapers/pib/pib_scraper.py --status
"""

import argparse
import html
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    print("⚠ truststore not installed — PIB requests will likely fail TLS verification.\n"
          "  Install it with: python -m pip install --use-feature=truststore truststore")

import requests

from core.db import get_connection, init_db

BASE_URL     = "https://www.pib.gov.in"
LIST_URL     = BASE_URL + "/allRel.aspx?reg={region}&lang={lang}"
RELEASE_URL  = BASE_URL + "/PressReleasePage.aspx?PRID={prid}"

REGIONS   = {3: "PIB Delhi"}           # others: see the ddlregion dropdown on allRel.aspx
LANGUAGES = {1: "english", 2: "hindi", 3: "urdu"}

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def _request(sess, method, url, retries=3, **kw):
    for attempt in range(retries):
        try:
            r = sess.request(method, url, timeout=60, **kw)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"    ↻ {e.__class__.__name__} — retrying in {wait}s")
            time.sleep(wait)


# ── Phase 1: listing ──────────────────────────────────────────────────────────

def _form_fields(page: str) -> dict:
    """Hidden ASP.NET state fields (__VIEWSTATE etc.) plus current dropdown values."""
    fields = dict(re.findall(
        r'<input type="hidden" name="([^"]+)" id="[^"]*" value="([^"]*)"', page))
    for name, body in re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        sel = re.search(r'<option[^>]*selected="selected"[^>]*value="([^"]*)"', body)
        first = re.search(r'<option[^>]*value="([^"]*)"', body)
        if sel or first:
            fields[name] = (sel or first).group(1)
    return fields


def _field_name(fields: dict, suffix: str) -> str:
    for name in fields:
        if name.endswith(suffix):
            return name
    raise RuntimeError(f"PIB listing form has no field ending in {suffix!r} — page layout changed?")


def list_releases(sess, day: date, region: int, lang: int) -> list[dict]:
    """Return [{prid, title, ministry}] for every release PIB lists on `day`."""
    url = LIST_URL.format(region=region, lang=lang)
    fields = _form_fields(_request(sess, "GET", url))

    day_f = _field_name(fields, "$ddlday")
    fields.update({
        day_f:                               str(day.day),
        _field_name(fields, "$ddlMonth"):    str(day.month),
        _field_name(fields, "$ddlYear"):     str(day.year),
        _field_name(fields, "$ddlMinistry"): "0",           # all ministries
        "__EVENTTARGET":                     day_f,
        "__EVENTARGUMENT":                   "",
    })
    page = _request(sess, "POST", url, data=fields)

    shown = re.search(r"Displaying\s+(\d+)\s+Press Release", page)
    releases = []
    # Releases are grouped: <li><h3 class='font104'>Ministry</h3><ul class='num'><li><a ...PRID=N>
    for ministry, block in re.findall(
            r"<h3 class='font104'>(.*?)</h3>\s*<ul class='num'>(.*?)</ul>", page, re.S):
        # Match from href onward — titles can contain raw tags (e.g. title='… <i>suo motu</i> …').
        for prid, title in re.findall(r"href='[^']*PRID=(\d+)'[^>]*>(.*?)</a>", block, re.S):
            releases.append({
                "prid":     int(prid),
                "title":    _clean(title),
                "ministry": _clean(ministry),
            })

    if shown and int(shown.group(1)) != len(releases):
        print(f"    ⚠ page says {shown.group(1)} releases, parsed {len(releases)} — check the listing markup")
    return releases


def store_listing(conn, releases, day: date, region: int, lang: int) -> int:
    added = 0
    for r in releases:
        cur = conn.execute("""
            INSERT INTO pib_releases (prid, title, ministry, release_date, region, language, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(prid) DO NOTHING
        """, (r["prid"], r["title"], r["ministry"], day.isoformat(),
              REGIONS.get(region, str(region)), LANGUAGES.get(lang, str(lang)),
              RELEASE_URL.format(prid=r["prid"])))
        added += cur.rowcount
    conn.commit()
    return added


# ── Phase 2: release pages ────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """HTML → plain text with paragraph breaks; drops script/style and embedded
    tweets (releases already quote the tweet text in the body)."""
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip, self._skip_tags = [], 0, []

    def handle_starttag(self, tag, attrs):
        if self._skip and tag == self._skip_tags[-1]:
            self._skip += 1             # nested same-name tag inside a skipped region
        elif tag in ("script", "style") or (
                tag == "blockquote" and "twitter-tweet" in (dict(attrs).get("class") or "")):
            self._skip += 1
            self._skip_tags.append(tag)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self._skip and tag == self._skip_tags[-1]:
            self._skip -= 1
            if not self._skip:
                self._skip_tags.pop()
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts).replace("\xa0", " ")
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.split("\n")]
        out, blank = [], False
        for ln in lines:
            if ln:
                out.append(ln)
                blank = False
            elif not blank and out:
                out.append("")
                blank = True
        return "\n".join(out).strip()


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _by_id(page: str, el_id: str) -> str | None:
    m = re.search(r'id="%s"[^>]*>(.*?)</(?:div|h2|span)>' % el_id, page, re.S)
    return _clean(m.group(1)) if m else None


def _parse_posted(text: str | None) -> tuple[str | None, str | None]:
    """'Posted On: 28 SEP 2026 9:19PM by PIB Delhi' → ('2026-09-28 21:19', 'PIB Delhi')."""
    if not text:
        return None, None
    m = re.search(r"(\d{1,2} [A-Za-z]{3} \d{4}) (\d{1,2}:\d{2}\s*[AP]M)(?:\s+by\s+(.+))?", text)
    if not m:
        return None, None
    dt = datetime.strptime(f"{m.group(1)} {m.group(2).replace(' ', '')}", "%d %b %Y %I:%M%p")
    return dt.strftime("%Y-%m-%d %H:%M"), (m.group(3) or "").strip() or None


def _strip_signoff(body: str) -> str:
    """Drop the '*****' separator and the officials' initials line (e.g. 'PK/KC/RT') at the end."""
    lines = body.split("\n")
    while lines and (not lines[-1].strip()
                     or re.fullmatch(r"\*+", lines[-1].strip())
                     or re.fullmatch(r"[^\s/]{1,12}(\s*/\s*[^\s/]{1,12})+", lines[-1].strip())):
        lines.pop()
    return "\n".join(lines).strip()


# Language names in the "Read this release in:" links are shown in the page's
# own language for a few scripts; normalise to English keys.
_LANG_NAMES = {"हिन्दी": "hindi", "English": "english", "اردو": "urdu"}


def parse_release(page: str) -> dict:
    title = _by_id(page, "Titleh2")
    if not title:
        raise ValueError("no Titleh2 on page — release missing or layout changed")

    posted_at, region = _parse_posted(_by_id(page, "PrDateTime"))

    # Body = everything between the date line and the "(Release ID: …)" span.
    start = re.search(r'id="PrDateTime"[^>]*>.*?</div>', page, re.S)
    end = page.find('id="ReleaseId"')
    body = ""
    if start and end > start.end():
        ex = _TextExtractor()
        ex.feed(page[start.end():end])
        body = _strip_signoff(ex.text())

    translations = {}
    lang_block = re.search(r'class="ReleaseLang">(.*?)</div>', page, re.S)
    if lang_block:
        for prid, lang in re.findall(r"PRID=(\d+)'[^>]*>\s*([^<]+?)\s*</a>", lang_block.group(1)):
            translations[_LANG_NAMES.get(lang, lang.lower())] = int(prid)

    return {
        "title":        title,
        "ministry":     _by_id(page, "MinistryName"),
        "posted_at":    posted_at,
        "region":       region,
        "body_text":    body,
        "word_count":   len(body.split()),
        "translations": json.dumps(translations, ensure_ascii=False) if translations else None,
    }


def fetch_pending(conn, sess, limit: int | None, delay: float) -> tuple[int, int]:
    rows = conn.execute("""
        SELECT prid FROM pib_releases
        WHERE fetch_status IN ('listed', 'error')
        ORDER BY release_date DESC, prid DESC
        LIMIT ?
    """, (limit or -1,)).fetchall()

    ok = err = 0
    for i, row in enumerate(rows, 1):
        prid = row["prid"]
        try:
            rel = parse_release(_request(sess, "GET", RELEASE_URL.format(prid=prid)))
            conn.execute("""
                UPDATE pib_releases SET
                    title        = ?,
                    ministry     = COALESCE(?, ministry),
                    posted_at    = ?,
                    release_date = COALESCE(substr(?, 1, 10), release_date),
                    region       = COALESCE(?, region),
                    body_text    = ?,
                    word_count   = ?,
                    translations = ?,
                    fetch_status = 'fetched',
                    fetch_error  = NULL,
                    fetched_at   = datetime('now')
                WHERE prid = ?
            """, (rel["title"], rel["ministry"], rel["posted_at"], rel["posted_at"],
                  rel["region"], rel["body_text"], rel["word_count"], rel["translations"], prid))
            ok += 1
            print(f"  [{i}/{len(rows)}] ✓ {prid}  {rel['word_count']:>5} words  {rel['title'][:70]}")
        except Exception as e:
            conn.execute("UPDATE pib_releases SET fetch_status = 'error', fetch_error = ? WHERE prid = ?",
                         (f"{e.__class__.__name__}: {e}"[:500], prid))
            err += 1
            print(f"  [{i}/{len(rows)}] ✗ {prid}  {e}")
        conn.commit()
        time.sleep(delay)
    return ok, err


# ── Status ────────────────────────────────────────────────────────────────────

def print_status(conn):
    total = conn.execute("SELECT COUNT(*) FROM pib_releases").fetchone()[0]
    print(f"\n{'='*65}\n📰  PIB press releases — {total} total\n{'='*65}")
    if not total:
        print("  (none yet — run with --days 7 to start)\n")
        return
    for r in conn.execute("SELECT fetch_status, COUNT(*) n FROM pib_releases GROUP BY 1"):
        print(f"  {r['fetch_status']:<10} {r['n']:>6}")
    span = conn.execute("SELECT MIN(release_date) lo, MAX(release_date) hi FROM pib_releases").fetchone()
    print(f"\n  Date range: {span['lo']} → {span['hi']}")
    print("\n  Top ministries:")
    for r in conn.execute("""SELECT ministry, COUNT(*) n FROM pib_releases
                             GROUP BY ministry ORDER BY n DESC LIMIT 10"""):
        print(f"    {r['n']:>5}  {r['ministry']}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _dates(args) -> list[date]:
    if args.date:
        return [date.fromisoformat(args.date)]
    if args.from_date:
        lo = date.fromisoformat(args.from_date)
        hi = date.fromisoformat(args.to_date) if args.to_date else date.today()
    else:
        hi = date.today()
        lo = hi - timedelta(days=args.days - 1)
    return [lo + timedelta(days=n) for n in range((hi - lo).days + 1)]


def main():
    ap = argparse.ArgumentParser(description="Scrape PIB press releases into sansad.db")
    ap.add_argument("--date", help="single date, YYYY-MM-DD")
    ap.add_argument("--from", dest="from_date", help="range start, YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", help="range end, YYYY-MM-DD (default today)")
    ap.add_argument("--days", type=int, default=1, help="last N days ending today (default 1)")
    ap.add_argument("--region", type=int, default=3, help="PIB region id (3 = PIB Delhi)")
    ap.add_argument("--lang", type=int, default=1, help="1 = English, 2 = Hindi, 3 = Urdu")
    ap.add_argument("--list-only", action="store_true", help="only index releases, don't fetch bodies")
    ap.add_argument("--fetch-only", action="store_true", help="only fetch bodies of already-listed releases")
    ap.add_argument("--limit", type=int, help="max release pages to fetch this run")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (be polite)")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    init_db()
    conn = get_connection()
    sess = _session()

    if args.status:
        print_status(conn)
        return

    if not args.fetch_only:
        days = _dates(args)
        print(f"\n📋 Listing PIB releases for {len(days)} day(s): {days[0]} → {days[-1]}")
        for d in days:
            try:
                releases = list_releases(sess, d, args.region, args.lang)
                added = store_listing(conn, releases, d, args.region, args.lang)
                print(f"  {d}  {len(releases):>4} listed, {added:>4} new")
            except Exception as e:
                print(f"  {d}  ✗ {e}")
            time.sleep(args.delay)

    if not args.list_only:
        print("\n📥 Fetching release pages")
        ok, err = fetch_pending(conn, sess, args.limit, args.delay)
        print(f"\n  Done: {ok} fetched, {err} errors")

    print_status(conn)
    conn.close()


if __name__ == "__main__":
    main()
