#!/usr/bin/env python3
"""Download an explicit list of {artist, track} entries into a playlist folder
via harmoni. Used by the playlist manager's Update flow to fetch only the
tracks missing locally. Track list is read as JSON from stdin."""
import asyncio
import json
import sys

sys.path.insert(0, "/Users/jacob/harmoni")

from downloader.playlist_download import download_playlist

if len(sys.argv) < 3:
    print("Usage: harmoni_tracks_download.py <playlist_name> <output_dir>", file=sys.stderr)
    sys.exit(1)

playlist_name = sys.argv[1]
output_dir = sys.argv[2]

tracks = json.load(sys.stdin)
if not tracks:
    print("No tracks to download", file=sys.stderr)
    sys.exit(0)

config_path = "/Users/jacob/harmoni/config.json"
with open(config_path) as f:
    config = json.load(f)

audio_format = config.get("audio_format", "mp3")
print(f"Downloading {len(tracks)} missing track(s) into '{playlist_name}'...")
asyncio.run(download_playlist(playlist_name, tracks, output_dir, audio_format, 0, config))
