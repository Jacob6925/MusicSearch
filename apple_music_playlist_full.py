#!/usr/bin/env python3
"""Fetch full Apple Music playlist metadata: title and every current track
(title, artist, duration, per-song URL), via gamdl's authenticated API."""
import asyncio
import json
import logging
import sys

logging.disable(logging.CRITICAL)

import structlog
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=open("/dev/null", "w")),
)

from gamdl.api.apple_music import AppleMusicApi

COOKIES_PATH = "/Users/jacob/.gamdl/cookies.txt"


async def get_full_playlist(playlist_id: str) -> dict:
    api = await AppleMusicApi.create_from_netscape_cookies(COOKIES_PATH)
    data = await api.get_playlist(playlist_id, limit_tracks=300)
    item = data.get("data", [{}])[0]
    attrs = item.get("attributes", {})

    relationships = item.get("relationships", {}).get("tracks", {})
    tracks = relationships.get("data", [])
    next_uri = relationships.get("next")
    href_uri = relationships.get("href")
    while next_uri:
        extended = await api.get_extended_api_data(next_uri, href_uri)
        if not extended:
            break
        tracks.extend(extended.get("data", []))
        next_uri = extended.get("next")

    track_list = []
    for t in tracks:
        t_attrs = t.get("attributes", {})
        if not t_attrs:
            continue
        track_list.append({
            "title": t_attrs.get("name", "Unknown"),
            "artist": t_attrs.get("artistName", "Unknown"),
            "duration_ms": t_attrs.get("durationInMillis", 0),
            "url": t_attrs.get("url", ""),
        })

    return {
        "title": attrs.get("name", "Unknown Playlist"),
        "track_count": len(track_list),
        "duration_ms": sum(t["duration_ms"] for t in track_list),
        "tracks": track_list,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No playlist ID provided"}))
        sys.exit(1)
    playlist_id = sys.argv[1]
    try:
        result = asyncio.run(get_full_playlist(playlist_id))
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
