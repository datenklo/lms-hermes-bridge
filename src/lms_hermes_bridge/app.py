import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__, config as cfgmod, installer, lmstudio, providers, router  # noqa: E402
from .i18n import set_language, t  # noqa: E402
from .install_window import InstallWindow  # noqa: E402
from .settings_dialog import SettingsWindow  # noqa: E402
from .tray import ICON_DIR, Tray  # noqa: E402

GITHUB_URL = "https://github.com/datenklo/lms-hermes-bridge"

CSS = b"""
window.bridge { background: @window_bg_color; border-radius: 20px; border: 1px solid alpha(@borders, 0.6); }
window.bridge entry.query { background: transparent; border: none; box-shadow: none; outline: none;
  font-size: 20px; min-height: 28px; padding: 14px 18px; }
window.bridge entry.query image { opacity: 0.45; }
window.bridge separator { opacity: 0.3; }
window.bridge label.route { font-size: 11px; opacity: 0.55; padding: 2px 18px 6px 18px; }
window.bridge textview.answer, window.bridge textview.answer text { background: transparent; font-size: 15px; }
window.bridge textview.answer { padding: 6px 14px 16px 14px; }
window.bridge popover > contents { border-radius: 12px; }

window.settings { background: @window_bg_color; }
window.settings notebook > header { background: transparent; border: none; padding: 8px 10px 0 10px; }
window.settings notebook > header tab { border-radius: 8px; padding: 6px 14px; margin: 0 2px; border: none; }
window.settings notebook > header tab:checked { background: alpha(@accent_bg_color, 0.15); }
window.settings notebook > stack { background: transparent; }
window.settings entry, window.settings dropdown > button { border-radius: 8px; }
window.settings button { border-radius: 8px; padding: 6px 16px; }
window.settings frame { border-radius: 12px; border: 1px solid alpha(@borders, 0.6); }
window.settings textview { border-radius: 8px; padding: 8px; font-size: 13px; }
window.settings scrolledwindow { border-radius: 10px; border: 1px solid alpha(@borders, 0.5); }
"""

SYSTEM_PROMPT = "You are a concise, helpful desktop assistant on Ubuntu Linux."


class BridgeWindow(Gtk.ApplicationWindow):
    def __init__(self, app, cfg):
        super().__init__(application=app, decorated=False, resizable=False)
        self.cfg = cfg
        self.cancel = threading.Event()
        self.add_css_class("bridge")
        self.set_default_size(720, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, margin_top=4, margin_bottom=4,
                      margin_start=4, margin_end=4)
        self.entry = Gtk.Entry(css_classes=["query"])
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.entry.connect("activate", self._submit)
        box.append(self.entry)

        result = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        result.append(Gtk.Separator())
        self.route_label = Gtk.Label(xalign=0, css_classes=["route"], wrap=True, visible=False)
        result.append(self.route_label)

        self.buf = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=self.buf, editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                            css_classes=["answer"])
        self.scroller = Gtk.ScrolledWindow(child=view, min_content_height=160, max_content_height=420,
                                           propagate_natural_height=True)
        result.append(self.scroller)
        self.answer_revealer = Gtk.Revealer(child=result, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        box.append(self.answer_revealer)
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
        self.answer_revealer.set_reveal_child(True)
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
        first = self.win is None
        self._ensure_window()
        if first:
            threading.Thread(target=self._scan_components, daemon=True).start()
        opts = cl.get_options_dict().end().unpack()
        if "background" not in opts:
            self.toggle()
        return 0

    def _scan_components(self):
        GLib.idle_add(self._offer, installer.missing(self.cfg))

    def _offer(self, queue: list):
        if not queue:
            return False
        name, rest = queue[0], queue[1:]
        label = installer.NAMES[name]
        dlg = Gtk.AlertDialog(
            message=t("setup_title", name=label),
            detail=t("setup_body", name=label, cmd=installer.command_text(name)),
            buttons=[t("install"), t("not_now"), t("never_ask")], default_button=1, cancel_button=1,
        )
        dlg.choose(None, None, self._on_offer_choice, name, rest)
        return False

    def _on_offer_choice(self, dlg, result, name, rest):
        try:
            choice = dlg.choose_finish(result)
        except GLib.Error:
            choice = 1
        if choice == 0:
            InstallWindow(None, name, lambda: self._offer(rest)).present()
            return
        if choice == 2:
            self.cfg["check_components"] = False
            cfgmod.save(self.cfg)
            return
        self._offer(rest)

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
