#!/usr/bin/env python3
"""Fetch a single Apple Music song's metadata (title, artist, duration, song URL)
via gamdl's authenticated API. Output matches one entry of playlist_full.py's
"tracks" list."""
import asyncio
import json
import sys

from _common import AppleMusicApi, COOKIES_PATH, format_artwork


async def get_song_info(song_id: str) -> dict:
    api = await AppleMusicApi.create_from_netscape_cookies(COOKIES_PATH)
    data = await api.get_song(song_id)
    items = data.get("data") or []
    attrs = items[0].get("attributes", {}) if items else {}
    if not attrs:
        raise RuntimeError("Song not found on Apple Music")
    artwork_raw = attrs.get("artwork", {}).get("url", "")
    return {
        "title": attrs.get("name", "Unknown"),
        "artist": attrs.get("artistName", "Unknown"),
        "album": attrs.get("albumName", ""),
        "artwork": format_artwork(artwork_raw) if artwork_raw else "",
        "preview_url": (attrs.get("previews") or [{}])[0].get("url", ""),
        "url": attrs.get("url", ""),
        "duration_ms": attrs.get("durationInMillis", 0),
        "release_date": attrs.get("releaseDate", ""),
        "explicit": attrs.get("contentRating", "") == "explicit",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No song ID provided"}))
        sys.exit(1)
    try:
        print(json.dumps(asyncio.run(get_song_info(sys.argv[1]))))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
