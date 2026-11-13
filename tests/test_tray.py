from pathlib import Path

from gi.repository import GLib

from lms_hermes_bridge.tray import ICON_DIR, ICON_NAME, Tray, WATCHER, has_host


def test_menu_item_has_blue_update_icon_only_when_update_exists():
    available = {"yes": False}
    tray = Tray(lambda: None, [
        (lambda: "Check updates", lambda: None,
         lambda: "update-available" if available["yes"] else None),
    ])
    props = tray._item(1).unpack()[1]
    assert props["label"] == "Check updates" and "icon-name" not in props
    available["yes"] = True
    props = tray._item(1).unpack()[1]
    assert props["icon-name"] == "update-available"


def test_tray_asks_for_the_symbolic_icon_variant():
    # Hosts recolour "-symbolic" icons to the panel's own foreground, which is the only
    # way an icon survives both a light and a dark top bar.
    assert ICON_NAME.endswith("-symbolic")
    assert (Path(ICON_DIR) / f"{ICON_NAME}.svg").is_file()


def test_has_host_is_true_only_for_the_watcher_name():
    class Conn:
        # The real signature is pinned here on purpose: a stub with *args hides a wrong
        # argument count, and Gio.DBusConnection.call answers that with TypeError.
        def __init__(self, names):
            self.names = names
            self.asked = ()

        def call(self, destination, object_path, interface_name, method_name, parameters,
                 reply_type, flags, timeout_msec, cancellable):
            self.asked = (destination, object_path, interface_name, method_name)
            return GLib.Variant("(as)", (self.names,))

    conn = Conn(["org.freedesktop.DBus", WATCHER])
    assert has_host(conn)
    assert conn.asked == ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames")
    # Our own item on the bus proves nothing: a host is the other side of the protocol.
    assert not has_host(Conn(["org.freedesktop.DBus", "org.kde.StatusNotifierItem-3229-1"]))


def test_has_host_is_false_when_the_bus_call_is_unusable():
    class Conn:
        def call(self, destination, object_path, interface_name, method_name, parameters,
                 reply_type, flags, timeout_msec, cancellable):
            raise TypeError("no such method")

    assert not has_host(Conn())
