import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__, config as cfgmod, lmstudio, providers, router  # noqa: E402
from .i18n import set_language, t  # noqa: E402
from .settings_dialog import SettingsWindow  # noqa: E402
from .tray import ICON_DIR, Tray  # noqa: E402

GITHUB_URL = "https://github.com/datenklo/lms-hermes-bridge"

CSS = b"""
window.bridge { background: alpha(@window_bg_color, 0.97); border-radius: 18px;
  border: 1px solid alpha(@borders, 0.8); }
entry.query { font-size: 18px; padding: 10px 14px; }
label.route { opacity: 0.6; font-size: 11px; }
textview.answer { font-size: 14px; padding: 8px; background: transparent; }
"""

SYSTEM_PROMPT = "You are a concise, helpful desktop assistant on Ubuntu Linux."


class BridgeWindow(Gtk.ApplicationWindow):
    def __init__(self, app, cfg):
        super().__init__(application=app, decorated=False, resizable=False)
        self.cfg = cfg
        self.cancel = threading.Event()
        self.add_css_class("bridge")
        self.set_default_size(720, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=10, margin_bottom=10,
                      margin_start=10, margin_end=10)
        self.entry = Gtk.Entry(css_classes=["query"])
        self.entry.connect("activate", self._submit)
        box.append(self.entry)

        self.route_label = Gtk.Label(xalign=0, css_classes=["route"], wrap=True, visible=False)
        box.append(self.route_label)

        self.buf = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self.buf, editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            css_classes=["answer"])
        self.scroller = Gtk.ScrolledWindow(child=view, min_content_height=260, visible=False)
        box.append(self.scroller)
        self.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        # Right-click anywhere opens the settings menu.
        click = Gtk.GestureClick(button=3)
        click.connect("pressed", self._on_right_click)
        box.add_controller(click)

        menu = Gio.Menu()
        menu.append(t("settings"), "app.settings")
        menu.append(t("about"), "app.about")
        menu.append(t("quit"), "app.quit")
        self.popover = Gtk.PopoverMenu.new_from_model(menu)
        self.popover.set_parent(box)
        self.popover.set_has_arrow(False)
        self.entry.set_placeholder_text(t("placeholder"))

        self.connect("notify::is-active", self._on_active)

    def _on_active(self, *_):
        # Behave like a launcher: dismiss when focus moves elsewhere.
        if not self.is_active():
            GLib.timeout_add(150, self._hide_if_inactive)

    def _hide_if_inactive(self):
        settings_open = any(isinstance(w, SettingsWindow) and w.get_visible()
                            for w in self.get_application().get_windows())
        if not self.is_active() and self.get_visible() and not settings_open:
            self.cancel.set()
            self.hide()
        return False

    def _on_key(self, _c, keyval, *_):
        if keyval == Gdk.KEY_Escape:
            self.cancel.set()
            self.hide()
            return True
        return False

    def _on_right_click(self, _g, _n, x, y):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.popover.set_pointing_to(rect)
        self.popover.popup()

    def show_overlay(self):
        self.present()
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    # -- query flow -----------------------------------------------------
    def _submit(self, *_):
        prompt = self.entry.get_text().strip()
        if not prompt:
            return
        self.cancel.set()  # stop any previous stream
        self.cancel = threading.Event()
        self.buf.set_text("")
        self.scroller.set_visible(True)
        self._status(t("thinking"))
        threading.Thread(target=self._worker, args=(prompt, self.cancel), daemon=True).start()

    def _status(self, text: str):
        self.route_label.set_text(text)
        self.route_label.set_visible(bool(text))

    def _append(self, text: str, cancel: threading.Event):
        if not cancel.is_set():
            self.buf.insert(self.buf.get_end_iter(), text)
        return False

    def _ui(self, fn, *a):
        GLib.idle_add(fn, *a)

    def _worker(self, prompt: str, cancel: threading.Event):
        cfg = self.cfg
        models = lmstudio.list_models(cfg["lmstudio"]["url"])
        route = router.decide(prompt, cfg, models, lmstudio.mem_total_bytes())
        if route is None:
            key = "err_local_only" if cfg["local_only"] else "err_no_target"
            self._ui(self._status, t(key))
            return
        try:
            if route.backend == "lmstudio" and route.needs_load and cfg["lmstudio"]["auto_load"]:
                self._ui(self._status, t("loading_model", model=route.model))
                lmstudio.load_model(route.model, route.params["context"], cfg["lmstudio"]["unload_others"])
            backend = {"lmstudio": "LM Studio", "hermes": "Hermes"}.get(route.backend, "API")
            self._ui(self._status, t("route_label", backend=backend, model=route.model,
                                     tier=t("tier_" + route.tier), reason=route.reason))
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
            for chunk in self._stream(route, messages):
                if cancel.is_set():
                    return
                self._ui(self._append, chunk, cancel)
        except providers.ChatError as e:
            self._ui(self._append, f"\n[{t('err_generic')}] {e}", cancel)

    def _stream(self, route: router.Route, messages: list):
        cfg = self.cfg
        if route.backend == "lmstudio":
            endpoint = cfg["lmstudio"]["url"].rstrip("/") + "/v1/chat/completions"
            return providers.stream("openai", endpoint, "", route.model, messages, route.params)
        if route.backend == "hermes":
            h = cfg["hermes"]
            return providers.stream("openai", h["endpoint"], h["api_key"], h["model"], messages, {})
        p = next(p for p in cfg["providers"] if p["id"] == route.provider_id)
        return providers.stream(p["kind"], p["endpoint"], p["api_key"], p["model"], messages,
                                router.TIER_PARAMS[route.tier])


class BridgeApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.cfg = cfgmod.load()
        self.win: BridgeWindow | None = None
        self.add_main_option("background", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Start hidden", None)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        set_language(self.cfg["language"])
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for name, cb in (("settings", self.open_settings), ("about", self.open_about),
                         ("quit", lambda *_: self.quit())):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", cb)
            self.add_action(act)
        self.hold()  # stay alive while the overlay is hidden
        try:
            self.tray = Tray(self._tray_toggle, [(lambda: t("settings"), self.open_settings),
                                           (lambda: t("about"), self.open_about),
                                           (lambda: t("quit"), self.quit)])
            self.tray.start()
        except Exception:
            self.tray = None  # no D-Bus session: run without tray icon

    def _tray_toggle(self):
        self._ensure_window()
        self.win.show_overlay()

    def _ensure_window(self):
        if self.win is None:
            self.win = BridgeWindow(self, self.cfg)

    def do_command_line(self, cl):
        self._ensure_window()
        opts = cl.get_options_dict().end().unpack()
        if "background" not in opts:
            self.toggle()
        return 0

    def toggle(self):
        if self.win.get_visible() and self.win.is_active():
            self.win.hide()
        else:
            self.win.show_overlay()

    def open_settings(self, *_):
        self._ensure_window()
        SettingsWindow(self.win, self.cfg, self._reload).present()

    def open_about(self, *_):
        self._ensure_window()
        dlg = Gtk.AboutDialog(
            transient_for=self.win, modal=True, program_name="LMS Hermes Bridge", version=__version__,
            comments=t("about_comments"), website=GITHUB_URL, website_label="GitHub",
            license_type=Gtk.License.MIT_X11, copyright="© 2026 datenklo",
        )
        try:
            dlg.set_logo(Gdk.Texture.new_from_filename(f"{ICON_DIR}/lms-hermes-bridge-brain.svg"))
        except GLib.Error:
            pass
        dlg.present()

    def _reload(self):
        set_language(self.cfg["language"])
        old = self.win
        self.win = BridgeWindow(self, self.cfg)
        old.destroy()
        self.win.show_overlay()


def main() -> int:
    return BridgeApp().run(sys.argv)
