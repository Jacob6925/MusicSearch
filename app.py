import json
import os
import re
import sys
import base64
import subprocess
import threading
import uuid
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

load_dotenv()

app = Flask(__name__)

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

spotify_token_cache = {"token": None}


def _tail_log(path, lines=20):
    try:
        with open(path) as f:
            return "".join(f.readlines()[-lines:])
    except Exception:
        return ""


DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Music", "MusicSearch")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

GAMDL = "/Library/Frameworks/Python.framework/Versions/3.11/bin/gamdl"

downloads = {}


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
    apple_script = os.path.join(os.path.dirname(__file__), "apple_music_search.py")
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
    token = get_spotify_token()
    if not token:
        return []
    resp = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "type": "track", "limit": limit},
        timeout=10,
    )
    if resp.status_code == 401:
        spotify_token_cache["token"] = None
        token = get_spotify_token()
        if not token:
            return []
        resp = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "track", "limit": limit},
            timeout=10,
        )
    if resp.status_code != 200:
        return []
    results = []
    body = resp.json()
    items = body.get("tracks", {}).get("items", [])
    for track in items:
        images = track.get("album", {}).get("images", [])
        artwork = images[0]["url"] if images else ""
        results.append({
            "platform": "spotify",
            "title": track.get("name", "Unknown"),
            "artist": ", ".join(a["name"] for a in track.get("artists", [])),
            "album": track.get("album", {}).get("name", ""),
            "artwork": artwork,
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
    am = re.search(r'https://music\.apple\.com/[^/]+/playlist/[^/]+/(pl\.[^/?#\s]+)', url)
    if am:
        return "apple", am.group(1)
    sp = re.search(r'https://open\.spotify\.com/playlist/([A-Za-z0-9]+)', url)
    if sp:
        return "spotify", sp.group(1)
    return None, None


def get_apple_music_playlist_info(playlist_id):
    script = os.path.join(os.path.dirname(__file__), "apple_music_playlist_info.py")
    result = subprocess.run(
        [sys.executable, script, playlist_id],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0 and result.stdout.strip():
        return json.loads(result.stdout)
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
    log_path = os.path.join(DOWNLOAD_DIR, f".dl_{download_id}.log")
    safe_name = re.sub(r'[/\\:*?"<>|]', "", playlist_name).strip() or "Playlist"
    playlist_dir = os.path.join(DOWNLOAD_DIR, safe_name)
    os.makedirs(playlist_dir, exist_ok=True)

    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = log_path

        if platform == "apple":
            cmd = [
                GAMDL, url,
                "-o", playlist_dir,
                "--config-path", os.path.expanduser("~/.gamdl/config.ini"),
            ]
            downloads[download_id]["cmd"] = " ".join(cmd)
            with open(log_path, "w") as log_file:
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                downloads[download_id]["pid"] = proc.pid
                returncode = proc.wait(timeout=7200)
        else:
            harmoni_script = os.path.join(os.path.dirname(__file__), "harmoni_playlist_download.py")
            cmd = [sys.executable, harmoni_script, playlist_id, safe_name, DOWNLOAD_DIR]
            downloads[download_id]["cmd"] = " ".join(cmd)
            with open(log_path, "w") as log_file:
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                downloads[download_id]["pid"] = proc.pid
                returncode = proc.wait(timeout=7200)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
        else:
            tail = _tail_log(log_path, 20)
            downloads[download_id]["status"] = "error"
            downloads[download_id]["error"] = f"Exit code {returncode}. Last output:\n{tail}"
    except subprocess.TimeoutExpired:
        proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 2 hours"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)
    finally:
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
        except Exception:
            pass


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




def download_worker(download_id, platform, title, artist, url):
    log_path = os.path.join(DOWNLOAD_DIR, f".dl_{download_id}.log")
    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = log_path

        if platform == "apple":
            cmd = [
                GAMDL, url,
                "-o", DOWNLOAD_DIR,
                "--config-path", os.path.expanduser("~/.gamdl/config.ini"),
            ]
        else:
            harmoni_script = os.path.join(os.path.dirname(__file__), "harmoni_download.py")
            cmd = [sys.executable, harmoni_script, artist, title, DOWNLOAD_DIR]

        downloads[download_id]["cmd"] = " ".join(cmd)

        with open(log_path, "w") as log_file:
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            downloads[download_id]["pid"] = proc.pid
            returncode = proc.wait(timeout=300)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
        else:
            tail = _tail_log(log_path, 20)
            downloads[download_id]["status"] = "error"
            downloads[download_id]["error"] = f"Exit code {returncode}. Last output:\n{tail}"
    except subprocess.TimeoutExpired:
        proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 5 minutes"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = str(e)
    finally:
        try:
            if os.path.exists(log_path):
                os.remove(log_path)
        except Exception:
            pass


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    platform = data.get("platform", "")
    title = data.get("title", "")
    artist = data.get("artist", "")
    url = data.get("url", "")

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
        args=(download_id, platform, title, artist, url),
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
