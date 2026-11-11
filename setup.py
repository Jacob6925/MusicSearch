#!/usr/bin/env python3
"""One-time setup (also the "update" step after `git pull`). Safe to re-run.

Uses only the Python standard library so it runs on a fresh machine:
    Windows:  setup.bat        macOS:  ./setup.command
    or by hand:  python setup.py   (python3 on macOS)

It will:
  1. check your Python version
  2. create a private virtual environment in .venv/ and install the dependencies
  3. download the pinned Harmoni helper (used for Spotify) into vendor/harmoni/
  4. download ffmpeg if you don't have it
  5. create your .env settings file
and then tell you what is still left to do.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENDOR = ROOT / "vendor"
HARMONI_DIR = VENDOR / "harmoni"
HARMONI_COMMIT = "6674612d82689cd277bee001b6d387c45c30faa3"
HARMONI_ZIP = f"https://github.com/Ssenseii/harmoni/archive/{HARMONI_COMMIT}.zip"
MIN_PYTHON = (3, 10)
IS_WINDOWS = os.name == "nt"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")


def fail(msg: str):
    print(f"\nSetup could not finish:\n  {msg}\n", file=sys.stderr)
    sys.exit(1)


def step(msg: str):
    print(f"\n==> {msg}", flush=True)


def check_python():
    if sys.version_info < MIN_PYTHON:
        have = ".".join(map(str, sys.version_info[:3]))
        want = ".".join(map(str, MIN_PYTHON))
        fail(f"Python {want} or newer is required (you have {have}). "
             "Install the latest Python from https://www.python.org/downloads/ and run setup again.")


def run(cmd, **kw):
    print("   $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], **kw)


def make_venv():
    step("Creating the virtual environment (.venv)")
    if venv_python().exists():
        # A venv built by a different/older Python breaks silently; rebuild it.
        r = subprocess.run([str(venv_python()), "-c", "import sys; print(sys.version_info >= %r)" % (MIN_PYTHON,)],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "True":
            print("   already exists")
            return
        shutil.rmtree(VENV, ignore_errors=True)
    r = run([sys.executable, "-m", "venv", VENV])
    if r.returncode != 0 or not venv_python().exists():
        hint = ""
        if not IS_WINDOWS and sys.platform != "darwin":
            hint = " On Debian/Ubuntu run: sudo apt install python3-venv"
        fail("Could not create the virtual environment (this Python install looks incomplete)." + hint +
             " Install Python from https://www.python.org/downloads/ and run setup again.")


def install_requirements():
    step("Installing Python packages (this can take a few minutes)")
    py = venv_python()
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip"])
    r = run([py, "-m", "pip", "install", "--disable-pip-version-check", "-r", ROOT / "requirements.txt"])
    if r.returncode == 0:
        # YouTube changes often; always move yt-dlp to the newest release (best effort).
        run([py, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "yt-dlp"])
    if r.returncode != 0:
        fail("Installing packages failed. Check your internet connection and run setup again. "
             "If the error mentions a compiler or 'wheel', make sure you have the 64-bit version of "
             "Python from python.org.")


def install_harmoni():
    step("Installing the Harmoni helper (used for Spotify)")
    marker = HARMONI_DIR / ".installed-commit"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == HARMONI_COMMIT:
        print("   already installed")
        return
    VENDOR.mkdir(exist_ok=True)
    zip_path = VENDOR / "harmoni.zip"
    try:
        print(f"   downloading {HARMONI_ZIP}")
        with urllib.request.urlopen(HARMONI_ZIP, timeout=60) as resp, open(zip_path, "wb") as out:
            shutil.copyfileobj(resp, out)
        tmp = VENDOR / "_extract"
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        inner = next(p for p in tmp.iterdir() if p.is_dir())
        # Keep the user's Spotify login if we are upgrading in place.
        keep = HARMONI_DIR / "data" / "spotify_tokens.json"
        saved = keep.read_bytes() if keep.exists() else None
        shutil.rmtree(HARMONI_DIR, ignore_errors=True)
        shutil.move(str(inner), str(HARMONI_DIR))
        shutil.rmtree(tmp, ignore_errors=True)
        if saved is not None:
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_bytes(saved)
        marker.write_text(HARMONI_COMMIT, encoding="utf-8")
    except Exception as e:
        fail(f"Could not download Harmoni ({e}). Check your internet connection and run setup again.")
    finally:
        zip_path.unlink(missing_ok=True)


def prepare_ffmpeg():
    step("Checking ffmpeg")
    code = ("import sys; sys.path.insert(0, %r); import appenv; "
            "sys.exit(0 if appenv.ensure_ffmpeg() else 1)" % str(ROOT))
    r = run([venv_python(), "-c", code])
    if r.returncode != 0:
        print("   WARNING: ffmpeg could not be set up automatically. Downloads will not work until you\n"
              "   install it yourself:  Windows: winget install Gyan.FFmpeg   macOS: brew install ffmpeg")


def create_env_file():
    step("Creating your settings file (.env)")
    env, example = ROOT / ".env", ROOT / ".env.example"
    if env.exists():
        print("   .env already exists, leaving it alone")
    else:
        shutil.copyfile(example, env)
        print("   created .env")


def verify():
    step("Checking the install")
    code = ("import sys; sys.path.insert(0, %r); "
            "import flask, requests, dotenv, gamdl, yt_dlp, mutagen; import appenv" % str(ROOT))
    if run([venv_python(), "-c", code]).returncode != 0:
        fail("The packages did not install correctly. Run setup again; if it keeps failing see the README's Troubleshooting section.")


def print_next_steps():
    cookies = ROOT / "gamdl" / "cookies.txt"
    env_text = (ROOT / ".env").read_text(encoding="utf-8-sig") if (ROOT / ".env").exists() else ""
    spotify_set = any(l.strip().startswith("SPOTIFY_CLIENT_ID=") and l.split("=", 1)[1].strip()
                      for l in env_text.splitlines())
    run_cmd = "run.bat" if IS_WINDOWS else "./run.command"
    print("\n" + "=" * 60)
    print("Setup finished.\n")
    print("Still to do:")
    todo = 0
    if not cookies.exists() or cookies.stat().st_size == 0:
        todo += 1
        print(f"  - Apple Music: save your cookies file as {cookies}\n    (README, step 5). Skip this if you only use YouTube Music.")
    if not spotify_set:
        todo += 1
        print("  - Spotify (optional): put your Client ID and Secret in the .env file (README, step 6).")
    if not todo:
        print("  - nothing")
    print(f"\nStart the app with:  {run_cmd}")
    print("=" * 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-ffmpeg", action="store_true", help="don't download ffmpeg now (it is fetched on first run instead)")
    args = ap.parse_args()
    os.chdir(ROOT)
    check_python()
    make_venv()
    install_requirements()
    install_harmoni()
    if not args.skip_ffmpeg:
        prepare_ffmpeg()
    create_env_file()
    verify()
    print_next_steps()


if __name__ == "__main__":
    main()
