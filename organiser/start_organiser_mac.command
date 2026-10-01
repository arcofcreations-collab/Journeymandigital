#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then echo "Python 3 is needed: install from https://www.python.org/downloads/ then run this again."; read -n1; exit 1; fi
(sleep 1.5; open http://127.0.0.1:8765) &
python3 -m msgorg.web
