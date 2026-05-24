# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import os
import sys
from typing import TextIO


def configure_utf8_stdio() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


def safe_print(text: str, *, file: TextIO | None = None, flush: bool = False) -> None:
    stream = file or sys.stdout
    try:
        print(text, file=stream, flush=flush)
        return
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        fallback = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        print(fallback, file=stream, flush=flush)
