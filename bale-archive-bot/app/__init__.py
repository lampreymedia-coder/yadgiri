"""Bale archive bot application package.

Force UTF-8 on Windows before any other module logs Persian text.
"""

from __future__ import annotations

import contextlib
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        with contextlib.suppress(OSError, ValueError):
            reconfigure(encoding="utf-8")
