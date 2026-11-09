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


@pytest.mark.skipif(not os.environ.get("LMS_BRIDGE_TEST_GUI"), reason="requires a GTK display")
def test_uninstall_requires_confirmation_and_quits_on_success(monkeypatch):
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    from lms_hermes_bridge import config, settings_dialog

    Gtk.init()
    calls = []
    monkeypatch.setattr(settings_dialog.uninstaller, "uninstall", lambda: calls.append("uninstall"))
    monkeypatch.setattr(settings_dialog.GLib, "idle_add", lambda callback, *args: callback(*args))
    monkeypatch.setattr(settings_dialog.threading, "Thread", lambda target, **kwargs:
                        SimpleNamespace(start=target))
    window = settings_dialog.SettingsWindow(None, copy.deepcopy(config.DEFAULTS), lambda: None,
                                             lambda: calls.append("quit"))
    try:
        window._uninstall_choice(SimpleNamespace(choose_finish=lambda _result: 0), None)
        assert calls == []
        window._uninstall_choice(SimpleNamespace(choose_finish=lambda _result: 1), None)
        assert calls == ["uninstall", "quit"]
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


def test_priority_worker_retries_local_then_lan_without_sending_to_cloud(monkeypatch):
    pytest.importorskip("gi")
    from lms_hermes_bridge import app, config, lmstudio, providers
    import threading

    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["routing"] = "priority"
    cfg["providers"] = [
        {"id": "cloud", "endpoint": "https://example.com/v1", "model": "cloud", "kind": "openai", "api_key": ""},
        {"id": "lan", "endpoint": "http://192.168.1.5/v1", "model": "lan", "kind": "openai", "api_key": ""},
    ]
    monkeypatch.setattr(lmstudio, "list_models", lambda _url: [lmstudio.ModelInfo("local", loaded=True)])
    calls, output = [], []

    def stream(route, _messages, _cancel):
        calls.append(route.model)
        if route.model == "local":
            raise providers.ChatError("offline")
        yield "answer"

    window = SimpleNamespace(cfg=cfg, _ui=lambda callback, *args: callback(*args), _status=lambda *_: None,
                             _append=lambda text, _cancel: output.append(text), _stream=stream,
                             _priority_model_lists=lambda: app.BridgeWindow._priority_model_lists(window))
    app.BridgeWindow._priority_worker(window, "hello", [], threading.Event())
    assert calls == ["local", "lan"]
    assert output == ["answer"]


def test_pi_priority_worker_uses_agent_for_each_safe_attempt(monkeypatch):
    pytest.importorskip("gi")
    from lms_hermes_bridge import app, config, lmstudio, pi_harness, providers
    import threading

    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["pi"].update(base_url="http://192.168.1.5:1234/v1", model="remote")
    calls, output = [], []

    def stream(pi_cfg, prompt, _system, _cancel):
        calls.append((pi_cfg["model"], pi_cfg["safe_fallback"], prompt))
        if pi_cfg["model"] == "local":
            raise providers.ChatError("offline")
        yield "agent answer"

    monkeypatch.setattr(pi_harness, "stream", stream)
    window = SimpleNamespace(cfg=cfg, _ui=lambda callback, *args: callback(*args), _status=lambda *_: None,
                             _append=lambda text, _cancel: output.append(text),
                             _priority_model_lists=lambda: {"lmstudio": [lmstudio.ModelInfo("local", loaded=True)]})
    app.BridgeWindow._priority_pi_worker(window, "open file", threading.Event())
    assert calls == [("local", True, "open file"), ("remote", True, "open file")]
    assert output == ["agent answer"]


@pytest.mark.skipif(not os.environ.get("LMS_BRIDGE_TEST_GUI"), reason="requires a GTK display")
def test_setup_window_saves_choices_and_preserves_existing_provider(monkeypatch):
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    from lms_hermes_bridge import config, i18n
    from lms_hermes_bridge.setup_window import SetupWindow

    Gtk.init()
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["providers"] = [{"id": "existing", "name": "Cloud", "kind": "openai",
                         "endpoint": "https://example.com/v1/chat/completions", "model": "model",
                         "api_key": "secret", "enabled": True}]
    saved = []
    monkeypatch.setattr(config, "save", lambda value: saved.append(copy.deepcopy(value)))
    i18n.set_language("de")
    window = SetupWindow(None, cfg, lambda: None)
    try:
        assert window.hermes_url.get_sensitive() and not window.pi_url.get_sensitive()
        window.agent.set_selected(0)
        assert window.pi_url.get_sensitive() and not window.hermes_url.get_sensitive()
        window.lms.set_active(False)
        window.strata.set_active(False)
        assert not window.lms_url.get_sensitive() and not window.strata_url.get_sensitive()
        window.pi_url.set_text("http://127.0.0.1:1234/v1")
        window.pi_model.set_text("test-model")
        window._save()
        assert not saved and window.error.get_visible()
        window.pi_url.set_text("http://192.168.1.5:1234/v1")
        window._save()
        assert saved[0]["routing"] == "priority"
        assert saved[0]["agent_backend"] == "pi" and saved[0]["pi"]["enabled"]
        assert saved[0]["pi"]["base_url"] == "http://192.168.1.5:1234/v1"
        assert not saved[0]["lmstudio"]["enabled"] and not saved[0]["strata"]["enabled"]
        assert saved[0]["providers"][0]["api_key"] == "secret"
    finally:
        window.destroy()


@pytest.mark.skipif(not os.environ.get("LMS_BRIDGE_TEST_GUI"), reason="requires a GTK display")
def test_setup_window_add_provider_and_report_save_error(monkeypatch):
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk
    from lms_hermes_bridge import config
    from lms_hermes_bridge.setup_window import SetupWindow

    Gtk.init()
    cfg = copy.deepcopy(config.DEFAULTS)
    def fail_save(_value):
        raise OSError("disk full")
    monkeypatch.setattr(config, "save", fail_save)
    window = SetupWindow(None, cfg, lambda: pytest.fail("must not finish on save error"))
    try:
        window._add_selected()
        assert len(window.provider_rows) == 1
        window.provider_rows[0]["model"].set_text("model")
        window._save()
        assert window.error.get_visible() and "disk full" in window.error.get_text()
        assert cfg["routing"] != "priority"
    finally:
        window.destroy()