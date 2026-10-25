"""System tray icon via the StatusNotifierItem D-Bus protocol (no extra dependencies).

Left click -> Activate (show overlay), right click -> dbusmenu with the given items.
GNOME needs the AppIndicator/KStatusNotifierItem extension, which Ubuntu ships by default.
"""
import os
from pathlib import Path

from gi.repository import Gio, GLib

ICON_DIR = str(Path(__file__).parent / "icons")
ICON_NAME = "lms-hermes-bridge-brain"
OBJ_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
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

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <method name="GetLayout">
      <arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
      <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/>
    </method>
    <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
    <method name="AboutToShowGroup">
      <arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/>
    </method>
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
  </interface>
</node>
"""


class Tray:
    def __init__(self, on_activate, items):
        """items: (label, callback[, icon-name]) callables for the right-click menu."""
        self.on_activate = on_activate
        self.items = items
        self.conn = None
        self.layout_revision = 1
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
            "Menu": GLib.Variant("o", MENU_PATH),
        }

    def start(self):
        self.conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
        self.conn.register_object(OBJ_PATH, info, self._on_call, self._on_get, None)
        menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.conn.register_object(MENU_PATH, menu_info, self._on_menu_call, self._on_menu_get, None)
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
        invocation.return_value(None)

    # -- dbusmenu ------------------------------------------------------
    def _item(self, idx: int):
        label, _cb, *icon_getter = self.items[idx - 1]
        props = {"label": GLib.Variant("s", label())}
        if icon_getter:
            icon = icon_getter[0]()
            if icon:
                props["icon-name"] = GLib.Variant("s", icon)
        return GLib.Variant("(ia{sv}av)", (idx, props, []))

    def notify_layout_changed(self):
        if self.conn is None:
            return
        self.layout_revision += 1
        self.conn.emit_signal(None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
                              GLib.Variant("(ui)", (self.layout_revision, 0)))

    def _on_menu_get(self, _c, _sender, _path, _iface, prop):
        return {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }.get(prop)

    def _on_menu_call(self, _c, _sender, _path, _iface, method, params, invocation):
        if method == "GetLayout":
            root = GLib.Variant("(ia{sv}av)", (
                0, {"children-display": GLib.Variant("s", "submenu")},
                [self._item(i) for i in range(1, len(self.items) + 1)]))
            invocation.return_value(GLib.Variant.new_tuple(GLib.Variant("u", 1), root))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0] or list(range(1, len(self.items) + 1))
            out = []
            for i in ids:
                if not 1 <= i <= len(self.items):
                    continue
                label, _callback, *icon_getter = self.items[i - 1]
                props = {"label": GLib.Variant("s", label())}
                if icon_getter and (icon := icon_getter[0]()):
                    props["icon-name"] = GLib.Variant("s", icon)
                out.append((i, props))
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (out,)))
        elif method == "GetProperty":
            invocation.return_value(GLib.Variant("(v)", (GLib.Variant("s", ""),)))
        elif method == "Event":
            idx, event, _data, _ts = params.unpack()
            if event == "clicked" and 1 <= idx <= len(self.items):
                GLib.idle_add(self.items[idx - 1][1])
            invocation.return_value(None)
        elif method == "EventGroup":
            for idx, event, _data, _ts in params.unpack()[0]:
                if event == "clicked" and 1 <= idx <= len(self.items):
                    GLib.idle_add(self.items[idx - 1][1])
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            invocation.return_value(None)
