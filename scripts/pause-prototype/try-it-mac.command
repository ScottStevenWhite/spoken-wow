#!/bin/bash
# Double-click to try the Spoken pause prototype. Needs Python 3 and ffmpeg (see TRY-IT.md).
cd "$(dirname "$0")"
python3 spoken_pause.py "$@"
echo
read -n 1 -s -r -p "Press any key to close this window"
