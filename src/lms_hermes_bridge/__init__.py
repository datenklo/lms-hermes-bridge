__version__ = "0.5.0"
APP_ID = "io.github.lmshermesbridge"
import os

from .session import wants_layer_shell

# Wayland forbids client-side window placement, so the overlay normally runs through
# XWayland, where X11 still allows moving the window. Compositors that hand the
# layer-shell protocol to ordinary clients (Hyprland, Sway, …) place the overlay without
# that detour, and layer-shell needs the native Wayland surface — so there the backend is
# left alone. LMS_BRIDGE_PLACEMENT overrides the choice before the config file is read.
_placement = os.environ.get("LMS_BRIDGE_PLACEMENT", "auto")
if (os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY")
        and "GDK_BACKEND" not in os.environ
        and not wants_layer_shell(os.environ, _placement)):
    os.environ["GDK_BACKEND"] = "x11"