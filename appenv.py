"""Environment preparation shared by app.py and the helper scripts: where
Harmoni lives, and making sure child processes can find yt-dlp / ffmpeg and
speak UTF-8 on every platform."""
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def find_harmoni_path() -> Path:
    """HARMONI_PATH env var, else the copy setup.py installs into vendor/harmoni,
    else a legacy ~/harmoni checkout."""
    env = os.environ.get("HARMONI_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    vendored = PROJECT_ROOT / "vendor" / "harmoni"
    if vendored.is_dir():
        return vendored
    return Path.home() / "harmoni"


def spotify_token_file() -> Path:
    return find_harmoni_path() / "data" / "spotify_tokens.json"


def spotify_logged_in() -> bool:
    try:
        return spotify_token_file().stat().st_size > 0
    except OSError:
        return False


def ensure_ffmpeg() -> bool:
    """Put ffmpeg + ffprobe on PATH. Uses the system ones if present, otherwise the
    copy provided by the `static-ffmpeg` pip package (downloaded once, then cached).
    Returns True if both are available afterwards."""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
        except Exception as e:  # offline, blocked download, package missing...
            print(f"[MusicSearch] Could not set up bundled ffmpeg: {e}", file=sys.stderr, flush=True)
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def prepare_environment() -> None:
    """Call once at startup, before launching any child process."""
    # Child Python processes (helper scripts, gamdl) read/write UTF-8 even on
    # Windows, where the default is the legacy ANSI code page.
    for stream in (sys.stdout, sys.stderr):  # this process's own console, too
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    # The folder holding this Python (the venv's bin/ or Scripts/) goes first on
    # PATH so tools installed with pip (yt-dlp, gamdl) work without activating
    # the venv.
    exe_dir = str(Path(sys.executable).parent)
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if exe_dir not in parts:
        os.environ["PATH"] = exe_dir + os.pathsep + os.environ.get("PATH", "")
    ensure_ffmpeg()
