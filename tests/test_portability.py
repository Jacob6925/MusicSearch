"""Cross-platform sanity tests. Run with:  python -m unittest discover -s tests -v
Only needs the packages from requirements.txt; no network, no Apple/Spotify account."""
import ntpath
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["MUSICSEARCH_NO_BROWSER"] = "1"

import folder_picker  # noqa: E402
import pathsafe  # noqa: E402


class SafeNameTests(unittest.TestCase):
    def test_windows_forbidden_characters_removed(self):
        self.assertEqual(pathsafe.safe_name('AC/DC: "Hits"? <1> | *'), "ACDC Hits 1")

    def test_slash_replacement(self):
        self.assertEqual(pathsafe.safe_name("AC/DC - Thunder", slash_to="-"), "AC-DC - Thunder")

    def test_trailing_dots_and_spaces(self):
        self.assertEqual(pathsafe.safe_name("Greatest Hits... "), "Greatest Hits")

    def test_reserved_names(self):
        self.assertEqual(pathsafe.safe_name("CON"), "_CON")
        self.assertEqual(pathsafe.safe_name("nul.txt"), "_nul.txt")

    def test_empty_and_long(self):
        self.assertEqual(pathsafe.safe_name("?*"), "Untitled")
        self.assertLessEqual(len(pathsafe.safe_name("x" * 500)), 120)

    def test_emoji_kept(self):
        self.assertEqual(pathsafe.safe_name("HOUSE \U0001F3E0"), "HOUSE \U0001F3E0")


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.app = app

    def test_ini_value_with_windows_path(self):
        text = "a = 1\ncookies_path = __COOKIES_PATH__\nb = 2\n"
        out = self.app._set_ini_value(text, "cookies_path", ntpath.join("C:\\", "Users", "me", "gamdl", "cookies.txt"))
        self.assertIn("cookies_path = C:\\Users\\me\\gamdl\\cookies.txt\n", out)
        self.assertIn("a = 1", out)
        self.assertIn("b = 2", out)

    def test_resolved_gamdl_config_has_absolute_paths(self):
        text = Path(self.app.GAMDL_CONFIG).read_text(encoding="utf-8")
        self.assertIn(f"cookies_path = {self.app._COOKIES_PATH}", text)
        self.assertNotIn("__COOKIES_PATH__", text)

    def test_url_parsing(self):
        p = self.app.parse_playlist_url
        self.assertEqual(p("https://music.apple.com/us/playlist/x/pl.abc123"), ("apple", "pl.abc123"))
        self.assertEqual(p("https://open.spotify.com/playlist/37i9dQZF1DX")[0], "spotify")
        self.assertEqual(p("https://music.youtube.com/playlist?list=PLabc-_1"), ("youtube", "PLabc-_1"))
        self.assertEqual(self.app.parse_song_url("https://youtu.be/dQw4w9WgXcQ"), ("youtube", "dQw4w9WgXcQ"))
        self.assertEqual(p("https://example.com"), (None, None))

    def test_status_endpoint(self):
        data = self.app.app.test_client().get("/api/status").get_json()
        for key in ("apple_music", "spotify", "spotify_login", "default_save_dir", "home_dir"):
            self.assertIn(key, data)

    def test_playlist_name_sanitised(self):
        self.assertEqual(self.app.safe_playlist_name("Mix: 2020?"), "Mix 2020")


class PlaylistStoreTests(unittest.TestCase):
    def test_round_trip_with_emoji(self):
        import playlist_store
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(playlist_store, "STORE_PATH", Path(tmp) / "playlists.json"):
                playlist_store.add_playlist({"id": "1", "platform": "spotify", "title": "\U0001F9D8 Calm",
                                             "folder": str(playlist_store.DOWNLOAD_DIR / "\U0001F9D8 Calm")})
                got = playlist_store.get_playlist("spotify", "1")
                self.assertEqual(got["title"], "\U0001F9D8 Calm")
                self.assertTrue(Path(got["folder"]).is_absolute())


class FolderPickerTests(unittest.TestCase):
    def test_windows_command(self):
        with mock.patch("shutil.which", return_value=r"C:\Windows\System32\powershell.exe"):
            argv, env = folder_picker._build_command("win32", r"C:\Users\me")
        self.assertEqual(env["MUSICSEARCH_START_DIR"], r"C:\Users\me")
        self.assertIn("-STA", argv)
        self.assertNotIn(r"C:\Users\me", " ".join(argv))  # path goes via env, not script text

    def test_mac_command(self):
        argv, env = folder_picker._build_command("darwin", "/Users/me")
        self.assertEqual(argv[0], "osascript")
        self.assertEqual(argv[-1], "/Users/me")


class ScriptHygieneTests(unittest.TestCase):
    """Cheap static guards against re-introducing things that only break on Windows."""

    def py_files(self):
        for p in ROOT.rglob("*.py"):
            parts = set(p.relative_to(ROOT).parts)
            if parts & {".venv", "vendor", "tests", "__pycache__"}:
                continue
            yield p

    def test_no_posix_only_calls(self):
        for p in self.py_files():
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("/dev/null", text, p)
            self.assertNotIn("shell=True", text, p)
            self.assertIsNone(re.search(r"\[\s*[\"']yt-dlp[\"']", text), f"{p}: call yt-dlp via python -m yt_dlp")

    def test_text_subprocess_calls_set_encoding(self):
        for p in self.py_files():
            if p.name in ("setup.py", "folder_picker.py"):
                continue
            for m in re.finditer(r"subprocess\.(?:run|Popen)\((?:[^()]|\([^()]*\))*?text=True(?:[^()]|\([^()]*\))*?\)", p.read_text(encoding="utf-8")):
                self.assertIn("encoding=", m.group(0), f"{p}: text=True without encoding")


if __name__ == "__main__":
    unittest.main()
