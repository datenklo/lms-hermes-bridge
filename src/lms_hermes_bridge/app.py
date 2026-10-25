import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import APP_ID, __version__, config as cfgmod, hotkey, installer, lmstudio, providers, router, routines, services  # noqa: E402
from . import desktop_context  # noqa: E402
from .i18n import set_language, t  # noqa: E402
from .install_window import InstallWindow  # noqa: E402
from .placement import move_to_top  # noqa: E402
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
        self.set_default_size(820, -1)
        self.context_text: list[tuple[str, str]] = []
        self.context_images: list[dict] = []
        self.active_model = None
        self.vision_models: list[lmstudio.ModelInfo] = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, margin_top=4, margin_bottom=4,
                      margin_start=4, margin_end=4)
        self.entry = Gtk.Entry(css_classes=["query"])
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search-symbolic")
        self.entry.connect("activate", self._submit)
        box.append(self.entry)

        self.context_status = Gtk.Label(xalign=0, css_classes=["route"], wrap=True, visible=False)
        box.append(self.context_status)
        toolbar = Gtk.Box(spacing=4, margin_start=10, margin_end=10, margin_bottom=6)
        self.image_button = self._icon_button("image-x-generic-symbolic", "context_image", self._choose_image)
        self.image_button.set_sensitive(False)
        self.clipboard_button = self._icon_button("edit-paste-symbolic", "context_clipboard", self._paste_clipboard)
        self.selection_button = self._icon_button("insert-text-symbolic", "context_selection", self._paste_selection)
        self.screenshot_button = self._icon_button("camera-photo-symbolic", "context_screenshot", self._capture_screenshot)
        self.clear_context_button = self._icon_button("edit-clear-symbolic", "context_clear", self._clear_context)
        toolbar.append(self.image_button)
        toolbar.append(self.clipboard_button)
        toolbar.append(self.selection_button)
        toolbar.append(self.screenshot_button)
        toolbar.append(self.clear_context_button)
        toolbar.append(Gtk.Box(hexpand=True))

        self.vision_load_button = self._icon_button("view-refresh-symbolic", "vision_load", self._load_vision_model)
        self.vision_load_button.set_visible(False)
        toolbar.append(self.vision_load_button)
        self.capability_button = Gtk.MenuButton(icon_name="dialog-information-symbolic", tooltip_text=t("capabilities"),
                                                css_classes=["flat"])
        self.capability_popover = Gtk.Popover()
        cap_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                          margin_start=14, margin_end=14)
        self.capability_rows = {}
        for key, icon in (("image", "image-x-generic-symbolic"),
                          ("thinking", "dialog-information-symbolic"),
                          ("tools", "applications-system-symbolic")):
            row = Gtk.Box(spacing=8)
            image = Gtk.Image.new_from_icon_name(icon)
            label = Gtk.Label(xalign=0)
            row.append(image)
            row.append(label)
            cap_box.append(row)
            self.capability_rows[key] = (image, label)
        self.capability_popover.set_child(cap_box)
        self.capability_button.set_popover(self.capability_popover)
        toolbar.append(self.capability_button)
        box.append(toolbar)

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
        self._update_context_status()
        threading.Thread(target=self._query_model_capabilities, daemon=True).start()

    def _icon_button(self, icon: str, tooltip: str, callback) -> Gtk.Button:
        button = Gtk.Button(icon_name=icon, css_classes=["flat"], tooltip_text=t(tooltip))
        button.connect("clicked", callback)
        return button

    def _query_model_capabilities(self):
        models = lmstudio.list_models(self.cfg["lmstudio"]["url"])
        loaded = next((m for m in models or [] if m.loaded and m.is_chat), None)
        vision_models = [m for m in models or [] if m.is_chat and m.supports_vision]
        GLib.idle_add(self._set_model_capabilities, loaded, vision_models)

    def _set_model_capabilities(self, model, vision_models=None):
        self.active_model = model
        if vision_models is not None:
            self.vision_models = vision_models
        for key, attr in (("image", "supports_vision"), ("thinking", "supports_thinking"),
                          ("tools", "supports_tools")):
            image, label = self.capability_rows[key]
            supported = bool(model and getattr(model, attr))
            image.set_opacity(1.0 if supported else 0.35)
            label.set_text(f"{t('cap_' + key)} · {t('cap_yes') if supported else t('cap_no') if model else t('cap_no_model')}")
        self.image_button.set_sensitive(bool(model and model.supports_vision))
        self.image_button.set_tooltip_text(t("context_image") if model and model.supports_vision else t("vision_required"))
        self.vision_load_button.set_visible(bool(vision_models) and not (model and model.supports_vision))
        if model:
            self.capability_button.set_tooltip_text(f"{t('capabilities')}: {model.key}")
        return False

    def _refresh_model_capabilities(self):
        threading.Thread(target=self._query_model_capabilities, daemon=True).start()

    def _update_context_status(self):
        labels = [name for name, _text in self.context_text]
        labels.extend(image["name"] for image in self.context_images)
        self.context_status.set_text(", ".join(labels))
        self.context_status.set_visible(bool(labels))
        self.clear_context_button.set_visible(bool(labels))

    def _add_context_text(self, name: str, text: str):
        text = text.strip()
        if not text:
            self._status(t("context_empty_selection" if name == t("context_selection") else "context_empty_clipboard"))
            return
        self.context_text.append((name, text))
        self._update_context_status()

    def _read_clipboard(self, primary: bool):
        display = Gdk.Display.get_default()
        clipboard = display.get_primary_clipboard() if primary else display.get_clipboard()
        if clipboard is None:
            self._status(t("context_empty_selection" if primary else "context_empty_clipboard"))
            return

        def read_done(source, result, _data):
            try:
                text = source.read_text_finish(result)
            except GLib.Error:
                text = None
            self._add_context_text(t("context_selection" if primary else "context_clipboard"), text or "")
        clipboard.read_text_async(None, read_done, None)

    def _paste_clipboard(self, *_):
        self._read_clipboard(False)

    def _paste_selection(self, *_):
        self._read_clipboard(True)

    def _choose_image(self, *_):
        dialog = Gtk.FileChooserNative.new(t("context_image"), self, Gtk.FileChooserAction.OPEN,
                                           t("select"), t("cancel"))
        image_filter = Gtk.FileFilter()
        image_filter.set_name(t("image_files"))
        for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp"):
            image_filter.add_pattern(pattern)
        dialog.add_filter(image_filter)

        def response(native, result):
            if result == Gtk.ResponseType.ACCEPT:
                file = native.get_file()
                try:
                    image = desktop_context.image_from_path(file.get_path())
                    self.context_images.append(image)
                    self._update_context_status()
                except Exception as e:
                    self._status(t("context_image_error", error=e))
            native.destroy()
        dialog.connect("response", response)
        dialog.show()

    def _capture_screenshot(self, *_):
        self._status(t("context_capture_wait"))
        def captured(image, error):
            if error:
                GLib.idle_add(self._status, t("context_image_error", error=error))
            else:
                GLib.idle_add(self._add_image, image)
        desktop_context.screenshot(captured)

    def _add_image(self, image):
        self.context_images.append(image)
        self._update_context_status()
        self._status(t("context_added", name=image["name"]))
        return False

    def _clear_context(self, *_):
        self.context_text.clear()
        self.context_images.clear()
        self._update_context_status()
        return False

    def _load_vision_model(self, *_):
        if not self.vision_models:
            self._status(t("vision_none"))
            return
        preferred = self.cfg["lmstudio"].get("preferred_vision", "")
        model = router.pick_model(self.vision_models, "fast", lmstudio.mem_total_bytes(), preferred,
                                  require_vision=True)
        if not model:
            self._status(t("vision_none"))
            return
        self.vision_load_button.set_sensitive(False)
        self._status(t("vision_loading", model=model.key))

        def load():
            loaded = lmstudio.load_model(model.key, min(model.max_context, 8192),
                                         self.cfg["lmstudio"].get("unload_others", True))
            GLib.idle_add(self._vision_loaded, model, loaded)
        threading.Thread(target=load, daemon=True).start()

    def _vision_loaded(self, model, loaded: bool):
        self.vision_load_button.set_sensitive(True)
        if loaded:
            self._status(t("vision_loaded", model=model.key))
            self._refresh_model_capabilities()
        else:
            self._status(t("vision_none"))
        return False

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
        self._refresh_model_capabilities()
        GLib.timeout_add(40, self._place)  # the surface must be mapped before it can be moved

    def _place(self):
        move_to_top(self)
        return False

    # -- query flow -----------------------------------------------------
    def _submit(self, *_):
        prompt = self.entry.get_text().strip()
        if not prompt and not self.context_text and not self.context_images:
            return
        if not prompt and self.context_images:
            prompt = t("image_prompt")
        self.cancel.set()  # stop any previous stream
        self.cancel = threading.Event()
        self.buf.set_text("")
        self.answer_revealer.set_reveal_child(True)
        self._status(t("thinking"))
        threading.Thread(target=self._worker,
                         args=(prompt, list(self.context_text), list(self.context_images), self.cancel),
                         daemon=True).start()

    def _status(self, text: str):
        self.route_label.set_text(text)
        self.route_label.set_visible(bool(text))

    def _append(self, text: str, cancel: threading.Event):
        if not cancel.is_set():
            self.buf.insert(self.buf.get_end_iter(), text)
        return False

    def _ui(self, fn, *a):
        GLib.idle_add(fn, *a)

    def _resolve_route(self, prompt: str, force: str | None = None, needs_image: bool = False):
        cfg = self.cfg
        if force == "hermes":
            if not cfg["hermes"]["enabled"]:
                return None
            self._ensure_hermes()
            return router.Route("hermes", "agent", "routine", cfg["hermes"]["model"])
        url = cfg["lmstudio"]["url"]
        models = lmstudio.list_models(url)
        route = router.decide(prompt, cfg, models, lmstudio.mem_total_bytes(), needs_image=needs_image)
        if models is None and (route is None or route.reason == "LM Studio unavailable"):
            self._ui(self._status, t("starting", name="LM Studio"))
            if services.ensure(cfg, "lmstudio"):
                models = lmstudio.list_models(url)
                route = router.decide(prompt, cfg, models, lmstudio.mem_total_bytes(), needs_image=needs_image)
        if route and route.backend == "hermes":
            self._ensure_hermes()
        return route

    def _ensure_hermes(self):
        if not services.hermes_up(self.cfg):
            self._ui(self._status, t("starting", name="Hermes"))
            services.ensure(self.cfg, "hermes")

    def _worker(self, prompt: str, context_text: list[tuple[str, str]], images: list[dict],
                cancel: threading.Event):
        cfg = self.cfg
        try:
            routine = routines.handle(prompt, cfg) if not (context_text or images) else None
        except Exception as e:  # a routine bug must never block normal answers
            routine = None
            print(f"routine failed: {e}", file=sys.stderr)
        force = None
        if isinstance(routine, routines.Redirect):
            self._ui(self._status, t("routine_label", name=routine.label))
            prompt, force = routine.prompt, routine.backend
        elif routine:
            name = routine.label or t("routine_" + routine.name)
            self._ui(self._status, t("routine_label", name=name))
            self._ui(self._append, routine.text, cancel)
            return
        full_prompt = prompt
        if context_text:
            full_prompt += "\n\n" + "\n\n".join(f"[{name}]\n{text}" for name, text in context_text)
        route = self._resolve_route(full_prompt, force if force == "hermes" else None, needs_image=bool(images))
        if route is None:
            key = ("err_no_vision" if images else "err_hermes_off" if force == "hermes"
                   else "err_local_only" if cfg["local_only"] else "err_no_target")
            self._ui(self._status, t(key))
            return
        try:
            if route.backend == "lmstudio" and route.needs_load:
                auto_load = cfg["lmstudio"].get("auto_load_vision_model", True) if images else cfg["lmstudio"]["auto_load"]
                if images and not auto_load:
                    self._ui(self._status, t("vision_required"))
                    return
                self._ui(self._status, t("loading_model", model=route.model))
                loaded = lmstudio.load_model(route.model, route.params["context"], cfg["lmstudio"]["unload_others"])
                if images and not loaded:
                    self._ui(self._status, t("vision_required"))
                    return
            if route.backend == "lmstudio":
                self._ui(self._set_model_capabilities,
                         lmstudio.ModelInfo(route.model, type="vlm" if route.params.get("supports_vision") else "llm",
                                            loaded=True, capabilities=tuple(k for k, v in (
                                                ("reasoning", route.params.get("supports_thinking")),
                                                ("tool_use", route.params.get("supports_tools"))) if v)),
                         self.vision_models)
            backend = {"lmstudio": "LM Studio", "hermes": "Hermes"}.get(route.backend, "API")
            self._ui(self._status, t("route_label", backend=backend, model=route.model,
                                     tier=t("tier_" + route.tier), reason=route.reason))
            user_content = full_prompt
            if images:
                user_content = [{"type": "text", "text": full_prompt}]
                user_content.extend({"type": "image_url", "image_url": {
                    "url": f"data:{image['mime']};base64,{image['data']}"}} for image in images)
            messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}]
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
        hotkey.refresh_command()
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
        self._start_services()

    def _start_services(self):
        """Bring local LM Studio / Hermes up in the background so the first request is fast."""
        if not self.cfg["autostart_backends"]:
            return
        names = ["lmstudio"] + (["hermes"] if self.cfg["hermes"]["enabled"] else [])
        for name in names:
            threading.Thread(target=services.ensure, args=(self.cfg, name), daemon=True).start()

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
