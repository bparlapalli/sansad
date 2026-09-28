"""
scrapers/youtube/explore_transcripts.py — Diagnostic probe: for each party's
official YouTube channel, list recent videos and check whether usable
captions/transcripts actually exist.

This is NOT a production pipeline — it's the feasibility check we agreed on
before building one. Rallies especially may lack captions; this tells us
which channels/video types are actually usable before we invest more here.

No API key needed:
  - yt-dlp lists a channel's recent uploads (title + video id) without
    downloading video.
  - youtube-transcript-api pulls existing captions (manual or
    auto-generated) for a given video id, when they exist.

Usage:
    python scrapers/youtube/explore_transcripts.py
    python scrapers/youtube/explore_transcripts.py --party bjp --limit 10
    python scrapers/youtube/explore_transcripts.py --channel-url "https://www.youtube.com/@SomeChannel"
"""

import argparse

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

# Candidate official channels found via web search — VERIFY these are
# actually current/official before relying on them; party channels have
# been known to change or get taken down.
PARTY_CHANNELS = {
    "bjp":      "https://www.youtube.com/@bjp",
    "congress": "https://www.youtube.com/@IndianNationalCongress",
    "sp":       "https://www.youtube.com/@SamajwadiPartyTV",
    "bsp":      "https://www.youtube.com/@bahujansamajparty_BSP",
}


def list_recent_videos(channel_url: str, limit: int) -> list[dict]:
    url = channel_url.rstrip("/") + "/videos"
    ydl_opts = {
        "extract_flat": True,
        "playlistend": limit,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    return [{"id": e.get("id"), "title": e.get("title")} for e in entries[:limit] if e.get("id")]


def check_transcript(video_id: str) -> tuple[bool, str]:
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "hi"])
        text = " ".join(t["text"] for t in transcript)
        return True, text[:200]
    except Exception as e:
        return False, str(e)[:150]


def probe(channel_url: str, limit: int):
    print(f"\nChannel: {channel_url}")
    try:
        videos = list_recent_videos(channel_url, limit)
    except Exception as e:
        print(f"  FAILED to list videos: {e}")
        return

    print(f"  Found {len(videos)} recent video(s)")
    usable = 0
    for v in videos:
        ok, sample = check_transcript(v["id"])
        status = "HAS TRANSCRIPT" if ok else "no transcript"
        print(f"  [{status}] {v['title'][:70]}")
        if ok:
            usable += 1
            print(f"      sample: {sample}...")
        else:
            print(f"      reason: {sample}")
    print(f"  -> {usable}/{len(videos)} videos have a usable transcript")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--party", choices=list(PARTY_CHANNELS), help="Check one known party channel")
    ap.add_argument("--channel-url", help="Or check an arbitrary channel URL")
    ap.add_argument("--limit", type=int, default=5, help="How many recent videos to check")
    ap.add_argument("--all", action="store_true", help="Check all known party channels")
    args = ap.parse_args()

    if args.all:
        for name, url in PARTY_CHANNELS.items():
            probe(url, args.limit)
    elif args.channel_url:
        probe(args.channel_url, args.limit)
    elif args.party:
        probe(PARTY_CHANNELS[args.party], args.limit)
    else:
        print("Pass --party {bjp,congress,sp,bsp}, --channel-url <url>, or --all")
