"""System tray icon via the StatusNotifierItem D-Bus protocol (no extra dependencies).

Left click -> Activate (toggle overlay), right click -> ContextMenu (open settings).
GNOME needs the AppIndicator/KStatusNotifierItem extension, which Ubuntu ships by default.
"""
import os
from pathlib import Path

from gi.repository import Gio, GLib

ICON_DIR = str(Path(__file__).parent / "icons")
ICON_NAME = "lms-hermes-bridge-brain"
OBJ_PATH = "/StatusNotifierItem"
WATCHER = "org.kde.StatusNotifierWatcher"

XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
    <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="WindowId" type="u" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
  </interface>
</node>
"""


class Tray:
    def __init__(self, on_activate, on_context_menu):
        self.on_activate = on_activate
        self.on_context_menu = on_context_menu
        self.conn = None
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self.props = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "lms-hermes-bridge"),
            "Title": GLib.Variant("s", "LMS Hermes Bridge"),
            "Status": GLib.Variant("s", "Active"),
            "WindowId": GLib.Variant("u", 0),
            "IconName": GLib.Variant("s", ICON_NAME),
            "IconThemePath": GLib.Variant("s", ICON_DIR),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", "/NO_DBUSMENU"),
        }

    def start(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        self.conn.register_object(OBJ_PATH, info, self._on_call, self._on_get, None)
        Gio.bus_own_name_on_connection(self.conn, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
        # Register (again) whenever the tray host appears, e.g. after a shell restart.
        Gio.bus_watch_name_on_connection(self.conn, WATCHER, Gio.BusNameWatcherFlags.NONE, self._register, None)

    def _register(self, conn, *_):
        conn.call(WATCHER, "/StatusNotifierWatcher", WATCHER, "RegisterStatusNotifierItem",
                  GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, -1, None, None, None)

    def _on_get(self, _c, _sender, _path, _iface, prop):
        return self.props.get(prop)

    def _on_call(self, _c, _sender, _path, _iface, method, _params, invocation):
        if method == "Activate":
            GLib.idle_add(self.on_activate)
        elif method in ("ContextMenu", "SecondaryActivate"):
            GLib.idle_add(self.on_context_menu)
        invocation.return_value(None)
