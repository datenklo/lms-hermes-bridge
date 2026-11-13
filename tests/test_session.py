"""Backend choice for window placement — pure logic, no GTK and no compositor needed."""
import pytest

from lms_hermes_bridge import session


@pytest.fixture
def no_typelib(monkeypatch):
    monkeypatch.setattr(session, "layer_shell_available", lambda: False)


@pytest.fixture
def with_typelib(monkeypatch):
    monkeypatch.setattr(session, "layer_shell_available", lambda: True)


HYPRLAND = {"XDG_SESSION_TYPE": "wayland", "HYPRLAND_INSTANCE_SIGNATURE": "sock", "DISPLAY": ":0"}
GNOME = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME", "DISPLAY": ":0"}


def test_x11_session_uses_x11():
    assert session.choose_backend({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) == "x11"


def test_hyprland_without_the_typelib_falls_back_to_x11(no_typelib):
    assert session.choose_backend(HYPRLAND) == "x11"


def test_hyprland_with_the_typelib_uses_layer_shell(with_typelib):
    assert session.choose_backend(HYPRLAND) == "layer-shell"
    assert session.wants_layer_shell(HYPRLAND)


def test_sway_is_detected_by_its_socket(with_typelib):
    env = {"XDG_SESSION_TYPE": "wayland", "SWAYSOCK": "/run/user/1000/sway-ipc.1000.1.sock"}
    assert session.choose_backend(env) == "layer-shell"


def test_gnome_stays_on_xwayland_even_with_the_typelib(with_typelib):
    # GNOME and KWin keep layer-shell for their own panels; an ordinary client is refused.
    assert session.choose_backend(GNOME) == "x11"
    assert session.choose_backend({**GNOME, "XDG_SESSION_DESKTOP": "gnome"}) == "x11"


def test_desktop_names_are_matched_case_insensitively(with_typelib):
    assert session.choose_backend({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"}) == "layer-shell"


def test_bare_wayland_without_xwayland_has_no_backend(no_typelib):
    assert session.choose_backend({"XDG_SESSION_TYPE": "wayland"}) == "none"


def test_explicit_choice_beats_the_session(with_typelib):
    assert session.choose_backend(GNOME, "layer-shell") == "layer-shell"
    assert session.choose_backend(HYPRLAND, "x11") == "x11"
    assert session.choose_backend(HYPRLAND, "none") == "none"


def test_a_typo_in_the_config_falls_back_to_auto(with_typelib):
    assert session.choose_backend(HYPRLAND, "layr-shell") == "layer-shell"


def test_typelib_lookup_uses_gi_typelib_path(tmp_path, monkeypatch):
    monkeypatch.setattr(session, "TYPELIB_DIRS", ())
    monkeypatch.setenv("GI_TYPELIB_PATH", str(tmp_path))
    assert not session.layer_shell_available()
    (tmp_path / session.TYPELIB).write_text("not a real typelib")
    assert session.layer_shell_available()
