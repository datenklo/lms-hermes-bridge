import copy
import uuid
from urllib.parse import urlparse

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import config, router  # noqa: E402
from .i18n import t  # noqa: E402
from .settings_dialog import _entry, _grid, _row  # noqa: E402


def _valid_url(value):
    try:
        parsed = urlparse(value)
        return parsed.scheme in ("http", "https") and bool(parsed.hostname) and parsed.port != 0
    except ValueError:
        return False


class SetupWindow(Gtk.Window):
    def __init__(self, parent, cfg, on_save):
        super().__init__(title=t("wizard_title"), transient_for=parent, modal=True)
        self.set_application(Gtk.Application.get_default())
        self.set_default_size(700, 680)
        self.add_css_class("settings")
        self.cfg = cfg
        self.on_save = on_save
        self.provider_rows = []

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18,
                        margin_start=20, margin_end=20)
        header = Gtk.Box(spacing=12)
        header.append(Gtk.Label(label=t("wizard_title"), xalign=0, hexpand=True, css_classes=["title-2"]))
        header.append(Gtk.LinkButton.new_with_label("https://github.com/datenklo/lms-hermes-bridge", "GitHub"))
        outer.append(header)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        grid = _grid()
        self.agent = _row(grid, t("agent_backend"), Gtk.DropDown.new_from_strings(["Pi", "Hermes"]))
        self.agent.set_selected(0 if cfg.get("agent_backend") == "pi" else 1)
        self.hermes_url = _row(grid, t("hermes_endpoint"), _entry(cfg["hermes"]["endpoint"]))
        self.pi_model = _row(grid, t("model"), _entry(cfg["pi"]["model"]))
        self.pi_url = _row(grid, t("wizard_pi_url"), _entry(cfg["pi"].get("base_url", "")))
        self.pi_key = _row(grid, t("api_key"), _entry(cfg["pi"].get("api_key", ""), secret=True))
        content.append(grid)
        content.append(Gtk.Label(label=t("wizard_agent_note"), xalign=0, wrap=True, css_classes=["dim-label"]))
        content.append(Gtk.Label(label=t("wizard_models"), xalign=0, css_classes=["heading"]))
        grid = _grid()
        self.lms = _row(grid, t("wizard_lms"), Gtk.Switch(halign=Gtk.Align.START,
                        active=cfg["lmstudio"].get("enabled", cfg.get("local_backend") == "lmstudio")))
        self.lms_url = _row(grid, t("lms_url"), _entry(cfg["lmstudio"]["url"]))
        self.strata = _row(grid, t("wizard_strata"), Gtk.Switch(halign=Gtk.Align.START,
                           active=cfg["strata"].get("enabled", cfg.get("local_backend") == "strata")))
        self.strata_url = _row(grid, t("strata_url"), _entry(cfg["strata"]["url"]))
        content.append(grid)
        self.agent.connect("notify::selected", self._update_sensitivity)
        self.lms.connect("notify::active", self._update_sensitivity)
        self.strata.connect("notify::active", self._update_sensitivity)
        self._update_sensitivity()
        content.append(Gtk.Label(label=t("wizard_cloud"), xalign=0, css_classes=["heading"]))
        bar = Gtk.Box(spacing=8)
        self.presets = list(config.PROVIDER_PRESETS)
        self.preset = Gtk.DropDown.new_from_strings([config.PROVIDER_PRESETS[key]["name"] for key in self.presets]
                                                   + [t("wizard_lan")])
        self.preset.set_hexpand(True)
        add = Gtk.Button(label=t("wizard_add_provider"))
        add.connect("clicked", self._add_selected)
        bar.append(self.preset)
        bar.append(add)
        content.append(bar)
        self.provider_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.append(self.provider_box)
        for provider in cfg["providers"]:
            self._add_provider(provider)
        outer.append(Gtk.ScrolledWindow(child=content, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.error = Gtk.Label(xalign=0, wrap=True, css_classes=["error"], visible=False)
        outer.append(self.error)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=t("cancel"))
        cancel.connect("clicked", lambda *_: self.close())
        save = Gtk.Button(label=t("save"), css_classes=["suggested-action"])
        save.connect("clicked", self._save)
        buttons.append(cancel)
        buttons.append(save)
        outer.append(buttons)
        self.set_child(outer)

    def _update_sensitivity(self, *_):
        pi_selected = self.agent.get_selected() == 0
        self.hermes_url.set_sensitive(not pi_selected)
        for field in (self.pi_model, self.pi_url, self.pi_key):
            field.set_sensitive(pi_selected)
        self.lms_url.set_sensitive(self.lms.get_active())
        self.strata_url.set_sensitive(self.strata.get_active())

    def _add_selected(self, *_):
        selected = self.preset.get_selected()
        base = (config.PROVIDER_PRESETS[self.presets[selected]] if selected < len(self.presets) else
                {"name": t("wizard_lan"), "kind": "openai", "endpoint": "", "model": "", "scope": "lan"})
        self._add_provider({**base, "id": uuid.uuid4().hex, "api_key": "", "enabled": True})

    def _add_provider(self, provider):
        grid = _grid()
        row = {"id": provider["id"], "kind": provider["kind"], "name": provider["name"],
             "enabled": provider.get("enabled", True), "scope": provider.get("scope"), "grid": grid}
        row["endpoint"] = _row(grid, provider["name"], _entry(provider["endpoint"]))
        row["model"] = _row(grid, t("model"), _entry(provider["model"]))
        row["api_key"] = _row(grid, t("api_key"), _entry(provider.get("api_key", ""), secret=True))
        remove = Gtk.Button(label=t("remove"), halign=Gtk.Align.END)
        remove.connect("clicked", lambda *_: (self.provider_box.remove(grid), self.provider_rows.remove(row)))
        grid.attach(remove, 1, grid.row, 1, 1)
        self.provider_rows.append(row)
        self.provider_box.append(grid)

    def _save(self, *_):
        agent = ("pi", "hermes")[min(self.agent.get_selected(), 1)]
        lms_url, strata_url, hermes_url = (widget.get_text().strip() for widget in
                                          (self.lms_url, self.strata_url, self.hermes_url))
        urls = ([lms_url] if self.lms.get_active() else []) + ([strata_url] if self.strata.get_active() else [])
        if agent == "hermes":
            urls.append(hermes_url)
        pi_url = self.pi_url.get_text().strip()
        if agent == "pi":
            if not pi_url or not self.pi_model.get_text().strip() or (
                not self.lms.get_active() and router.endpoint_scope(pi_url) == "local"
            ):
                self.error.set_text(t("wizard_pi_remote"))
                self.error.set_visible(True)
                return
            urls.append(pi_url)
        providers = []
        for row in self.provider_rows:
            endpoint, model = row["endpoint"].get_text().strip(), row["model"].get_text().strip()
            urls.append(endpoint)
            if not model:
                self.error.set_text(t("wizard_invalid"))
                self.error.set_visible(True)
                return
            providers.append({key: row[key] for key in ("id", "kind", "name", "enabled")} | {
                "endpoint": endpoint, "model": model, "api_key": row["api_key"].get_text()})
            if row["scope"]:
                providers[-1]["scope"] = row["scope"]
        if not all(_valid_url(url) for url in urls):
            self.error.set_text(t("wizard_invalid"))
            self.error.set_visible(True)
            return
        updated = copy.deepcopy(self.cfg)
        updated["agent_backend"] = agent
        updated["hermes"].update(enabled=agent == "hermes", endpoint=hermes_url)
        updated["pi"].update(enabled=agent == "pi", model=self.pi_model.get_text().strip(),
                     base_url=pi_url, api_key=self.pi_key.get_text())
        updated["lmstudio"].update(enabled=self.lms.get_active(), url=lms_url)
        updated["strata"].update(enabled=self.strata.get_active(), url=strata_url)
        updated["local_backend"] = "lmstudio" if self.lms.get_active() else "strata"
        updated["providers"] = providers
        updated["routing"] = "priority"
        try:
            config.save(updated)
        except OSError as error:
            self.error.set_text(t("wizard_save_error").format(error=error))
            self.error.set_visible(True)
            return
        self.cfg.clear()
        self.cfg.update(updated)
        self.close()
        self.on_save()