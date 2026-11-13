"""Which window-placement backend this session can offer. Pure logic: no GTK, no D-Bus.

Wayland forbids clients from positioning their own windows. Two ways out:

* layer-shell — the protocol panels use. wlroots compositors (Hyprland, Sway, river,
  labwc, Wayfire, niri) hand it to any client. GNOME and KWin reserve it for their own
  panels, so an ordinary app does not get a layer surface there.
* XWayland — the X11 protocol still lets the client move its own window, so the overlay
  runs through XWayland on desktops without usable layer-shell.

The desktop names are a heuristic (what those sessions put into XDG_CURRENT_DESKTOP); the
compositor-specific environment variables are the reliable signal.
"""
import os
from pathlib import Path

LAYER_SHELL_SESSIONS = {"hyprland", "sway", "river", "labwc", "wayfire", "niri", "cage"}
PLACEMENTS = ("auto", "layer-shell", "x11", "none")
TYPELIB = "Gtk4LayerShell-1.0.typelib"
TYPELIB_DIRS = ("/usr/lib/girepository-1.0", "/usr/lib64/girepository-1.0",
                "/usr/local/lib/girepository-1.0", "/usr/lib/x86_64-linux-gnu/girepository-1.0")


def layer_shell_available() -> bool:
    """True when the gtk4-layer-shell typelib is installed, without importing gi."""
    extra = (os.environ.get("GI_TYPELIB_PATH") or "").split(os.pathsep)
    for directory in TYPELIB_DIRS + tuple(d for d in extra if d):
        if Path(directory, TYPELIB).is_file():
            return True
    return False


def choose_backend(env: dict, config: str = "auto") -> str:
    """Return 'layer-shell', 'x11' or 'none' for the given environment.

    config lets the user override the decision (settings dialog: "Fensterplatzierung").
    An unknown value falls back to 'auto' instead of failing on a typo in the JSON.
    """
    if config not in PLACEMENTS:
        config = "auto"
    if config != "auto":
        return config
    if (env.get("XDG_SESSION_TYPE") or "").lower() != "wayland":
        return "x11"
    if env.get("HYPRLAND_INSTANCE_SIGNATURE") or env.get("SWAYSOCK"):
        return "layer-shell" if layer_shell_available() else "x11"
    names = {n.strip().lower() for n in (env.get("XDG_CURRENT_DESKTOP") or "").split(":") if n.strip()}
    names.add((env.get("XDG_SESSION_DESKTOP") or "").strip().lower())
    if names & LAYER_SHELL_SESSIONS:
        return "layer-shell" if layer_shell_available() else "x11"
    return "x11" if env.get("DISPLAY") else "none"


def wants_layer_shell(env: dict, config: str = "auto") -> bool:
    return choose_backend(env, config) == "layer-shell"
