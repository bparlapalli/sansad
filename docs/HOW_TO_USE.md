# How to use ParamaSrota

A searchable record of what was actually said on the floor of the Lok Sabha. This is the same content as
the live site's [`/how-to-use`](../app/templates/how_to_use.html) page, kept here for anyone reading the repo.

ParamaSrota parses Lok Sabha debate PDFs into individual, attributed statements — who said what, on which
date, on which subject — instead of leaving them buried in a scanned transcript. Below are a few things
people actually come here to do, and exactly how to do them.

## "I want to see what happened in Parliament on a specific day"

1. Go to Search and click the **By Date** tab.
2. Pick the sitting date from the dropdown.
3. Hit Search — every statement from that day appears in order, with who said it and what kind of statement
   it was (question, answer, speech, ruling).

Shortcut: the **Today** page does this automatically for the most recent sitting day, plus an AI-written
summary of what happened.

## "I want to know what the PM (or my MP) has been saying lately"

1. Go to Search and click the **Politician** tab.
2. Start typing their name — a dropdown of matching MPs (with how many statements each has) appears as you type.
3. Hit Search — every statement from them shows up, most recent first.
4. Once you have results, a **"Refine with free text"** box appears above them — type a topic (e.g. "budget",
   "farmers", "railways") to narrow it down to just what they've said about that specific subject.

## "I want to see how what an MP said has changed over time — or find something they said a while back"

1. Same starting point as above — Search → Politician tab, search their name.
2. Every one of their statements is dated, and results are newest-first — scroll down to go further back in time.
3. Use the **"Refine with free text"** box to jump straight to every time they've spoken about a specific
   bill, scheme, or issue, regardless of date — the fastest way to compare what someone said about the same
   subject at two different points in time.

Heads up: "back in time" is only as far back as what's currently in the dataset — see below.

## "I have a keyword — a scheme, a bill, a phrase — and want to know who's said what about it"

1. Go to Search and click the **Free Text** tab.
2. Type the word or phrase and hit Search.
3. Each result shows the exact passage that matched — not the whole speech it came from — via a
   `statement_chunks` layer (paragraph-sized, sentence-safe slices, indexed separately from the full
   statement) — so you're not hunting through a wall of text. Click **"Show full statement"** to expand to
   the complete remarks with full speaker/date/page context.

## Other search modes not covered above

- **Party** — see all MPs from a party and what they've said, optionally filtered by date or keyword.

## What's in the data

This is an actively-growing dataset. The full historical archive is maintained locally and grows daily; the
public site shows a rolling recent window (see [Deployment](#deployment) below) rather than the complete
record. Older sessions are added to the local archive over time.

## Other pages

- **Today** — the latest sitting day's summary and proceedings.
- **News** — a running briefing of recent parliamentary activity.
- **PDFs** — the source debate documents processed so far.
- **Speakers** — every MP with a statement in the dataset, each with a profile page.
- **Sessions** — an overview of Lok Sabha sessions and their sitting dates.

## Where this comes from

Source PDFs are published by the Lok Sabha Secretariat at [eparlib.sansad.in](https://eparlib.sansad.in).
Statements are extracted and attributed automatically, non-English statements are translated where noted,
and daily summaries are AI-generated from the parsed statements — treat them as a starting point for finding
the primary source, not a substitute for it.

## Deployment

The live site is intentionally a **partial mirror**: the complete `sansad.db` never leaves the machine it's
scraped and parsed on. A trimmed export (default: last 30 days of statements, relative to the newest sitting
date in the data) is pushed to the deployed app over an authenticated endpoint. See
[CLAUDE.md § Deployment](../CLAUDE.md#deployment) for the full architecture.
