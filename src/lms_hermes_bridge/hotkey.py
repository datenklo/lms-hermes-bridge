"""Registers the global hotkey as a GNOME custom keybinding (works on X11 and Wayland)."""
import shutil
import sys

from gi.repository import Gio

BASE = "org.gnome.settings-daemon.plugins.media-keys"
PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lms-hermes-bridge/"


def launch_command() -> str:
    exe = shutil.which("lms-hermes-bridge")
    return exe or f"{sys.executable} -m lms_hermes_bridge"


def register(accelerator: str) -> bool:
    try:
        schemas = Gio.SettingsSchemaSource.get_default()
        if not schemas.lookup(BASE, True):
            return False
        media = Gio.Settings.new(BASE)
        paths = media.get_strv("custom-keybindings")
        if PATH not in paths:
            media.set_strv("custom-keybindings", paths + [PATH])
        kb = Gio.Settings.new_with_path(BASE + ".custom-keybinding", PATH)
        kb.set_string("name", "LMS Hermes Bridge")
        kb.set_string("command", launch_command())
        kb.set_string("binding", accelerator)
        Gio.Settings.sync()
        return True
    except Exception:
        return False
