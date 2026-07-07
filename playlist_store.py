"""JSON-backed store for playlists downloaded on this machine."""
import json
import threading
from pathlib import Path

STORE_PATH = Path(__file__).parent / "playlists.json"
DOWNLOAD_DIR = Path.home() / "Music" / "MusicSearch"
_lock = threading.Lock()


def _key(platform, playlist_id):
    return f"{platform}:{playlist_id}"


def _to_relative_folder(folder: str) -> str:
    """Store only the playlist subfolder name so the record is machine-portable."""
    p = Path(folder)
    try:
        return str(p.relative_to(DOWNLOAD_DIR))
    except ValueError:
        return str(p)


def _resolve_folder(folder: str) -> str:
    """Reconstruct the absolute folder path from a stored relative or absolute value."""
    p = Path(folder)
    if p.is_absolute():
        return str(p)
    return str(DOWNLOAD_DIR / p)


def _load():
    if not STORE_PATH.exists():
        return {}
    try:
        with open(STORE_PATH) as f:
            data = json.load(f)
        for entry in data.values():
            if "folder" in entry:
                entry["folder"] = _resolve_folder(entry["folder"])
        return data
    except Exception:
        return {}


def _save(data):
    portable = {}
    for key, entry in data.items():
        e = dict(entry)
        if "folder" in e:
            e["folder"] = _to_relative_folder(e["folder"])
        portable[key] = e
    tmp_path = STORE_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w") as f:
        json.dump(portable, f, indent=2)
    tmp_path.replace(STORE_PATH)


def list_playlists():
    with _lock:
        return list(_load().values())


def get_playlist(platform, playlist_id):
    with _lock:
        return _load().get(_key(platform, playlist_id))


def add_playlist(entry):
    """Adds entry if not already present (deduped by platform+id). No-op if it exists."""
    with _lock:
        data = _load()
        key = _key(entry["platform"], entry["id"])
        if key in data:
            return data[key]
        data[key] = entry
        _save(data)
        return entry


def update_playlist(platform, playlist_id, updates):
    with _lock:
        data = _load()
        key = _key(platform, playlist_id)
        if key not in data:
            return None
        data[key].update(updates)
        _save(data)
        return data[key]


def remove_playlist(platform, playlist_id):
    with _lock:
        data = _load()
        key = _key(platform, playlist_id)
        if key not in data:
            return False
        del data[key]
        _save(data)
        return True
