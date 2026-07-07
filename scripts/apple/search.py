#!/usr/bin/env python3
"""Use gamdl's authenticated Apple Music API to search for songs, preferring explicit."""
import asyncio
import json
import sys

from _common import AppleMusicApi, COOKIES_PATH, format_artwork


def pick_explicit(songs: list[dict]) -> list[dict]:
    """
    Deduplicate by ISRC: if both explicit and clean versions exist, keep explicit.
    Then return the remaining list in original relevance order.
    """
    by_isrc: dict[str, dict] = {}
    no_isrc: list[dict] = []

    for song in songs:
        attrs = song.get("attributes", {})
        isrc = attrs.get("isrc")
        rating = attrs.get("contentRating", "")
        if not isrc:
            no_isrc.append(song)
            continue
        existing = by_isrc.get(isrc)
        if existing is None:
            by_isrc[isrc] = song
        elif rating == "explicit":
            by_isrc[isrc] = song

    seen_isrc = set()
    result = []
    for song in songs:
        attrs = song.get("attributes", {})
        isrc = attrs.get("isrc")
        if not isrc:
            result.append(song)
            continue
        if isrc in seen_isrc:
            continue
        seen_isrc.add(isrc)
        result.append(by_isrc[isrc])

    return result


async def search(query: str, limit: int = 20) -> list[dict]:
    api = await AppleMusicApi.create_from_netscape_cookies(COOKIES_PATH)
    raw = await api.get_search_results(query, types="songs", limit=limit * 2)
    songs = raw.get("results", {}).get("songs", {}).get("data", [])

    deduped = pick_explicit(songs)[:limit]

    results = []
    for song in deduped:
        attrs = song.get("attributes", {})
        artwork_raw = attrs.get("artwork", {}).get("url", "")
        results.append({
            "platform": "apple",
            "title": attrs.get("name", "Unknown"),
            "artist": attrs.get("artistName", "Unknown"),
            "album": attrs.get("albumName", ""),
            "artwork": format_artwork(artwork_raw) if artwork_raw else "",
            "preview_url": (attrs.get("previews") or [{}])[0].get("url", ""),
            "url": attrs.get("url", ""),
            "duration_ms": attrs.get("durationInMillis", 0),
            "release_date": attrs.get("releaseDate", ""),
            "explicit": attrs.get("contentRating", "") == "explicit",
        })

    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps([]))
        sys.exit(0)
    query = " ".join(sys.argv[1:])
    results = asyncio.run(search(query))
    print(json.dumps(results))
