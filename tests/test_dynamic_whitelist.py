# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

from telegram import Update, User

from miband_tracker.bot import app
from miband_tracker.config import Settings


def test_dynamic_whitelisting(tmp_path: Path) -> None:
    # Setup temporary directories and config
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Override settings in app and os.environ
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["TELEGRAM_ALLOWED_USER_ID"] = ""

    app.SETTINGS = Settings.from_env()
    app.ALLOWED_USER_ID = None

    # Verify initial state
    assert app.ALLOWED_USER_ID is None
    assert not (data_dir / "allowed_user.id").exists()

    # 1. First user tries to access
    user_1 = MagicMock(spec=User)
    user_1.id = 999999
    update_1 = MagicMock(spec=Update)
    update_1.effective_user = user_1

    # First access should be allowed and should bind user_1
    assert app.is_allowed(update_1) is True
    assert app.ALLOWED_USER_ID == 999999
    assert (data_dir / "allowed_user.id").exists()
    assert (data_dir / "allowed_user.id").read_text(encoding="utf-8").strip() == "999999"

    # 2. Second user tries to access
    user_2 = MagicMock(spec=User)
    user_2.id = 888888
    update_2 = MagicMock(spec=Update)
    update_2.effective_user = user_2

    # Access for user_2 must be blocked
    assert app.is_allowed(update_2) is False

    # 3. First user accesses again
    assert app.is_allowed(update_1) is True

    # 4. Verify settings reloading
    reloaded_settings = Settings.from_env()
    assert reloaded_settings.telegram_allowed_user_id == 999999
