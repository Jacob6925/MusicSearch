#!/usr/bin/env python3
"""Fetch full Spotify playlist metadata: title and every current track
(title, artist, duration), via harmoni's OAuth user token."""
import json
import sys

sys.path.insert(0, "/Users/jacob/harmoni")

from spotify_api.client import SpotifyClient

if len(sys.argv) < 2:
    print(json.dumps({"error": "No playlist ID provided"}))
    sys.exit(1)

playlist_id = sys.argv[1]

config_path = "/Users/jacob/harmoni/config.json"
with open(config_path) as f:
    config = json.load(f)

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
        artists = [a["name"] for a in track.get("artists", []) if a.get("name")]
        tracks.append({
            "title": track["name"],
            "artist": artists[0] if artists else "Unknown",
            "duration_ms": track.get("duration_ms", 0),
        })

    result = {
        "title": meta.get("name", "Unknown Playlist"),
        "track_count": len(tracks),
        "duration_ms": sum(t["duration_ms"] for t in tracks),
        "tracks": tracks,
    }
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
