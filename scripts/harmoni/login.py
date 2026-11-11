#!/usr/bin/env python3
"""One-time Spotify login for playlist/track downloads.

Opens Spotify's sign-in page in your browser, waits for the redirect back to
http://127.0.0.1:8888/callback, and stores the token where Harmoni expects it.
Uses the Client ID from .env (PKCE flow, no secret needed).

Run by the "Connect Spotify" button in the web app, or by hand:
    python scripts/harmoni/login.py
"""
import http.server
import socketserver
import sys
import threading
import urllib.parse
import webbrowser

from _common import config

from spotify_api.auth import SpotifyPKCEAuth, extract_code_from_redirect_url

TIMEOUT_SECONDS = 300
HOST, PORT = "127.0.0.1", 8888

_PAGE = (
    "<!doctype html><meta charset='utf-8'><title>MusicSearch</title>"
    "<body style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
    "<h2>{msg}</h2><p>You can close this tab and return to MusicSearch.</p></body>"
)


def main() -> int:
    client_id = str(config.get("spotify_client_id", "")).strip()
    if not client_id:
        print("Error: Set SPOTIFY_CLIENT_ID in the .env file first, then restart the app.", flush=True)
        return 1

    auth = SpotifyPKCEAuth(config)
    flow = auth.begin_oauth_flow(show_dialog=False)
    result: dict = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if urllib.parse.urlparse(self.path).path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            result.update(extract_code_from_redirect_url(self.path))
            msg = "Spotify connected." if result.get("code") else "Spotify sign-in was not completed."
            body = _PAGE.format(msg=msg).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, *args):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    try:
        server = socketserver.TCPServer((HOST, PORT), Handler)
    except OSError as e:
        print(f"Error: Port {PORT} is busy ({e.strerror or e}). Close whatever is using it and try again.", flush=True)
        return 1

    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = flow["auth_url"]
    print("Opening Spotify sign-in in your browser...", flush=True)
    print(f"If nothing opens, visit this link:\n{url}", flush=True)
    webbrowser.open(url)

    try:
        if not done.wait(TIMEOUT_SECONDS):
            print("Error: Timed out waiting for the Spotify sign-in.", flush=True)
            return 1
    finally:
        server.shutdown()
        server.server_close()

    if result.get("error"):
        print(f"Error: Spotify refused the sign-in ({result['error']}).", flush=True)
        return 1
    if not result.get("code") or result.get("state") != flow["state"]:
        print("Error: Spotify sign-in response was invalid. Try again.", flush=True)
        return 1

    try:
        auth.exchange_code_for_token(code=result["code"], code_verifier=flow["pkce_pair"].code_verifier)
    except Exception as e:
        print(f"Error: Could not finish the Spotify sign-in: {e}", flush=True)
        return 1
    print("Spotify connected.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
