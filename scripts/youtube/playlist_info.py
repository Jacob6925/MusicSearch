#!/usr/bin/env python3
"""Fetch YouTube Music playlist title and track count."""
import json
import sys

from _common import fetch_playlist

if len(sys.argv) < 2:
    print(json.dumps({"error": "No playlist ID provided"}))
    sys.exit(1)

try:
    data = fetch_playlist(sys.argv[1], first_only=True)
    print(json.dumps({
        "title": data.get("title") or "Unknown Playlist",
        "track_count": data.get("playlist_count") or len(data.get("entries") or []),
    }))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
