#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import asyncio
import sys

from miband_tracker.stdio import configure_utf8_stdio

configure_utf8_stdio()

from miband_tracker.config import ConfigError, Settings  # noqa: E402
from miband_tracker.sync import daemon_main, run_sync  # noqa: E402

__all__ = ["run_sync"]


def main() -> None:
    try:
        exit_code = asyncio.run(daemon_main(Settings.from_env()))
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr, flush=True)
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
