"""Registers the global hotkey as a GNOME custom keybinding (works on X11 and Wayland)."""
import shlex
import shutil
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

BASE = "org.gnome.settings-daemon.plugins.media-keys"
PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lms-hermes-bridge/"
KB_SCHEMA = BASE + ".custom-keybinding"
# Schemas whose shortcuts could collide with ours.
CONFLICT_SCHEMAS = (
    "org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings", "org.gnome.mutter.keybindings",
    "org.gnome.mutter.wayland.keybindings", BASE,
)


def launch_command() -> str:
    """The shortcut runs outside any shell session, so it must work without PYTHONPATH."""
    exe = shutil.which("lms-hermes-bridge")
    if exe:
        return exe
    pkg_parent = Path(__file__).resolve().parent.parent
    if "site-packages" in str(pkg_parent) or "dist-packages" in str(pkg_parent):
        return shlex.join([sys.executable, "-m", "lms_hermes_bridge"])
    return shlex.join(["env", f"PYTHONPATH={pkg_parent}", sys.executable, "-m", "lms_hermes_bridge"])


def _norm(accel: str):
    ok, key, mods = Gtk.accelerator_parse(accel)
    return (key, int(mods)) if ok and key else None


def is_valid(accel: str) -> bool:
    return _norm(accel) is not None


def conflicts(accel: str) -> list[str]:
    """Names of other shortcuts that use the same key combination."""
    target = _norm(accel)
    found: list[str] = []
    if target is None:
        return found
    src = Gio.SettingsSchemaSource.get_default()
    for sid in CONFLICT_SCHEMAS:
        schema = src.lookup(sid, True)
        if not schema:
            continue
        settings = Gio.Settings.new(sid)
        for key in schema.list_keys():
            if schema.get_key(key).get_value_type().dup_string() != "as":
                continue
            if any(_norm(a) == target for a in settings.get_strv(key)):
                found.append(f"{sid.rsplit('.', 1)[-1]}: {key}")
    if src.lookup(BASE, True):
        for path in Gio.Settings.new(BASE).get_strv("custom-keybindings"):
            if path == PATH:
                continue
            kb = Gio.Settings.new_with_path(KB_SCHEMA, path)
            if _norm(kb.get_string("binding")) == target:
                found.append(kb.get_string("name") or path)
    return found


def current_binding() -> str | None:
    try:
        if PATH not in Gio.Settings.new(BASE).get_strv("custom-keybindings"):
            return None
        return Gio.Settings.new_with_path(KB_SCHEMA, PATH).get_string("binding")
    except Exception:
        return None


def register(accelerator: str) -> bool:
    try:
        if not Gio.SettingsSchemaSource.get_default().lookup(BASE, True) or not is_valid(accelerator):
            return False
        media = Gio.Settings.new(BASE)
        paths = media.get_strv("custom-keybindings")
        if PATH not in paths:
            media.set_strv("custom-keybindings", paths + [PATH])
        kb = Gio.Settings.new_with_path(KB_SCHEMA, PATH)
        kb.set_string("name", "LMS Hermes Bridge")
        kb.set_string("command", launch_command())
        kb.set_string("binding", accelerator)
        Gio.Settings.sync()
        return True
    except Exception:
        return False


def refresh_command() -> None:
    """Repairs a registered shortcut whose command no longer matches how the app is launched."""
    try:
        if current_binding() is None:
            return
        kb = Gio.Settings.new_with_path(KB_SCHEMA, PATH)
        if kb.get_string("command") != launch_command():
            kb.set_string("command", launch_command())
            Gio.Settings.sync()
    except Exception:
        pass
