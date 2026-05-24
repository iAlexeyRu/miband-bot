import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import miband_tracker.bot.app as bot_app
from miband_tracker.config import Settings
from miband_tracker.sync import SyncResult


class FakeUser:
    id = 123


class FakeUpdate:
    effective_user = FakeUser()
    message = object()
    callback_query = None


def test_service_menu_does_not_expose_invites_or_second_user() -> None:
    keyboard = bot_app.more_keyboard()
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    rendered = "\n".join(labels + [bot_app.more_text()])

    assert "Принять приглашения" not in rendered
    assert "Приглашения" not in rendered
    assert "втор" not in rendered.lower()


@pytest.mark.asyncio
async def test_cmd_start_without_token_shows_onboarding(monkeypatch: pytest.MonkeyPatch) -> None:
    update = FakeUpdate()
    context = object()
    show_onboarding = AsyncMock()
    show_main_menu = AsyncMock()

    monkeypatch.setattr(bot_app, "is_allowed", lambda _: True)
    monkeypatch.setattr(bot_app, "has_xiaomi_token", lambda: False)
    monkeypatch.setattr(bot_app, "safe_delete", AsyncMock())
    monkeypatch.setattr(bot_app, "show_onboarding", show_onboarding)
    monkeypatch.setattr(bot_app, "show_main_menu", show_main_menu)

    await bot_app.cmd_start(update, context)

    show_onboarding.assert_awaited_once_with(update, context, force_new=True)
    show_main_menu.assert_not_awaited()


@pytest.mark.asyncio
async def test_start_xiaomi_login_saves_token_syncs_and_opens_menu(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = FakeUpdate()
    context = object()
    token_path = tmp_path / "token_123.json"

    class FakeToken:
        def model_dump(self):
            return {
                "user_id": "456",
                "c_user_id": "",
                "service_token": "service",
                "ssecurity": "sec",
                "pass_token": "pass",
                "device_id": "device",
            }

    class FakeAuth:
        async def login_qr(self, *, qr_callback, max_wait):
            await qr_callback("https://example.test/qr.png", "https://example.test/login")
            return FakeToken()

        async def close(self):
            return None

    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "miband.db",
        status_path=tmp_path / "status.json",
        bot_state_db_path=tmp_path / "fitness_bot_state.db",
        telegram_bot_token="token",
        telegram_allowed_user_id=123,
        sync_interval=900,
        query_duration=2,
        enable_fds_sleep_details=True,
    )
    run_sync = AsyncMock(return_value=SyncResult(True, user_id=123))
    show_main_menu = AsyncMock()

    monkeypatch.setattr(bot_app, "SETTINGS", settings)
    monkeypatch.setattr(bot_app, "ALLOWED_USER_ID", 123)
    monkeypatch.setattr(bot_app, "AUTH_LOCK", asyncio.Lock())
    monkeypatch.setattr(bot_app, "SYNC_LOCK", asyncio.Lock())
    monkeypatch.setattr(bot_app, "XiaomiAuth", FakeAuth)
    monkeypatch.setattr(bot_app, "update_menu", AsyncMock())
    monkeypatch.setattr(bot_app, "run_sync", run_sync)
    monkeypatch.setattr(bot_app, "show_main_menu", show_main_menu)

    await bot_app.start_xiaomi_login(update, context)

    data = json.loads(token_path.read_text(encoding="utf-8"))
    assert data["user_id"] == "456"
    assert data["service_token"] == "service"
    run_sync.assert_awaited_once_with(123, settings)
    show_main_menu.assert_awaited_once_with(update, context)
