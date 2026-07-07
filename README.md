# MusicSearch

A Flask web app for searching Apple Music and Spotify, and downloading tracks and playlists. Apple Music downloads are handled by [gamdl](https://github.com/glomatico/gamdl); Spotify downloads are handled by [Harmoni](https://github.com/YourHarmoniLink).

---

## Prerequisites

- macOS (Intel or Apple Silicon)
- [Homebrew](https://brew.sh)
- Python 3.11 or later

---

## 1. Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After installation, follow any instructions Homebrew prints to add it to your shell PATH.

---

## 2. Install system dependencies

```bash
brew install python@3.11 ffmpeg yt-dlp
```

`ffmpeg` and `yt-dlp` are required by gamdl for downloading and processing Apple Music tracks.

> **Harmoni** is a separate Python application, not a Homebrew package. It is set up in a later step.

---

## 3. Clone the repository

```bash
git clone <repo-url>
cd MusicSearch
```

---

## 4. Create and activate a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

You must activate the virtual environment every time you open a new terminal session before running the app.

---

## 5. Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs Flask, Requests, python-dotenv, structlog, and gamdl (along with all of gamdl's own dependencies).

---

## 6. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Spotify API credentials:

```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

Create credentials at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) — create an app, then copy the Client ID and Client Secret. Spotify is optional; Apple Music search and downloads work without it.

---

## 7. Configure gamdl

gamdl requires a Netscape-format cookies file from an active Apple Music browser session.

1. In your browser, log in to [music.apple.com](https://music.apple.com).
2. Export your cookies in Netscape format (e.g., using the [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) Chrome extension).
3. Save the exported file as `gamdl/cookies.txt` inside this repository.

`gamdl/config.ini` is already included and pre-configured. Do not rename or move it.

> gamdl may require additional first-time setup (such as Widevine decryption keys) depending on your use case. Follow [gamdl's documentation](https://github.com/glomatico/gamdl) to complete its setup before using this app.

---

## 8. Set up Harmoni

Harmoni is a separate Python application used for Spotify downloads. This project expects it to be installed at `~/harmoni`.

Follow Harmoni's own documentation to install and configure it, including completing Spotify authentication inside Harmoni. Spotify playlist downloads will not work until Harmoni is fully configured.

If you install Harmoni somewhere other than `~/harmoni`, add this to your `.env`:

```
HARMONI_PATH=/path/to/your/harmoni
```

---

## 9. Start the application

```bash
python app.py
```

Open the app at:

```
http://localhost:5050/
```

Downloaded music is saved to `~/Music/MusicSearch/`.
