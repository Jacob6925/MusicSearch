#!/usr/bin/env python3
"""Download an explicit list of {artist, track, duration_ms} entries into a playlist
folder, matching each to the best YouTube video (instead of harmoni's blind
top-search-result) and embedding metadata via harmoni's own metadata embedder.
Used by playlist downloads, the playlist manager's Update flow (only the tracks
missing locally) and single-song link downloads (empty playlist_name = output_dir itself).
Track list is read as JSON from stdin."""
import asyncio
import json
import os
import sys

from _common import config
from pathsafe import safe_name
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

# An empty playlist_name means "download straight into output_dir" (single-song links).
folder_name = safe_name(playlist_name, fallback="", slash_to="-") if playlist_name.strip() else ""
playlist_dir = os.path.join(output_dir, folder_name) if folder_name else output_dir
os.makedirs(playlist_dir, exist_ok=True)

print(f"Downloading {len(tracks)} track(s) into '{folder_name or output_dir}'...")

try:
    asyncio.run(download_many(tracks, playlist_dir, config))
except Exception as e:
    print(f"Error: Download failed — {e}", file=sys.stderr)
    sys.exit(1)
