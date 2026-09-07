#!/usr/bin/env python3
"""Match a list of Spotify tracks to Apple Music catalog songs (ISRC exact
match, then fuzzy fallback). Reads track list JSON from stdin
([{"artist","title","duration_ms","isrc"}, ...]), writes
{"matched": [...], "unmatched": [...]} JSON to stdout. Progress goes to
stderr so it can be folded into the caller's download log."""
import asyncio
import json
import sys

from _common import AppleMusicApi, COOKIES_PATH
from match import find_best_match

MAX_CONCURRENCY = 5


async def match_all(tracks: list[dict]) -> dict:
    api = await AppleMusicApi.create_from_netscape_cookies(COOKIES_PATH)
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async def process(t: dict):
        artist = (t.get("artist") or "").strip()
        title = (t.get("title") or t.get("track") or "").strip()
        isrc = t.get("isrc") or ""
        duration_ms = t.get("duration_ms") or 0

        async with sem:
            result = await find_best_match(api, artist, title, isrc, duration_ms)

        entry = {**t, "artist": artist, "title": title}
        if result:
            print(
                f"Apple Music match ({result['method']}, score={result['score']:.2f}): "
                f"{artist} - {title} -> {result['apple_artist']} - {result['apple_title']}",
                file=sys.stderr,
            )
            entry["apple_url"] = result["apple_url"]
            return "matched", entry
        print(f"No Apple Music match for: {artist} - {title}", file=sys.stderr)
        return "unmatched", entry

    results = await asyncio.gather(*(process(t) for t in tracks))
    matched = [entry for kind, entry in results if kind == "matched"]
    unmatched = [entry for kind, entry in results if kind == "unmatched"]
    return {"matched": matched, "unmatched": unmatched}


if __name__ == "__main__":
    tracks = json.load(sys.stdin)
    try:
        result = asyncio.run(match_all(tracks))
    except Exception as e:
        print(f"Apple Music matching failed: {e}", file=sys.stderr)
        print(json.dumps({"matched": [], "unmatched": tracks}))
        sys.exit(0)
    print(json.dumps(result))
