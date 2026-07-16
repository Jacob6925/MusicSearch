import json
import os
import re
import sys
import time
import base64
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

import playlist_store

load_dotenv()

app = Flask(__name__)

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

spotify_token_cache = {"token": None}

PROJECT_ROOT = Path(__file__).parent
DOWNLOAD_DIR = Path.home() / "Music" / "MusicSearch"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

GAMDL = shutil.which("gamdl") or "/Library/Frameworks/Python.framework/Versions/3.11/bin/gamdl"

_GAMDL_CONFIG_TEMPLATE = PROJECT_ROOT / "gamdl" / "config.ini"
_COOKIES_PATH = PROJECT_ROOT / "gamdl" / "cookies.txt"
_GAMDL_CONFIG_RESOLVED = PROJECT_ROOT / "gamdl" / ".config_resolved.ini"


def _resolve_gamdl_config() -> str:
    """Write config.ini with the absolute cookies_path substituted in."""
    template = _GAMDL_CONFIG_TEMPLATE.read_text()
    resolved = re.sub(
        r"^cookies_path\s*=.*$",
        f"cookies_path = {_COOKIES_PATH}",
        template,
        flags=re.MULTILINE,
    )
    _GAMDL_CONFIG_RESOLVED.write_text(resolved)
    return str(_GAMDL_CONFIG_RESOLVED)


GAMDL_CONFIG = _resolve_gamdl_config()

downloads = {}


def _tail_log(path, lines=20):
    try:
        with open(path) as f:
            return "".join(f.readlines()[-lines:])
    except Exception:
        return ""


def _cleanup_log(log_path):
    try:
        if os.path.exists(log_path):
            os.remove(log_path)
    except Exception:
        pass


def _parse_download_error(log_text):
    """Extract a clean error message from log output, or return None to fall back to raw output."""
    # Our own scripts prefix clean error lines with "Error:" — use the last one found.
    clean_msg = None
    for line in log_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("Error:", "Download failed:", "Spotify error:", "Network error:")):
            clean_msg = stripped
    if clean_msg:
        return clean_msg

    low = log_text.lower()
    if "does not exist" in log_text and ("create the file" in low or "drag and drop" in low):
        return "A required gamdl file is missing. Check that gamdl/config.ini and gamdl/cookies.txt exist."
    if "no module named" in low:
        return "A required Python module is missing. Check that harmoni is installed at ~/harmoni (or set the HARMONI_PATH env var)."
    if "filenotfounderror" in low and "config.json" in low:
        return "harmoni config not found. Check that ~/harmoni/config.json exists (or set the HARMONI_PATH env var)."
    if "429" in log_text or "rate limit" in low or "too many requests" in low:
        return "429 Too Many Requests: Spotify rate limit reached. Wait a moment and try again."
    if "503" in log_text and "spotify" in low:
        return "503 Service Unavailable: Spotify is temporarily down. Try again in a few minutes."
    if "502" in log_text and "spotify" in low:
        return "502 Bad Gateway: Spotify server error. Try again in a few minutes."
    if "500" in log_text and "spotify" in low:
        return "500 Internal Server Error: Spotify server error. Try again in a few minutes."

    return None


def _fail_on_returncode(download_id, returncode, log_path):
    tail = _tail_log(log_path, 40)
    msg = _parse_download_error(tail) or f"Exit code {returncode}. Last output:\n{tail}"
    downloads[download_id]["status"] = "error"
    downloads[download_id]["error"] = msg


def get_spotify_token():
    if spotify_token_cache["token"]:
        return spotify_token_cache["token"]
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    auth = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "client_credentials"},
        timeout=10,
    )
    if resp.status_code == 200:
        spotify_token_cache["token"] = resp.json()["access_token"]
        return spotify_token_cache["token"]
    return None


def search_apple_music(query, limit=20):
    apple_script = PROJECT_ROOT / "scripts" / "apple" / "search.py"
    try:
        result = subprocess.run(
            [sys.executable, apple_script, query],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)[:limit]
    except Exception:
        pass
    return []


def search_spotify(query, limit=10):
    for _ in range(2):
        token = get_spotify_token()
        if not token:
            return []
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "track", "limit": limit},
            timeout=10,
        )
        if resp.status_code != 401:
            break
        spotify_token_cache["token"] = None
    if resp.status_code != 200:
        return []
    results = []
    items = resp.json().get("tracks", {}).get("items", [])
    for track in items:
        images = track.get("album", {}).get("images", [])
        results.append({
            "platform": "spotify",
            "title": track.get("name", "Unknown"),
            "artist": ", ".join(a["name"] for a in track.get("artists", [])),
            "album": track.get("album", {}).get("name", ""),
            "artwork": images[0]["url"] if images else "",
            "preview_url": track.get("preview_url", ""),
            "url": track.get("external_urls", {}).get("spotify", ""),
            "duration_ms": track.get("duration_ms", 0),
            "release_date": track.get("album", {}).get("release_date", ""),
        })
    return results


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    platform = request.args.get("platform", "both")
    if not query:
        return jsonify({"results": [], "error": "No query provided"})

    results = []
    errors = []

    if platform in ("apple", "both"):
        try:
            results.extend(search_apple_music(query))
        except Exception as e:
            errors.append(f"Apple Music error: {e}")

    if platform in ("spotify", "both"):
        if not SPOTIFY_CLIENT_ID:
            errors.append("Spotify not configured — set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars")
        else:
            try:
                results.extend(search_spotify(query))
            except Exception as e:
                errors.append(f"Spotify error: {e}")

    if platform == "both":
        seen = set()
        deduped = []
        for r in results:
            key = re.sub(r"[^a-z0-9]", "", r["title"].lower()) + "|" + re.sub(r"[^a-z0-9]", "", r["artist"].lower())
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        results = deduped

    return jsonify({"results": results, "errors": errors})


@app.route("/api/status")
def api_status():
    return jsonify({
        "apple_music": True,
        "spotify": bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET),
    })


def parse_playlist_url(url):
    """Returns (platform, playlist_id) or (None, None)."""
    url = url.strip()
    am = re.search(r'music\.apple\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?playlist/(?:[^/?#\s]+/)?(pl\.[^/?#\s]+)', url, re.IGNORECASE)
    if am:
        return "apple", am.group(1)
    sp = re.search(r'open\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/([A-Za-z0-9]+)', url, re.IGNORECASE)
    if sp:
        return "spotify", sp.group(1)
    return None, None


def get_apple_music_playlist_info(playlist_id):
    script = PROJECT_ROOT / "scripts" / "apple" / "playlist_info.py"
    result = subprocess.run(
        [sys.executable, script, playlist_id],
        capture_output=True, text=True, timeout=30,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    raise RuntimeError(result.stderr.strip() or "Failed to fetch Apple Music playlist info")


def get_spotify_playlist_info(playlist_id):
    token = get_spotify_token()
    if not token:
        raise RuntimeError("Spotify not configured")
    resp = requests.get(
        f"https://api.spotify.com/v1/playlists/{playlist_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Spotify API returned {resp.status_code}")
    data = resp.json()
    return {"title": data["name"], "track_count": data.get("tracks", {}).get("total", 0)}


def fetch_full_playlist_info(platform, playlist_id):
    """Returns {title, track_count, duration_ms, tracks:[{title,artist,duration_ms,...}]}."""
    if platform == "apple":
        script = PROJECT_ROOT / "scripts" / "apple" / "playlist_full.py"
    else:
        script = PROJECT_ROOT / "scripts" / "harmoni" / "playlist_full.py"
    result = subprocess.run(
        [sys.executable, script, playlist_id],
        capture_output=True, text=True, timeout=60,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if "error" in data:
            raise RuntimeError(data["error"])
        data["platform"] = platform
        for t in data.get("tracks", []):
            t["platform"] = platform
        return data
    raise RuntimeError(result.stderr.strip() or "Failed to fetch playlist info")


def safe_playlist_name(name):
    return re.sub(r'[/\\:*?"<>|]', "", name).strip() or "Playlist"


def normalize_name(s):
    return re.sub(r'[^a-z0-9]+', '', (s or "").lower())


def primary_artist(artist):
    return re.split(r',|&| feat\.?| ft\.?', artist or "", flags=re.IGNORECASE)[0].strip()


def local_track_exists(folder, artist, title):
    if not os.path.isdir(folder):
        return False
    norm_title = normalize_name(title)
    norm_artist = normalize_name(primary_artist(artist))
    if not norm_title:
        return False
    for fname in os.listdir(folder):
        stem = os.path.splitext(fname)[0]
        norm_stem = normalize_name(stem)
        if norm_title in norm_stem and (not norm_artist or norm_artist in norm_stem):
            return True
    return False


def missing_tracks(folder, tracks):
    return [t for t in tracks if not local_track_exists(folder, t["artist"], t["title"])]


@app.route("/api/playlist/info")
def api_playlist_info():
    url = request.args.get("url", "").strip()
    platform, playlist_id = parse_playlist_url(url)
    if not platform:
        return jsonify({"error": "Not a valid Apple Music or Spotify playlist URL"}), 400
    try:
        if platform == "apple":
            info = get_apple_music_playlist_info(playlist_id)
        else:
            info = get_spotify_playlist_info(playlist_id)
        info["platform"] = platform
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def playlist_download_worker(download_id, platform, url, playlist_id, playlist_name):
    log_path = DOWNLOAD_DIR / f".dl_{download_id}.log"
    safe_name = safe_playlist_name(playlist_name)
    playlist_dir = DOWNLOAD_DIR / safe_name
    playlist_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = str(log_path)

        if platform == "apple":
            cmd = [GAMDL, url, "-o", str(playlist_dir), "--config-path", GAMDL_CONFIG]
        else:
            harmoni_script = PROJECT_ROOT / "scripts" / "harmoni" / "playlist_download.py"
            cmd = [sys.executable, str(harmoni_script), playlist_id, safe_name, str(DOWNLOAD_DIR)]
        downloads[download_id]["cmd"] = " ".join(cmd)
        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            downloads[download_id]["pid"] = proc.pid
            returncode = proc.wait(timeout=7200)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
            try:
                info = fetch_full_playlist_info(platform, playlist_id)
                playlist_store.add_playlist({
                    "id": playlist_id,
                    "platform": platform,
                    "title": info["title"],
                    "folder": str(playlist_dir),
                    "song_count": info["track_count"],
                    "duration_ms": info["duration_ms"],
                    "added_at": time.time(),
                    "updated_at": time.time(),
                })
            except Exception as e:
                downloads[download_id]["manager_error"] = str(e)
        else:
            _fail_on_returncode(download_id, returncode, log_path)
    except subprocess.TimeoutExpired:
        proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 2 hours"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)
    finally:
        _cleanup_log(log_path)


@app.route("/api/playlist/download", methods=["POST"])
def api_playlist_download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    url = data.get("url", "").strip()
    playlist_name = data.get("playlist_name", "Playlist")
    platform, playlist_id = parse_playlist_url(url)
    if not platform:
        return jsonify({"error": "Invalid playlist URL"}), 400

    download_id = str(uuid.uuid4())[:8]
    downloads[download_id] = {
        "status": "queued",
        "title": playlist_name,
        "platform": platform,
        "type": "playlist",
    }
    thread = threading.Thread(
        target=playlist_download_worker,
        args=(download_id, platform, url, playlist_id, playlist_name),
        daemon=True,
    )
    thread.start()
    return jsonify({"download_id": download_id, "status": "queued"})


@app.route("/api/playlists")
def api_playlists():
    return jsonify({"playlists": playlist_store.list_playlists()})


@app.route("/api/playlists/<platform>/<playlist_id>", methods=["DELETE"])
def api_playlist_delete(platform, playlist_id):
    removed = playlist_store.remove_playlist(platform, playlist_id)
    if not removed:
        return jsonify({"error": "Playlist not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/playlists/<platform>/<playlist_id>/view")
def api_playlist_view(platform, playlist_id):
    entry = playlist_store.get_playlist(platform, playlist_id)
    if not entry:
        return jsonify({"error": "Playlist not found in manager"}), 404
    try:
        info = fetch_full_playlist_info(platform, playlist_id)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def update_playlist_worker(download_id, platform, playlist_id):
    entry = playlist_store.get_playlist(platform, playlist_id)
    log_path = DOWNLOAD_DIR / f".dl_{download_id}.log"
    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = str(log_path)

        info = fetch_full_playlist_info(platform, playlist_id)
        old_folder = Path(entry["folder"])
        new_safe_name = safe_playlist_name(info["title"])
        new_folder = DOWNLOAD_DIR / new_safe_name

        folder = old_folder
        if new_folder != old_folder:
            if old_folder.is_dir() and not new_folder.exists():
                old_folder.rename(new_folder)
                folder = new_folder
            elif not old_folder.is_dir():
                new_folder.mkdir(parents=True, exist_ok=True)
                folder = new_folder
        folder.mkdir(parents=True, exist_ok=True)

        to_download = missing_tracks(str(folder), info["tracks"])

        playlist_store.update_playlist(platform, playlist_id, {
            "title": info["title"],
            "folder": str(folder),
            "song_count": info["track_count"],
            "duration_ms": info["duration_ms"],
            "updated_at": time.time(),
        })

        if not to_download:
            downloads[download_id]["status"] = "done"
            downloads[download_id]["downloaded_count"] = 0
            return

        safe_name = folder.name
        with open(log_path, "w") as log_file:
            if platform == "apple":
                cmd = [
                    GAMDL, *[t["url"] for t in to_download],
                    "-o", str(folder),
                    "--config-path", GAMDL_CONFIG,
                ]
                downloads[download_id]["cmd"] = " ".join(cmd)
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                downloads[download_id]["pid"] = proc.pid
                returncode = proc.wait(timeout=7200)
            else:
                harmoni_script = PROJECT_ROOT / "scripts" / "harmoni" / "tracks_download.py"
                cmd = [sys.executable, str(harmoni_script), safe_name, str(DOWNLOAD_DIR)]
                downloads[download_id]["cmd"] = " ".join(cmd)
                stdin_payload = json.dumps([
                    {"artist": t["artist"], "track": t["title"], "duration_ms": t.get("duration_ms", 0)}
                    for t in to_download
                ])
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=log_file, stderr=subprocess.STDOUT, text=True,
                )
                downloads[download_id]["pid"] = proc.pid
                proc.stdin.write(stdin_payload)
                proc.stdin.close()
                returncode = proc.wait(timeout=7200)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
            downloads[download_id]["downloaded_count"] = len(to_download)
        else:
            _fail_on_returncode(download_id, returncode, log_path)
    except subprocess.TimeoutExpired:
        proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 2 hours"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)
    finally:
        _cleanup_log(log_path)


@app.route("/api/playlists/<platform>/<playlist_id>/update", methods=["POST"])
def api_playlist_update(platform, playlist_id):
    entry = playlist_store.get_playlist(platform, playlist_id)
    if not entry:
        return jsonify({"error": "Playlist not found in manager"}), 404

    download_id = str(uuid.uuid4())[:8]
    downloads[download_id] = {
        "status": "queued",
        "title": entry["title"],
        "platform": platform,
        "type": "playlist_update",
    }
    thread = threading.Thread(
        target=update_playlist_worker,
        args=(download_id, platform, playlist_id),
        daemon=True,
    )
    thread.start()
    return jsonify({"download_id": download_id, "status": "queued"})


def download_worker(download_id, platform, title, artist, url, duration_ms=0):
    log_path = DOWNLOAD_DIR / f".dl_{download_id}.log"
    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = str(log_path)

        if platform == "apple":
            cmd = [GAMDL, url, "-o", str(DOWNLOAD_DIR), "--config-path", GAMDL_CONFIG]
        else:
            harmoni_script = PROJECT_ROOT / "scripts" / "harmoni" / "download.py"
            cmd = [sys.executable, str(harmoni_script), artist, title, str(DOWNLOAD_DIR), str(duration_ms)]
        downloads[download_id]["cmd"] = " ".join(cmd)

        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            downloads[download_id]["pid"] = proc.pid
            returncode = proc.wait(timeout=300)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
        else:
            _fail_on_returncode(download_id, returncode, str(log_path))
    except subprocess.TimeoutExpired:
        proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 5 minutes"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)
    finally:
        _cleanup_log(log_path)


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    platform = data.get("platform", "")
    title = data.get("title", "")
    artist = data.get("artist", "")
    url = data.get("url", "")
    duration_ms = data.get("duration_ms", 0)

    if not title or not artist:
        return jsonify({"error": "Missing title or artist"}), 400

    download_id = str(uuid.uuid4())[:8]
    downloads[download_id] = {
        "status": "queued",
        "title": title,
        "artist": artist,
        "platform": platform,
    }

    thread = threading.Thread(
        target=download_worker,
        args=(download_id, platform, title, artist, url, duration_ms),
        daemon=True,
    )
    thread.start()

    return jsonify({"download_id": download_id, "status": "queued"})


@app.route("/api/download/<download_id>")
def api_download_status(download_id):
    if download_id not in downloads:
        return jsonify({"error": "Not found"}), 404
    info = dict(downloads[download_id])
    if info.get("status") == "downloading":
        log_path = info.get("log", "")
        if log_path and os.path.exists(log_path):
            info["log_tail"] = _tail_log(log_path, 5)
    return jsonify(info)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
