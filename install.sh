#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if command -v pacman >/dev/null 2>&1; then
	packages=(python python-gobject gtk4 python-pipx xorg-xwayland libx11 gnome-terminal xdg-desktop-portal-gnome gnome-shell-extension-appindicator curl git)
	missing=()
	for package in "${packages[@]}"; do
		pacman -Qq "$package" >/dev/null 2>&1 || missing+=("$package")
	done
	install_command=(sudo pacman -S --needed -- "${missing[@]}")
elif command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1; then
	packages=(python3 python3-venv python3-gi gir1.2-gtk-4.0 pipx xwayland libx11-6 gnome-terminal xdg-desktop-portal-gnome gnome-shell-extension-appindicator curl git)
	missing=()
	for package in "${packages[@]}"; do
		[[ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)" == installed ]] || missing+=("$package")
	done
	install_command=(sudo apt-get install -- "${missing[@]}")
else
	printf 'Unsupported package manager. Install the system dependencies listed in the README first.\n' >&2
	exit 1
fi

if (( ${#missing[@]} )); then
	printf 'Missing system packages: %s\n' "${missing[*]}"
	printf 'Install with:'
	printf ' %q' "${install_command[@]}"
	printf '\nContinue? [y/N] '
	read -r answer || answer=""
	if [[ "$answer" != [yY] && "$answer" != [yY][eE][sS] ]]; then
		printf 'Installation cancelled.\n' >&2
		exit 1
	fi
	"${install_command[@]}"
fi

pipx install --system-site-packages --force .
pipx ensurepath >/dev/null

mkdir -p "$HOME/.local/share/applications" \
	"$HOME/.local/share/icons/hicolor/scalable/apps"

desktop_entry="$HOME/.local/share/applications/io.github.lmshermesbridge.desktop"
sed "s|@EXEC@|\"$HOME/.local/bin/lms-hermes-bridge\"|" \
	data/io.github.lmshermesbridge.desktop.in > "$desktop_entry"
cp src/lms_hermes_bridge/icons/lms-hermes-bridge-brain.svg \
	"$HOME/.local/share/icons/hicolor/scalable/apps/io.github.lmshermesbridge.svg"
# The tray asks for the symbolic variant by name; having it in the theme as well covers
# hosts that ignore the IconThemePath the app advertises.
mkdir -p "$HOME/.local/share/icons/hicolor/symbolic/apps"
cp src/lms_hermes_bridge/icons/lms-hermes-bridge-brain-symbolic.svg \
	"$HOME/.local/share/icons/hicolor/symbolic/apps/"
chmod 644 "$HOME/.local/share/icons/hicolor/symbolic/apps/lms-hermes-bridge-brain-symbolic.svg"
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

if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]] && command -v gnome-extensions >/dev/null; then
	indicator="appindicatorsupport@rgcjonas.gmail.com"
	if ! gnome-extensions list --enabled | grep -Fxq "$indicator"; then
		printf '\nThe GNOME AppIndicator extension is not enabled. The tray icon needs a StatusNotifier host.\n'
		if ! gnome-extensions list | grep -Fxq "$indicator"; then
			printf 'Arch/CachyOS: sudo pacman -S gnome-shell-extension-appindicator\n'
			printf 'Ubuntu: sudo apt install gnome-shell-extension-appindicator\n'
			printf 'Then run: gnome-extensions enable %s\n' "$indicator"
		elif [[ -t 0 ]]; then
			# Installed but disabled: that is the usual state on Arch and CachyOS, and
			# enabling it is one command, so ask instead of leaving the user to find it.
			printf 'The extension is installed but disabled. Enable it now? [Y/n] '
			read -r answer || answer=""
			case "$answer" in
				[nN]*) printf 'Left it off: no tray icon, the overlay menu button and Ctrl+, reach the settings instead.\n' ;;
				*) gnome-extensions enable "$indicator" \
					&& printf 'Enabled. The icon appears once the shell reloaded the extensions.\n' ;;
			esac
		else
			printf 'Then run: gnome-extensions enable %s\n' "$indicator"
		fi
		printf 'If the extension is not found after installation, log out and back in first.\n'
	fi
fi
