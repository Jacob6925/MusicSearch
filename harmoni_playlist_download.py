#!/usr/bin/env python3
"""Download a Spotify playlist via harmoni: fetches tracks using harmoni's OAuth token, then batch downloads."""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/Users/jacob/harmoni")

from spotify_api.client import SpotifyClient
from downloader.playlist_download import download_playlist

if len(sys.argv) < 4:
    print("Usage: harmoni_playlist_download.py <playlist_id> <playlist_name> <output_dir>", file=sys.stderr)
    sys.exit(1)

playlist_id = sys.argv[1]
playlist_name = sys.argv[2]
output_dir = sys.argv[3]

config_path = "/Users/jacob/harmoni/config.json"
with open(config_path) as f:
    config = json.load(f)

# Use harmoni's OAuth token (has playlist-read-private scope)
client = SpotifyClient(config)
raw_items = client.get_playlist_tracks(playlist_id)

tracks = []
for item in raw_items:
    if not isinstance(item, dict):
        continue
    # /items endpoint uses "item" key; legacy /tracks endpoint uses "track"
    track = item.get("item") or item.get("track")
    if not track or not track.get("name"):
        continue
    artists = [a["name"] for a in track.get("artists", []) if a.get("name")]
    tracks.append({"artist": artists[0] if artists else "", "track": track["name"]})

if not tracks:
    print(f"No tracks found in playlist {playlist_id}", file=sys.stderr)
    sys.exit(1)

print(f"Found {len(tracks)} tracks in '{playlist_name}', downloading...")

audio_format = config.get("audio_format", "mp3")
asyncio.run(download_playlist(playlist_name, tracks, output_dir, audio_format, 0, config))
