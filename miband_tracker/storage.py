from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Settings

LOCAL_TZ = ZoneInfo("Europe/Moscow")
EXPORT_TABLES = ["steps_daily", "sleep_daily", "sleep_stages", "heart_rate", "blood_oxygen", "stress"]


@contextmanager
def sqlite_conn(path: Path, *, row_factory: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA busy_timeout = 5000")
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_health_db(db_path: Path) -> None:
    with sqlite_conn(db_path, row_factory=False) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS steps_daily (
                date TEXT PRIMARY KEY,
                total_steps INTEGER,
                calories REAL,
                distance_m REAL,
                last_sync INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS steps_detail (
                timestamp INTEGER PRIMARY KEY,
                steps INTEGER,
                calories REAL,
                distance_m REAL,
                activity_type TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sleep_daily (
                date TEXT PRIMARY KEY,
                light_sleep_min INTEGER,
                deep_sleep_min INTEGER,
                start_time INTEGER,
                end_time INTEGER,
                rem_sleep_min INTEGER DEFAULT 0,
                awake_min INTEGER DEFAULT 0,
                total_duration_min INTEGER DEFAULT 0,
                sleep_score INTEGER DEFAULT 0
            )
            """
        )
        _ensure_columns(cursor, "sleep_daily", {
            "rem_sleep_min": "INTEGER DEFAULT 0",
            "awake_min": "INTEGER DEFAULT 0",
            "total_duration_min": "INTEGER DEFAULT 0",
            "sleep_score": "INTEGER DEFAULT 0",
        })
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sleep_stages (
                start_time INTEGER PRIMARY KEY,
                stop_time INTEGER,
                stage TEXT,
                duration_min INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS heart_rate (
                timestamp INTEGER PRIMARY KEY,
                value INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stress (
                timestamp INTEGER PRIMARY KEY,
                value INTEGER
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blood_oxygen (
                timestamp INTEGER PRIMARY KEY,
                spo2 REAL,
                type TEXT
            )
            """
        )
        conn.commit()


def _ensure_columns(cursor: sqlite3.Cursor, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_state_db(settings: Settings) -> None:
    with sqlite_conn(settings.bot_state_db_path, row_factory=False) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_menu (
                user_id INTEGER PRIMARY KEY,
                menu_message_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def get_user_menu_msg_id(settings: Settings, user_id: int) -> int | None:
    try:
        with sqlite_conn(settings.bot_state_db_path, row_factory=False) as conn:
            row = conn.execute(
                "SELECT menu_message_id FROM user_menu WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return int(row[0]) if row else None
    except sqlite3.Error:
        return None


def set_user_menu_msg_id(settings: Settings, user_id: int, msg_id: int) -> None:
    with sqlite_conn(settings.bot_state_db_path, row_factory=False) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_menu (user_id, menu_message_id, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, msg_id, datetime.now(LOCAL_TZ).isoformat(timespec="seconds")),
        )
        conn.commit()


def health_db_exists(settings: Settings, user_id: int | None = None) -> bool:
    return settings.user_db_path(user_id).exists()


def fetch_one(settings: Settings, query: str, params: tuple = (), user_id: int | None = None) -> sqlite3.Row | None:
    if not health_db_exists(settings, user_id):
        return None
    with sqlite_conn(settings.user_db_path(user_id)) as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(settings: Settings, query: str, params: tuple = (), user_id: int | None = None) -> list[sqlite3.Row]:
    if not health_db_exists(settings, user_id):
        return []
    with sqlite_conn(settings.user_db_path(user_id)) as conn:
        return conn.execute(query, params).fetchall()


def read_status_file(settings: Settings, user_id: int | None = None) -> dict:
    try:
        return json.loads(settings.user_status_path(user_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def zip_export(settings: Settings, user_id: int | None = None) -> io.BytesIO:
    bio = io.BytesIO()
    with sqlite_conn(settings.user_db_path(user_id)) as conn:
        with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for table in EXPORT_TABLES:
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table,),
                ).fetchone()
                if not exists:
                    continue
                cursor = conn.execute(f"SELECT * FROM {table} ORDER BY 1")
                rows = cursor.fetchall()
                if not rows:
                    continue
                csv_text = io.StringIO()
                writer = csv.writer(csv_text)
                writer.writerow([desc[0] for desc in cursor.description])
                writer.writerows([tuple(row) for row in rows])
                archive.writestr(f"{table}.csv", csv_text.getvalue())
    bio.seek(0)
    bio.name = f"miband-health-{datetime.now(LOCAL_TZ).strftime('%Y%m%d-%H%M')}.zip"
    return bio
