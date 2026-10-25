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


def move_to_top(window, keep_above: bool = False) -> None:
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
