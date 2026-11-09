import copy
import os
from types import SimpleNamespace

import pytest


@pytest.mark.skipif(not os.environ.get("LMS_BRIDGE_TEST_GUI"), reason="requires a GTK display")
def test_settings_window_supports_selected_backends_and_languages():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    from lms_hermes_bridge import config, i18n
    from lms_hermes_bridge.settings_dialog import SettingsWindow

    Gtk.init()
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg.update(language="de", local_backend="strata", agent_backend="pi")
    i18n.set_language("de")
    window = SettingsWindow(None, cfg, lambda *_: None)
    try:
        assert window.w_lang.get_selected() == window.langs.index("de")
        assert window.w_local_backend.get_selected() == 1
        assert window.w_agent_backend.get_selected() == 1
        window.w_lang.set_selected(window.langs.index("en"))
        window.w_local_backend.set_selected(0)
        window.w_agent_backend.set_selected(0)
        assert window.w_lang.get_selected() == window.langs.index("en")
        assert window.w_local_backend.get_selected() == 0
        assert window.w_agent_backend.get_selected() == 0
    finally:
        window.destroy()


def test_pi_fallback_still_attempts_lmstudio_start(monkeypatch):
    pytest.importorskip("gi")
    from lms_hermes_bridge import app, config

    cfg = copy.deepcopy(config.DEFAULTS)
    cfg.update(agent_backend="pi", local_only=False)
    cfg["pi"]["enabled"] = True
    starts = []
    monkeypatch.setattr(app.services, "ensure", lambda cfg, name: starts.append(name) or False)
    monkeypatch.setattr(app.lmstudio, "mem_total_bytes", lambda: 0)
    window = SimpleNamespace(cfg=cfg, _local_models=lambda: None, _ui=lambda *args: None, _status=lambda *args: None)
    route = app.BridgeWindow._resolve_route(window, "What is the answer?")
    assert route.backend == "pi"
    assert starts == ["lmstudio"]