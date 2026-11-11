"""Open the operating system's own "choose a folder" dialog and return the path.

The Flask server runs on the same machine as the browser, so the dialog opens
on the user's screen: Finder-style on macOS, the standard Windows folder
browser on Windows, and zenity / kdialog on Linux. Commands are built as
argument lists (no shell), and the start directory is passed as an argument or
environment variable — never spliced into script text.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROMPT = "Choose where to save songs"
DIALOG_TIMEOUT = 600  # seconds the user has to pick before we give up


class FolderPickerError(Exception):
    """The dialog couldn't be shown or failed. The message is safe to show in the UI."""


_MAC_SCRIPT = [
    "on run argv",
    "tell current application to activate",
    "try",
    f'set f to choose folder with prompt "{PROMPT}" default location (POSIX file (item 1 of argv) as alias)',
    "on error number -128",
    'return ""',
    "end try",
    "return POSIX path of f",
    "end run",
]

_WINDOWS_SCRIPT = f"""
try {{ [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 }} catch {{}}
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{PROMPT}'
$dialog.ShowNewFolderButton = $true
$dialog.SelectedPath = $env:MUSICSEARCH_START_DIR
if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::Out.Write($dialog.SelectedPath)
}}
"""


def _build_command(platform_name, start_dir):
    """Returns (argv, extra_env) for the current platform, or raises FolderPickerError."""
    if platform_name == "darwin":
        argv = ["osascript"]
        for line in _MAC_SCRIPT:
            argv += ["-e", line]
        return argv + [start_dir], {}

    if platform_name == "win32":
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            raise FolderPickerError("PowerShell was not found, so the folder dialog can't open.")
        argv = [shell, "-NoProfile", "-NonInteractive", "-STA", "-Command", _WINDOWS_SCRIPT]
        return argv, {"MUSICSEARCH_START_DIR": start_dir}

    if shutil.which("zenity"):
        start = start_dir.rstrip("/") + "/"
        return ["zenity", "--file-selection", "--directory", f"--title={PROMPT}", f"--filename={start}"], {}
    if shutil.which("kdialog"):
        return ["kdialog", "--title", PROMPT, "--getexistingdirectory", start_dir], {}
    raise FolderPickerError("No folder dialog found. Install zenity or kdialog, or type the folder path instead.")


def choose_folder(start_dir=None):
    """Show the native folder chooser. Returns the chosen absolute path, or None
    if the user cancelled. Raises FolderPickerError if the dialog can't be used."""
    start = str(start_dir) if start_dir and os.path.isdir(start_dir) else str(Path.home())
    argv, extra_env = _build_command(sys.platform, start)

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, **extra_env}, timeout=DIALOG_TIMEOUT, **kwargs,
        )
    except subprocess.TimeoutExpired:
        raise FolderPickerError("The folder dialog timed out.")
    except OSError as e:
        raise FolderPickerError(f"Couldn't open the folder dialog: {e.strerror or e}")

    if proc.returncode == 1 and sys.platform not in ("darwin", "win32"):
        return None  # zenity / kdialog: exit code 1 means cancelled
    if proc.returncode != 0:
        raise FolderPickerError("The folder dialog failed to open.")

    chosen = proc.stdout.strip()
    if not chosen:
        return None  # cancelled (macOS / Windows print nothing)
    if len(chosen) > 1:
        chosen = chosen.rstrip("/\\") if not chosen.endswith(":\\") else chosen
    if not os.path.isdir(chosen):
        raise FolderPickerError("The selected folder doesn't exist.")
    return chosen
