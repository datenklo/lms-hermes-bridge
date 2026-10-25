import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import updater  # noqa: E402
from .i18n import t  # noqa: E402


class UpdateWindow(Gtk.Window):
    def __init__(self, parent, on_restart):
        super().__init__(title=t("update_title"), transient_for=parent, modal=True)
        self.set_default_size(620, 360)
        self.on_restart = on_restart
        self.set_deletable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14,
                      margin_start=14, margin_end=14)
        self.status = Gtk.Label(label=t("update_checking"), xalign=0, wrap=True)
        self.spinner = Gtk.Spinner(spinning=True)
        heading = Gtk.Box(spacing=8)
        heading.append(self.spinner)
        heading.append(self.status)
        box.append(heading)
        self.buffer = Gtk.TextBuffer()
        log = Gtk.TextView(buffer=self.buffer, editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        box.append(Gtk.ScrolledWindow(child=log, vexpand=True))

        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.restart_button = Gtk.Button(label=t("update_restart"), css_classes=["suggested-action"], visible=False)
        self.restart_button.connect("clicked", lambda *_: self.on_restart())
        self.close_button = Gtk.Button(label=t("close"), sensitive=False)
        self.close_button.connect("clicked", lambda *_: self.close())
        actions.append(self.restart_button)
        actions.append(self.close_button)
        box.append(actions)
        self.set_child(box)
        self.connect("close-request", lambda *_: not self.close_button.get_sensitive())
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result = updater.perform_update(lambda line: GLib.idle_add(self._append, line))
            GLib.idle_add(self._done, result, None)
        except Exception as e:
            GLib.idle_add(self._done, "error", str(e))

    def _append(self, line: str):
        self.buffer.insert(self.buffer.get_end_iter(), line + "\n")
        return False

    def _done(self, result: str, error: str | None):
        self.spinner.set_spinning(False)
        if error:
            self.status.set_text(t("update_failed", error=error))
        elif result == "updated":
            self.status.set_text(t("update_ready"))
            self.restart_button.set_visible(True)
        else:
            self.status.set_text(t("update_current"))
        self.close_button.set_sensitive(True)
        self.set_deletable(True)
        return False
