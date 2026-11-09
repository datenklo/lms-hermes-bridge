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


@pytest.mark.parametrize("answer,expected", [("", 1), ("n", 1), ("yes", 0)])
def test_terminal_uninstall_requires_confirmation(monkeypatch, answer, expected):
    calls = []
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    monkeypatch.setattr(uninstaller, "uninstall", lambda: calls.append("uninstall"))
    assert uninstaller.main([]) == expected
    assert calls == (["uninstall"] if expected == 0 else [])


def test_delete_all_removes_configuration_before_uninstall(monkeypatch, tmp_path):
    configuration = tmp_path / "lms-hermes-bridge"
    configuration.mkdir()
    (configuration / "config.json").write_text("secret")
    monkeypatch.setattr(uninstaller.config, "CONFIG_DIR", configuration)
    monkeypatch.setattr(uninstaller, "_component_paths", lambda _home: {})
    monkeypatch.setattr(uninstaller, "_hermes_command", lambda _home: None)
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    monkeypatch.setattr(uninstaller, "uninstall", lambda: None if not configuration.exists() else pytest.fail("configuration remains"))
    assert uninstaller.main(["--delete-all"]) == 0


def test_delete_all_refuses_symlinked_configuration(monkeypatch, tmp_path):
    target = tmp_path / "other"
    target.mkdir()
    configuration = tmp_path / "lms-hermes-bridge"
    configuration.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(uninstaller.config, "CONFIG_DIR", configuration)
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    monkeypatch.setattr(uninstaller, "uninstall", lambda: pytest.fail("uninstall should not run"))
    assert uninstaller.main(["--delete-all"]) == 1
    assert target.exists()


def test_delete_all_confirms_each_component(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(uninstaller.Path, "home", lambda: home)
    for variable in ("STRATA_DATA_DIR", "STRATA_BIN_DIR", "XDG_DATA_HOME", "HERMES_HOME"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(uninstaller.shutil, "which", lambda _name: None)
    config = home / ".config/lms-hermes-bridge"
    pi = home / ".pi/agent"
    lmstudio = home / ".lmstudio"
    strata = home / ".local/share/strata"
    for path in (config, pi, lmstudio, strata):
        path.mkdir(parents=True)
        (path / "secret").write_text("private")
    monkeypatch.setattr(uninstaller.config, "CONFIG_DIR", config)
    answers = iter(["yes", "no", "yes", "no"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(uninstaller, "uninstall", lambda: None)
    assert uninstaller.main(["--delete-all"]) == 0
    assert not config.exists() and not pi.exists()
    assert lmstudio.exists() and strata.exists()


def test_eof_during_component_confirmation_deletes_nothing(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "lms-hermes-bridge"
    config.mkdir()
    pi = home / ".pi/agent"
    pi.mkdir(parents=True)
    monkeypatch.setattr(uninstaller.Path, "home", lambda: home)
    monkeypatch.setattr(uninstaller.config, "CONFIG_DIR", config)
    monkeypatch.setattr(uninstaller, "_component_paths", lambda _home: {"Pi": [pi]})
    answers = iter(["yes"])
    def answer(_prompt):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError
    monkeypatch.setattr("builtins.input", answer)
    monkeypatch.setattr(uninstaller, "uninstall", lambda: pytest.fail("must not uninstall"))
    assert uninstaller.main(["--delete-all"]) == 1
    assert config.exists() and pi.exists()


def test_hermes_preview_and_uninstall(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    configuration = home / "lms-hermes-bridge"
    configuration.mkdir()
    monkeypatch.setattr(uninstaller.Path, "home", lambda: home)
    monkeypatch.setattr(uninstaller.config, "CONFIG_DIR", configuration)
    monkeypatch.setattr(uninstaller, "_component_paths", lambda _home: {})
    monkeypatch.setattr(uninstaller, "_hermes_command", lambda _home: "/fake/hermes")
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    calls = []
    monkeypatch.setattr(uninstaller.subprocess, "run", lambda command, **kwargs:
                        calls.append(command) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(uninstaller, "uninstall", lambda: None)
    assert uninstaller.main(["--delete-all"]) == 0
    assert calls == [["/fake/hermes", "uninstall", "--full", "--dry-run"],
                     ["/fake/hermes", "uninstall", "--full"]]


def test_component_paths_refuse_symlinks_and_unsafe_strata_location(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / ".pi").mkdir()
    (home / ".pi/agent").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("STRATA_DATA_DIR", str(home))
    monkeypatch.delenv("STRATA_BIN_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert uninstaller._component_paths(home) == {}
    assert outside.exists() and home.exists()


def test_strata_link_must_point_into_its_installation(monkeypatch, tmp_path):
    home = tmp_path / "home"
    data = home / ".local/share/strata"
    binary = home / ".local/bin/strata"
    data.mkdir(parents=True)
    binary.parent.mkdir(parents=True)
    foreign = home / "foreign"
    foreign.touch()
    binary.symlink_to(foreign)
    monkeypatch.delenv("STRATA_DATA_DIR", raising=False)
    monkeypatch.delenv("STRATA_BIN_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert uninstaller._component_paths(home)["Strata"] == [data]
    uninstaller._remove_component_paths([data], home)
    assert binary.is_symlink() and foreign.exists()


def test_failed_hermes_preview_preserves_bridge(monkeypatch, tmp_path):
    configuration = tmp_path / "lms-hermes-bridge"
    configuration.mkdir()
    monkeypatch.setattr(uninstaller.config, "CONFIG_DIR", configuration)
    monkeypatch.setattr(uninstaller, "_component_paths", lambda _home: {})
    monkeypatch.setattr(uninstaller, "_hermes_command", lambda _home: "/fake/hermes")
    monkeypatch.setattr(uninstaller.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    monkeypatch.setattr(uninstaller, "uninstall", lambda: pytest.fail("must not uninstall"))
    assert uninstaller.main(["--delete-all"]) == 1
    assert configuration.exists()