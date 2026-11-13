"""The GObject-Introspection typelib versions must be pinned before import.

PyGObject warns once per unpinned namespace (`PyGIWarning: Gdk was not
specified: version can be arbitrary`), and a warning on every single start
is noise that hides the warnings worth reading.  The check runs in a
subprocess with warnings escalated to errors, because the namespace is only
unpinned on the *first* import in a process — reloading the module in the
test process would always pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("gi")

SRC = str(Path(__file__).resolve().parents[1] / "src")


def test_app_imports_without_pygi_warning() -> None:
    # pytest reaches the package through its own path configuration, which a
    # subprocess does not inherit; hand it the source root explicitly.
    pythonpath = SRC if not os.environ.get("PYTHONPATH") else SRC + os.pathsep + os.environ["PYTHONPATH"]
    result = subprocess.run(
        [sys.executable, "-W", "error::UserWarning", "-c", "import lms_hermes_bridge.app"],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )
    assert result.returncode == 0, result.stderr
