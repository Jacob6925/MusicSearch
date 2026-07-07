#!/usr/bin/env python3
"""Wrapper to invoke harmoni's download_track from a subprocess."""
import sys

from _common import config, audio_format
from downloader.base_downloader import download_track

if len(sys.argv) < 4:
    print("Usage: harmoni_download.py <artist> <track> <output_dir>", file=sys.stderr)
    sys.exit(1)

artist = sys.argv[1]
track = sys.argv[2]
output_dir = sys.argv[3]

try:
    download_track(
        artist=artist,
        track=track,
        output_dir=output_dir,
        audio_format=audio_format,
        sleep_between=0,
        config=config,
    )
except Exception as e:
    print(f"Error: Download failed — {e}", file=sys.stderr)
    sys.exit(1)
