"""Places the overlay near the top centre of the screen.

Wayland compositors forbid client-side placement, so there are two backends (see
session.py): the layer-shell protocol on compositors that give it to ordinary clients,
and X11/XWayland everywhere else, where the X11 protocol still allows XMoveWindow.
"""
import ctypes
import os
import sys

import gi

gi.require_version("Gdk", "4.0")
try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
except (ValueError, ImportError):
    GdkX11 = None

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
except (ValueError, ImportError):
    Gtk4LayerShell = None

from .session import choose_backend  # noqa: E402

TOP_MARGIN = 72  # logical px below the top edge, clears the GNOME top bar


class _ClientMessageData(ctypes.Union):
    _fields_ = [("b", ctypes.c_char * 20), ("s", ctypes.c_short * 10), ("l", ctypes.c_long * 5)]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p), ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int), ("data", _ClientMessageData),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [("type", ctypes.c_int), ("xclient", _XClientMessageEvent), ("pad", ctypes.c_long * 24)]


def move_to_top(window, keep_above: bool = False, backend: str = "auto") -> None:
    """Place the overlay near the top edge with whichever backend this session allows."""
    if choose_backend(os.environ, backend) == "layer-shell" and _place_layer_shell(window):
        return
    _x11_move_to_top(window, keep_above)


def _place_layer_shell(window) -> bool:
    """Anchor the window to the top layer; True when the compositor gave us a surface.

    Anchoring top+start+end spans the usable width and lets the window centre its content,
    which is how every panel does it. init_for_window has to run before the first map, so
    this is called from show_overlay, not from a map handler.
    """
    if Gtk4LayerShell is None:
        return False
    if getattr(window, "_layer_shell_done", False):
        return True
    try:
        Gtk4LayerShell.init_for_window(window)
        Gtk4LayerShell.set_layer(window, Gtk4LayerShell.Layer.TOP)
        for edge in (Gtk4LayerShell.Edge.TOP, Gtk4LayerShell.Edge.START, Gtk4LayerShell.Edge.END):
            Gtk4LayerShell.set_anchor(window, edge, True)
        Gtk4LayerShell.set_margin(window, Gtk4LayerShell.Edge.TOP, TOP_MARGIN)
        Gtk4LayerShell.set_keyboard_mode(window, Gtk4LayerShell.KeyboardMode.ON_DEMAND)
    except Exception as error:  # compositor without the protocol, or a renamed symbol
        print(f"layer-shell placement failed, falling back: {error}", file=sys.stderr)
        return False
    window._layer_shell_done = True
    return True


def _x11_move_to_top(window, keep_above: bool = False) -> None:
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
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    xlib.XInternAtom.restype = ctypes.c_ulong
    xlib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
                                ctypes.POINTER(_XEvent)]
    xlib.XSendEvent.restype = ctypes.c_int
    xlib.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    dpy = xlib.XOpenDisplay(None)
    if not dpy:
        return
    xid = surface.get_xid()
    xlib.XMoveWindow(dpy, xid, x, y)
    if keep_above:
        state = xlib.XInternAtom(dpy, b"_NET_WM_STATE", 0)
        above = xlib.XInternAtom(dpy, b"_NET_WM_STATE_ABOVE", 0)
        event = _XEvent()
        event.xclient.type = 33  # ClientMessage
        event.xclient.send_event = 1
        event.xclient.display = dpy
        event.xclient.window = xid
        event.xclient.message_type = state
        event.xclient.format = 32
        event.xclient.data.l[0] = 1  # _NET_WM_STATE_ADD
        event.xclient.data.l[1] = above
        event.xclient.data.l[3] = 1  # application request
        root = xlib.XDefaultRootWindow(dpy)
        xlib.XSendEvent(dpy, root, 0, (1 << 20) | (1 << 19), ctypes.byref(event))
        xlib.XRaiseWindow(dpy, xid)
    xlib.XFlush(dpy)
    xlib.XCloseDisplay(dpy)
