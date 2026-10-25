from lms_hermes_bridge import autostart
from lms_hermes_bridge.config import DEFAULTS


def test_login_autostart_defaults_to_enabled():
    assert DEFAULTS["start_on_login"] is True


def test_enable_writes_user_autostart_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "launch_command", lambda: "/home/test/.local/bin/lms-hermes-bridge")
    path = autostart.set_enabled(True, tmp_path)
    assert path == tmp_path / "autostart" / "lms-hermes-bridge.desktop"
    assert "Exec=/home/test/.local/bin/lms-hermes-bridge --background" in path.read_text()
    assert "X-GNOME-Autostart-enabled=true" in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o644


def test_disable_removes_only_bridge_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "launch_command", lambda: "/app")
    bridge = autostart.set_enabled(True, tmp_path)
    other = bridge.parent / "other.desktop"
    other.write_text("other")
    autostart.set_enabled(False, tmp_path)
    assert not bridge.exists()
    assert other.read_text() == "other"


def test_enable_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "launch_command", lambda: "/app")
    path = autostart.set_enabled(True, tmp_path)
    first = path.read_text()
    autostart.set_enabled(True, tmp_path)
    assert path.read_text() == first
