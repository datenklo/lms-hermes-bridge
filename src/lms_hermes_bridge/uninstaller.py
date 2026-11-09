"""Remove the app's per-user installation without deleting user configuration."""
import subprocess
from pathlib import Path

from . import autostart, hotkey


class UninstallError(Exception):
    pass


def uninstall():
    try:
        result = subprocess.run(["pipx", "uninstall", "lms-hermes-bridge"],
                                capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        raise UninstallError(str(error)) from error
    if result.returncode:
        raise UninstallError(result.stderr.strip() or result.stdout.strip() or "pipx uninstall failed")
    try:
        autostart.set_enabled(False)
        data = Path.home() / ".local" / "share"
        (data / "applications" / "io.github.lmshermesbridge.desktop").unlink(missing_ok=True)
        (data / "icons" / "hicolor" / "scalable" / "apps" / "io.github.lmshermesbridge.svg").unlink(missing_ok=True)
        if not hotkey.unregister():
            raise UninstallError("Could not remove the GNOME shortcut")
    except OSError as error:
        raise UninstallError(str(error)) from error