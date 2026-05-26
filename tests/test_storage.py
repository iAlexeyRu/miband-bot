# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

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
    assert {
        "steps_daily",
        "sleep_daily",
        "heart_rate",
        "blood_oxygen",
        "stress",
        "calories_daily",
        "weight",
        "workouts",
    }.issubset(tables)


def test_extended_health_tables_have_expected_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "miband_123.db"
    storage.init_health_db(db_path)

    with storage.sqlite_conn(db_path, row_factory=False) as conn:
        columns = {
            table: {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for table in ("stress", "calories_daily", "weight", "workouts")
        }

    assert columns["stress"] == {"timestamp", "value"}
    assert {
        "date",
        "total_cal",
        "active_cal",
        "valid_stand_hours",
        "intensity_minutes",
        "last_sync",
    }.issubset(columns["calories_daily"])
    assert {"timestamp", "weight_kg", "bmi", "body_fat_pct"}.issubset(columns["weight"])
    assert {
        "workout_id",
        "sport_type",
        "start_time",
        "end_time",
        "duration_sec",
        "calories",
        "avg_hr",
        "max_hr",
        "min_hr",
        "watermark",
        "raw_json",
    }.issubset(columns["workouts"])


def test_zip_export_includes_non_empty_tables_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db_path = settings.canonical_user_db_path()
    storage.init_health_db(db_path)
    with storage.sqlite_conn(db_path, row_factory=False) as conn:
        conn.execute(
            "INSERT INTO steps_daily (date, total_steps, calories, distance_m, last_sync) VALUES (?, ?, ?, ?, ?)",
            ("2026-05-24", 1000, 10.0, 800.0, 1),
        )
        conn.execute(
            "INSERT INTO stress (timestamp, value) VALUES (?, ?)",
            (1779760000, 42),
        )
        conn.execute(
            """
            INSERT INTO workouts
                (workout_id, sport_type, start_time, end_time, duration_sec,
                 calories, avg_hr, max_hr, min_hr, watermark, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("w1", "free_training", 1779760000, 1779760600, 600, 55.0, 110, 130, 90, 1, "{}"),
        )
        conn.commit()

    archive = storage.zip_export(settings)

    assert archive.getbuffer().nbytes > 0
    assert b"steps_daily.csv" in archive.getvalue()
    assert b"stress.csv" in archive.getvalue()
    assert b"workouts.csv" in archive.getvalue()
