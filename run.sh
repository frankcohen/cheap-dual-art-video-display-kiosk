#!/usr/bin/env bash
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
exec /usr/bin/python3 -u "$(dirname "$(readlink -f "$0")")/dual_art_kiosk.py"
