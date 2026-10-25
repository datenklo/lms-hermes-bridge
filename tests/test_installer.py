import copy

from lms_hermes_bridge import installer, lmstudio
from lms_hermes_bridge.config import DEFAULTS


def cfg(**over):
    c = copy.deepcopy(DEFAULTS)
    c.update(over)
    return c


def test_remote_endpoints_are_never_offered(monkeypatch):
    c = cfg()
    c["lmstudio"]["url"] = "http://192.168.1.5:1234"
    c["hermes"]["endpoint"] = "https://example.org/v1/chat/completions"
    assert installer.missing(c) == []


def test_disabled_check_offers_nothing():
    assert installer.missing(cfg(check_components=False)) == []


def test_missing_detected_when_nothing_present(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _n: None)
    monkeypatch.setattr(lmstudio, "_lms_bin", lambda: None)
    monkeypatch.setattr(lmstudio, "list_models", lambda _u: None)
    assert installer.missing(cfg()) == ["lmstudio", "hermes"]


def test_running_server_counts_as_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(installer.shutil, "which", lambda _n: None)
    monkeypatch.setattr(lmstudio, "_lms_bin", lambda: None)
    monkeypatch.setattr(lmstudio, "list_models", lambda _u: [])
    assert installer.missing(cfg()) == ["hermes"]


def test_command_text_uses_official_urls():
    assert installer.command_text("hermes") == "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"
    assert installer.command_text("lmstudio").startswith("curl -fsSL https://lmstudio.ai/")
