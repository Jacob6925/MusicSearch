#!/usr/bin/env python3
"""Fetch a single YouTube / YouTube Music video's metadata (title, artist,
duration, video URL) via yt-dlp. Output matches one entry of playlist_full.py's
"tracks" list."""
import json
import sys

from _common import fetch_video, entry_to_track

if len(sys.argv) < 2:
    print(json.dumps({"error": "No video ID provided"}))
    sys.exit(1)

try:
    data = fetch_video(sys.argv[1])
    if not data.get("id") or not data.get("title"):
        raise RuntimeError("Video not found")
    print(json.dumps(entry_to_track(data)))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
