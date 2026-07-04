"""JSON-backed store for playlists downloaded on this machine."""
import json
import os
import threading

STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlists.json")
_lock = threading.Lock()


def _key(platform, playlist_id):
    return f"{platform}:{playlist_id}"


def _load():
    if not os.path.exists(STORE_PATH):
        return {}
    try:
        with open(STORE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    tmp_path = STORE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, STORE_PATH)


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
