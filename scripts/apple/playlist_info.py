#!/usr/bin/env python3
"""Fetch Apple Music playlist title and track count via gamdl's authenticated API."""
import asyncio
import json
import sys

from _common import AppleMusicApi, COOKIES_PATH


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
    try:
        result = asyncio.run(get_info(playlist_id))
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
