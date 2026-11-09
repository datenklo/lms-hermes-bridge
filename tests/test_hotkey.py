import shlex

from lms_hermes_bridge import hotkey


def test_launch_command_works_from_a_source_checkout(monkeypatch):
    monkeypatch.setattr(hotkey.shutil, "which", lambda _n: None)
    argv = shlex.split(hotkey.launch_command())
    assert argv[0] == "env" and argv[1].startswith("PYTHONPATH=") and argv[-2:] == ["-m", "lms_hermes_bridge"]
    assert argv[1].endswith("/src")


def test_installed_executable_is_preferred(monkeypatch):
    monkeypatch.setattr(hotkey.shutil, "which", lambda _n: "/home/u/.local/bin/lms-hermes-bridge")
    assert hotkey.launch_command() == "/home/u/.local/bin/lms-hermes-bridge"


def test_accelerator_validation():
    assert hotkey.is_valid("<Control><Alt>space") and hotkey.is_valid("<Super>F1")
    assert not hotkey.is_valid("Ctrl+Alt+X") and not hotkey.is_valid("")


def test_unregister_removes_only_own_shortcut(monkeypatch):
    from types import SimpleNamespace

    paths = ["/other/", hotkey.PATH]
    removed_keys = []
    media = SimpleNamespace(get_strv=lambda _key: paths,
                            set_strv=lambda _key, value: paths.__setitem__(slice(None), value) or True)
    binding = SimpleNamespace(reset=removed_keys.append)
    settings = SimpleNamespace(new=lambda _schema: media, new_with_path=lambda _schema, _path: binding,
                               sync=lambda: None)
    schemas = SimpleNamespace(get_default=lambda: SimpleNamespace(lookup=lambda *_: True))
    monkeypatch.setattr(hotkey, "Gio", SimpleNamespace(Settings=settings, SettingsSchemaSource=schemas))
    assert hotkey.unregister()
    assert paths == ["/other/"]
    assert removed_keys == ["name", "command", "binding"]
