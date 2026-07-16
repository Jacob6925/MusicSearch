#!/usr/bin/env python3
"""Download a Spotify playlist: fetches tracks using harmoni's OAuth token, then
matches each to the best YouTube video (instead of harmoni's blind top-search-result)
and embeds metadata via harmoni's own metadata embedder."""
import asyncio
import os
import sys

from _common import config, audio_format, spotify_error_message
from spotify_api.client import SpotifyClient
from _yt_download import download_many

if len(sys.argv) < 4:
    print("Usage: harmoni_playlist_download.py <playlist_id> <playlist_name> <output_dir>", file=sys.stderr)
    sys.exit(1)

playlist_id = sys.argv[1]
playlist_name = sys.argv[2]
output_dir = sys.argv[3]

try:
    client = SpotifyClient(config)
    raw_items = client.get_playlist_tracks(playlist_id)
except Exception as e:
    print(spotify_error_message(e), file=sys.stderr)
    sys.exit(1)

tracks = []
for item in raw_items:
    if not isinstance(item, dict):
        continue
    # /items endpoint uses "item" key; legacy /tracks endpoint uses "track"
    track = item.get("item") or item.get("track")
    if not track or not track.get("name"):
        continue
    artists = [a["name"] for a in track.get("artists", []) if a.get("name")]
    tracks.append({
        "artist": artists[0] if artists else "",
        "track": track["name"],
        "duration_ms": track.get("duration_ms", 0),
    })

if not tracks:
    print(f"Error: No tracks found in playlist {playlist_id}. The playlist may be empty or inaccessible.", file=sys.stderr)
    sys.exit(1)

print(f"Found {len(tracks)} tracks in '{playlist_name}', downloading...")

playlist_dir = os.path.join(output_dir, playlist_name.replace("/", "-").strip())
os.makedirs(playlist_dir, exist_ok=True)

try:
    asyncio.run(download_many(tracks, playlist_dir, audio_format, config))
except Exception as e:
    print(f"Error: Download failed — {e}", file=sys.stderr)
    sys.exit(1)
