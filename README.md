# MusicSearch

A small web app that runs on your own computer. Search Apple Music and Spotify, paste links to songs or playlists (Apple Music, Spotify, YouTube Music, YouTube), and download them as audio files. It keeps a list of the playlists you've downloaded so you can re-sync them later.

Works on **Windows 10/11** and **macOS** (Intel and Apple Silicon). You don't need any programming experience: just follow the steps below in order.

- Apple Music downloads use [gamdl](https://github.com/glomatico/gamdl) and need an Apple Music subscription.
- Spotify links are matched to Apple Music (or YouTube if there is no match) using [Harmoni](https://github.com/Ssenseii/harmoni), which setup installs for you.
- YouTube Music links work with no accounts or keys.
- You can also download any audio straight from YouTube. You must hit the share button and copy that link, not the one from the browser.

> Only download music you have the right to download. Respect the terms of the services you use.

---

## What you need first

You need two free programs: **Git** (to download this project) and **Python 3.10 or newer** (to run it). Check whether you already have them in step 1.

### Step 1. Open a terminal

**Windows:** click the Start button, type `PowerShell`, and press Enter. A window with a blue or black background and a blinking cursor opens. (Windows Terminal or Command Prompt also work.)

**Mac:** press `Cmd + Space`, type `Terminal`, and press Enter.

You will type (or paste) each command below and press **Enter**. Wait for it to finish before typing the next one.

### Step 2. Check for Git and Python

Type these two commands one at a time:

```bash
git --version
```

Windows:

```bash
py --version
```

Mac:

```bash
python3 --version
```

- If `git --version` prints a version number, you have Git. If you get an error or (on a Mac) a pop-up asking to install developer tools, install Git as described below.
- Python must show **3.10 or higher** (3.12 recommended). If it shows something older, or you get an error, install Python as described below.

#### Install Git and Python on Windows

In PowerShell:

```bash
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
```

(If `winget` isn't recognised, download the installers instead: [git-scm.com/download/win](https://git-scm.com/download/win) and [python.org/downloads](https://www.python.org/downloads/). In the Python installer, **tick "Add python.exe to PATH"** on the first screen.)

**Then close PowerShell and open a new one** so it can find the new programs.

#### Install Git and Python on Mac

- **Git:** run `xcode-select --install` and click *Install* in the pop-up (or install from [git-scm.com](https://git-scm.com/download/mac)).
- **Python:** download and run the macOS installer from [python.org/downloads](https://www.python.org/downloads/). Don't use the `python3` that came with the Mac if it's older than 3.10.

Then close Terminal and open a new window.

---

## Install

### Step 3. Download the project

Pick a folder to keep it in (your home folder is fine) and run:

```bash
git clone https://github.com/Jacob6925/MusicSearch.git
cd MusicSearch
```

### Step 4. Run the setup script

This creates a private Python environment inside the project, installs everything the app needs (including ffmpeg and Harmoni), and creates your settings file. It needs an internet connection and takes a few minutes the first time.

Windows:

```bash
.\setup.bat
```

Mac:

```bash
./setup.command
```

When it prints **"Setup finished"** it also lists anything you still need to configure.

> You can also double-click `setup.bat` (Windows) or `setup.command` (Mac) in your file manager.

### Step 5. Add your Apple Music cookies (needed for Apple Music)

If you do not have an Apple Music subscription, skip this step. The app uses your logged-in Apple Music session to search and download.

1. In Chrome, install the extension [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Firefox has similar add-ons).
2. Go to [music.apple.com](https://music.apple.com) and sign in.
3. With that tab open, click the extension and choose **Export** (Netscape format).
4. Save the file as **`cookies.txt`** inside the project's **`gamdl`** folder, so the final path is `MusicSearch/gamdl/cookies.txt`.

Cookies expire after a while. If Apple Music stops working, repeat this step with a fresh export.

### Step 6. Spotify (optional)

Skip this if you don't have a Spotify subscription. Spotify needs its own free developer app, because each person uses their own keys:

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard), log in, and click **Create app**.
2. Give it any name and description. In **Redirect URIs** enter exactly `http://127.0.0.1:8888/callback` and click **Add**, then tick the *Web API* box and save.
3. Open the app's **Settings** and copy the **Client ID**; click *View client secret* and copy the **Client secret**.
4. Open the file named **`.env`** in the project folder with any text editor (Notepad, TextEdit) and fill in the two lines, with no quotes or spaces:

   ```
   SPOTIFY_CLIENT_ID=paste_your_client_id_here
   SPOTIFY_CLIENT_SECRET=paste_your_client_secret_here
   ```

   (On a Mac, files starting with a dot are hidden in Finder. Press `Cmd + Shift + .` to show them, or run `open -e .env` in Terminal. On Windows run `notepad .env`.)
5. Save, then start the app (next step). A banner at the top will show a **Connect Spotify** button. Click it, sign in to Spotify in the browser tab that opens, and approve. You only do this once.

---

## Run

### Step 7. Start the app

Windows:

```bash
.\run.bat
```

Mac:

```bash
./run.command
```

Your browser opens to **http://127.0.0.1:5050/**. If it doesn't, open that address yourself. Leave the terminal window open while you use the app; press `Ctrl + C` in it (or close it) to stop the app.

The first time you open the app, a message asks you to choose the folder your music is saved in, then a folder window opens. That folder becomes your **default** and is remembered, even after you restart the app.

At the top of the page, **Save to** shows where the next download will go:

- **Change…** picks a different folder for the *next download only*. After that download succeeds, it goes back to your default. (If the download fails, the chosen folder stays so you can retry.)
- **Set as default** appears while a different folder is selected. Click it to make that folder your new default.

---

## Updating

When there are new changes, from inside the `MusicSearch` folder run:

```bash
git pull
```

then run the setup script again (step 4) to update the installed packages, and start the app as usual. Your `.env`, cookies, chosen save folder and downloaded-playlist list are kept.

If downloads from YouTube suddenly start failing, update just the downloader by running the setup script again, which installs the newest `yt-dlp`.

---

## If a script doesn't work: run the commands by hand

The scripts only automate the following. If one fails, you can type these yourself from inside the `MusicSearch` folder.

**Windows (PowerShell):**

```bash
py -3 setup.py
.venv\Scripts\python app.py
```

**Mac (Terminal):**

```bash
python3 setup.py
.venv/bin/python app.py
```

`setup.py` is the program `setup.bat` / `setup.command` run: it creates the `.venv` folder, installs the packages, downloads Harmoni and creates `.env`. If even that fails, here is the same thing in plain commands:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

(On Windows use `py -3 -m venv .venv` and `.venv\Scripts\python -m pip install -r requirements.txt`.) You then still need Harmoni for Spotify: download [this zip](https://github.com/Ssenseii/harmoni/archive/6674612d82689cd277bee001b6d387c45c30faa3.zip), and unzip its contents into a folder named `vendor/harmoni` inside the project, and copy `.env.example` to `.env`.

---

## Troubleshooting

**"git is not recognized" / "python is not recognized" (Windows).** The program isn't installed, or PowerShell was open before you installed it. Install it (see above), close PowerShell, and open a new window. Use `py` instead of `python`. If typing `python` opens the Microsoft Store, ignore it: install Python from python.org and use `py`.

**"Python 3.10 or newer was not found".** Install the latest Python from [python.org/downloads](https://www.python.org/downloads/), then close the terminal, open a new one, and run setup again. On Macs, the built-in `python3` is often too old.

**Setup says it "could not create the virtual environment".** Your Python install is incomplete (this sometimes happens with Python installed through other tools). Install Python from python.org and run setup again. Delete the `.venv` folder first if it exists.

**Mac: "permission denied" or the script won't open when double-clicked.** Run it from Terminal with `bash setup.command` (or `bash run.command`). This also applies if you downloaded the project as a ZIP instead of using `git clone`.

**Windows: "running scripts is disabled on this system".** That message is about `.ps1` files; this project uses `.bat` files, which aren't affected. Make sure you typed `.\setup.bat`, not `setup.ps1`. If SmartScreen says "Windows protected your PC", click *More info* then *Run anyway*.

**"Port 5050 is busy" / the app won't start.** Another copy of MusicSearch (or another program) is using the port. Close the other terminal window running it. Or choose a different port: in PowerShell `$env:PORT=5051; .\run.bat`, on Mac `PORT=5051 ./run.command`, then open that port in the browser.

**The banner says Apple Music is not set up / Apple search returns nothing / downloads fail with "error downloading".** `gamdl/cookies.txt` is missing, in the wrong place, empty, or expired. Export fresh cookies while signed in to music.apple.com (step 5), save over the old file, and restart the app. You need an active Apple Music subscription.

**Spotify: "Spotify is not configured".** Check `.env`: the two values must be on the lines `SPOTIFY_CLIENT_ID=` and `SPOTIFY_CLIENT_SECRET=` with no quotes or spaces, and you must restart the app after editing it.

**Spotify sign-in fails with "INVALID_CLIENT: Invalid redirect URI".** In the Spotify dashboard, add `http://127.0.0.1:8888/callback` exactly (not `localhost`) to your app's Redirect URIs.

**Spotify: "No Spotify token found" or a 401 error.** Click **Connect Spotify** in the banner and sign in again. A 403 on a playlist usually means it's private or owned by someone else (for example Spotify's own editorial playlists).

**"Port 8888 is busy" when connecting Spotify.** Close the program using it (often an old, unfinished sign-in) and click the button again.

**ffmpeg problems / "ffmpeg not found".** Setup downloads ffmpeg for you; if that was blocked (offline, company network), install it yourself and re-run the app. Windows: `winget install Gyan.FFmpeg` then open a new PowerShell. Mac: install [Homebrew](https://brew.sh) then `brew install ffmpeg`.

**YouTube downloads suddenly fail.** YouTube changes often. Run the setup script again to get the newest downloader (yt-dlp).

**Windows: some downloads fail on very long names, or the folder is inside OneDrive.** Windows limits full file paths to about 260 characters. Pick a shorter save folder (for example `C:\Music`) for single songs. If your `Music` folder is synced by OneDrive, make sure files are set to download/keep on this device.

**Antivirus blocks the setup or the app.** Setup downloads packages from the internet and the app starts a local web server on your own computer (it is not reachable from other devices). If your antivirus quarantines something, allow the project folder.

**Something else.** Keep the terminal window open: it prints the real error. Searching that message online or opening an [issue](https://github.com/Jacob6925/MusicSearch/issues) with it (remove any personal info) usually gets you unstuck.

---

## For developers

- `app.py` is the Flask app; `scripts/` holds the helper programs it launches (Apple Music via gamdl's API, YouTube via yt-dlp, Spotify and tagging via Harmoni).
- Settings: `.env` (Spotify keys only). Optional environment variables: `PORT` (default 5050), `HARMONI_PATH` (use your own Harmoni checkout instead of `vendor/harmoni`), `FLASK_DEBUG=1`, `MUSICSEARCH_NO_BROWSER=1`.
- Tests: `.venv/bin/python -m unittest discover -s tests` (Windows: `.venv\Scripts\python`). GitHub Actions runs setup, the tests, and a start-up check on Windows, macOS (Apple Silicon) and macOS (Intel).
