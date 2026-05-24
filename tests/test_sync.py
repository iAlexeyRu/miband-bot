from pathlib import Path

import pytest

from miband_tracker.config import Settings
from miband_tracker.sync import run_sync


@pytest.mark.asyncio
async def test_run_sync_missing_token_returns_failed_result(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "miband.db",
        status_path=tmp_path / "status.json",
        bot_state_db_path=tmp_path / "fitness_bot_state.db",
        telegram_bot_token="token",
        telegram_allowed_user_id=123,
        sync_interval=0,
        query_duration=2,
        enable_fds_sleep_details=True,
    )

    result = await run_sync(settings=settings)

    assert not result.success
    assert result.user_id == 123
    assert "Token file not found" in (result.error or "")
