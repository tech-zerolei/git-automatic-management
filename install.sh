#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
chmod +x "$ROOT/start.sh"
exec /usr/bin/python3 -B "$ROOT/local_app/install_launcher.py"
