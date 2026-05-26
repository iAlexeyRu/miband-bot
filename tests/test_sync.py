# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from pathlib import Path

import pytest

from miband_tracker.config import Settings
from miband_tracker.storage import init_health_db, sqlite_conn
from miband_tracker.sync import _sync_workouts, run_sync


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


@pytest.mark.asyncio
async def test_sync_workouts_inserts_watermark_records(tmp_path: Path) -> None:
    db_path = tmp_path / "miband_123.db"
    init_health_db(db_path)

    class FakeClient:
        async def _request(self, method, path, params):
            assert method == "GET"
            assert path == "/app/v1/data/get_sport_records_by_watermark"
            assert params["relative_uid"] == 456
            return {
                "result": {
                    "has_more": False,
                    "sport_records": [
                        {
                            "sid": "w1",
                            "key": "free_training",
                            "time": 1779752903,
                            "watermark": 12345,
                            "value": (
                                '{"start_time": 1779752903, "end_time": 1779753050, '
                                '"duration": 142, "calories": 7, "avg_hrm": 95, '
                                '"max_hrm": 152, "min_hrm": 80}'
                            ),
                        }
                    ],
                }
            }

    counters = {"workouts": 0}
    with sqlite_conn(db_path, row_factory=False) as conn:
        cursor = conn.cursor()
        await _sync_workouts(FakeClient(), cursor, counters, 456)
        conn.commit()

    with sqlite_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM workouts WHERE workout_id = ?", ("w1",)).fetchone()

    assert counters["workouts"] == 1
    assert row is not None
    assert row["sport_type"] == "free_training"
    assert row["duration_sec"] == 142
    assert row["avg_hr"] == 95
    assert row["watermark"] == 12345
