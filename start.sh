#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! test -x /usr/bin/python3 || ! test -x /usr/bin/git || ! test -x /usr/bin/bwrap; then
    printf '%s\n' '需要 /usr/bin/python3、/usr/bin/git 和 /usr/bin/bwrap；不进行不隔离读取。' >&2
    exit 1
fi
exec /usr/bin/python3 -B "$ROOT/local_app/server.py" "$@"
