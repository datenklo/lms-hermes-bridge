from types import SimpleNamespace

import pytest

from lms_hermes_bridge import uninstaller


def test_uninstall_removes_only_app_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(uninstaller.Path, "home", lambda: tmp_path)
    files = [tmp_path / ".local/share/applications/io.github.lmshermesbridge.desktop",
             tmp_path / ".local/share/icons/hicolor/scalable/apps/io.github.lmshermesbridge.svg",
             tmp_path / ".config/lms-hermes-bridge/config.json",
             tmp_path / ".local/share/applications/other.desktop"]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep or remove")
    calls = []
    monkeypatch.setattr(uninstaller.subprocess, "run", lambda command, **kwargs:
                        calls.append(command) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(uninstaller.autostart, "set_enabled", lambda enabled: calls.append(("autostart", enabled)))
    monkeypatch.setattr(uninstaller.hotkey, "unregister", lambda: calls.append("hotkey") or True)
    uninstaller.uninstall()
    assert calls == [["pipx", "uninstall", "lms-hermes-bridge"], ("autostart", False), "hotkey"]
    assert not files[0].exists() and not files[1].exists()
    assert files[2].exists() and files[3].exists()


def test_failed_pipx_uninstall_keeps_desktop_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(uninstaller.Path, "home", lambda: tmp_path)
    desktop = tmp_path / ".local/share/applications/io.github.lmshermesbridge.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.touch()
    monkeypatch.setattr(uninstaller.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout="", stderr="pipx failed"))
    with pytest.raises(uninstaller.UninstallError, match="pipx failed"):
        uninstaller.uninstall()
    assert desktop.exists()