#!/usr/bin/env python3
"""Fetch a YouTube Music playlist's title and every current track (title, artist,
duration, video URL) via yt-dlp."""
import json
import sys

from _common import fetch_playlist, entry_to_track

if len(sys.argv) < 2:
    print(json.dumps({"error": "No playlist ID provided"}))
    sys.exit(1)

try:
    data = fetch_playlist(sys.argv[1])
    tracks = []
    for e in data.get("entries") or []:
        if not e or not e.get("id") or not e.get("title"):
            continue
        if e["title"] in ("[Private video]", "[Deleted video]"):
            continue
        tracks.append(entry_to_track(e))
    print(json.dumps({
        "title": data.get("title") or "Unknown Playlist",
        "track_count": len(tracks),
        "duration_ms": sum(t["duration_ms"] for t in tracks),
        "tracks": tracks,
    }))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
