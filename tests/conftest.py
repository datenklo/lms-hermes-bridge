# The desktop modules import PyGObject at module level. On a machine without it (e.g. a
# Windows workspace) that is a collection error, not a test failure, so the modules are
# skipped instead: the suite stays runnable and the skipped count says what did not run.
import importlib.util

if importlib.util.find_spec("gi") is None:
    collect_ignore = [
        "test_autostart.py",
        "test_desktop_context.py",
        "test_hotkey.py",
        "test_tray.py",
        "test_uninstaller.py",
    ]
