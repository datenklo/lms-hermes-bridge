import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import installer  # noqa: E402
from .i18n import t  # noqa: E402


class InstallWindow(Gtk.Window):
    def __init__(self, parent, name: str, on_finished):
        label = installer.NAMES[name]
        super().__init__(title=t("installing", name=label), transient_for=parent, modal=True)
        self.set_default_size(640, 360)
        self.set_application(Gtk.Application.get_default())
        self.name = name
        self.on_finished = on_finished

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10,
                      margin_start=10, margin_end=10)
        self.status = Gtk.Label(label=t("installing", name=label), xalign=0)
        self.spinner = Gtk.Spinner(spinning=True)
        head = Gtk.Box(spacing=8)
        head.append(self.spinner)
        head.append(self.status)
        box.append(head)

        self.buf = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self.buf, editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        box.append(Gtk.ScrolledWindow(child=view, vexpand=True))

        self.close_btn = Gtk.Button(label=t("close"), halign=Gtk.Align.END, sensitive=False)
        self.close_btn.connect("clicked", lambda *_: self.close())
        box.append(self.close_btn)
        self.set_child(box)
        self.set_deletable(False)
        self.connect("close-request", lambda *_: not self.close_btn.get_sensitive())

        installer.run(name, lambda s: GLib.idle_add(self._line, s), lambda c: GLib.idle_add(self._done, c))

    def _line(self, text: str):
        self.buf.insert(self.buf.get_end_iter(), text)
        return False

    def _done(self, code: int):
        label = installer.NAMES[self.name]
        self.spinner.set_spinning(False)
        if code == 0:
            msg = t("install_done", name=label)
            if self.name == "hermes":
                msg += " " + t("hermes_next")
        else:
            msg = t("install_failed", name=label, code=code)
        self.status.set_text(msg)
        self.status.set_wrap(True)
        self.close_btn.set_sensitive(True)
        self.set_deletable(True)
        self.connect("destroy", lambda *_: self.on_finished())
        return False
