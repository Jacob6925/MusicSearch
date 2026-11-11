#!/usr/bin/env python3
"""Fetch a single Spotify track's metadata (title, artist, duration, ISRC), via
harmoni's OAuth user token. Output matches one entry of playlist_full.py's
"tracks" list."""
import json
import sys

from _common import config, spotify_error_message, spotify_track_to_dict
from spotify_api.client import SpotifyClient

if len(sys.argv) < 2:
    print(json.dumps({"error": "No track ID provided"}))
    sys.exit(1)

track_id = sys.argv[1]

try:
    client = SpotifyClient(config)
    track = client.request_json("GET", f"/tracks/{track_id}")
    if not track or not track.get("name"):
        raise RuntimeError("404 Not Found: track has no metadata")
    print(json.dumps(spotify_track_to_dict(track)))
except Exception as e:
    msg = spotify_error_message(e, kind="track")
    print(json.dumps({"error": msg[7:] if msg.startswith("Error: ") else msg}))
    sys.exit(1)
