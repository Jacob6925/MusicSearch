import json
import subprocess
import sys

YT_DLP = [sys.executable, "-m", "yt_dlp"]


def fetch_playlist(playlist_id: str, first_only: bool = False) -> dict:
    """Return yt-dlp's flat JSON for a YouTube Music playlist (works for public/unlisted
    playlists without authentication)."""
    cmd = [*YT_DLP, "--flat-playlist", "-J", "--no-warnings",
           f"https://music.youtube.com/playlist?list={playlist_id}"]
    if first_only:
        cmd += ["--playlist-items", "1"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if result.returncode != 0 or not result.stdout.strip():
        err = (result.stderr or "").strip().splitlines()
        detail = err[-1] if err else "yt-dlp failed"
        if "private" in detail.lower():
            detail = "This playlist is private. Make it public or unlisted and try again."
        raise RuntimeError(detail.removeprefix("ERROR: "))
    return json.loads(result.stdout)


def clean_artist(name: str) -> str:
    name = (name or "").strip()
    return name.removesuffix(" - Topic").strip() or "Unknown"


def entry_to_track(e: dict) -> dict:
    """Convert a yt-dlp video/entry dict into the track dict the app uses."""
    artists = e.get("artists") or e.get("creators")
    artist = ", ".join(artists) if artists else clean_artist(e.get("channel") or e.get("uploader"))
    thumbs = e.get("thumbnails") or []
    return {
        "title": e["title"],
        "artist": artist,
        "album": e.get("album") or "",
        "artwork": thumbs[-1]["url"] if thumbs else "",
        "preview_url": "",
        "url": f"https://music.youtube.com/watch?v={e['id']}",
        "duration_ms": int((e.get("duration") or 0) * 1000),
        "release_date": "",
    }


def fetch_video(video_id: str) -> dict:
    """Return yt-dlp's JSON for a single video (ignoring any playlist it belongs to)."""
    cmd = [*YT_DLP, "-J", "--no-playlist", "--no-warnings",
           f"https://music.youtube.com/watch?v={video_id}"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    if result.returncode != 0 or not result.stdout.strip():
        err = (result.stderr or "").strip().splitlines()
        detail = err[-1] if err else "yt-dlp failed"
        if "private" in detail.lower():
            detail = "This video is private."
        raise RuntimeError(detail.removeprefix("ERROR: "))
    return json.loads(result.stdout)
