import copy

from lms_hermes_bridge import services
from lms_hermes_bridge.config import DEFAULTS


def cfg(**over):
    c = copy.deepcopy(DEFAULTS)
    c.update(over)
    return c


def test_hermes_health_url_from_endpoint():
    c = cfg()
    c["hermes"]["endpoint"] = "http://127.0.0.1:8642/v1/chat/completions"
    assert services.hermes_health_url(c) == "http://127.0.0.1:8642/health"


def test_ensure_does_nothing_when_already_up(monkeypatch):
    monkeypatch.setattr(services, "lmstudio_up", lambda _c: True)
    monkeypatch.setattr(services, "_start_lmstudio", lambda _c: (_ for _ in ()).throw(AssertionError("started")))
    assert services.ensure(cfg(), "lmstudio") is True


def test_ensure_respects_switch_remote_url_and_missing_install(monkeypatch):
    started = []
    monkeypatch.setattr(services, "lmstudio_up", lambda _c: False)
    monkeypatch.setattr(services, "_start_lmstudio", lambda _c: started.append(1))
    monkeypatch.setattr(services.lmstudio, "_lms_bin", lambda: "/x/lms")
    assert services.ensure(cfg(autostart_backends=False), "lmstudio", timeout=0) is False
    remote = cfg()
    remote["lmstudio"]["url"] = "http://192.168.0.9:1234"
    assert services.ensure(remote, "lmstudio", timeout=0) is False
    monkeypatch.setattr(services.lmstudio, "_lms_bin", lambda: None)
    assert services.ensure(cfg(), "lmstudio", timeout=0) is False
    assert started == []


def test_ensure_starts_and_waits(monkeypatch):
    state = {"up": False}
    monkeypatch.setattr(services, "hermes_up", lambda _c: state["up"])
    monkeypatch.setattr(services, "hermes_bin", lambda: "/x/hermes")
    monkeypatch.setattr(services, "_start_hermes", lambda _c: state.update(up=True))
    assert services.ensure(cfg(), "hermes", timeout=2) is True
