#!/usr/bin/env python3
"""Download a single track by finding the best-matching YouTube video
(instead of harmoni's blind top-search-result), then embedding metadata
via harmoni's own metadata embedder."""
import sys

from _common import config
from _yt_download import download_one

if len(sys.argv) < 4:
    print("Usage: harmoni_download.py <artist> <track> <output_dir> [duration_ms] [video_url]", file=sys.stderr)
    sys.exit(1)

artist = sys.argv[1]
track = sys.argv[2]
output_dir = sys.argv[3]
duration_ms = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else None

video_url = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else None

track_dict = {"artist": artist, "track": track, "duration_ms": duration_ms, "video_url": video_url}

try:
    if not download_one(track_dict, output_dir, config):
        sys.exit(1)
except Exception as e:
    print(f"Error: Download failed — {e}", file=sys.stderr)
    sys.exit(1)
