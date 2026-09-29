"""
core/party_registry.py — Who we track off the Parliament floor, and where.

Three layers, all seeded into the DB by seed_registry():

  PARTIES       one row per party / movement
  PEOPLE        one identity per leader, for life — their party is NOT stored
                here. It lives in time-bounded AFFILIATIONS, so when someone
                switches parties they keep the same person row, and each quote
                is tagged with the party they belonged to on the day they said
                it (see party_on()).
  ACCOUNTS      where to listen: a platform + handle, owned by a party or a
                person. `verified=1` only for handles we actually resolved and
                checked (channel name + subscriber count). Everything else is
                `active=0` until someone confirms it — party handles are a
                favourite target for impostors (e.g. YouTube's @INCIndia and
                @priyankagandhivadra are NOT the real ones).

Editing this file then running
    python scrapers/youtube/youtube_scraper.py --seed
is how you add a leader, a party switch, or a new channel. Seeding is
idempotent: existing rows are updated, nothing is deleted.
"""

import json

# ── Parties ───────────────────────────────────────────────────────────────────
PARTIES = [
    # slug,  name,                          short,      kind
    ("inc", "Indian National Congress",     "Congress", "party"),
    ("bjp", "Bharatiya Janata Party",       "BJP",      "party"),
    ("cjp", "Cockroach Janta Party",        "CJP",      "movement"),
    # Not a registered party: satirical youth movement founded 2026-05-16 by
    # Abhijeet Dipke; founder has said it will stay a pressure group.
]

# ── People ────────────────────────────────────────────────────────────────────
# aliases: matched (case-insensitively) against video titles on party channels
# to work out who is speaking. Include Hindi spellings — many titles are Hindi.
# member: members.name_normalized, to link to their Parliament record.
PEOPLE = [
    # Congress
    dict(slug="rahul-gandhi", name="Rahul Gandhi", member="rahul gandhi",
         aliases=["Rahul Gandhi", "राहुल गांधी"]),
    dict(slug="mallikarjun-kharge", name="Mallikarjun Kharge",
         aliases=["Kharge", "खरगे", "खड़गे"]),
    dict(slug="priyanka-gandhi", name="Priyanka Gandhi Vadra",
         aliases=["Priyanka Gandhi", "प्रियंका गांधी"]),
    dict(slug="jairam-ramesh", name="Jairam Ramesh",
         aliases=["Jairam Ramesh", "जयराम रमेश"]),
    dict(slug="pawan-khera", name="Pawan Khera",
         aliases=["Pawan Khera", "पवन खेड़ा"]),
    # BJP
    dict(slug="narendra-modi", name="Narendra Modi",
         aliases=["PM Modi", "Narendra Modi", "प्रधानमंत्री मोदी", "पीएम मोदी", "नरेंद्र मोदी"]),
    dict(slug="amit-shah", name="Amit Shah",
         aliases=["Amit Shah", "अमित शाह"]),
    dict(slug="nitin-nabin", name="Nitin Nabin",
         aliases=["Nitin Nabin", "नितिन नबीन"]),
    dict(slug="jp-nadda", name="J. P. Nadda", member="jagat prakash nadda",
         aliases=["JP Nadda", "J P Nadda", "J.P. Nadda", "नड्डा"]),
    dict(slug="sudhanshu-trivedi", name="Sudhanshu Trivedi",
         aliases=["Sudhanshu Trivedi", "सुधांशु त्रिवेदी"]),
    # Party-switch example — one identity, two affiliations (see below)
    dict(slug="jyotiraditya-scindia", name="Jyotiraditya Scindia",
         aliases=["Scindia", "सिंधिया"]),
    # CJP
    dict(slug="abhijeet-dipke", name="Abhijeet Dipke",
         aliases=["Abhijeet Dipke", "Abhijit Dipke", "अभिजीत दिपके"],
         notes="Founder, Cockroach Janta Party. Worked on AAP's digital campaigns "
               "2020–23 as staff (not tracked as a party affiliation)."),
]

# ── Affiliations ──────────────────────────────────────────────────────────────
# (person, party, role, start, end). start=None means "since before we track";
# end=None means current. Roles are deliberately sparse — only add one when
# you've checked it's current; posts change (BJP's president changed in 2026).
AFFILIATIONS = [
    ("rahul-gandhi",        "inc", "Leader of Opposition, Lok Sabha", None, None),
    ("mallikarjun-kharge",  "inc", "Congress President",              None, None),
    ("priyanka-gandhi",     "inc", "General Secretary",               None, None),
    ("jairam-ramesh",       "inc", "General Secretary (Communications)", None, None),
    ("pawan-khera",         "inc", "Chairman, Media & Publicity",     None, None),
    ("narendra-modi",       "bjp", "Prime Minister",                  None, None),
    ("amit-shah",           "bjp", "Home Minister",                   None, None),
    ("nitin-nabin",         "bjp", "National President",              None, None),
    ("jp-nadda",            "bjp", None,                              None, None),
    ("sudhanshu-trivedi",   "bjp", "National Spokesperson",           None, None),
    ("jyotiraditya-scindia", "inc", None,                             None, "2020-03-10"),
    ("jyotiraditya-scindia", "bjp", None,                             "2020-03-11", None),
    ("abhijeet-dipke",      "cjp", "Founder",                         "2026-05-16", None),
]

# ── Accounts ──────────────────────────────────────────────────────────────────
# owner is ("party", slug) or ("person", slug).
# kind="search": no official channel exists, so we run a YouTube search for the
# handle (a query) and keep results whose title names the owner. Lower
# confidence — these are news channels' uploads, anchors talk too.
ACCOUNTS = [
    # YouTube — resolved and checked 2026-09-28
    dict(platform="youtube", handle="@IndianNationalCongress", owner=("party", "inc"),
         external_id="UCjfYRVmU3JrKN78mLJHHUPQ", verified=1,
         notes="~8M subs. Daily AICC briefings are livestreams (/streams tab)."),
    dict(platform="youtube", handle="@bjp", owner=("party", "bjp"),
         external_id="UCrwE8kVqtIUVUzKui2WVpuQ", verified=1, notes="~6.4M subs."),
    dict(platform="youtube", handle="@RahulGandhi", owner=("person", "rahul-gandhi"),
         external_id="UC1DtEMePmr4O6F2do6BVl7A", verified=1, notes="~10.9M subs."),
    dict(platform="youtube", handle="@PriyankaGandhi", owner=("person", "priyanka-gandhi"),
         external_id="UCARYeq2BneMi_0oqwNySsyg", verified=1, notes="~1.7M subs."),
    dict(platform="youtube", handle="@narendramodi", owner=("person", "narendra-modi"),
         external_id="UC1NF71EwP41VdjAU1iXdLkw", verified=1, notes="~31M subs."),
    dict(platform="youtube", handle="@AmitShah", owner=("person", "amit-shah"),
         external_id="UCnC4JCEAMQetXkR_DVy2onA", verified=1, notes="~714K subs."),
    # Kharge, Jairam Ramesh, Pawan Khera, Nabin, Trivedi: no personal channel
    # found — they appear on the party channels and are picked up by title.

    # CJP has no verified official YouTube channel (@CockroachRevolution2029
    # looks fan-run) — its press meets are uploaded by news channels.
    # Each search returns ~25 results and they vary run to run, so a few
    # angled queries; the scraper keeps only pressers/interviews naming him.
    *[dict(platform="youtube", kind="search", handle=q,
           owner=("person", "abhijeet-dipke"), verified=0,
           notes="Search-based: news channels' uploads of Dipke's press meets/interviews.")
      for q in ("Abhijeet Dipke", "Abhijeet Dipke press conference",
                "Abhijeet Dipke interview", "CJP press conference Dipke")],

    # Not scraped yet — recorded so the map is in one place. From memory,
    # NOT verified: check each handle before setting active=1.
    dict(platform="x", handle="@INCIndia",        owner=("party", "inc"), active=0),
    dict(platform="x", handle="@BJP4India",       owner=("party", "bjp"), active=0),
    dict(platform="x", handle="@RahulGandhi",     owner=("person", "rahul-gandhi"), active=0),
    dict(platform="x", handle="@kharge",          owner=("person", "mallikarjun-kharge"), active=0),
    dict(platform="x", handle="@Jairam_Ramesh",   owner=("person", "jairam-ramesh"), active=0),
    dict(platform="x", handle="@narendramodi",    owner=("person", "narendra-modi"), active=0),
    dict(platform="x", handle="@AmitShah",        owner=("person", "amit-shah"), active=0),
    dict(platform="website", handle="inc.in",     owner=("party", "inc"), active=0,
         url="https://inc.in", notes="Press releases / statements section"),
    dict(platform="website", handle="bjp.org",    owner=("party", "bjp"), active=0,
         url="https://www.bjp.org", notes="Press releases section"),
    dict(platform="website", handle="cockroachjantaparty.org", owner=("party", "cjp"), active=0,
         url="https://cockroachjantaparty.org", notes="Reported offline at times."),
]


def _account_url(a):
    if a.get("url"):
        return a["url"]
    if a["platform"] == "youtube" and a.get("kind", "channel") == "channel":
        return f"https://www.youtube.com/{a['handle']}"
    if a["platform"] == "x":
        return f"https://x.com/{a['handle'].lstrip('@')}"
    return None


def seed_registry(conn):
    """Upsert PARTIES, PEOPLE, AFFILIATIONS and ACCOUNTS. Never deletes."""
    c = conn.cursor()
    for slug, name, short, kind in PARTIES:
        c.execute("""INSERT INTO parties (slug, name, short_name, kind) VALUES (?,?,?,?)
                     ON CONFLICT(slug) DO UPDATE SET name=excluded.name,
                       short_name=excluded.short_name, kind=excluded.kind""",
                  (slug, name, short, kind))
    party_id = {r[0]: r[1] for r in c.execute("SELECT slug, id FROM parties")}

    for p in PEOPLE:
        member_id = None
        if p.get("member"):
            row = c.execute("SELECT id FROM members WHERE name_normalized = ?",
                            (p["member"],)).fetchone()
            member_id = row[0] if row else None
        c.execute("""INSERT INTO people (slug, name, aliases, member_id, notes) VALUES (?,?,?,?,?)
                     ON CONFLICT(slug) DO UPDATE SET name=excluded.name, aliases=excluded.aliases,
                       member_id=COALESCE(excluded.member_id, people.member_id),
                       notes=excluded.notes""",
                  (p["slug"], p["name"], json.dumps(p.get("aliases", []), ensure_ascii=False),
                   member_id, p.get("notes")))
    person_id = {r[0]: r[1] for r in c.execute("SELECT slug, id FROM people")}

    for person, party, role, start, end in AFFILIATIONS:
        # UNIQUE(person, party, start) can't dedupe NULL starts, so upsert by hand.
        row = c.execute("""SELECT id FROM affiliations WHERE person_id=? AND party_id=?
                           AND start_date IS ?""",
                        (person_id[person], party_id[party], start)).fetchone()
        if row:
            c.execute("UPDATE affiliations SET role=?, end_date=?, source='registry' WHERE id=?",
                      (role, end, row[0]))
        else:
            c.execute("""INSERT INTO affiliations (person_id, party_id, role, start_date, end_date, source)
                         VALUES (?,?,?,?,?,'registry')""",
                      (person_id[person], party_id[party], role, start, end))

    for a in ACCOUNTS:
        owner_type, owner_slug = a["owner"]
        c.execute("""INSERT INTO source_accounts (platform, kind, handle, external_id, url,
                       owner_party_id, owner_person_id, verified, active, notes)
                     VALUES (?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(platform, handle) DO UPDATE SET kind=excluded.kind,
                       external_id=COALESCE(excluded.external_id, source_accounts.external_id),
                       url=excluded.url, owner_party_id=excluded.owner_party_id,
                       owner_person_id=excluded.owner_person_id, verified=excluded.verified,
                       active=excluded.active, notes=excluded.notes""",
                  (a["platform"], a.get("kind", "channel"), a["handle"], a.get("external_id"),
                   _account_url(a),
                   party_id[owner_slug] if owner_type == "party" else None,
                   person_id[owner_slug] if owner_type == "person" else None,
                   a.get("verified", 0), a.get("active", 1), a.get("notes")))
    conn.commit()


def party_on(conn, person_id, on_date):
    """The party `person_id` belonged to on `on_date` (ISO), or None."""
    row = conn.execute("""SELECT party_id FROM affiliations
                          WHERE person_id = ?
                            AND (start_date IS NULL OR start_date <= ?)
                            AND (end_date   IS NULL OR end_date   >= ?)
                          ORDER BY start_date DESC LIMIT 1""",
                       (person_id, on_date, on_date)).fetchone()
    return row[0] if row else None
