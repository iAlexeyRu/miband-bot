#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import asyncio
import html
import io
import logging
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from mi_fitness.auth import XiaomiAuth
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from miband_tracker import storage
from miband_tracker.config import ConfigError, Settings
from miband_tracker.secure_files import save_auth_token
from miband_tracker.sync import run_sync

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logger = logging.getLogger("fitness-bot")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SETTINGS = Settings.from_env()
BOT_TOKEN = SETTINGS.telegram_bot_token
ALLOWED_USER_ID = SETTINGS.telegram_allowed_user_id
DB_PATH = str(SETTINGS.db_path)
LOCAL_TZ = ZoneInfo("Europe/Moscow")
SYNC_LOCK = asyncio.Lock()
AUTH_LOCK = asyncio.Lock()

STEP_GOAL = 10_000  # можно вынести в env при желании


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def is_allowed(update: Update) -> bool:
    global ALLOWED_USER_ID
    uid = update.effective_user.id if update.effective_user else None
    if uid is None:
        return False
    if ALLOWED_USER_ID is None:
        ALLOWED_USER_ID = uid
        try:
            allowed_user_file = SETTINGS.data_dir / "allowed_user.id"
            SETTINGS.data_dir.mkdir(parents=True, exist_ok=True)
            allowed_user_file.write_text(str(uid), encoding="utf-8")
            logger.info("🎉 Бот успешно привязан к первому пользователю (ID: %s)!", uid)
        except Exception as e:
            logger.error("Не удалось сохранить ID владельца в файл: %s", e)
        return True
    return uid == ALLOWED_USER_ID


def with_user_context(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        return await func(update, context, *args, **kwargs)
    return wrapper


def get_user_db_path() -> str:
    if ALLOWED_USER_ID is None:
        return DB_PATH
    return str(SETTINGS.user_db_path(ALLOWED_USER_ID))


def get_user_status_path() -> str:
    if ALLOWED_USER_ID is None:
        return str(SETTINGS.status_path)
    return str(SETTINGS.user_status_path(ALLOWED_USER_ID))


def get_xiaomi_token_path() -> Path | None:
    if ALLOWED_USER_ID is None:
        return None
    try:
        return SETTINGS.token_path(ALLOWED_USER_ID)
    except ConfigError:
        return None


def has_xiaomi_token() -> bool:
    token_path = get_xiaomi_token_path()
    return bool(token_path and token_path.exists())


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------
def format_epoch(epoch: int | float | None, with_date: bool = True) -> str:
    if not epoch:
        return "н/д"
    fmt = "%Y-%m-%d %H:%M" if with_date else "%H:%M"
    return datetime.fromtimestamp(int(epoch), LOCAL_TZ).strftime(fmt)


def format_relative_time(epoch: int | float | None) -> str:
    if not epoch:
        return "н/д"
    diff = int(time.time() - int(epoch))
    if diff < 60:
        return "только что"
    diff_min = diff // 60
    if diff_min < 60:
        return f"{diff_min} мин. назад"
    diff_hours = diff_min // 60
    if diff_hours < 24:
        return f"{diff_hours} ч. назад"
    diff_days = diff_hours // 24
    if diff_days == 1:
        return "вчера"
    return f"{diff_days} дн. назад"


def format_minutes(minutes: int | float | None) -> str:
    if minutes is None:
        return "н/д"
    minutes = int(minutes)
    return f"{minutes // 60} ч {minutes % 60:02d} мин"


def step_goal_bar(steps: int | float | None, goal: int = STEP_GOAL) -> str:
    if steps is None:
        steps = 0
    steps_int = int(steps)
    percent = min(100, round(steps_int / goal * 100)) if goal > 0 else 0
    filled = percent // 10
    bar = "█" * filled + "░" * (10 - filled)
    return f"<code>[{bar}]</code> {percent}%"


def step_goal_text(steps: int | float | None, goal: int = STEP_GOAL) -> str:
    if steps is None:
        return f"Цель {goal:,} шагов".replace(",", " ")
    steps_int = int(steps)
    left = max(0, goal - steps_int)
    if left:
        text = f"Цель {goal:,} · осталось {left:,} шагов"
    else:
        text = f"Цель {goal:,} · дневная цель выполнена! 🎉"
    return text.replace(",", " ")


def make_sparkline(values: list[float | int]) -> str:
    if not values:
        return ""
    sparks = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val
    if val_range == 0:
        return sparks[4] * min(len(values), 20)
    sparkline = []
    for val in values:
        idx = int((val - min_val) / val_range * (len(sparks) - 1))
        sparkline.append(sparks[idx])
    return "".join(sparkline)


def get_sleep_sparkline(table: str, field: str, start_epoch: int, end_epoch: int) -> str:
    rows = fetch_all(
        f"SELECT {field} FROM {table} WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
        (start_epoch, end_epoch),
    )
    if not rows:
        return ""
    values = [row[field] for row in rows]
    if len(values) > 20:
        step = len(values) / 20
        values = [values[int(i * step)] for i in range(20)]
    return make_sparkline(values)


def relative_day_label(day_str: str | None) -> str:
    if not day_str:
        return "Последний день"
    try:
        day_value = parse_day(day_str)
    except ValueError:
        return f"День: {day_str}"
    today = datetime.now(LOCAL_TZ).date()
    if day_value == today:
        return "Сегодня"
    if day_value == today - timedelta(days=1):
        return "Вчера"
    return day_str


def day_bounds(day_value: date) -> tuple[int, int]:
    start = datetime.combine(day_value, dt_time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def parse_day(day_str: str) -> date:
    return datetime.strptime(day_str, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Sleep quality label
# ---------------------------------------------------------------------------
def sleep_total(sleep: sqlite3.Row) -> int:
    """Реальное время сна: total_duration_min если есть, иначе light+deep."""
    total = int(sleep["total_duration_min"]) if sleep["total_duration_min"] else 0
    if total > 0:
        return total
    return int(sleep["light_sleep_min"] or 0) + int(sleep["deep_sleep_min"] or 0)


def sleep_quality_label(total_min: int, deep_min: int) -> str:
    """Оценка качества сна по общей длительности и доле глубокого сна."""
    if total_min >= 420 and deep_min >= 60:
        return "🟢 Отличный"
    if total_min >= 360 and deep_min >= 40:
        return "🟡 Хороший"
    if total_min >= 300:
        return "🟠 Средний"
    return "🔴 Недостаточный"


# ---------------------------------------------------------------------------
# Daily tip engine
# ---------------------------------------------------------------------------
def daily_tip(steps: sqlite3.Row | None, sleep: sqlite3.Row | None, hr: sqlite3.Row | None) -> str:
    """Генерирует один персональный инсайт на основе последних данных."""
    tips = []

    if steps:
        s = int(steps["total_steps"] or 0)
        if s < 5000:
            tips.append("💡 Сегодня совсем мало шагов. Прогулка в 20 минут добавит ~2 000 шагов и заметно поднимет настроение.")
        elif s >= STEP_GOAL:
            tips.append("💡 Дневная норма шагов выполнена — отличный результат!")
        elif s >= 7000:
            tips.append(f"💡 До цели {STEP_GOAL:,} шагов осталось {STEP_GOAL - s:,} — почти дошли!".replace(",", " "))

    if sleep:
        total = sleep_total(sleep)
        deep = int(sleep["deep_sleep_min"] or 0)
        if total < 300:
            tips.append("💡 Ночной сон меньше 5 часов — это мало. Постарайтесь лечь пораньше сегодня.")
        elif total < 360:
            tips.append("💡 Ночной сон меньше 6 часов. Постарайтесь лечь пораньше сегодня.")
        elif deep < 30:
            tips.append("💡 Глубокого сна было совсем мало. Попробуйте проветрить комнату и ограничить экраны за час до сна.")

    if hr:
        bpm = int(hr["value"])
        if bpm > 90:
            tips.append("💡 Пульс в покое выше нормы — возможно, организм устал или есть стресс. Следите за самочувствием.")
        elif bpm < 50:
            tips.append("💡 Очень низкий пульс — если это спортивная норма, всё хорошо. Если нет — стоит обратить внимание.")

    if not tips:
        tips.append("💡 Данных достаточно, продолжайте в том же духе!")

    return tips[0]  # показываем один самый актуальный совет


# ---------------------------------------------------------------------------
# DB: health
# ---------------------------------------------------------------------------
def health_db_exists() -> bool:
    return storage.health_db_exists(SETTINGS, ALLOWED_USER_ID)


def health_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_user_db_path())
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    return conn


def fetch_one(query: str, params: tuple = ()) -> sqlite3.Row | None:
    return storage.fetch_one(SETTINGS, query, params, ALLOWED_USER_ID)


def fetch_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    return storage.fetch_all(SETTINGS, query, params, ALLOWED_USER_ID)


# ---------------------------------------------------------------------------
# DB: bot state
# ---------------------------------------------------------------------------
def init_state_db() -> None:
    storage.init_state_db(SETTINGS)


def get_user_menu_msg_id(user_id: int) -> int | None:
    try:
        return storage.get_user_menu_msg_id(SETTINGS, user_id)
    except Exception as e:
        logger.warning("Failed to read menu message id for %s: %s", user_id, e)
        return None


def set_user_menu_msg_id(user_id: int, msg_id: int) -> None:
    try:
        storage.set_user_menu_msg_id(SETTINGS, user_id, msg_id)
    except Exception as e:
        logger.warning("Failed to save menu message id for %s: %s", user_id, e)


# ---------------------------------------------------------------------------
# Telegram: safe edit with exponential backoff
# ---------------------------------------------------------------------------
async def safe_delete(message: Message | None) -> None:
    if not message:
        return
    try:
        await message.delete()
    except Exception as e:
        logger.debug("Failed to delete message: %s", e)


async def send_or_update_menu(
    bot,
    user_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    force_new: bool = False,
) -> None:
    chat_id = user_id
    msg_id = get_user_menu_msg_id(user_id)

    if msg_id and not force_new:
        for attempt in range(3):
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
                return
            except RetryAfter as e:
                wait = e.retry_after + attempt
                logger.warning("Flood control: waiting %ss (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
            except TelegramError as e:
                msg = str(e)
                if "Message is not modified" in msg:
                    return
                if "Message to edit not found" in msg or "message can't be edited" in msg.lower():
                    break  # сообщение пропало — создаём новое
                logger.warning("Edit failed (attempt %d): %s", attempt + 1, e)
                break

    # Старое сообщение устарело или не найдено — удаляем и создаём новое
    if msg_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.debug("Failed to delete old menu message %s: %s", msg_id, e)

    new_msg = await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True,
    )
    set_user_menu_msg_id(user_id, new_msg.message_id)


async def update_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    force_new: bool = False,
) -> None:
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    if update.callback_query and update.callback_query.message:
        set_user_menu_msg_id(user_id, update.callback_query.message.message_id)
    await send_or_update_menu(context.bot, user_id, text, reply_markup, force_new)


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------
def read_status_file() -> dict:
    return storage.read_status_file(SETTINGS, ALLOWED_USER_ID)


def latest_steps() -> sqlite3.Row | None:
    return fetch_one(
        """
        SELECT date, total_steps, calories, distance_m, last_sync
        FROM steps_daily
        ORDER BY date DESC
        LIMIT 1
        """
    )


def latest_sleep() -> sqlite3.Row | None:
    return fetch_one(
        """
        SELECT date, light_sleep_min, deep_sleep_min, start_time, end_time,
               COALESCE(rem_sleep_min, 0) AS rem_sleep_min,
               COALESCE(awake_min, 0) AS awake_min,
               COALESCE(total_duration_min, 0) AS total_duration_min,
               COALESCE(sleep_score, 0) AS sleep_score
        FROM sleep_daily
        ORDER BY date DESC
        LIMIT 1
        """
    )


def latest_hr() -> sqlite3.Row | None:
    return fetch_one("SELECT timestamp, value FROM heart_rate ORDER BY timestamp DESC LIMIT 1")


def latest_spo2() -> sqlite3.Row | None:
    return fetch_one(
        "SELECT timestamp, spo2, type FROM blood_oxygen ORDER BY timestamp DESC LIMIT 1"
    )


def resting_hr(start_epoch: int, end_epoch: int) -> int | None:
    """Пульс покоя = минимальный за окно сна (игнорируем нули и аномалии < 30)."""
    row = fetch_one(
        """
        SELECT MIN(value) AS min_hr
        FROM heart_rate
        WHERE timestamp >= ? AND timestamp < ? AND value > 30
        """,
        (start_epoch, end_epoch),
    )
    if row and row["min_hr"]:
        return int(row["min_hr"])
    return None


def metric_stats(table: str, field: str, start_epoch: int, end_epoch: int) -> sqlite3.Row | None:
    return fetch_one(
        f"""
        SELECT COUNT(*) AS count,
               ROUND(AVG({field}), 1) AS avg_value,
               MIN({field}) AS min_value,
               MAX({field}) AS max_value
        FROM {table}
        WHERE timestamp >= ? AND timestamp < ?
        """,
        (start_epoch, end_epoch),
    )


def sleep_window_stats(sleep: sqlite3.Row | None) -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
    if not sleep or not sleep["start_time"] or not sleep["end_time"]:
        return None, None
    hr = metric_stats("heart_rate", "value", int(sleep["start_time"]), int(sleep["end_time"]))
    spo2 = metric_stats(
        "blood_oxygen", "spo2", int(sleep["start_time"]), int(sleep["end_time"])
    )
    return hr, spo2


def day_summary(day_str: str) -> dict:
    day_value = parse_day(day_str)
    start_epoch, end_epoch = day_bounds(day_value)
    steps = fetch_one(
        """
        SELECT date, total_steps, calories, distance_m, last_sync
        FROM steps_daily
        WHERE date = ?
        """,
        (day_str,),
    )
    sleep = fetch_one(
        """
        SELECT date, light_sleep_min, deep_sleep_min, start_time, end_time,
               COALESCE(rem_sleep_min, 0) AS rem_sleep_min,
               COALESCE(awake_min, 0) AS awake_min,
               COALESCE(total_duration_min, 0) AS total_duration_min,
               COALESCE(sleep_score, 0) AS sleep_score
        FROM sleep_daily
        WHERE date = ?
        """,
        (day_str,),
    )
    hr = metric_stats("heart_rate", "value", start_epoch, end_epoch)
    spo2 = metric_stats("blood_oxygen", "spo2", start_epoch, end_epoch)
    return {"date": day_str, "steps": steps, "sleep": sleep, "hr": hr, "spo2": spo2}


def available_days(limit: int = 14) -> list[str]:
    rows = fetch_all(
        """
        SELECT date FROM (
            SELECT date FROM steps_daily
            UNION
            SELECT date FROM sleep_daily
        )
        ORDER BY date DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [row["date"] for row in rows]


def period_bounds(days: int) -> tuple[date, date, int, int]:
    end_day = datetime.now(LOCAL_TZ).date()
    start_day = end_day - timedelta(days=days - 1)
    start_epoch, _ = day_bounds(start_day)
    _, end_epoch = day_bounds(end_day)
    return start_day, end_day, start_epoch, end_epoch


def period_summary(days: int) -> dict:
    start_day, end_day, start_epoch, end_epoch = period_bounds(days)
    steps = fetch_all(
        """
        SELECT date, total_steps, calories, distance_m
        FROM steps_daily
        WHERE date BETWEEN ? AND ?
        ORDER BY date DESC
        """,
        (start_day.isoformat(), end_day.isoformat()),
    )
    sleep = fetch_all(
        """
        SELECT date, light_sleep_min, deep_sleep_min, start_time, end_time,
               COALESCE(rem_sleep_min, 0) AS rem_sleep_min,
               COALESCE(awake_min, 0) AS awake_min,
               COALESCE(total_duration_min, 0) AS total_duration_min,
               COALESCE(sleep_score, 0) AS sleep_score
        FROM sleep_daily
        WHERE date BETWEEN ? AND ?
        ORDER BY date DESC
        """,
        (start_day.isoformat(), end_day.isoformat()),
    )
    hr = metric_stats("heart_rate", "value", start_epoch, end_epoch)
    spo2 = metric_stats("blood_oxygen", "spo2", start_epoch, end_epoch)
    return {
        "days": days,
        "start": start_day,
        "end": end_day,
        "steps": steps,
        "sleep": sleep,
        "hr": hr,
        "spo2": spo2,
    }


# ---------------------------------------------------------------------------
# Day emoji helpers — для календаря
# ---------------------------------------------------------------------------
def day_emoji(steps_row: sqlite3.Row | None, sleep_row: sqlite3.Row | None) -> str:
    """Один emoji для строки дня в календаре."""
    score = 0
    if steps_row and int(steps_row["total_steps"] or 0) >= STEP_GOAL:
        score += 1
    if sleep_row:
        total = sleep_total(sleep_row)
        if total >= 420:
            score += 1
    if score == 2:
        return "🟢"
    if score == 1:
        return "🟡"
    return "🔴"


# ---------------------------------------------------------------------------
# Dashboard text — «умный» с динамическим заголовком и советом дня
# ---------------------------------------------------------------------------
def main_menu_text() -> str:
    steps = latest_steps()
    sleep = latest_sleep()
    hr = latest_hr()
    spo2 = latest_spo2()
    lines = []

    # Шаги
    if steps:
        label = relative_day_label(steps["date"])
        steps_count = int(steps["total_steps"])
        lines.append(f"🚶 <b>{esc(label)}: {steps_count:,}</b> шагов".replace(",", " "))
        lines.append(f"   {step_goal_bar(steps_count)}")
        lines.append(f"   {step_goal_text(steps_count)}")
        lines.append(
            f"   {float(steps['distance_m']) / 1000:.1f} км · {float(steps['calories']):.0f} ккал"
        )
    else:
        lines.append("🚶 Шаги: жду первую синхронизацию")

    lines.append("")

    # Сон — краткая сводка на дашборде
    if sleep:
        total_sleep = sleep_total(sleep)
        deep = int(sleep["deep_sleep_min"] or 0)
        quality = sleep_quality_label(total_sleep, deep)
        lines.append(f"😴 <b>Сон: {format_minutes(total_sleep)}</b> · {quality}")
        lines.append(
            f"   {esc(relative_day_label(sleep['date']))} · "
            f"глубокий: {deep} мин · лёгкий: {sleep['light_sleep_min']} мин"
            + (f" · REM: {sleep['rem_sleep_min']} мин" if sleep['rem_sleep_min'] else "")
        )
    else:
        lines.append("😴 Сон: данных пока нет")

    lines.append("")

    # Пульс
    if hr:
        bpm = int(hr["value"])
        lines.append(f"❤️ <b>Пульс: {bpm} bpm</b> · {format_relative_time(hr['timestamp'])}")
    else:
        lines.append("❤️ Пульс: данных пока нет")

    # SpO2
    if spo2:
        spo2_val = float(spo2["spo2"])
        color = "🟢" if spo2_val >= 95 else ("🟡" if spo2_val >= 90 else "🔴")
        lines.append(f"🩸 <b>SpO2: {color} {spo2_val:.1f}%</b> · {format_relative_time(spo2['timestamp'])}")
    else:
        lines.append("🩸 SpO2: данных пока нет")

    # Совет дня
    tip = daily_tip(steps, sleep, hr)
    lines.extend(["", tip])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Day detail text
# ---------------------------------------------------------------------------
def day_text(data: dict) -> str:
    steps = data["steps"]
    sleep = data["sleep"]
    hr = data["hr"]
    spo2 = data["spo2"]
    day_str = data["date"]

    day_value = parse_day(day_str)
    start_epoch, end_epoch = day_bounds(day_value)

    day_label = relative_day_label(day_str)
    lines = [f"📊 <b>{esc(day_label)} · {esc(day_str)}</b>", ""]

    # Шаги
    if steps:
        steps_count = int(steps["total_steps"])
        lines.extend(
            [
                "🚶 <b>Активность:</b>",
                f"   Шаги: <b>{steps_count:,}</b>".replace(",", " "),
                f"   {step_goal_bar(steps_count)}",
                f"   {step_goal_text(steps_count)}",
                f"   Дистанция: {float(steps['distance_m']) / 1000:.1f} км · {float(steps['calories']):.0f} ккал",
            ]
        )
    else:
        lines.append("🚶 Шаги: за этот день данных нет")

    lines.append("")

    # Сон
    if sleep:
        total_sleep = sleep_total(sleep)
        deep = int(sleep["deep_sleep_min"] or 0)
        quality = sleep_quality_label(total_sleep, deep)
        lines.extend(
            [
                f"😴 <b>Сон: {format_minutes(total_sleep)}</b> · {quality}",
                f"   Глубокий: {format_minutes(deep)} · Лёгкий: {format_minutes(sleep['light_sleep_min'])}"
                + (f" · REM: {format_minutes(sleep['rem_sleep_min'])}" if sleep['rem_sleep_min'] else ""),
                f"   Окно: {format_epoch(sleep['start_time'], False)} — {format_epoch(sleep['end_time'], False)}",
            ]
        )
        # Пульс покоя
        rest_hr = resting_hr(int(sleep["start_time"]), int(sleep["end_time"]))
        if rest_hr:
            lines.append(f"   Пульс покоя во сне: <b>{rest_hr} bpm</b>")

        # Sparklines ЧСС и SpO2
        sleep_hr_spark = get_sleep_sparkline(
            "heart_rate", "value", int(sleep["start_time"]), int(sleep["end_time"])
        )
        sleep_spo2_spark = get_sleep_sparkline(
            "blood_oxygen", "spo2", int(sleep["start_time"]), int(sleep["end_time"])
        )
        if sleep_hr_spark:
            lines.append(f"   📈 ЧСС: <code>[{sleep_hr_spark}]</code>")
        if sleep_spo2_spark:
            lines.append(f"   📉 SpO2: <code>[{sleep_spo2_spark}]</code>")
    else:
        lines.append("😴 Сон: за этот день данных нет")

    lines.append("")
    lines.append("❤️ <b>За сутки:</b>")
    if hr and hr["count"]:
        lines.append(
            f"   Пульс: ср. {hr['avg_value']} · диапазон {hr['min_value']}–{hr['max_value']} bpm"
        )
    else:
        lines.append("   Пульс: точек нет")

    if spo2 and spo2["count"]:
        lines.append(
            f"   SpO2: ср. {spo2['avg_value']}% · диапазон {spo2['min_value']}–{spo2['max_value']}%"
        )
    else:
        lines.append("   SpO2: точек нет")

    lines.extend(
        ["", "<i>Статистика с датчиков браслета. Не является медицинским заключением.</i>"]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# History / Calendar
# ---------------------------------------------------------------------------
def history_text(days: int = 7) -> str:
    summary = period_summary(days)
    rows = summary["steps"]
    sleep_by_day = {row["date"]: row for row in summary["sleep"]}
    # Все уникальные дни из обоих источников
    all_days = sorted(
        set([r["date"] for r in rows] + list(sleep_by_day.keys())),
        reverse=True,
    )[:days]

    lines = [
        f"📅 <b>Календарь · последние {days} дней</b>",
        f"{summary['start'].isoformat()} — {summary['end'].isoformat()}",
        "",
    ]

    if not all_days:
        lines.append("Пока пусто: за этот период данных нет.")
        return "\n".join(lines)

    for d in all_days:
        steps_row = next((r for r in rows if r["date"] == d), None)
        sleep_row = sleep_by_day.get(d)
        icon = day_emoji(steps_row, sleep_row)

        steps_text = f"{int(steps_row['total_steps']):,} шагов".replace(",", " ") if steps_row else "шаги н/д"
        sleep_text = "сон н/д"
        if sleep_row:
            total = sleep_total(sleep_row)
            sleep_text = format_minutes(total)
        lines.append(f"{icon} <b>{d}</b>: {steps_text} · {sleep_text}")

    lines.append("")
    lines.append("<i>Нажми на кнопку дня ниже, чтобы открыть детальный разрез.</i>")
    return "\n".join(lines)


def history_keyboard(days: int = 7) -> InlineKeyboardMarkup:
    # Переключатели периода
    period_row = [
        InlineKeyboardButton(
            "· 7 дней ·" if days == 7 else "7 дней",
            callback_data="period_cal:7",
        ),
        InlineKeyboardButton(
            "· 30 дней ·" if days == 30 else "30 дней",
            callback_data="period_cal:30",
        ),
    ]
    buttons: list[list[InlineKeyboardButton]] = [period_row]

    day_buttons = [
        InlineKeyboardButton(day, callback_data=f"day:{day}")
        for day in available_days(days)
    ]
    for idx in range(0, len(day_buttons), 3):
        buttons.append(day_buttons[idx: idx + 3])

    buttons.append([InlineKeyboardButton("⬅️ Главная", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Day navigation keyboard
# ---------------------------------------------------------------------------
def day_keyboard(current: date) -> InlineKeyboardMarkup:
    today = datetime.now(LOCAL_TZ).date()
    prev_day = current - timedelta(days=1)
    next_day = current + timedelta(days=1)

    prev_btn = InlineKeyboardButton(f"◀️ {prev_day.isoformat()}", callback_data=f"day:{prev_day.isoformat()}")
    if current >= today:
        next_btn = InlineKeyboardButton("📊 Главная", callback_data="menu:main")
    else:
        next_btn = InlineKeyboardButton(f"{next_day.isoformat()} ▶️", callback_data=f"day:{next_day.isoformat()}")

    return InlineKeyboardMarkup([
        [prev_btn, next_btn],
        [InlineKeyboardButton("📅 Календарь", callback_data="menu:history")],
    ])


# ---------------------------------------------------------------------------
# Sleep detail text
# ---------------------------------------------------------------------------
def latest_sleep_text() -> str:
    sleep = latest_sleep()
    if not sleep:
        return "😴 <b>Ночной сон</b>\n\nПока нет данных."

    hr, spo2 = sleep_window_stats(sleep)
    total_sleep = sleep_total(sleep)
    deep = int(sleep["deep_sleep_min"] or 0)
    rem = int(sleep["rem_sleep_min"] or 0)
    awake = int(sleep["awake_min"] or 0)
    score = int(sleep["sleep_score"] or 0)
    quality = sleep_quality_label(total_sleep, deep)

    lines = [
        f"😴 <b>Ночной сон · {esc(relative_day_label(sleep['date']))}</b>",
        f"Дата: {esc(sleep['date'])}",
        "",
        f"⏳ <b>Длительность: {format_minutes(total_sleep)}</b> · {quality}"
        + (f" · Счёт: {score}/100" if score else ""),
        f"   • Глубокий: {format_minutes(deep)}",
        f"   • Лёгкий:   {format_minutes(sleep['light_sleep_min'])}",
    ]
    if rem:
        lines.append(f"   • REM:       {format_minutes(rem)}")
    if awake:
        lines.append(f"   • Пробуждений: {awake} мин")
    lines.append(f"   • Постель:  {format_epoch(sleep['start_time'], False)} — {format_epoch(sleep['end_time'], False)}")

    # Пульс покоя
    if sleep["start_time"] and sleep["end_time"]:
        rest_hr = resting_hr(int(sleep["start_time"]), int(sleep["end_time"]))
        if rest_hr:
            lines.append(f"   • Пульс покоя: <b>{rest_hr} bpm</b>")

    lines.append("")

    # Sparklines
    if sleep["start_time"] and sleep["end_time"]:
        sleep_hr_spark = get_sleep_sparkline(
            "heart_rate", "value", int(sleep["start_time"]), int(sleep["end_time"])
        )
        sleep_spo2_spark = get_sleep_sparkline(
            "blood_oxygen", "spo2", int(sleep["start_time"]), int(sleep["end_time"])
        )

        if sleep_hr_spark:
            lines.append("📈 <b>ЧСС во сне:</b>")
            lines.append(f"   <code>[{sleep_hr_spark}]</code>")
            if hr and hr["count"]:
                lines.append(
                    f"   Ср. {hr['avg_value']} bpm · диапазон {hr['min_value']}–{hr['max_value']} bpm"
                )
            lines.append("")
        else:
            lines.append("📈 ЧСС: детальных точек нет\n")

        if sleep_spo2_spark:
            lines.append("📉 <b>SpO2 во сне:</b>")
            lines.append(f"   <code>[{sleep_spo2_spark}]</code>")
            if spo2 and spo2["count"]:
                lines.append(
                    f"   Ср. {spo2['avg_value']}% · мин. {spo2['min_value']}%"
                )
            lines.append("")
        else:
            lines.append("📉 SpO2: детальных точек нет\n")

    lines.append("<i>Детали подтягиваются автоматически при фоновой синхронизации с FDS.</i>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analytics / Trends
# ---------------------------------------------------------------------------
def period_text(days: int) -> str:
    summary = period_summary(days)
    steps = summary["steps"]
    sleep_rows = summary["sleep"]

    total_steps = sum(int(row["total_steps"] or 0) for row in steps)
    avg_steps = round(total_steps / len(steps)) if steps else 0
    total_distance = sum(float(row["distance_m"] or 0) for row in steps) / 1000
    best_steps = max(steps, key=lambda r: int(r["total_steps"] or 0), default=None)
    worst_steps = min(steps, key=lambda r: int(r["total_steps"] or 0), default=None)

    sleep_totals = [
        sleep_total(row) for row in sleep_rows
    ]
    avg_sleep = round(sum(sleep_totals) / len(sleep_totals)) if sleep_totals else None
    best_sleep = max(sleep_totals) if sleep_totals else None
    goal_days = sum(1 for r in steps if int(r["total_steps"] or 0) >= STEP_GOAL)

    hr = summary["hr"]
    spo2 = summary["spo2"]

    lines = [
        f"📊 <b>Аналитика · {days} дней</b>",
        f"{summary['start'].isoformat()} — {summary['end'].isoformat()}",
        "",
        "🚶 <b>Активность:</b>",
        f"   Всего шагов: {total_steps:,}".replace(",", " "),
        f"   В среднем: {avg_steps:,} / день".replace(",", " "),
        f"   Дистанция: {total_distance:.1f} км",
        f"   Норма {STEP_GOAL:,} выполнена: {goal_days} из {len(steps)} дней".replace(",", " "),
    ]
    if best_steps:
        lines.append(
            f"   🏆 Лучший день: {best_steps['date']} · {int(best_steps['total_steps']):,} шагов".replace(",", " ")
        )
    if worst_steps and len(steps) > 1:
        lines.append(
            f"   📉 Слабейший: {worst_steps['date']} · {int(worst_steps['total_steps']):,} шагов".replace(",", " ")
        )

    lines.append("")
    lines.append("😴 <b>Сон:</b>")
    if avg_sleep is not None:
        lines.append(f"   Среднее: {format_minutes(avg_sleep)}")
    else:
        lines.append("   Среднее: н/д")
    if best_sleep is not None:
        lines.append(f"   Лучшая ночь: {format_minutes(best_sleep)}")

    lines.append("")
    lines.append("❤️ <b>ЧСС и SpO2:</b>")
    if hr and hr["count"]:
        lines.append(
            f"   Пульс: ср. {hr['avg_value']} bpm · диапазон {hr['min_value']}–{hr['max_value']} bpm"
        )
    else:
        lines.append("   Пульс: данных нет")

    if spo2 and spo2["count"]:
        lines.append(
            f"   SpO2: ср. {spo2['avg_value']}% · мин. {spo2['min_value']}%"
        )
    else:
        lines.append("   SpO2: данных нет")

    lines.extend(["", "<i>Берегите здоровье!</i>"])
    return "\n".join(lines)


def trends_keyboard(days: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "· 7 дней ·" if days == 7 else "7 дней",
                    callback_data="period:7d",
                ),
                InlineKeyboardButton(
                    "· 30 дней ·" if days == 30 else "30 дней",
                    callback_data="period:30d",
                ),
            ],
            [InlineKeyboardButton("⬅️ Главная", callback_data="menu:main")],
        ]
    )


# ---------------------------------------------------------------------------
# Service menu
# ---------------------------------------------------------------------------
def more_text() -> str:
    return (
        "⚙️ <b>Сервис</b>\n\n"
        "Технические функции: принудительная синхронизация, статус базы данных и выгрузка CSV."
    )


def more_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Принудительный синк", callback_data="menu:sync")],
            [
                InlineKeyboardButton("💾 Экспорт ZIP", callback_data="menu:export"),
                InlineKeyboardButton("🧰 Статус БД", callback_data="menu:db_status"),
            ],
            [InlineKeyboardButton("⬅️ Главная", callback_data="menu:main")],
        ]
    )


def db_status_text() -> str:
    status = read_status_file()
    lines = ["🧰 <b>Статус базы данных</b>", ""]
    if not health_db_exists():
        return "🧰 <b>Статус базы данных</b>\n\nБаза пока не создана."

    conn = health_conn()
    try:
        tables = ["steps_daily", "sleep_daily", "sleep_stages", "heart_rate", "blood_oxygen"]
        for table in tables:
            exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            if not exists:
                lines.append(f"• {table}: таблицы нет")
                continue
            count = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            lines.append(f"• {table}: <b>{count:,}</b> строк".replace(",", " "))
    finally:
        conn.close()

    last_sync_epoch = status.get("last_sync")
    last_sync = format_epoch(last_sync_epoch) if last_sync_epoch else status.get("last_sync_time", "н/д")
    lines.extend(
        [
            "",
            f"Путь: <code>{esc(DB_PATH)}</code>",
            f"Последний синк: {esc(last_sync)}",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def zip_export() -> io.BytesIO:
    return storage.zip_export(SETTINGS, ALLOWED_USER_ID)


# ---------------------------------------------------------------------------
# Xiaomi onboarding
# ---------------------------------------------------------------------------
def onboarding_text() -> str:
    return (
        "🔐 <b>Авторизация Xiaomi</b>\n\n"
        "Для первого запуска нужен вход в Xiaomi Fitness. Нажми кнопку ниже, подтверди вход, "
        "а я дождусь ответа и сразу запущу синхронизацию."
    )


def onboarding_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔐 Войти в Xiaomi", callback_data="auth:start")]]
    )


def normalize_login_url(url: str | None) -> str:
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url


def xiaomi_wait_keyboard(login_url: str, qr_image_url: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    login_url = normalize_login_url(login_url)
    qr_image_url = normalize_login_url(qr_image_url)
    if login_url:
        rows.append([InlineKeyboardButton("🔐 Открыть вход Xiaomi", url=login_url)])
    if qr_image_url:
        rows.append([InlineKeyboardButton("▦ Открыть QR-код", url=qr_image_url)])
    return InlineKeyboardMarkup(rows or [[InlineKeyboardButton("🔄 Повторить", callback_data="auth:start")]])


def auth_retry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔐 Войти заново", callback_data="auth:relogin")],
            [InlineKeyboardButton("⬅️ Сервис", callback_data="menu:more")],
        ]
    )


async def show_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE, force_new: bool = False) -> None:
    await update_menu(update, context, onboarding_text(), onboarding_keyboard(), force_new=force_new)


async def start_xiaomi_login(update: Update, context: ContextTypes.DEFAULT_TYPE, *, force: bool = False) -> None:
    if has_xiaomi_token() and not force:
        await show_main_menu(update, context)
        return
    if AUTH_LOCK.locked():
        await update_menu(
            update,
            context,
            "🔐 <b>Авторизация Xiaomi</b>\n\nУже жду подтверждение входа. Открой ссылку из предыдущего сообщения.",
            onboarding_keyboard(),
        )
        return

    async with AUTH_LOCK:
        if has_xiaomi_token() and not force:
            await show_main_menu(update, context)
            return

        await update_menu(
            update,
            context,
            "🔐 <b>Авторизация Xiaomi</b>\n\nГотовлю ссылку входа…",
            None,
        )
        auth = XiaomiAuth()

        async def qr_callback(qr_image_url: str, login_url: str) -> None:
            await update_menu(
                update,
                context,
                "🔐 <b>Авторизация Xiaomi</b>\n\nОткрой ссылку, подтверди вход и вернись сюда. Я жду результат.",
                xiaomi_wait_keyboard(login_url, qr_image_url),
            )

        try:
            token = await auth.login_qr(qr_callback=qr_callback, max_wait=300)
            token_path = get_xiaomi_token_path()
            if token_path is None:
                raise ConfigError("Не удалось определить путь для Xiaomi token")
            save_auth_token(token, token_path)
            await update_menu(
                update,
                context,
                "✅ <b>Авторизация Xiaomi</b>\n\nВход подтверждён. Запускаю первую синхронизацию…",
                None,
            )
            await run_initial_sync_after_login(update, context)
        except Exception as e:
            logger.exception("Xiaomi login failed")
            await update_menu(
                update,
                context,
                f"⚠️ <b>Авторизация Xiaomi</b>\n\nНе удалось войти: {esc(e)}",
                auth_retry_keyboard(),
            )
        finally:
            await auth.close()


async def run_initial_sync_after_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if SYNC_LOCK.locked():
        await update_menu(
            update,
            context,
            "✅ <b>Авторизация Xiaomi</b>\n\nВход готов. Синхронизация уже идёт, открою меню.",
            main_keyboard(),
        )
        return

    async with SYNC_LOCK:
        result = await run_sync(ALLOWED_USER_ID, SETTINGS)

    if result.success:
        await show_main_menu(update, context)
        return

    detail = f"\n\nПричина: {esc(result.error)}" if result.error else ""
    await update_menu(
        update,
        context,
        f"⚠️ <b>Первая синхронизация</b>\n\nАвторизация сохранена, но данные не обновились.{detail}",
        auth_retry_keyboard(),
    )


# ---------------------------------------------------------------------------
# Menu keyboards
# ---------------------------------------------------------------------------
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 Календарь", callback_data="menu:history"),
                InlineKeyboardButton("📊 Аналитика", callback_data="menu:trends"),
            ],
            [
                InlineKeyboardButton("😴 Детали сна", callback_data="menu:sleep"),
                InlineKeyboardButton("⚙️ Сервис", callback_data="menu:more"),
            ],
        ]
    )


def back_keyboard(back_to: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=back_to)]])


# ---------------------------------------------------------------------------
# Handlers: show_* functions
# ---------------------------------------------------------------------------
async def show_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, force_new: bool = False
) -> None:
    await update_menu(update, context, main_menu_text(), main_keyboard(), force_new=force_new)


async def show_history(
    update: Update, context: ContextTypes.DEFAULT_TYPE, days: int = 7
) -> None:
    await update_menu(update, context, history_text(days), history_keyboard(days))


async def show_day(
    update: Update, context: ContextTypes.DEFAULT_TYPE, day_str: str
) -> None:
    day_value = parse_day(day_str)
    await update_menu(
        update,
        context,
        day_text(day_summary(day_str)),
        day_keyboard(day_value),
    )


async def run_manual_sync(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not has_xiaomi_token():
        await show_onboarding(update, context)
        return
    if not run_sync:
        await update_menu(
            update,
            context,
            "🔄 <b>Синхронизация</b>\n\nМодуль синхронизации не найден.",
            back_keyboard("menu:more"),
        )
        return
    if SYNC_LOCK.locked():
        await update_menu(
            update,
            context,
            "🔄 <b>Синхронизация</b>\n\nУже идёт обновление. Подожди завершения.",
            back_keyboard("menu:more"),
        )
        return

    await update_menu(
        update,
        context,
        "🔄 <b>Синхронизация</b>\n\nЗабираю данные из Xiaomi Fitness…",
        back_keyboard("menu:more"),
    )
    async with SYNC_LOCK:
        try:
            result = await run_sync(ALLOWED_USER_ID, SETTINGS)
        except Exception as e:
            logger.exception("Manual sync failed")
            await update_menu(
                update,
                context,
                f"🔄 <b>Синхронизация</b>\n\nОшибка запуска: {esc(e)}",
                back_keyboard("menu:more"),
            )
            return

    if result.success:
        await update_menu(
            update,
            context,
            "✅ <b>Синхронизация</b>\n\nГотово, данные обновлены.",
            InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📊 На главную", callback_data="menu:main")],
                    [InlineKeyboardButton("⬅️ Сервис", callback_data="menu:more")],
                ]
            ),
        )
    else:
        detail = f"\n\nПричина: {esc(result.error)}" if result.error else ""
        keyboard = auth_retry_keyboard() if "Token" in (result.error or "") else back_keyboard("menu:more")
        await update_menu(
            update,
            context,
            f"⚠️ <b>Синхронизация</b>\n\nНе вышло обновиться.{detail}",
            keyboard,
        )


async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    if not health_db_exists():
        await update_menu(
            update,
            context,
            "💾 <b>Экспорт</b>\n\nБаза данных пока не создана.",
            back_keyboard("menu:more"),
        )
        return

    await update_menu(update, context, "💾 <b>Экспорт</b>\n\nСобираю ZIP…", None)
    try:
        export_file = zip_export()
        if export_file.getbuffer().nbytes == 0:
            await update_menu(
                update,
                context,
                "💾 <b>Экспорт</b>\n\nВ базе нет данных.",
                back_keyboard("menu:more"),
            )
            return
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=export_file,
            filename=export_file.name,
            caption="💚 MiBand Health CSV Export",
        )
        await update_menu(
            update,
            context,
            "✅ <b>Экспорт</b>\n\nZIP с CSV-таблицами отправлен выше.",
            back_keyboard("menu:more"),
        )
    except Exception as e:
        logger.exception("Export failed")
        await update_menu(
            update,
            context,
            f"⚠️ <b>Экспорт</b>\n\nОшибка: {esc(e)}",
            back_keyboard("menu:more"),
        )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------
@with_user_context
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        uid = update.effective_user.id if update.effective_user else "unknown"
        logger.warning("Unauthorized access from user: %s", uid)
        return
    await safe_delete(update.message)
    if not has_xiaomi_token():
        await show_onboarding(update, context, force_new=True)
        return
    await show_main_menu(update, context, force_new=True)


@with_user_context
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await safe_delete(update.message)
    await update_menu(update, context, db_status_text(), back_keyboard("menu:more"))


@with_user_context
async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await safe_delete(update.message)
    if not has_xiaomi_token():
        await show_onboarding(update, context)
        return
    await run_manual_sync(update, context)


@with_user_context
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await safe_delete(update.message)
    if not has_xiaomi_token():
        await show_onboarding(update, context)
        return
    await show_main_menu(update, context)


# ---------------------------------------------------------------------------
# Callback router
# ---------------------------------------------------------------------------
@with_user_context
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
    if not is_allowed(update):
        return

    data = query.data if query else "menu:main"

    if data in {"auth:start", "auth:relogin"}:
        await start_xiaomi_login(update, context, force=data == "auth:relogin")

    elif not has_xiaomi_token():
        await show_onboarding(update, context)

    elif data == "menu:main":
        await show_main_menu(update, context)

    elif data == "menu:history":
        await show_history(update, context, 7)

    elif data.startswith("period_cal:"):
        # Переключение числа дней в Календаре
        days = int(data.split(":")[1])
        await show_history(update, context, days)

    elif data == "menu:sleep":
        await update_menu(
            update,
            context,
            latest_sleep_text(),
            InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📅 Календарь", callback_data="menu:history")],
                    [InlineKeyboardButton("⬅️ Главная", callback_data="menu:main")],
                ]
            ),
        )

    elif data == "menu:trends":
        await update_menu(update, context, period_text(30), trends_keyboard(30))

    elif data.startswith("period:"):
        days = 7 if data == "period:7d" else 30
        await update_menu(update, context, period_text(days), trends_keyboard(days))

    elif data.startswith("day:"):
        try:
            await show_day(update, context, data.split(":", 1)[1])
        except Exception as e:
            logger.exception("Failed to show day")
            await update_menu(
                update,
                context,
                f"📊 <b>День</b>\n\nНе удалось открыть: {esc(e)}",
                back_keyboard("menu:history"),
            )

    elif data == "menu:more":
        await update_menu(update, context, more_text(), more_keyboard())

    elif data == "menu:sync":
        await run_manual_sync(update, context)

    elif data == "menu:export":
        await export_data(update, context)

    elif data == "menu:db_status":
        await update_menu(update, context, db_status_text(), back_keyboard("menu:more"))

    else:
        await show_main_menu(update, context)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    global SETTINGS, BOT_TOKEN, ALLOWED_USER_ID, DB_PATH
    try:
        SETTINGS = Settings.from_env(require_bot=True)
    except ConfigError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    BOT_TOKEN = SETTINGS.telegram_bot_token
    ALLOWED_USER_ID = SETTINGS.telegram_allowed_user_id
    if ALLOWED_USER_ID is not None:
        DB_PATH = str(SETTINGS.user_db_path(ALLOWED_USER_ID))
        logger.info("Стартую fitness-bot для пользователя: %s", ALLOWED_USER_ID)
    else:
        DB_PATH = str(SETTINGS.db_path)
        logger.info("Стартую fitness-bot в режиме ожидания привязки владельца (первое входящее сообщение привяжет бота)...")

    init_state_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sync", cmd_sync))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
