#!/usr/bin/env python3
"""Download an explicit list of {artist, track, duration_ms} entries into a playlist
folder, matching each to the best YouTube video (instead of harmoni's blind
top-search-result) and embedding metadata via harmoni's own metadata embedder.
Used by the playlist manager's Update flow to fetch only the tracks missing locally.
Track list is read as JSON from stdin."""
import asyncio
import json
import os
import sys

from _common import config
from _yt_download import download_many

if len(sys.argv) < 3:
    print("Usage: harmoni_tracks_download.py <playlist_name> <output_dir>", file=sys.stderr)
    sys.exit(1)

playlist_name = sys.argv[1]
output_dir = sys.argv[2]

tracks = json.load(sys.stdin)
if not tracks:
    print("No tracks to download", file=sys.stderr)
    sys.exit(0)

playlist_dir = os.path.join(output_dir, playlist_name.replace("/", "-").strip())
os.makedirs(playlist_dir, exist_ok=True)

print(f"Downloading {len(tracks)} missing track(s) into '{playlist_name}'...")

try:
    asyncio.run(download_many(tracks, playlist_dir, config))
except Exception as e:
    print(f"Error: Download failed — {e}", file=sys.stderr)
    sys.exit(1)
