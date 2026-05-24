from pathlib import Path

from miband_tracker import storage
from miband_tracker.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
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


def test_init_health_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "miband_123.db"

    storage.init_health_db(db_path)
    storage.init_health_db(db_path)

    with storage.sqlite_conn(db_path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
    assert {"steps_daily", "sleep_daily", "heart_rate", "blood_oxygen"}.issubset(tables)


def test_zip_export_includes_non_empty_tables_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db_path = settings.canonical_user_db_path()
    storage.init_health_db(db_path)
    with storage.sqlite_conn(db_path, row_factory=False) as conn:
        conn.execute(
            "INSERT INTO steps_daily (date, total_steps, calories, distance_m, last_sync) VALUES (?, ?, ?, ?, ?)",
            ("2026-05-24", 1000, 10.0, 800.0, 1),
        )
        conn.commit()

    archive = storage.zip_export(settings)

    assert archive.getbuffer().nbytes > 0
    assert b"steps_daily.csv" in archive.getvalue()
