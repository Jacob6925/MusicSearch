"""Start the app exactly the way a user does (run.bat / run.command), wait for it to
answer, check /api/status, then stop it. Used by CI:  python tests/smoke_run.py"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = "5099"
IS_WINDOWS = os.name == "nt"


def main() -> int:
    env = {**os.environ, "MUSICSEARCH_CI": "1", "MUSICSEARCH_NO_BROWSER": "1", "PORT": PORT}
    cmd = ["cmd", "/c", "run.bat"] if IS_WINDOWS else ["./run.command"]
    kwargs = {} if IS_WINDOWS else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", **kwargs)
    status = None
    try:
        deadline = time.time() + 90
        while time.time() < deadline and status is None:
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=3) as r:
                    status = json.load(r)
            except Exception:
                time.sleep(1)
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=5) as r:
            page = r.read().decode("utf-8", "replace") if status else ""
    except Exception as e:
        print(f"Request failed: {e}")
        page = ""
    finally:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            out, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    print("---- app output ----")
    print(out)
    print("---- /api/status ----")
    print(status)
    if not status or "apple_music" not in status or "spotify_login" not in status or "Music Search" not in page:
        print("SMOKE TEST FAILED")
        return 1
    print("SMOKE TEST OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
