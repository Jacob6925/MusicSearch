import os
import sys

import appenv

# Must run before any third-party import: if this process wasn't started with
# the venv's python, re-exec with it so those imports (and every child
# process this app launches) use the venv where this project's packages live.
appenv.reexec_in_venv()

import json
import re
import time
import base64
import shutil
import subprocess
import threading
import unicodedata
import uuid
import webbrowser
from pathlib import Path
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

import folder_picker
import pathsafe
import playlist_store

PROJECT_ROOT = appenv.PROJECT_ROOT
GITHUB_REPO = "Jacob6925/MusicSearch"

# Must run before anything launches a child process (UTF-8, PATH, ffmpeg).
appenv.prepare_environment()

# utf-8-sig so a .env saved by Windows Notepad (which may add a BOM) still works.
load_dotenv(PROJECT_ROOT / ".env", encoding="utf-8-sig")

app = Flask(__name__)

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
# Harmoni's helper scripts read the Client ID from the environment too.
if SPOTIFY_CLIENT_ID:
    os.environ["SPOTIFY_CLIENT_ID"] = SPOTIFY_CLIENT_ID

spotify_token_cache = {"token": None}

# The default download folder is chosen by the user on first run and remembered in
# settings.json (next to this file). Until it is set, downloads are refused.
SETTINGS_PATH = PROJECT_ROOT / "settings.json"
_settings_lock = threading.Lock()


def get_download_dir():
    """The saved default download folder as a Path, or None if not chosen yet
    (or if the saved folder no longer exists)."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        folder = Path(str(data.get("download_dir") or "")).expanduser()
    except (OSError, ValueError):
        return None
    return folder if str(folder) not in ("", ".") and folder.is_dir() else None


def set_download_dir(folder):
    with _settings_lock:
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data["download_dir"] = str(folder)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)


def require_download_dir():
    folder = get_download_dir()
    if folder is None:
        raise ValueError("Choose a save folder first (use the Choose… button at the top).")
    return folder


def _log_path(download_id):
    _TEMP_DIR.mkdir(exist_ok=True)
    return _TEMP_DIR / f".dl_{download_id}.log"

# Run gamdl through this same Python so it works inside the venv on any OS.
GAMDL_CMD = [sys.executable, "-m", "gamdl"]

_GAMDL_CONFIG_TEMPLATE = PROJECT_ROOT / "gamdl" / "config.ini"
_COOKIES_PATH = PROJECT_ROOT / "gamdl" / "cookies.txt"
_GAMDL_CONFIG_RESOLVED = PROJECT_ROOT / "gamdl" / ".config_resolved.ini"
_TEMP_DIR = PROJECT_ROOT / ".tmp"


def _set_ini_value(text: str, key: str, value) -> str:
    # A function (not a string) as the replacement: a Windows path such as
    # C:\Users\me contains backslashes that re.sub would treat as escapes.
    return re.sub(
        rf"^{key}\s*=.*$",
        lambda _m: f"{key} = {value}",
        text,
        flags=re.MULTILINE,
    )


def _resolve_gamdl_config() -> str:
    """Write config.ini with absolute cookies / ffmpeg / temp paths substituted in."""
    _TEMP_DIR.mkdir(exist_ok=True)
    text = _GAMDL_CONFIG_TEMPLATE.read_text(encoding="utf-8")
    text = _set_ini_value(text, "cookies_path", _COOKIES_PATH)
    text = _set_ini_value(text, "temp_path", _TEMP_DIR)
    text = _set_ini_value(text, "ffmpeg_path", shutil.which("ffmpeg") or "ffmpeg")
    _GAMDL_CONFIG_RESOLVED.write_text(text, encoding="utf-8")
    return str(_GAMDL_CONFIG_RESOLVED)


GAMDL_CONFIG = _resolve_gamdl_config()


def apple_music_is_configured() -> bool:
    """Whether gamdl is installed and has a usable Apple Music cookie/config setup."""
    import importlib.util
    gamdl_ok = importlib.util.find_spec("gamdl") is not None
    cookies_ok = _COOKIES_PATH.exists() and _COOKIES_PATH.stat().st_size > 0
    config_ok = _GAMDL_CONFIG_TEMPLATE.exists() and _GAMDL_CONFIG_TEMPLATE.stat().st_size > 0
    return gamdl_ok and cookies_ok and config_ok


downloads = {}


def _tail_log(path, lines=20):
    """Last `lines` lines of a log file. Server-side debugging only — never sent to the UI."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except Exception:
        return ""


def _server_log(text):
    """Write raw diagnostic output to the Flask terminal (not to the browser)."""
    print(f"[MusicSearch] {text}", file=sys.stderr, flush=True)


def _clean_message(msg, fallback):
    """Return `msg` if it is a short, single-line, human-readable message.
    Otherwise (tracebacks, stderr dumps, multi-line output) log the raw text to
    the server terminal and return `fallback` for the UI."""
    msg = (str(msg) if msg is not None else "").strip()
    if msg and "\n" not in msg and len(msg) <= 200 and "Traceback" not in msg:
        return msg
    if msg:
        _server_log(f"{fallback} Details:\n{msg}")
    return fallback


def _count_new_audio(dest_dir, since):
    """How many audio files under dest_dir were written at/after `since` (epoch secs)."""
    count = 0
    try:
        for root, _dirs, files in os.walk(dest_dir):
            for fname in files:
                if os.path.splitext(fname)[1].lower() not in AUDIO_EXTENSIONS:
                    continue
                try:
                    if os.path.getmtime(os.path.join(root, fname)) >= since:
                        count += 1
                except OSError:
                    pass
    except Exception:
        pass
    return count


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
        return "A required Python module is missing. Run the setup script again to reinstall it."
    if "filenotfounderror" in low and "config.json" in low:
        return "Spotify helper is not installed. Run the setup script again."
    if "429" in log_text or "rate limit" in low or "too many requests" in low:
        return "429 Too Many Requests: Spotify rate limit reached. Wait a moment and try again."
    if "503" in log_text and "spotify" in low:
        return "503 Service Unavailable: Spotify is temporarily down. Try again in a few minutes."
    if "502" in log_text and "spotify" in low:
        return "502 Bad Gateway: Spotify server error. Try again in a few minutes."
    if "500" in log_text and "spotify" in low:
        return "500 Internal Server Error: Spotify server error. Try again in a few minutes."
    if "failed to download" in low or "error details" in low:
        return "One or more tracks couldn't be downloaded from YouTube. Try again in a moment."
    if "error downloading" in low:
        return "One or more tracks couldn't be downloaded from Apple Music. Check your Apple Music cookies and try again."

    return None


def _fail_on_returncode(download_id, returncode, log_path):
    tail = _tail_log(log_path, 40)
    msg = _parse_download_error(tail)
    if not msg:
        # Raw output stays in the server terminal; the UI only gets a plain message.
        _server_log(f"Download {download_id} exited with code {returncode}. Last output:\n{tail}")
        msg = "Download failed. Check the server log for details."
    downloads[download_id]["status"] = "error"
    downloads[download_id]["error"] = _clean_message(msg, "Download failed. Check the server log for details.")


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
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
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
            _server_log(f"Apple Music search failed: {e}")
            errors.append("Apple Music search is unavailable right now.")

    if platform in ("spotify", "both"):
        if not SPOTIFY_CLIENT_ID:
            errors.append("Spotify not configured — add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to the .env file and restart")
        else:
            try:
                results.extend(search_spotify(query))
            except Exception as e:
                _server_log(f"Spotify search failed: {e}")
                errors.append("Spotify search is unavailable right now.")

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
        "apple_music": apple_music_is_configured(),
        "spotify": bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET),
        "spotify_login": appenv.spotify_logged_in(),
        "default_save_dir": str(get_download_dir() or ""),
        "home_dir": str(Path.home()),
    })


def _local_commit_sha():
    """The commit this working copy is checked out at, or None if it can't be
    determined (git missing, not a git checkout, etc)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5,
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


@app.route("/api/version")
def api_version():
    local_sha = _local_commit_sha()
    if not local_sha:
        return jsonify({"update_available": False})

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/commits/main",
            headers={"Accept": "application/vnd.github+json"},
            timeout=5,
        )
        resp.raise_for_status()
        remote_sha = resp.json().get("sha", "")
    except Exception as e:
        _server_log(f"Update check failed: {e}")
        return jsonify({"update_available": False})

    return jsonify({
        "update_available": bool(remote_sha) and remote_sha != local_sha,
        "compare_url": f"https://github.com/{GITHUB_REPO}/compare/{local_sha}...main",
    })


_spotify_login = {"status": "idle", "error": ""}


def _spotify_login_worker():
    script = PROJECT_ROOT / "scripts" / "harmoni" / "login.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=330,
        )
        if result.returncode == 0:
            _spotify_login.update(status="done", error="")
            return
        lines = [l.strip() for l in (result.stdout + result.stderr).splitlines() if l.strip().startswith("Error:")]
        if not lines:
            _server_log(f"Spotify login failed:\n{result.stdout}\n{result.stderr}")
        _spotify_login.update(status="error", error=(lines[-1][6:].strip() if lines else "Spotify sign-in failed."))
    except Exception as e:
        _server_log(f"Spotify login failed: {e}")
        _spotify_login.update(status="error", error="Spotify sign-in failed.")


@app.route("/api/spotify/login", methods=["GET", "POST"])
def api_spotify_login():
    """POST starts the one-time Spotify sign-in (opens a browser tab on this
    machine); GET reports its state: idle | waiting | done | error."""
    if request.method == "POST":
        if not SPOTIFY_CLIENT_ID:
            return jsonify({"error": "Add SPOTIFY_CLIENT_ID to the .env file and restart the app first."}), 400
        if _spotify_login["status"] != "waiting":
            _spotify_login.update(status="waiting", error="")
            threading.Thread(target=_spotify_login_worker, daemon=True).start()
    return jsonify({**_spotify_login, "logged_in": appenv.spotify_logged_in()})


def resolve_save_dir(raw):
    """Validate a client-chosen destination folder for single songs. Empty/None
    means the saved default folder. Returns a Path; raises ValueError with a
    UI-safe message if it isn't an absolute, existing, writable directory."""
    if not raw or not str(raw).strip():
        return require_download_dir()
    path = Path(str(raw).strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("Enter a full folder path.")
    if not path.is_dir():
        raise ValueError("That folder doesn't exist.")
    if not os.access(path, os.W_OK):
        raise ValueError("That folder isn't writable.")
    return path


_folder_dialog_lock = threading.Lock()


@app.route("/api/choose-folder", methods=["POST"])
def api_choose_folder():
    """Opens the OS-native folder chooser on this machine and returns the pick."""
    data = request.get_json(silent=True) or {}
    try:
        start = resolve_save_dir(data.get("start"))
    except ValueError:
        start = get_download_dir() or Path.home()
    if not _folder_dialog_lock.acquire(blocking=False):
        return jsonify({"error": "A folder dialog is already open."}), 409
    try:
        chosen = folder_picker.choose_folder(start)
    except folder_picker.FolderPickerError as e:
        return jsonify({"error": str(e)}), 500
    finally:
        _folder_dialog_lock.release()
    if chosen is None:
        return jsonify({"cancelled": True})
    try:
        return jsonify({"path": str(resolve_save_dir(chosen))})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/validate-folder", methods=["POST"])
def api_validate_folder():
    """Checks a typed folder path (fallback when no native dialog is available)."""
    data = request.get_json(silent=True) or {}
    if not str(data.get("path") or "").strip():
        return jsonify({"error": "Enter a folder path."}), 400
    try:
        return jsonify({"path": str(resolve_save_dir(data.get("path")))})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/default-dir", methods=["POST"])
def api_set_default_dir():
    """Save the folder all downloads go to (chosen on first run, changeable later)."""
    data = request.get_json(silent=True) or {}
    if not str(data.get("path") or "").strip():
        return jsonify({"error": "Enter a folder path."}), 400
    try:
        folder = resolve_save_dir(data["path"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    set_download_dir(folder)
    return jsonify({"path": str(folder)})


def parse_playlist_url(url):
    """Returns (platform, playlist_id) or (None, None)."""
    url = url.strip()
    am = re.search(r'music\.apple\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?playlist/(?:[^/?#\s]+/)?(pl\.[^/?#\s]+)', url, re.IGNORECASE)
    if am:
        return "apple", am.group(1)
    sp = re.search(r'open\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/([A-Za-z0-9]+)', url, re.IGNORECASE)
    if sp:
        return "spotify", sp.group(1)
    yt = re.search(r'(?:music|www|m)\.youtube\.com/(?:playlist|watch)\?[^\s#]*?\blist=([A-Za-z0-9_-]+)', url, re.IGNORECASE)
    if yt:
        return "youtube", yt.group(1)
    return None, None


def parse_song_url(url):
    """Returns (platform, song_id) for an individual-song link, or (None, None)."""
    url = url.strip()
    am = re.search(r'music\.apple\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?song/(?:[^/?#\s]+/)?(\d+)', url, re.IGNORECASE)
    if not am:
        # An album link only identifies a single song when it carries ?i=<songId>.
        am = re.search(r'music\.apple\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?album/[^?#\s]*\?(?:[^#\s]*&)?i=(\d+)', url, re.IGNORECASE)
    if am:
        return "apple", am.group(1)
    sp = re.search(r'open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([A-Za-z0-9]+)', url, re.IGNORECASE)
    if sp:
        return "spotify", sp.group(1)
    yt = re.search(r'(?:music|www|m)\.youtube\.com/watch\?[^\s#]*?\bv=([A-Za-z0-9_-]{11})', url, re.IGNORECASE)
    if not yt:
        yt = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})', url, re.IGNORECASE)
    if yt:
        return "youtube", yt.group(1)
    return None, None


def get_apple_music_playlist_info(playlist_id):
    script = PROJECT_ROOT / "scripts" / "apple" / "playlist_info.py"
    result = subprocess.run(
        [sys.executable, script, playlist_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    if result.stderr.strip():
        _server_log(f"Apple Music playlist_info stderr:\n{result.stderr.strip()}")
    raise RuntimeError("Failed to fetch Apple Music playlist info")


def get_youtube_playlist_info(playlist_id):
    script = PROJECT_ROOT / "scripts" / "youtube" / "playlist_info.py"
    result = subprocess.run(
        [sys.executable, script, playlist_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    if result.stderr.strip():
        _server_log(f"YouTube playlist_info stderr:\n{result.stderr.strip()}")
    raise RuntimeError("Failed to fetch YouTube Music playlist info")


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
    elif platform == "youtube":
        script = PROJECT_ROOT / "scripts" / "youtube" / "playlist_full.py"
    else:
        script = PROJECT_ROOT / "scripts" / "harmoni" / "playlist_full.py"
    result = subprocess.run(
        [sys.executable, script, playlist_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if "error" in data:
            raise RuntimeError(data["error"])
        data["platform"] = platform
        for t in data.get("tracks", []):
            t["platform"] = platform
        return data
    if result.stderr.strip():
        _server_log(f"playlist_full stderr:\n{result.stderr.strip()}")
    raise RuntimeError("Failed to fetch playlist info")


def safe_playlist_name(name):
    return pathsafe.safe_name(name, fallback="Playlist")


def normalize_name(s):
    # Strip accents regardless of whether the source string is precomposed (NFC,
    # typical of API/JSON text) or decomposed (NFD, what macOS returns for filenames) —
    # otherwise e.g. "Bailão" from an API and "Bailão" read back via os.listdir()
    # normalize to different strings and never match.
    s = unicodedata.normalize('NFKD', (s or "").lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', s)


def normalize_words(s):
    s = unicodedata.normalize('NFKD', (s or "").lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return [w for w in re.split(r'[^a-z0-9]+', s) if w]


# Connector words in a title's "(feat. X)"/"(with X)" collaborator annotation —
# the collaborator's name is usually folded into the filename via the artist
# list, but these linking words themselves are not, e.g. title "One Kiss (with
# Dua Lipa)" downloaded as "Calvin Harris & Dua Lipa - One Kiss.m4a".
_TITLE_FILLER_WORDS = {"feat", "featuring", "ft", "with"}


def title_words_for_matching(title):
    return [w for w in normalize_words(title) if w not in _TITLE_FILLER_WORDS]


def primary_artist(artist):
    # Drop parenthetical asides (e.g. "Olly Alexander (Years & Years)") before
    # splitting on separators, so they don't get chopped mid-name by the "&"/","
    # split below.
    artist = re.sub(r'\([^)]*\)', '', artist or "")
    return re.split(r',|&| feat\.?| ft\.?', artist, flags=re.IGNORECASE)[0].strip()


def _title_artist_match(title_words, artist_words, stem_words):
    # Word-based (not contiguous-substring) matching: a real filename often
    # inserts "(feat. X)" or "[Remix]" between words that are adjacent in the
    # playlist's title, e.g. "In My Mind (feat. Georgi Kay) [Axwell Radio Edit]"
    # vs. the title "In My Mind - Axwell Radio Edit".
    return bool(title_words) and all(w in stem_words for w in title_words) and all(w in stem_words for w in artist_words)


def local_track_exists(folder, artist, title):
    if not os.path.isdir(folder):
        return False
    title_words = title_words_for_matching(title)
    artist_words = normalize_words(primary_artist(artist))
    if not title_words:
        return False
    for fname in os.listdir(folder):
        stem_words = set(normalize_words(os.path.splitext(fname)[0]))
        if _title_artist_match(title_words, artist_words, stem_words):
            return True
    return False


def missing_tracks(folder, tracks):
    return [t for t in tracks if not local_track_exists(folder, t["artist"], t["title"])]


AUDIO_EXTENSIONS = {".m4a", ".mp3", ".flac", ".wav", ".aac", ".ogg", ".opus", ".wma"}


def local_only_files(folder, tracks):
    """Local audio files in `folder` that don't match any track in `tracks`."""
    if not os.path.isdir(folder):
        return []
    track_word_pairs = [
        (title_words_for_matching(t["title"]), normalize_words(primary_artist(t["artist"])))
        for t in tracks
    ]
    result = []
    for fname in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(fname)
        if ext.lower() not in AUDIO_EXTENSIONS:
            continue
        stem_words = set(normalize_words(stem))
        if any(_title_artist_match(tw, aw, stem_words) for tw, aw in track_word_pairs):
            continue
        result.append(fname)
    return result


def parse_local_filename(fname):
    """Best-effort split of a "Artist - Title.ext" filename for display."""
    stem = os.path.splitext(fname)[0]
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip(), title.strip()
    return "", stem.strip()


@app.route("/api/playlist/info")
def api_playlist_info():
    url = request.args.get("url", "").strip()
    platform, playlist_id = parse_playlist_url(url)
    if not platform:
        return jsonify({"error": "Not a valid Apple Music, Spotify, or YouTube Music playlist URL"}), 400
    try:
        if platform == "apple":
            info = get_apple_music_playlist_info(playlist_id)
        elif platform == "youtube":
            info = get_youtube_playlist_info(playlist_id)
        else:
            info = get_spotify_playlist_info(playlist_id)
        info["platform"] = platform
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": _clean_message(e, "Couldn't load that playlist. Check the link and try again.")}), 500


def fetch_song_info(platform, song_id):
    """Returns one track dict ({title, artist, album, url, duration_ms, ...}) in the
    same shape as the entries of fetch_full_playlist_info()["tracks"]."""
    if platform == "apple":
        script = PROJECT_ROOT / "scripts" / "apple" / "song_full.py"
    elif platform == "youtube":
        script = PROJECT_ROOT / "scripts" / "youtube" / "song_full.py"
    else:
        script = PROJECT_ROOT / "scripts" / "harmoni" / "song_full.py"
    result = subprocess.run(
        [sys.executable, script, song_id],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    if result.stdout.strip():
        data = json.loads(result.stdout)
        if "error" in data:
            raise RuntimeError(data["error"])
        data["platform"] = platform
        return data
    if result.stderr.strip():
        _server_log(f"song_full stderr:\n{result.stderr.strip()}")
    raise RuntimeError("Failed to fetch song info")


@app.route("/api/song/info")
def api_song_info():
    url = request.args.get("url", "").strip()
    platform, song_id = parse_song_url(url)
    if not platform:
        return jsonify({"error": "Not a valid Apple Music, Spotify, or YouTube song URL"}), 400
    try:
        return jsonify(fetch_song_info(platform, song_id))
    except Exception as e:
        return jsonify({"error": _clean_message(e, "Couldn't load that song. Check the link and try again.")}), 500


def _harmoni_dest_args(folder):
    """(subfolder name, root dir) as tracks_download.py expects them. An empty
    name makes it download straight into the given folder, which works for any
    absolute path (a playlist folder or a user-chosen song folder)."""
    return "", str(folder)


def download_spotify_tracks(download_id, tracks, folder, log_path):
    """Download Spotify tracks preferring Apple Music (exact ISRC match, then
    fuzzy title/artist/duration match) and falling back to YouTube via harmoni
    for any track with no confident Apple Music match. Appends progress to
    log_path and returns a combined returncode (0 = both stages succeeded)."""
    matched, unmatched = [], list(tracks)

    if tracks and apple_music_is_configured():
        match_script = PROJECT_ROOT / "scripts" / "apple" / "match_tracks.py"
        try:
            proc = subprocess.run(
                [sys.executable, str(match_script)],
                input=json.dumps(tracks), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
            )
            with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
                log_file.write("--- Matching tracks against Apple Music ---\n")
                if proc.stderr:
                    log_file.write(proc.stderr)
            result = json.loads(proc.stdout)
            matched = result.get("matched", [])
            unmatched = result.get("unmatched", [])
        except Exception as e:
            with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
                log_file.write(f"Apple Music matching failed, falling back to YouTube for all tracks: {e}\n")
            matched, unmatched = [], list(tracks)

    returncode = 0

    if matched:
        cmd = [*GAMDL_CMD, *[t["apple_url"] for t in matched], "-o", str(folder), "--config-path", GAMDL_CONFIG]
        downloads[download_id]["cmd"] = " ".join(cmd)
        with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
            log_file.write(f"\n--- Downloading {len(matched)} track(s) from Apple Music ---\n")
            log_file.flush()
            proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            downloads[download_id]["pid"] = proc.pid
            try:
                rc = proc.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise
            if rc != 0:
                returncode = rc

    if unmatched:
        harmoni_script = PROJECT_ROOT / "scripts" / "harmoni" / "tracks_download.py"
        cmd = [sys.executable, str(harmoni_script), *_harmoni_dest_args(folder)]
        downloads[download_id]["cmd"] = " ".join(cmd)
        stdin_payload = json.dumps([
            {"artist": t["artist"], "track": t["title"], "duration_ms": t.get("duration_ms", 0)}
            for t in unmatched
        ])
        with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
            log_file.write(f"\n--- Downloading {len(unmatched)} track(s) from YouTube ---\n")
            log_file.flush()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log_file, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
            downloads[download_id]["pid"] = proc.pid
            proc.stdin.write(stdin_payload)
            proc.stdin.close()
            try:
                rc = proc.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise
            if rc != 0:
                returncode = rc

    return returncode


def download_youtube_tracks(download_id, tracks, folder, log_path):
    """Download tracks whose YouTube video is already known via the shared
    harmoni/yt-dlp path (metadata embedding included). Returns the returncode."""
    harmoni_script = PROJECT_ROOT / "scripts" / "harmoni" / "tracks_download.py"
    cmd = [sys.executable, str(harmoni_script), *_harmoni_dest_args(folder)]
    downloads[download_id]["cmd"] = " ".join(cmd)
    payload = json.dumps([
        {"artist": t["artist"], "track": t["title"], "duration_ms": t.get("duration_ms", 0),
         "video_url": t["url"], "album": t.get("album", "")}
        for t in tracks
    ])
    with open(log_path, "a", encoding="utf-8", errors="replace") as log_file:
        log_file.write(f"--- Downloading {len(tracks)} track(s) from YouTube Music ---\n")
        log_file.flush()
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log_file, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        downloads[download_id]["pid"] = proc.pid
        proc.stdin.write(payload)
        proc.stdin.close()
        try:
            return proc.wait(timeout=7200)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise


def playlist_download_worker(download_id, platform, url, playlist_id, playlist_name, base_dir, track_count=None):
    log_path = _log_path(download_id)
    safe_name = safe_playlist_name(playlist_name)
    playlist_dir = Path(base_dir) / safe_name
    playlist_dir.mkdir(parents=True, exist_ok=True)
    info = None
    proc = None

    try:
        downloads[download_id]["log"] = str(log_path)
        # Progress is derived from files appearing on disk, not from parsing the log.
        downloads[download_id]["dest_dir"] = str(playlist_dir)
        downloads[download_id]["total"] = track_count
        downloads[download_id]["started_at"] = time.time()
        downloads[download_id]["status"] = "downloading"

        if platform == "apple":
            cmd = [*GAMDL_CMD, url, "-o", str(playlist_dir), "--config-path", GAMDL_CONFIG]
            downloads[download_id]["cmd"] = " ".join(cmd)
            with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                downloads[download_id]["pid"] = proc.pid
                returncode = proc.wait(timeout=7200)
        else:
            info = fetch_full_playlist_info(platform, playlist_id)
            downloads[download_id]["total"] = len(info["tracks"])
            open(log_path, "w").close()
            if platform == "youtube":
                returncode = download_youtube_tracks(download_id, info["tracks"], playlist_dir, log_path)
            else:
                returncode = download_spotify_tracks(download_id, info["tracks"], playlist_dir, log_path)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
            try:
                if info is None:
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
        if proc is not None:
            proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 2 hours"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = _clean_message(e, "Download failed. Check the server log for details.")
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

    try:
        base_dir = resolve_save_dir(data.get("save_dir"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    download_id = str(uuid.uuid4())[:8]
    downloads[download_id] = {
        "status": "queued",
        "title": playlist_name,
        "platform": platform,
        "type": "playlist",
    }
    try:
        track_count = int(data.get("track_count") or 0) or None
    except (TypeError, ValueError):
        track_count = None
    thread = threading.Thread(
        target=playlist_download_worker,
        args=(download_id, platform, url, playlist_id, playlist_name, base_dir, track_count),
        daemon=True,
    )
    thread.start()
    return jsonify({"download_id": download_id, "status": "queued"})


def song_download_worker(download_id, platform, song_id, dest_dir):
    """Download one song by link, through the same per-track paths a playlist's
    tracks take (Apple -> gamdl; Spotify -> Apple Music match with YouTube
    fallback; YouTube -> yt-dlp on the known video), straight into dest_dir."""
    log_path = _log_path(download_id)
    proc = None
    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = str(log_path)

        track = fetch_song_info(platform, song_id)
        downloads[download_id]["title"] = track["title"]
        downloads[download_id]["artist"] = track["artist"]

        if platform == "apple":
            cmd = [*GAMDL_CMD, track["url"], "-o", str(dest_dir), "--config-path", GAMDL_CONFIG]
            downloads[download_id]["cmd"] = " ".join(cmd)
            with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                downloads[download_id]["pid"] = proc.pid
                returncode = proc.wait(timeout=600)
        else:
            open(log_path, "w").close()
            if platform == "youtube":
                returncode = download_youtube_tracks(download_id, [track], dest_dir, log_path)
            else:
                returncode = download_spotify_tracks(download_id, [track], dest_dir, log_path)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
        else:
            _fail_on_returncode(download_id, returncode, log_path)
    except subprocess.TimeoutExpired:
        if proc is not None:
            proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = _clean_message(e, "Download failed. Check the server log for details.")
    finally:
        _cleanup_log(log_path)


@app.route("/api/song/download", methods=["POST"])
def api_song_download():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    url = data.get("url", "").strip()
    platform, song_id = parse_song_url(url)
    if not platform:
        return jsonify({"error": "Invalid song URL"}), 400
    try:
        dest_dir = resolve_save_dir(data.get("save_dir"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    download_id = str(uuid.uuid4())[:8]
    downloads[download_id] = {
        "status": "queued",
        "title": "Song",
        "platform": platform,
        "type": "song",
    }
    thread = threading.Thread(
        target=song_download_worker,
        args=(download_id, platform, song_id, dest_dir),
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
        folder = entry.get("folder", "")
        for t in info["tracks"]:
            t["local"] = local_track_exists(folder, t["artist"], t["title"])
        info["local_only"] = []
        for fname in local_only_files(folder, info["tracks"]):
            artist, title = parse_local_filename(fname)
            info["local_only"].append({"artist": artist, "title": title, "filename": fname})
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": _clean_message(e, "Couldn't load that playlist right now. Try again.")}), 500


def update_playlist_worker(download_id, platform, playlist_id):
    entry = playlist_store.get_playlist(platform, playlist_id)
    log_path = _log_path(download_id)
    proc = None
    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = str(log_path)

        info = fetch_full_playlist_info(platform, playlist_id)
        old_folder = Path(entry["folder"])
        new_safe_name = safe_playlist_name(info["title"])
        # Rename within the folder it already lives in, so changing the default folder
        # later doesn't drag old playlists along.
        new_folder = old_folder.parent / new_safe_name

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

        downloads[download_id]["dest_dir"] = str(folder)
        downloads[download_id]["total"] = len(to_download)
        downloads[download_id]["started_at"] = time.time()

        if platform == "apple":
            cmd = [
                *GAMDL_CMD, *[t["url"] for t in to_download],
                "-o", str(folder),
                "--config-path", GAMDL_CONFIG,
            ]
            downloads[download_id]["cmd"] = " ".join(cmd)
            with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
                proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
                downloads[download_id]["pid"] = proc.pid
                returncode = proc.wait(timeout=7200)
        else:
            open(log_path, "w").close()
            if platform == "youtube":
                returncode = download_youtube_tracks(download_id, to_download, folder, log_path)
            else:
                returncode = download_spotify_tracks(download_id, to_download, folder, log_path)

        if returncode == 0:
            downloads[download_id]["status"] = "done"
            # Report tracks actually confirmed on disk, not just attempted —
            # a per-track downloader can silently fail on one track while still
            # exiting 0 overall.
            still_missing = missing_tracks(str(folder), to_download)
            downloads[download_id]["downloaded_count"] = len(to_download) - len(still_missing)
        else:
            _fail_on_returncode(download_id, returncode, log_path)
    except subprocess.TimeoutExpired:
        if proc is not None:
            proc.kill()
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = "Timed out after 2 hours"
    except Exception as e:
        downloads[download_id]["status"] = "error"
        downloads[download_id]["error"] = _clean_message(e, "Update failed. Check the server log for details.")
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


def download_worker(download_id, platform, title, artist, url, duration_ms, dest_dir):
    log_path = _log_path(download_id)
    try:
        downloads[download_id]["status"] = "downloading"
        downloads[download_id]["log"] = str(log_path)

        if platform == "apple":
            cmd = [*GAMDL_CMD, url, "-o", str(dest_dir), "--config-path", GAMDL_CONFIG]
        else:
            harmoni_script = PROJECT_ROOT / "scripts" / "harmoni" / "download.py"
            cmd = [sys.executable, str(harmoni_script), artist, title, str(dest_dir), str(duration_ms)]
            if platform == "youtube" and url:
                cmd.append(url)
        downloads[download_id]["cmd"] = " ".join(cmd)

        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
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
        downloads[download_id]["error"] = _clean_message(e, "Download failed. Check the server log for details.")
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
    try:
        dest_dir = resolve_save_dir(data.get("save_dir"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    download_id = str(uuid.uuid4())[:8]
    downloads[download_id] = {
        "status": "queued",
        "title": title,
        "artist": artist,
        "platform": platform,
    }

    thread = threading.Thread(
        target=download_worker,
        args=(download_id, platform, title, artist, url, duration_ms, dest_dir),
        daemon=True,
    )
    thread.start()

    return jsonify({"download_id": download_id, "status": "queued"})


@app.route("/api/download/<download_id>")
def api_download_status(download_id):
    if download_id not in downloads:
        return jsonify({"error": "Not found"}), 404
    info = dict(downloads[download_id])
    # Whitelist: internals (cmd, log path, pid, raw log output) stay on the server.
    out = {k: info[k] for k in ("status", "title", "artist", "platform", "type", "error", "downloaded_count") if k in info}
    total = info.get("total")
    if info.get("status") == "downloading" and total and info.get("dest_dir") and info.get("started_at"):
        out["progress"] = {
            "done": min(_count_new_audio(info["dest_dir"], info["started_at"]), total),
            "total": total,
        }
    return jsonify(out)


def main():
    port = int(os.environ.get("PORT", "5050"))
    url = f"http://127.0.0.1:{port}/"
    print(f"\nMusicSearch is running at {url}\nPress Ctrl+C in this window to stop it.\n", flush=True)
    if os.environ.get("MUSICSEARCH_NO_BROWSER") != "1":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        # Debug mode serves interactive tracebacks to the browser; opt in explicitly.
        app.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
    except OSError as e:
        print(f"\nCould not start on port {port}: {e.strerror or e}.\n"
              "Another copy of MusicSearch may already be running - close it, or set a different PORT.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
