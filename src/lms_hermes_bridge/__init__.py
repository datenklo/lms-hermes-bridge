__version__ = "0.4.0"
APP_ID = "io.github.lmshermesbridge"
import os

# Wayland forbids client-side window placement; XWayland lets the overlay sit at the top edge.
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY") and "GDK_BACKEND" not in os.environ:
    os.environ["GDK_BACKEND"] = "x11"