# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import asyncio
import datetime
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from mi_fitness import MiHealthClient, TokenExpiredError

from .config import ConfigError, Settings
from .fds import download_and_decrypt_sleep_details, parse_all_day_sleep_bytes
from .lock import LockUnavailable, exclusive_file_lock
from .secure_files import save_auth_token, write_json_atomic, write_secret_json
from .stdio import safe_print
from .storage import init_health_db, sqlite_conn


@dataclass
class SyncResult:
    success: bool
    user_id: int | None = None
    counters: dict[str, int] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def failed(cls, message: str, *, user_id: int | None = None) -> SyncResult:
        return cls(False, user_id=user_id, error=message)


def log(message: str) -> None:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_print(f"[{now}] {message}", flush=True)


def format_epoch(epoch: int | float | None) -> str | None:
    if not epoch:
        return None
    return datetime.datetime.fromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M:%S")


async def run_sync(
    user_id: int | None = None,
    settings: Settings | None = None,
) -> SyncResult:
    settings = settings or Settings.from_env()
    try:
        resolved_user_id = settings.require_user_id(user_id)
    except ConfigError as exc:
        log(str(exc))
        return SyncResult.failed(str(exc), user_id=user_id)

    lock_path = settings.data_dir / f"sync_{resolved_user_id}.lock"
    try:
        with exclusive_file_lock(lock_path):
            return await _run_sync_locked(resolved_user_id, settings)
    except LockUnavailable:
        message = "Sync is already running for this user"
        log(message)
        return SyncResult.failed(message, user_id=resolved_user_id)


async def _run_sync_locked(resolved_user_id: int, settings: Settings) -> SyncResult:
    token_path = settings.token_path(resolved_user_id)
    if not token_path.exists() and os.getenv("SSECURITY"):
        _bootstrap_token_from_env(token_path)

    if not token_path.exists():
        message = f"Token file not found at: {token_path}"
        log(message)
        return SyncResult.failed(message, user_id=resolved_user_id)

    target_relative_uid = _target_relative_uid(token_path)
    if not target_relative_uid:
        message = f"No TARGET_RELATIVE_UID, target_relative_uid or user_id found in {token_path.name}"
        log(message)
        return SyncResult.failed(message, user_id=resolved_user_id)

    db_path = settings.canonical_user_db_path(resolved_user_id)
    status_path = settings.canonical_user_status_path(resolved_user_id)
    return await run_sync_for_user(
        token_path=token_path,
        db_path=db_path,
        status_path=status_path,
        target_relative_uid=target_relative_uid,
        user_id=resolved_user_id,
        settings=settings,
    )


def _bootstrap_token_from_env(token_path: Path) -> None:
    log(f"Token file not found. Auto-generating {token_path} from environment variables...")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "user_id": os.getenv("USER_ID", ""),
        "c_user_id": os.getenv("C_USER_ID", ""),
        "service_token": os.getenv("SERVICE_TOKEN", ""),
        "ssecurity": os.getenv("SSECURITY", ""),
        "pass_token": os.getenv("PASS_TOKEN", ""),
        "device_id": os.getenv("DEVICE_ID", f"an_{os.urandom(16).hex()}"),
        "target_relative_uid": os.getenv("TARGET_RELATIVE_UID", ""),
    }
    write_secret_json(token_path, token_data)


def _target_relative_uid(token_path: Path) -> str:
    try:
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log(f"Failed to read token file {token_path.name}: {exc}")
        return ""
    return (
        str(token_data.get("target_relative_uid", "")).strip()
        or os.getenv("TARGET_RELATIVE_UID", "").strip()
        or str(token_data.get("user_id", "")).strip()
    )


async def run_sync_for_user(
    *,
    token_path: Path,
    db_path: Path,
    status_path: Path,
    target_relative_uid: str,
    user_id: int,
    settings: Settings,
) -> SyncResult:
    try:
        relative_uid = int(target_relative_uid)
    except ValueError:
        message = "TARGET_RELATIVE_UID must be a valid integer UID"
        log(message)
        return SyncResult.failed(message, user_id=user_id)

    counters = {
        "steps_daily": 0,
        "sleep_daily": 0,
        "sleep_stages": 0,
        "heart_rate": 0,
        "blood_oxygen": 0,
    }
    log(
        f"Starting sync. Target UID: {relative_uid}. Query duration: {settings.query_duration} days. "
        f"DB: {db_path}. FDS sleep details: {'enabled' if settings.enable_fds_sleep_details else 'disabled'}"
    )
    init_health_db(db_path)
    latest_heart_rate = None
    latest_steps = None
    latest_sleep = None

    try:
        with sqlite_conn(db_path, row_factory=False) as conn:
            cursor = conn.cursor()
            async with MiHealthClient.from_token(str(token_path)) as client:
                from mi_fitness.auth.sts import sts_exchange

                log("Forcing STS exchange with clientSign to obtain a full serviceToken...")
                await sts_exchange(client.auth._ensure_http(), client.auth.token)
                save_auth_token(client.auth.token, token_path)

                steps_list = await client.get_steps(relative_uid, days=settings.query_duration)
                for item in steps_list:
                    if not item.at:
                        continue
                    date_str = item.at.date().isoformat()
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO steps_daily (date, total_steps, calories, distance_m, last_sync)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (date_str, item.steps, float(item.calories), float(item.distance), int(time.time())),
                    )
                    counters["steps_daily"] += 1
                    if not latest_steps or date_str >= latest_steps["date"]:
                        latest_steps = {
                            "date": date_str,
                            "total_steps": item.steps,
                            "calories": float(item.calories),
                            "distance_m": float(item.distance),
                            "last_sync": int(time.time()),
                        }

                sleep_list = await client.get_sleep(relative_uid, days=settings.query_duration)
                for sleep in sleep_list:
                    if not sleep.at:
                        continue
                    date_str = sleep.at.date().isoformat()
                    start_time = 0
                    end_time = 0
                    if sleep.segment_details:
                        start_time = sleep.segment_details[0].bedtime
                        end_time = sleep.segment_details[-1].wake_up_time
                        for segment in sleep.segment_details:
                            cursor.execute(
                                """
                                INSERT OR REPLACE INTO sleep_stages (start_time, stop_time, stage, duration_min)
                                VALUES (?, ?, ?, ?)
                                """,
                                (segment.bedtime, segment.wake_up_time, "sleep_segment", segment.duration),
                            )
                            counters["sleep_stages"] += 1
                            if settings.enable_fds_sleep_details:
                                await _sync_fds_segment(cursor, counters, client, relative_uid, segment)

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO sleep_daily
                            (date, light_sleep_min, deep_sleep_min, rem_sleep_min, awake_min,
                             total_duration_min, sleep_score, start_time, end_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            date_str,
                            sleep.sleep_light_duration,
                            sleep.sleep_deep_duration,
                            getattr(sleep, "sleep_rem_duration", 0) or 0,
                            getattr(sleep, "sleep_awake_duration", 0) or 0,
                            getattr(sleep, "total_duration", 0) or 0,
                            getattr(sleep, "sleep_score", 0) or 0,
                            start_time,
                            end_time,
                        ),
                    )
                    counters["sleep_daily"] += 1
                    if not latest_sleep or date_str >= latest_sleep["date"]:
                        latest_sleep = {
                            "date": date_str,
                            "light_sleep_min": sleep.sleep_light_duration,
                            "deep_sleep_min": sleep.sleep_deep_duration,
                            "rem_sleep_min": getattr(sleep, "sleep_rem_duration", 0) or 0,
                            "awake_min": getattr(sleep, "sleep_awake_duration", 0) or 0,
                            "total_duration_min": getattr(sleep, "total_duration", 0) or 0,
                            "sleep_score": getattr(sleep, "sleep_score", 0) or 0,
                            "start_time": start_time,
                            "end_time": end_time,
                        }

                hr_list = await client.get_heart_rate(relative_uid, days=settings.query_duration)
                for hr in hr_list:
                    cursor.execute(
                        "INSERT OR IGNORE INTO heart_rate (timestamp, value) VALUES (?, ?)",
                        (hr.time, hr.avg_hr),
                    )
                    counters["heart_rate"] += cursor.rowcount > 0
                    if hr.latest_hr:
                        cursor.execute(
                            "INSERT OR IGNORE INTO heart_rate (timestamp, value) VALUES (?, ?)",
                            (hr.latest_hr.time, hr.latest_hr.bpm),
                        )
                        counters["heart_rate"] += cursor.rowcount > 0
                        if not latest_heart_rate or hr.latest_hr.time > latest_heart_rate["timestamp"]:
                            latest_heart_rate = {"timestamp": hr.latest_hr.time, "value": hr.latest_hr.bpm}

                try:
                    spo2_list = await client.get_spo2_history(relative_uid, days=settings.query_duration)
                    for spo2 in spo2_list:
                        cursor.execute(
                            "INSERT OR IGNORE INTO blood_oxygen (timestamp, spo2, type) VALUES (?, ?, ?)",
                            (spo2.time, float(spo2.avg_spo2), "daily_avg"),
                        )
                        counters["blood_oxygen"] += cursor.rowcount > 0
                        if spo2.latest_spo2:
                            cursor.execute(
                                "INSERT OR IGNORE INTO blood_oxygen (timestamp, spo2, type) VALUES (?, ?, ?)",
                                (spo2.latest_spo2.time, float(spo2.latest_spo2.spo2), "latest"),
                            )
                            counters["blood_oxygen"] += cursor.rowcount > 0
                except Exception as exc:
                    log(f"Failed to fetch blood oxygen: {exc}")

                conn.commit()
    except TokenExpiredError:
        message = "Token has expired and auto-refresh failed. Action required: re-login."
        log(message)
        return SyncResult.failed(message, user_id=user_id)
    except Exception as exc:
        message = f"API request failed: {exc}"
        log(message)
        return SyncResult.failed(message, user_id=user_id)

    _write_status_file(status_path, latest_steps, latest_heart_rate, latest_sleep)
    log("Sync completed successfully.")
    return SyncResult(True, user_id=user_id, counters=counters)


async def _sync_fds_segment(cursor, counters: dict[str, int], client, relative_uid: int, segment) -> None:
    try:
        log(f"Requesting FDS sleep details for wake_up_time {segment.wake_up_time} ({format_epoch(segment.wake_up_time)})...")
        bin_data = await download_and_decrypt_sleep_details(
            client,
            relative_uid,
            segment.wake_up_time,
            segment.timezone,
            log_fn=log,
        )
        if not bin_data:
            return
        parsed = parse_all_day_sleep_bytes(bin_data)
        if not parsed:
            return
        log(
            f"Parsed {len(parsed['records']['heart_rate'])} HR readings and "
            f"{len(parsed['records']['spo2'])} SpO2 readings from FDS."
        )
        for timestamp, value in parsed["records"]["heart_rate"]:
            cursor.execute(
                "INSERT OR REPLACE INTO heart_rate (timestamp, value) VALUES (?, ?)",
                (timestamp, value),
            )
            counters["heart_rate"] += 1
        for timestamp, value in parsed["records"]["spo2"]:
            cursor.execute(
                "INSERT OR REPLACE INTO blood_oxygen (timestamp, spo2, type) VALUES (?, ?, ?)",
                (timestamp, float(value), "fds_detail"),
            )
            counters["blood_oxygen"] += 1
    except Exception as exc:
        log(f"Failed to sync details from FDS: {exc}")


def _write_status_file(status_path: Path, latest_steps, latest_heart_rate, latest_sleep) -> None:
    now_epoch = int(time.time())
    status_data = {
        "last_sync": now_epoch,
        "last_sync_time": format_epoch(now_epoch),
        "today": None,
        "latest_heart_rate": None,
        "latest_sleep": None,
    }
    if latest_steps:
        status_data["today"] = {
            "date": latest_steps["date"],
            "steps": latest_steps["total_steps"],
            "calories": latest_steps["calories"],
            "distance_m": latest_steps["distance_m"],
        }
    if latest_heart_rate:
        status_data["latest_heart_rate"] = {
            "timestamp": latest_heart_rate["timestamp"],
            "time": format_epoch(latest_heart_rate["timestamp"]),
            "value": latest_heart_rate["value"],
        }
    if latest_sleep:
        status_data["latest_sleep"] = {
            "date": latest_sleep["date"],
            "light_sleep_min": latest_sleep["light_sleep_min"],
            "deep_sleep_min": latest_sleep["deep_sleep_min"],
            "rem_sleep_min": latest_sleep["rem_sleep_min"],
            "awake_min": latest_sleep["awake_min"],
            "total_sleep_min": latest_sleep["total_duration_min"]
            or latest_sleep["light_sleep_min"] + latest_sleep["deep_sleep_min"],
            "sleep_score": latest_sleep["sleep_score"],
            "start_time": format_epoch(latest_sleep["start_time"]),
            "end_time": format_epoch(latest_sleep["end_time"]),
        }
    write_json_atomic(status_path, status_data)
    log(f"Status file written to {status_path}")


async def daemon_main(settings: Settings | None = None) -> int:
    settings = settings or Settings.from_env()
    if settings.sync_interval <= 0:
        result = await run_sync(settings=settings)
        return 0 if result.success else 1

    _waiting_logged = False
    while True:
        try:
            current_settings = Settings.from_env()
            if current_settings.telegram_allowed_user_id is None:
                if not _waiting_logged:
                    log("Синхронизатор ожидает привязки аккаунта через Telegram (/start)...")
                    _waiting_logged = True
                await asyncio.sleep(5)
                continue

            _waiting_logged = False  # Reset so we log again if user unregisters
            await run_sync(settings=current_settings)
        except Exception as exc:
            log(f"Unhandled error in main loop: {exc}")

        interval = Settings.from_env().sync_interval
        await asyncio.sleep(interval)
