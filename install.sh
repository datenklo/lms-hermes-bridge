#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

pipx install --system-site-packages --force .
pipx ensurepath >/dev/null

mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/lms-hermes-bridge.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=LMS Hermes Bridge
Exec=$HOME/.local/bin/lms-hermes-bridge --background
X-GNOME-Autostart-enabled=true
EOF

# Register the default hotkey (GNOME custom shortcut).
PATH="$HOME/.local/bin:$PATH" python3 - <<'PY'
from lms_hermes_bridge import hotkey
print("hotkey registered" if hotkey.register("<Control><Alt>space") else "hotkey registration failed")
PY
