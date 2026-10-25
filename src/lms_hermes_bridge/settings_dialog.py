import copy
import uuid

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import config as cfgmod, hotkey  # noqa: E402
from .i18n import STRINGS, current, t  # noqa: E402

KINDS = ["openai", "anthropic"]


def _grid() -> Gtk.Grid:
    g = Gtk.Grid(row_spacing=14, column_spacing=18, margin_top=18, margin_bottom=18, margin_start=20, margin_end=20)
    g.row = 0
    return g


def _row(grid: Gtk.Grid, label: str, widget: Gtk.Widget) -> Gtk.Widget:
    lab = Gtk.Label(label=label, xalign=0, css_classes=["dim-label"])
    widget.set_hexpand(True)
    grid.attach(lab, 0, grid.row, 1, 1)
    grid.attach(widget, 1, grid.row, 1, 1)
    grid.row += 1
    return widget


def _entry(text: str, secret: bool = False) -> Gtk.Entry:
    e = Gtk.Entry(text=text or "", width_chars=44)
    if secret:
        e.set_visibility(False)
        e.set_input_purpose(Gtk.InputPurpose.PASSWORD)
    return e


class SettingsWindow(Gtk.Window):
    def __init__(self, parent, cfg: dict, on_save):
        super().__init__(title=t("settings").rstrip("…"), transient_for=parent, modal=True)
        self.set_default_size(980, 620)
        self.add_css_class("settings")
        self.cfg = cfg
        self.on_save = on_save
        self.kw_lang = current() if current() in STRINGS else "en"
        self.langs = ["auto"] + list(STRINGS)
        self.routes = ["auto", "local", "hermes"]

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        nb = Gtk.Notebook(vexpand=True)
        nb.append_page(self._general(), Gtk.Label(label=t("tab_general")))
        nb.append_page(self._lmstudio(), Gtk.Label(label=t("tab_lmstudio")))
        nb.append_page(self._hermes(), Gtk.Label(label=t("tab_hermes")))
        nb.append_page(self._routines(), Gtk.Label(label=t("tab_routines")))
        nb.append_page(self._keywords(), Gtk.Label(label=t("tab_keywords")))
        nb.append_page(self._providers_tab(), Gtk.Label(label=t("tab_providers")))
        box.append(nb)

        bar = Gtk.Box(spacing=8, halign=Gtk.Align.END, margin_top=10, margin_bottom=14, margin_end=20)
        cancel = Gtk.Button(label=t("cancel"))
        cancel.connect("clicked", lambda *_: self.close())
        save = Gtk.Button(label=t("save"), css_classes=["suggested-action"])
        save.connect("clicked", self._save)
        bar.append(cancel)
        bar.append(save)
        box.append(bar)
        self.set_child(box)

    # -- tabs ---------------------------------------------------------
    def _general(self):
        g = _grid()
        names = [t("auto")] + [s["language_name"] for k, s in STRINGS.items()]
        self.w_lang = _row(g, t("language"), Gtk.DropDown.new_from_strings(names))
        self.w_lang.set_selected(self.langs.index(self.cfg["language"]) if self.cfg["language"] in self.langs else 0)

        self.w_local = _row(g, t("local_only"), Gtk.Switch(halign=Gtk.Align.START))
        self.w_local.set_active(self.cfg["local_only"])

        self.w_check = _row(g, t("check_components"), Gtk.Switch(halign=Gtk.Align.START))
        self.w_check.set_active(self.cfg["check_components"])

        self.w_autostart = _row(g, t("autostart_backends"), Gtk.Switch(halign=Gtk.Align.START))
        self.w_autostart.set_active(self.cfg["autostart_backends"])

        self.w_routing = _row(g, t("routing"), Gtk.DropDown())
        self._fill_routing()

        hk = Gtk.Box(spacing=8)
        self.w_hotkey = _entry(self.cfg["hotkey"])
        self.w_hotkey.set_hexpand(True)
        btn = Gtk.Button(label=t("hotkey_apply"))
        self.w_hk_status = Gtk.Label(xalign=0)
        btn.connect("clicked", self._apply_hotkey)
        hk.append(self.w_hotkey)
        hk.append(btn)
        _row(g, t("hotkey"), hk)
        _row(g, "", self.w_hk_status)
        return g

    # -- routines table ---------------------------------------------------
    CUSTOM_ACTIONS = ("answer", "command", "url", "hermes", "llm")

    def _routines(self):
        c = self.cfg
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=10,
                        margin_start=18, margin_end=18)
        top = Gtk.Grid(row_spacing=10, column_spacing=18)
        top.row = 0
        self.w_routines = _row(top, t("routines_enabled"), Gtk.Switch(halign=Gtk.Align.START, active=c["routines_enabled"]))
        self.w_weather_loc = _row(top, t("weather_location"), _entry(c["weather_location"]))
        outer.append(top)
        outer.append(Gtk.Label(label=t("routines_table_hint"), xalign=0, wrap=True, css_classes=["dim-label"]))

        self.rt_grid = Gtk.Grid(row_spacing=8, column_spacing=10)
        outer.append(Gtk.ScrolledWindow(child=self.rt_grid, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER))

        bar = Gtk.Box(spacing=8)
        add = Gtk.Button(label=t("add_routine"))
        add.connect("clicked", self._add_routine)
        reset = Gtk.Button(label=t("reset_routines"))
        reset.connect("clicked", lambda *_: self._render_routines(copy.deepcopy(cfgmod.DEFAULT_ROUTINES)))
        bar.append(add)
        bar.append(reset)
        outer.append(bar)
        self._render_routines(copy.deepcopy(c["routines"]))
        return outer

    def _action_label(self, action: str) -> str:
        return t("act_" + action)

    def _render_routines(self, rows: list):
        grid = self.rt_grid
        while (child := grid.get_first_child()):
            grid.remove(child)
        self.rt_rows = []
        for col, key in enumerate(("col_on", "col_name", "col_keywords", "col_action", "col_value")):
            grid.attach(Gtk.Label(label=t(key), xalign=0, css_classes=["dim-label"]), col, 0, 1, 1)
        for i, row in enumerate(rows, start=1):
            builtin = row["id"] in cfgmod.BUILTIN_ROUTINES
            on = Gtk.CheckButton(active=row.get("enabled", True), valign=Gtk.Align.CENTER)
            name = _entry(self._row_name(row))
            name.set_width_chars(14)
            name.set_sensitive(not builtin)
            kw = _entry(", ".join(row.get("keywords", [])))
            kw.set_width_chars(26)
            kw.set_hexpand(True)
            kw.set_placeholder_text(t("kw_placeholder_builtin" if builtin else "kw_placeholder"))
            actions = [row["action"]] if builtin else list(self.CUSTOM_ACTIONS)
            act = Gtk.DropDown.new_from_strings([self._action_label(a) for a in actions])
            act.set_selected(actions.index(row["action"]) if row["action"] in actions else 0)
            act.set_sensitive(not builtin)
            value = _entry(row.get("value", ""))
            value.set_width_chars(30)
            value.set_hexpand(True)
            value.set_sensitive(not builtin)
            act.connect("notify::selected", lambda w, _p, v=value, a=actions: v.set_placeholder_text(
                t("ph_" + self._action_of(w, a))))
            value.set_placeholder_text("" if builtin else t("ph_" + row["action"]))
            delete = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"], sensitive=not builtin,
                                tooltip_text=t("remove"))
            delete.connect("clicked", lambda _b, idx=i - 1: self._delete_routine(idx))
            for col, w in enumerate((on, name, kw, act, value, delete)):
                grid.attach(w, col, i, 1, 1)
            self.rt_rows.append({"id": row["id"], "name": row.get("name", ""), "on": on, "name_w": name,
                                 "kw": kw, "act": act, "actions": actions, "value": value, "builtin": builtin})

    def _row_name(self, row: dict) -> str:
        if row["id"] == "builtin:google":
            return t("routine_google")
        return t("routine_" + row["action"]) if row["id"] in cfgmod.BUILTIN_ROUTINES else row.get("name", "")

    @staticmethod
    def _action_of(dropdown, actions) -> str:
        return actions[min(dropdown.get_selected(), len(actions) - 1)]

    def _collect_routines(self) -> list:
        rows = []
        for r in self.rt_rows:
            rows.append({
                "id": r["id"],
                "name": r["name"] if r["builtin"] else r["name_w"].get_text().strip(),
                "enabled": r["on"].get_active(),
                "keywords": [k.strip() for k in r["kw"].get_text().split(",") if k.strip()],
                "action": self._action_of(r["act"], r["actions"]),
                "value": "" if r["builtin"] else r["value"].get_text().strip(),
            })
        return rows

    def _add_routine(self, *_):
        rows = self._collect_routines()
        rows.append({"id": f"custom:{uuid.uuid4().hex[:8]}", "name": t("new_routine"), "enabled": True,
                     "keywords": [], "action": "answer", "value": ""})
        self._render_routines(rows)

    def _delete_routine(self, idx: int):
        rows = self._collect_routines()
        del rows[idx]
        self._render_routines(rows)

    def _fill_routing(self):
        labels = [t("route_auto"), t("route_local"), t("route_hermes")]
        self.routes = ["auto", "local", "hermes"]
        for p in self.cfg["providers"]:
            self.routes.append("provider:" + p["id"])
            labels.append(p["name"])
        self.w_routing.set_model(Gtk.StringList.new(labels))
        cur = self.cfg["routing"]
        self.w_routing.set_selected(self.routes.index(cur) if cur in self.routes else 0)

    def _lmstudio(self):
        c = self.cfg["lmstudio"]
        g = _grid()
        self.w_lms_url = _row(g, t("lms_url"), _entry(c["url"]))
        self.w_lms_load = _row(g, t("lms_auto_load"), Gtk.Switch(halign=Gtk.Align.START, active=c["auto_load"]))
        self.w_lms_unload = _row(g, t("lms_unload"), Gtk.Switch(halign=Gtk.Align.START, active=c["unload_others"]))
        self.w_pref = {}
        for tier in ("fast", "balanced", "deep", "code"):
            self.w_pref[tier] = _row(g, t("pref_" + tier), _entry(c[f"preferred_{tier}"]))
        return g

    def _hermes(self):
        c = self.cfg["hermes"]
        g = _grid()
        self.w_h_on = _row(g, t("hermes_enabled"), Gtk.Switch(halign=Gtk.Align.START, active=c["enabled"]))
        self.w_h_url = _row(g, t("hermes_endpoint"), _entry(c["endpoint"]))
        self.w_h_key = _row(g, t("api_key"), _entry(c["api_key"], secret=True))
        self.w_h_model = _row(g, t("model"), _entry(c["model"]))
        return g

    def _keywords(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12,
                      margin_start=12, margin_end=12)
        box.append(Gtk.Label(label=t("keywords_help", lang=STRINGS[self.kw_lang]["language_name"]), xalign=0,
                             wrap=True, css_classes=["dim-label"]))
        self.kw_buf = Gtk.TextBuffer()
        self.kw_buf.set_text("\n".join(self.cfg["agent_keywords"].get(self.kw_lang, [])))
        view = Gtk.TextView(buffer=self.kw_buf, monospace=True, wrap_mode=Gtk.WrapMode.NONE)
        box.append(Gtk.ScrolledWindow(child=view, vexpand=True))
        reset = Gtk.Button(label=t("keywords_reset"), halign=Gtk.Align.START)
        reset.connect("clicked", lambda *_: self.kw_buf.set_text("\n".join(cfgmod.DEFAULT_AGENT_KEYWORDS.get(self.kw_lang, []))))
        box.append(reset)
        return box

    def _providers_tab(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8, margin_start=8, margin_end=8)
        presets = list(cfgmod.PROVIDER_PRESETS)
        bar = Gtk.Box(spacing=8)
        self.w_preset = Gtk.DropDown.new_from_strings([cfgmod.PROVIDER_PRESETS[k]["name"] for k in presets] + ["Custom"])
        add = Gtk.Button(label=t("add"))
        add.connect("clicked", lambda *_: self._add_provider(presets))
        bar.append(self.w_preset)
        bar.append(add)
        outer.append(bar)
        self.prov_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sw = Gtk.ScrolledWindow(vexpand=True, child=self.prov_box)
        outer.append(sw)
        self.prov_rows: list[dict] = []
        for p in self.cfg["providers"]:
            self._provider_card(p)
        return outer

    def _provider_card(self, p: dict):
        frame = Gtk.Frame()
        g = _grid()
        w = {
            "id": p["id"],
            "name": _row(g, t("name"), _entry(p["name"])),
            "kind": _row(g, t("kind"), Gtk.DropDown.new_from_strings(["OpenAI-compatible", "Anthropic"])),
            "endpoint": _row(g, t("endpoint"), _entry(p["endpoint"])),
            "api_key": _row(g, t("api_key"), _entry(p.get("api_key", ""), secret=True)),
            "model": _row(g, t("model"), _entry(p["model"])),
            "enabled": _row(g, t("enabled"), Gtk.Switch(halign=Gtk.Align.START, active=p.get("enabled", True))),
            "frame": frame,
        }
        w["kind"].set_selected(KINDS.index(p["kind"]) if p["kind"] in KINDS else 0)
        rm = Gtk.Button(label=t("remove"), halign=Gtk.Align.END, css_classes=["destructive-action"])
        rm.connect("clicked", lambda *_: self._remove_provider(w))
        g.attach(rm, 1, g.row, 1, 1)
        frame.set_child(g)
        self.prov_box.append(frame)
        self.prov_rows.append(w)

    def _add_provider(self, presets):
        i = self.w_preset.get_selected()
        base = cfgmod.PROVIDER_PRESETS[presets[i]] if i < len(presets) else {
            "name": "Custom", "kind": "openai", "endpoint": "", "model": ""}
        pid = f"p{len(self.prov_rows)}_{id(base) & 0xFFFF:x}"
        self._provider_card({**base, "id": pid, "api_key": "", "enabled": True})

    def _remove_provider(self, w):
        self.prov_box.remove(w["frame"])
        self.prov_rows.remove(w)

    # -- actions ------------------------------------------------------
    def _apply_hotkey(self, *_):
        accel = self.w_hotkey.get_text().strip()
        if not hotkey.is_valid(accel):
            self.w_hk_status.set_text(t("hotkey_invalid"))
            return
        ok = hotkey.register(accel)
        used = hotkey.conflicts(accel) if ok else []
        self.w_hk_status.set_text(t("hotkey_conflict", names=", ".join(used)) if used
                                  else t("hotkey_ok" if ok else "hotkey_fail"))

    def _save(self, *_):
        c = self.cfg
        c["language"] = self.langs[self.w_lang.get_selected()]
        c["local_only"] = self.w_local.get_active()
        c["check_components"] = self.w_check.get_active()
        c["autostart_backends"] = self.w_autostart.get_active()
        c["routines_enabled"] = self.w_routines.get_active()
        c["routines"] = self._collect_routines()
        cfgmod.normalize_routines(c)
        c["weather_location"] = self.w_weather_loc.get_text().strip()
        c["hotkey"] = self.w_hotkey.get_text().strip()
        if hotkey.is_valid(c["hotkey"]) and hotkey.current_binding() != c["hotkey"]:
            hotkey.register(c["hotkey"])  # saving must be enough; the button only gives feedback
        l = c["lmstudio"]
        l["url"] = self.w_lms_url.get_text().strip()
        l["auto_load"] = self.w_lms_load.get_active()
        l["unload_others"] = self.w_lms_unload.get_active()
        for tier, e in self.w_pref.items():
            l[f"preferred_{tier}"] = e.get_text().strip()
        h = c["hermes"]
        h["enabled"] = self.w_h_on.get_active()
        h["endpoint"] = self.w_h_url.get_text().strip()
        h["api_key"] = self.w_h_key.get_text()
        h["model"] = self.w_h_model.get_text().strip()
        text = self.kw_buf.get_text(self.kw_buf.get_start_iter(), self.kw_buf.get_end_iter(), False)
        c["agent_keywords"][self.kw_lang] = list(dict.fromkeys(ln.strip() for ln in text.splitlines() if ln.strip()))
        c["providers"] = [
            {
                "id": w["id"],
                "name": w["name"].get_text().strip(),
                "kind": KINDS[w["kind"].get_selected()],
                "endpoint": w["endpoint"].get_text().strip(),
                "api_key": w["api_key"].get_text(),
                "model": w["model"].get_text().strip(),
                "enabled": w["enabled"].get_active(),
            }
            for w in self.prov_rows
        ]
        sel = self.routes[self.w_routing.get_selected()] if self.w_routing.get_selected() < len(self.routes) else "auto"
        valid = {"auto", "local", "hermes"} | {"provider:" + p["id"] for p in c["providers"]}
        c["routing"] = sel if sel in valid else "auto"
        cfgmod.save(c)
        self.on_save()
        self.close()
