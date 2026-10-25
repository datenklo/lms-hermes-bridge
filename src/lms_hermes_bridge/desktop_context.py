"""Capture clipboard selections, images and portal-approved screenshots."""
import base64
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

import gi
from gi.repository import Gio, GLib

MAX_IMAGE_BYTES = 16 * 1024 * 1024
PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
REQUEST_IFACE = "org.freedesktop.portal.Request"


class ContextError(Exception):
    pass


def image_data(data: bytes, mime: str, name: str = "image") -> dict:
    if len(data) > MAX_IMAGE_BYTES:
        raise ContextError(f"Image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    if not mime.startswith("image/"):
        raise ContextError("Selected file is not an image")
    return {"name": name, "mime": mime, "data": base64.b64encode(data).decode("ascii")}


def image_from_path(path: str | Path) -> dict:
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        return image_data(path.read_bytes(), mime, path.name)
    except OSError as e:
        raise ContextError(str(e)) from e


def _read_uri_async(conn, uri: str, name: str, callback) -> None:
    file = Gio.File.new_for_uri(uri)

    def loaded(gfile, result, _data):
        try:
            contents = gfile.load_contents_finish(result)
            if isinstance(contents, tuple):
                if contents and isinstance(contents[0], bool):
                    data = contents[1]
                else:
                    data = contents[0]
            else:
                data = contents
            mime = mimetypes.guess_type(unquote(urlparse(uri).path))[0] or "image/png"
            callback(image_data(data, mime, name), None)
        except Exception as e:
            callback(None, ContextError(str(e)))

    file.load_contents_async(None, loaded, None)


def screenshot(callback) -> None:
    """Ask the desktop portal for a screenshot; user confirms the screen/window capture."""
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        options = {"interactive": GLib.Variant("b", True)}
        params = GLib.Variant("(sa{sv})", ("", options))
    except Exception as e:
        callback(None, ContextError(str(e)))
        return

    def request_ready(connection, result, _data):
        try:
            handle = connection.call_finish(result).unpack()[0]
        except Exception as e:
            callback(None, ContextError(str(e)))
            return

        def response(_conn, _sender, _path, _iface, _signal, signal_params, _user):
            code, values = signal_params.unpack()
            connection.signal_unsubscribe(subscription)
            if code != 0:
                callback(None, ContextError("Screenshot cancelled"))
                return
            uri = values.get("uri")
            if not uri:
                callback(None, ContextError("Screenshot portal returned no image"))
                return
            name = unquote(urlparse(uri).path.rsplit("/", 1)[-1]) or "screenshot.png"
            _read_uri_async(connection, uri, name, callback)

        subscription = connection.signal_subscribe(
            PORTAL, REQUEST_IFACE, "Response", handle, None, Gio.DBusSignalFlags.NONE, response, None
        )

    conn.call(PORTAL, PORTAL_PATH, SCREENSHOT_IFACE, "Screenshot", params,
              GLib.VariantType.new("(o)"), Gio.DBusCallFlags.NONE, -1, None, request_ready, None)
