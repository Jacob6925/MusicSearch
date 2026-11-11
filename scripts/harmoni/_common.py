import json
import os
import sys
from pathlib import Path

HARMONI_PATH = Path(os.environ.get("HARMONI_PATH", Path.home() / "harmoni"))
sys.path.insert(0, str(HARMONI_PATH))

try:
    with open(HARMONI_PATH / "config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Error: harmoni config not found at {HARMONI_PATH / 'config.json'}.", file=sys.stderr)
    sys.exit(1)


def spotify_track_to_dict(track: dict) -> dict:
    """Convert a Spotify API track object into the track dict the app uses."""
    artists = [a["name"] for a in track.get("artists", []) if a.get("name")]
    album = track.get("album", {}) or {}
    images = album.get("images", []) or []
    return {
        "title": track["name"],
        "artist": ", ".join(artists) if artists else "Unknown",
        "album": album.get("name", ""),
        "artwork": images[0]["url"] if images else "",
        "preview_url": track.get("preview_url", "") or "",
        "url": track.get("external_urls", {}).get("spotify", ""),
        "duration_ms": track.get("duration_ms", 0),
        "release_date": album.get("release_date", ""),
        "explicit": bool(track.get("explicit", False)),
        "isrc": track.get("external_ids", {}).get("isrc", ""),
    }


def spotify_error_message(exc: Exception, kind: str = "playlist") -> str:
    """Map a Spotify API exception to a user-readable error line.
    `kind` ("playlist" or "track") only tunes the 400/403/404 wording."""
    msg = str(exc)
    if "400" in msg:
        return f"Error: 400 Bad Request: The {kind} URL may be malformed."
    if "401" in msg:
        return "Error: 401 Unauthorized: Please re-authenticate harmoni."
    if "403" in msg:
        if kind == "track":
            return "Error: 403 Forbidden: Spotify denied access to this track."
        return (
            "Error: 403 Forbidden: The playlist must be public and owned by your Spotify account. "
            "Artist release playlists and playlists owned by others cannot be downloaded."
        )
    if "404" in msg:
        return f"Error: 404 Not Found: Check that the {kind} URL is correct."
    if "429" in msg:
        return "Error: 429 Too Many Requests: Spotify rate limit reached. Wait a moment and try again."
    if "500" in msg:
        return "Error: 500 Internal Server Error: Spotify server error. Try again in a few minutes."
    if "502" in msg:
        return "Error: 502 Bad Gateway: Spotify server error. Try again in a few minutes."
    if "503" in msg:
        return "Error: 503 Service Unavailable: Spotify is temporarily down. Try again in a few minutes."
    if "No Spotify token" in msg or ("token" in msg.lower() and "available" in msg.lower()):
        return "Error: No Spotify token found. Open harmoni and sign in to Spotify first."
    if any(w in msg.lower() for w in ("connection", "network", "timeout", "timed out")):
        return "Error: Network error connecting to Spotify. Check your internet connection."
    return f"Error: Spotify error — {msg}"
