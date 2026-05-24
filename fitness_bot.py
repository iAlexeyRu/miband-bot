#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

from miband_tracker.stdio import configure_utf8_stdio

configure_utf8_stdio()

from miband_tracker.bot.app import main  # noqa: E402

if __name__ == "__main__":
    main()
