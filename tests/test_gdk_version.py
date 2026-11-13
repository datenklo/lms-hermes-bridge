"""The GObject-Introspection typelib versions must be pinned before import.

PyGObject warns once per unpinned namespace on every single start
(`PyGIWarning: Gdk was imported without specifying a version first`), and a
warning that fires every time hides the warnings that carry information.

Two measured properties of that warning decide the shape of this test:

* it only surfaces on the *first* import in a process, so the check runs in a
  subprocess — reloading the module in the test process always passes;
* `gi.PyGIWarning` derives from `Warning`, not `UserWarning`, so
  `-W error::UserWarning` lets it through (exit 0, warning on stderr).  The
  catch-all `-W error` does escalate it, but it also escalates every
  unrelated warning, which would fail the test for reasons it does not
  describe.

So the assertion is on the observable defect: the warning text in stderr.
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
        [sys.executable, "-c", "import lms_hermes_bridge.app"],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )
    assert result.returncode == 0, result.stderr
    assert "PyGIWarning" not in result.stderr, result.stderr
