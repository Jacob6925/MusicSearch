#!/bin/bash
# macOS: run ./setup.command in Terminal, or double-click it in Finder.
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo
  echo "Python 3.10 or newer was not found."
  echo "Install it from https://www.python.org/downloads/ (the macOS installer),"
  echo "then close this window and run setup again."
  [ -z "$MUSICSEARCH_CI" ] && read -r -p "Press Enter to close..." _
  exit 1
fi

"$PY" setup.py "$@"
rc=$?
[ -z "$MUSICSEARCH_CI" ] && read -r -p "Press Enter to close..." _
exit $rc
