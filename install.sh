#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

pipx install --system-site-packages --force .
pipx ensurepath >/dev/null

mkdir -p "$HOME/.local/share/applications" \
	"$HOME/.local/share/icons/hicolor/scalable/apps"

desktop_entry="$HOME/.local/share/applications/io.github.lmshermesbridge.desktop"
sed "s|@EXEC@|\"$HOME/.local/bin/lms-hermes-bridge\"|" \
	data/io.github.lmshermesbridge.desktop.in > "$desktop_entry"
cp src/lms_hermes_bridge/icons/lms-hermes-bridge-brain.svg \
	"$HOME/.local/share/icons/hicolor/scalable/apps/io.github.lmshermesbridge.svg"
chmod 644 "$desktop_entry" "$HOME/.local/share/icons/hicolor/scalable/apps/io.github.lmshermesbridge.svg"
if command -v desktop-file-validate >/dev/null; then
	desktop-file-validate "$desktop_entry"
fi
if command -v update-desktop-database >/dev/null; then
	update-desktop-database "$HOME/.local/share/applications" >/dev/null
fi

PATH="$HOME/.local/bin:$PATH" PYTHONPATH=src /usr/bin/python3 - <<'PY'
from lms_hermes_bridge import autostart, config
autostart.set_enabled(config.load()["start_on_login"])
PY

# Register the default hotkey (GNOME custom shortcut).
PATH="$HOME/.local/bin:$PATH" PYTHONPATH=src /usr/bin/python3 - <<'PY'
from lms_hermes_bridge import hotkey
print("hotkey registered" if hotkey.register("<Control><Alt>space") else "hotkey registration failed")
PY
