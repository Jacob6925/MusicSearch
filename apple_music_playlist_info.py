#!/usr/bin/env python3
"""Fetch Apple Music playlist title and track count via gamdl's authenticated API."""
import asyncio
import json
import logging
import sys

logging.disable(logging.CRITICAL)

import structlog
structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=open("/dev/null", "w")),
)

from gamdl.api.apple_music import AppleMusicApi

COOKIES_PATH = "/Users/jacob/.gamdl/cookies.txt"


async def get_info(playlist_id: str) -> dict:
    api = await AppleMusicApi.create_from_netscape_cookies(COOKIES_PATH)
    data = await api.get_playlist(playlist_id, limit_tracks=1)
    item = data.get("data", [{}])[0]
    attrs = item.get("attributes", {})
    return {
        "title": attrs.get("name", "Unknown Playlist"),
        "track_count": attrs.get("trackCount", 0),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No playlist ID provided"}))
        sys.exit(1)
    playlist_id = sys.argv[1]
    result = asyncio.run(get_info(playlist_id))
    print(json.dumps(result))
