#!/usr/bin/env python3
"""Fetch full Spotify playlist metadata: title and every current track
(title, artist, duration), via harmoni's OAuth user token."""
import json
import sys

from _common import config, spotify_error_message, spotify_track_to_dict
from spotify_api.client import SpotifyClient

if len(sys.argv) < 2:
    print(json.dumps({"error": "No playlist ID provided"}))
    sys.exit(1)

playlist_id = sys.argv[1]

try:
    client = SpotifyClient(config)
    meta = client.request_json("GET", f"/playlists/{playlist_id}", params={"fields": "name"})
    raw_items = client.get_playlist_tracks(playlist_id)

    tracks = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        track = item.get("item") or item.get("track")
        if not track or not track.get("name"):
            continue
        tracks.append(spotify_track_to_dict(track))

    result = {
        "title": meta.get("name", "Unknown Playlist"),
        "track_count": len(tracks),
        "duration_ms": sum(t["duration_ms"] for t in tracks),
        "tracks": tracks,
    }
    print(json.dumps(result))
except Exception as e:
    msg = spotify_error_message(e)
    print(json.dumps({"error": msg[7:] if msg.startswith("Error: ") else msg}))
    sys.exit(1)
