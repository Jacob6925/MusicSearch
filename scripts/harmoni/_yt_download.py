"""Shared single-track download logic: picks the best-matching YouTube video
via yt_search (instead of harmoni's blind ytsearch1 top-hit), downloads it
directly with yt-dlp, then embeds metadata using harmoni's own metadata
embedder so downloaded files retain the same tags harmoni would have written."""
import asyncio
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

from tqdm import tqdm
from utils import log_info, log_success, log_error, log_warning
from downloader.metadata import embed_track_metadata, find_downloaded_audio_path

from yt_search import find_best_match


# YouTube is only the fallback source (Apple Music via gamdl is primary, and its
# files are .m4a/AAC). Prefer YouTube's native AAC stream so it is stored as M4A
# without a lossy re-encode; Rekordbox reads M4A but not Opus/WebM. The harmoni
# config's audio_format is deliberately ignored here.
YT_AUDIO_FORMAT = "m4a"
YT_FORMAT_SELECTOR = "bestaudio[ext=m4a]/bestaudio/best"
# Only applies if yt-dlp has to transcode (no native AAC stream available).
YT_TRANSCODE_BITRATE = "256K"


def _base_filename(artist: str, track: str) -> str:
    return f"{artist} - {track}".replace("/", "-")


def _log_audio_info(path: str) -> None:
    """Log the codec/bitrate of the downloaded file; best-effort, never raises."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name,bit_rate", "-of", "csv=p=0", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30,
        ).stdout.strip()
        codec, _, bit_rate = out.partition(",")
        kbps = f"{int(bit_rate) // 1000} kbps" if bit_rate.isdigit() else "unknown bitrate"
        log_info(f"Audio quality: {codec or 'unknown codec'}, {kbps} ({os.path.basename(path)})")
    except Exception:
        pass


def download_one(track_dict: dict, output_dir: str, config: dict | None = None) -> bool:
    """Download a single track dict (must have 'artist' and 'track', may include
    'duration_ms' and other harmoni metadata fields) by finding the best-matching
    YouTube video and downloading it directly. Returns True on success."""
    artist = (track_dict.get("artist") or "").strip()
    track = (track_dict.get("track") or "").strip()
    duration_ms = track_dict.get("duration_ms")
    query = f"{artist} - {track}"
    filename = _base_filename(artist, track)

    video_url = track_dict.get("video_url")
    match = None if video_url else find_best_match(artist, track, duration_ms)
    if video_url:
        # Source already identifies the exact video (e.g. a YouTube Music playlist) — no search needed.
        target = video_url
    elif match:
        log_info(f"Best match for '{query}': {match['title']} (score={match['score']:.2f})")
        target = match["url"]
    else:
        log_warning(f"No YouTube match found via search for '{query}', falling back to top result")
        target = f"ytsearch1:{query}"

    output_template = os.path.join(output_dir, f"{filename}.%(ext)s")
    # Tiered so the track always arrives: native AAC -> any stream converted to M4A
    # (Rekordbox-compatible) -> yt-dlp's plain defaults (may not be M4A).
    audio_args = ["-x", "--audio-format", YT_AUDIO_FORMAT, "--audio-quality", YT_TRANSCODE_BITRATE,
                  "-o", output_template]
    attempts = [
        ("preferred", ["yt-dlp", target, "-f", YT_FORMAT_SELECTOR, *audio_args]),
        ("converted", ["yt-dlp", target, "-f", "bestaudio/best", *audio_args]),
        ("default", ["yt-dlp", target, "-x", "-o", output_template]),
    ]

    process = None
    for i, (label, cmd) in enumerate(attempts):
        try:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception as e:
            log_error(f"Error downloading {query}: {e}")
            return False
        if process.returncode == 0:
            if label == "converted":
                log_warning(f"No native AAC stream for '{query}'; converted to M4A")
            elif label == "default":
                log_warning(f"Used default yt-dlp settings for '{query}'; file may not be M4A")
            break
        if i < len(attempts) - 1:
            log_warning(f"'{label}' download failed for '{query}', trying '{attempts[i + 1][0]}'")
            if process.stderr:
                log_warning(f"Error details: {process.stderr.strip()}")

    if process.returncode != 0:
        log_error(f"Failed to download: {query}")
        if process.stderr:
            log_error(f"Error details: {process.stderr.strip()}")
        return False

    log_success(f"Downloaded successfully: {query}")

    try:
        audio_path = find_downloaded_audio_path(output_dir, filename)
        if audio_path:
            _log_audio_info(audio_path)
            config = config or {}
            if config.get("enable_metadata_embedding", True):
                ok = embed_track_metadata(
                    audio_path,
                    track_dict,
                    template=config.get("metadata_template", "basic"),
                    allow_musicbrainz=config.get("enable_musicbrainz_lookup", True),
                    config=config,
                )
                if ok:
                    log_info(f"Metadata embedded for {query}")
                else:
                    log_warning(f"Metadata embedding failed for {query}")
        else:
            log_warning(f"Could not find downloaded audio file for metadata embedding: {filename}")
    except Exception as e:
        log_warning(f"Metadata embedding step failed: {e}")

    return True


async def download_many(tracks: list[dict], output_dir: str, config: dict | None = None, max_workers: int = 4) -> None:
    """Download multiple tracks concurrently, mirroring harmoni's batch_download
    (concurrency, auto-backup, auto-cleanup) but with per-track YouTube matching."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = []
        with tqdm(total=len(tracks), desc="Downloading", unit="track") as pbar:
            for track in tracks:
                task = loop.run_in_executor(executor, download_one, track, output_dir, config)
                task.add_done_callback(lambda _: pbar.update(1))
                tasks.append(task)
            await asyncio.gather(*tasks)

    if not config:
        return

    if config.get("auto_backup", True):
        try:
            from managers.backup_manager import backup_all
            log_info("Creating backups of data files...")
            backup_all(config)
        except ImportError:
            pass
        except Exception as e:
            log_error(f"Backup failed: {e}")

    if config.get("auto_cleanup", True):
        try:
            from managers.cleanup_manager import cleanup_after_download
            log_info("Running post-download cleanup...")
            cleanup_results = cleanup_after_download(config)
            total_cleaned = (
                cleanup_results.get("temp_files_removed", 0) +
                cleanup_results.get("empty_dirs_removed", 0) +
                cleanup_results.get("partial_files_removed", 0)
            )
            if total_cleaned > 0:
                log_info(f"Cleaned up {total_cleaned} items")
        except ImportError:
            pass
        except Exception as e:
            log_error(f"Cleanup failed: {e}")
