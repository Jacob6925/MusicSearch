"""Match a Spotify track to an Apple Music catalog song: exact ISRC lookup
first (identifies the precise recording/version, e.g. a specific remix), then
fuzzy title/artist/duration scoring as a fallback when no ISRC match exists.
Mirrors the YouTube matching approach in scripts/harmoni/yt_search.py."""
import re

FUZZY_THRESHOLD = 0.75
NOISE_WORDS = {"feat", "ft", "the", "a", "an"}


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[^\W_]+", (s or "").lower()) if t not in NOISE_WORDS and len(t) > 1}


def _artist_tokens(artist: str) -> set:
    parts = re.split(r",|&| feat\.?| ft\.?", artist or "", flags=re.IGNORECASE)
    tokens = set()
    for p in parts:
        tokens |= _tokens(p)
    return tokens


def _score(attrs: dict, title_tokens: set, artist_tokens: set, duration_ms: int | None) -> float:
    cand_title_tokens = _tokens(attrs.get("name", ""))
    cand_artist_tokens = _tokens(attrs.get("artistName", ""))

    title_score = len(title_tokens & cand_title_tokens) / len(title_tokens) if title_tokens else 0.0
    artist_score = len(artist_tokens & cand_artist_tokens) / len(artist_tokens) if artist_tokens else 0.0

    score = 0.55 * title_score + 0.25 * artist_score

    cand_duration = attrs.get("durationInMillis")
    if duration_ms and cand_duration:
        diff_s = abs(cand_duration - duration_ms) / 1000
        score += 0.20 * max(0.0, 1 - diff_s / 10)
    else:
        # Redistribute weight when duration can't be compared.
        score = score / 0.8

    return score


def _song_result(song: dict, score: float, method: str) -> dict:
    attrs = song.get("attributes", {})
    return {
        "apple_url": attrs.get("url", ""),
        "apple_title": attrs.get("name", ""),
        "apple_artist": attrs.get("artistName", ""),
        "score": score,
        "method": method,
    }


async def find_best_match(api, artist: str, title: str, isrc: str = "", duration_ms: int | None = None) -> dict | None:
    """Find the Apple Music catalog song matching a Spotify track. Tries an
    exact ISRC lookup first, then falls back to fuzzy title/artist/duration
    scoring. Returns None if neither finds a confident match."""
    if isrc:
        try:
            data = await api._amp_request(
                f"/v1/catalog/{api.storefront}/songs",
                {"filter[isrc]": isrc},
            )
            candidates = data.get("data", [])
            if candidates:
                return _song_result(candidates[0], score=1.0, method="isrc")
        except Exception:
            pass

    try:
        raw = await api.get_search_results(f"{artist} {title}", types="songs", limit=10)
        songs = raw.get("results", {}).get("songs", {}).get("data", [])
    except Exception:
        return None

    if not songs:
        return None

    title_tokens = _tokens(title)
    artist_tokens = _artist_tokens(artist)

    best = max(songs, key=lambda s: _score(s.get("attributes", {}), title_tokens, artist_tokens, duration_ms))
    score = _score(best.get("attributes", {}), title_tokens, artist_tokens, duration_ms)
    if score < FUZZY_THRESHOLD:
        return None

    return _song_result(best, score=score, method="fuzzy")
