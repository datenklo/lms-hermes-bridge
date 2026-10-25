"""Manage the per-user GNOME login autostart entry."""
import os
from pathlib import Path

from .hotkey import launch_command

DESKTOP_NAME = "lms-hermes-bridge.desktop"


def entry_path(config_home: str | Path | None = None) -> Path:
    root = Path(config_home or os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "autostart" / DESKTOP_NAME


def set_enabled(enabled: bool, config_home: str | Path | None = None) -> Path:
    """Create or remove this app's autostart entry. Other autostart items are untouched."""
    path = entry_path(config_home)
    if not enabled:
        path.unlink(missing_ok=True)
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=LMS Hermes Bridge\n"
        "Comment=Start LMS Hermes Bridge after login\n"
        f"Exec={launch_command()} --background\n"
        "Icon=io.github.lmshermesbridge\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )
    tmp = path.with_suffix(".desktop.tmp")
    tmp.write_text(content)
    tmp.chmod(0o644)
    os.replace(tmp, path)
    return path
