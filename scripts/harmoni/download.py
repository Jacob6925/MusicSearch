#!/usr/bin/env python3
"""Download a single track by finding the best-matching YouTube video
(instead of harmoni's blind top-search-result), then embedding metadata
via harmoni's own metadata embedder."""
import sys

from _common import config, audio_format
from _yt_download import download_one

if len(sys.argv) < 4:
    print("Usage: harmoni_download.py <artist> <track> <output_dir> [duration_ms]", file=sys.stderr)
    sys.exit(1)

artist = sys.argv[1]
track = sys.argv[2]
output_dir = sys.argv[3]
duration_ms = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else None

track_dict = {"artist": artist, "track": track, "duration_ms": duration_ms}

try:
    if not download_one(track_dict, output_dir, audio_format, config):
        sys.exit(1)
except Exception as e:
    print(f"Error: Download failed — {e}", file=sys.stderr)
    sys.exit(1)
