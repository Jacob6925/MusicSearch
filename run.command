#!/bin/bash
# macOS: run ./run.command in Terminal, or double-click it in Finder.
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo
  echo "MusicSearch is not set up yet. Run ./setup.command first."
  [ -z "$MUSICSEARCH_CI" ] && read -r -p "Press Enter to close..." _
  exit 1
fi

.venv/bin/python app.py "$@"
rc=$?
if [ $rc -ne 0 ] && [ -z "$MUSICSEARCH_CI" ]; then
  echo
  read -r -p "MusicSearch stopped with an error. Press Enter to close..." _
fi
exit $rc
