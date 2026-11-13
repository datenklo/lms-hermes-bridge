"""The GObject-Introspection typelib versions must be pinned before import.

PyGObject warns once per unpinned namespace (`PyGIWarning: Gdk was not
specified: version can be arbitrary`), and a warning on every single start
is noise that hides the warnings worth reading.  The check runs in a
subprocess with warnings escalated to errors, because the namespace is only
unpinned on the *first* import in a process — reloading the module in the
test process would always pass.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

pytest.importorskip("gi")


def test_app_imports_without_pygi_warning() -> None:
    result = subprocess.run(
        [sys.executable, "-W", "error::UserWarning", "-c", "import lms_hermes_bridge.app"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
