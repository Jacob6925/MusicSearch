"""Turn arbitrary titles into names that are valid file/folder names on both
Windows and macOS. Used by app.py and by the helper scripts in scripts/."""
import re

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL",
             *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(name, fallback="Untitled", max_len=120, slash_to=""):
    """Return `name` made safe as a single path component.

    Characters Windows forbids are dropped ("/" and "\\" become `slash_to`),
    trailing dots/spaces (also forbidden on Windows) are stripped, reserved
    device names such as CON/NUL get an underscore, and the result is cut to
    `max_len` characters so long titles don't hit Windows' 260-char path limit.
    """
    s = str(name or "")
    s = re.sub(r"[/\\]", slash_to, s)
    s = _ILLEGAL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    if len(s) > max_len:
        s = s[:max_len].rstrip(" .")
    if not s:
        return fallback
    if s.split(".")[0].strip().upper() in _RESERVED:
        s = "_" + s
    return s
