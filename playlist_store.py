"""JSON-backed store for playlists downloaded on this machine."""
import json
import threading
from pathlib import Path

STORE_PATH = Path(__file__).parent / "playlists.json"
# Folders are stored as absolute paths. Entries written by older versions were
# relative to this folder, so keep resolving those against it.
LEGACY_DOWNLOAD_DIR = Path.home() / "Music" / "MusicSearch"
_lock = threading.Lock()


def _key(platform, playlist_id):
    return f"{platform}:{playlist_id}"


def _resolve_folder(folder: str) -> str:
    p = Path(folder)
    return str(p if p.is_absolute() else LEGACY_DOWNLOAD_DIR / p)


def _load():
    if not STORE_PATH.exists():
        return {}
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.values():
            if "folder" in entry:
                entry["folder"] = _resolve_folder(entry["folder"])
        return data
    except Exception:
        return {}


def _save(data):
    tmp_path = STORE_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
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
