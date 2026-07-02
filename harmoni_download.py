#!/usr/bin/env python3
"""Wrapper to invoke harmoni's download_track from a subprocess."""
import sys
import json
import os

sys.path.insert(0, "/Users/jacob/harmoni")

from downloader.base_downloader import download_track

if len(sys.argv) < 4:
    print("Usage: harmoni_download.py <artist> <track> <output_dir>", file=sys.stderr)
    sys.exit(1)

artist = sys.argv[1]
track = sys.argv[2]
output_dir = sys.argv[3]

config_path = "/Users/jacob/harmoni/config.json"
with open(config_path) as f:
    config = json.load(f)

audio_format = config.get("audio_format", "mp3")

download_track(
    artist=artist,
    track=track,
    output_dir=output_dir,
    audio_format=audio_format,
    sleep_between=0,
    config=config,
)
