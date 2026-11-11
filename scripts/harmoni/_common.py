import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from appenv import find_harmoni_path  # noqa: E402

# Never crash on a non-ASCII title just because the console is cp1252.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


try:  # so running a script by hand sees the same .env the app does
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")
except ImportError:
    pass

HARMONI_PATH = find_harmoni_path()
sys.path.insert(0, str(HARMONI_PATH))


def _load_config() -> dict:
    for name in ("config.json", "config.json.example"):
        path = HARMONI_PATH / name
        if path.is_file():
            with open(path, encoding="utf-8-sig") as f:
                return json.load(f)
    print(
        f"Error: Harmoni is not installed at {HARMONI_PATH}. "
        "Run the setup script again (setup.bat on Windows, setup.command on Mac).",
        file=sys.stderr,
    )
    sys.exit(1)


config = _load_config()
# The app's .env is the single place the Spotify Client ID lives.
if os.environ.get("SPOTIFY_CLIENT_ID", "").strip():
    config["spotify_client_id"] = os.environ["SPOTIFY_CLIENT_ID"].strip()
config["spotify_redirect_uri"] = "http://127.0.0.1:8888/callback"
# ffmpeg / yt-dlp are found through PATH (the app puts them there).
config["ffmpeg_path"] = ""
config["ytdlp_path"] = ""
config["auto_cleanup"] = False
config["auto_backup"] = False


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
