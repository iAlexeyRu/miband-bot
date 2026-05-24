# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import io

from miband_tracker.stdio import safe_print


def test_safe_print_does_not_crash_on_non_ascii_with_charmap_stream() -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1251", errors="strict")

    safe_print("API 业务错误", file=stream, flush=True)
    stream.flush()

    assert b"API " in raw.getvalue()
    assert b"\\u4e1a" in raw.getvalue()
