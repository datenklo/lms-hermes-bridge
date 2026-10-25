"""Places the overlay at the top centre of the screen.

Wayland compositors do not let clients position windows, so the app runs through
XWayland (see __init__.py) and moves its X11 window directly.
"""
import ctypes

import gi

gi.require_version("Gdk", "4.0")
try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
except (ValueError, ImportError):
    GdkX11 = None

TOP_MARGIN = 72  # logical px below the top edge, clears the GNOME top bar


def move_to_top(window) -> None:
    surface = window.get_surface()
    if GdkX11 is None or not isinstance(surface, GdkX11.X11Surface):
        return
    monitor = window.get_display().get_monitor_at_surface(surface)
    if monitor is None:
        return
    geo = monitor.get_geometry()
    scale = surface.get_scale_factor()
    x = (geo.x + max(0, (geo.width - window.get_width()) // 2)) * scale
    y = (geo.y + TOP_MARGIN) * scale

    xlib = ctypes.CDLL("libX11.so.6")
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XMoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]
    xlib.XFlush.argtypes = [ctypes.c_void_p]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        return
    xlib.XMoveWindow(dpy, surface.get_xid(), x, y)
    xlib.XFlush(dpy)
    xlib.XCloseDisplay(dpy)
