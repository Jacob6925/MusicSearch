"""Pick the best-matching YouTube result for a track instead of blindly taking
the top search hit (which is often the most-viewed video, not the requested
version — e.g. a remix's original instead of the remix itself)."""
import json
import re
import subprocess

NOISE_WORDS = {"feat", "ft", "the", "a", "an"}


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[^\W_]+", (s or "").lower()) if t not in NOISE_WORDS and len(t) > 1}


def _artist_tokens(artist: str) -> set:
    parts = re.split(r",|&| feat\.?| ft\.?", artist or "", flags=re.IGNORECASE)
    tokens = set()
    for p in parts:
        tokens |= _tokens(p)
    return tokens


def _score(entry: dict, title_tokens: set, artist_tokens: set, duration_s: float | None) -> float:
    cand_title_tokens = _tokens(entry.get("title", ""))
    cand_channel_tokens = _tokens(entry.get("channel", "")) | _tokens(entry.get("uploader", ""))

    title_score = len(title_tokens & cand_title_tokens) / len(title_tokens) if title_tokens else 0.0
    artist_score = (
        len(artist_tokens & (cand_title_tokens | cand_channel_tokens)) / len(artist_tokens)
        if artist_tokens else 0.0
    )

    score = 0.55 * title_score + 0.25 * artist_score

    cand_duration = entry.get("duration")
    if duration_s and cand_duration:
        diff = abs(cand_duration - duration_s)
        score += 0.20 * max(0.0, 1 - diff / 30)
    else:
        # Redistribute weight when duration can't be compared.
        score = score / 0.8

    return score


def find_best_match(artist: str, track: str, duration_ms: int | None = None, search_count: int = 5) -> dict | None:
    """Search YouTube for `artist - track` and return the best-scoring candidate as
    {'url', 'title', 'score'}, or None if the search returns nothing or yt-dlp fails."""
    query = f"{artist} - {track}"
    cmd = ["yt-dlp", f"ytsearch{search_count}:{query}", "--flat-playlist", "-J", "--no-warnings"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
    except Exception:
        return None

    entries = data.get("entries") or []
    if not entries:
        return None

    title_tokens = _tokens(track)
    artist_tokens = _artist_tokens(artist)
    duration_s = duration_ms / 1000 if duration_ms else None

    best = max(entries, key=lambda e: _score(e, title_tokens, artist_tokens, duration_s))
    return {
        "url": best.get("url") or f"https://www.youtube.com/watch?v={best.get('id')}",
        "title": best.get("title", ""),
        "score": _score(best, title_tokens, artist_tokens, duration_s),
    }
