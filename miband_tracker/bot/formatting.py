# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import html
import os
import time
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Moscow")
RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
RU_WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
DEFAULT_STEP_GOAL = 10_000

SPORT_TYPE_LABELS: dict[str, str] = {
    "free_training": "Свободная тренировка",
    "outdoor_running": "Бег на улице",
    "treadmill": "Беговая дорожка",
    "walking": "Ходьба",
    "cycling": "Велосипед",
    "swimming": "Плавание",
    "yoga": "Йога",
    "strength_training": "Силовая",
    "hiit": "HIIT",
    "jump_rope": "Скакалка",
    "elliptical": "Эллипсоид",
    "rowing": "Гребля",
    "outdoor_cycling": "Велосипед (улица)",
    "basketball": "Баскетбол",
    "football": "Футбол",
    "table_tennis": "Настольный теннис",
    "badminton": "Бадминтон",
    "tennis": "Теннис",
    "volleyball": "Волейбол",
    "dancing": "Танцы",
    "martial_arts": "Боевые искусства",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def format_mia_date(dt: date) -> str:
    month_name = RU_MONTHS[dt.month - 1]
    weekday_name = RU_WEEKDAYS[dt.weekday()]
    return f"{dt.day} {month_name}, {weekday_name}"


def make_sleep_bar(stage_min: int, total_min: int) -> str:
    if total_min <= 0:
        return "░" * 10
    blocks = int(round((stage_min / total_min) * 10))
    blocks = max(0, min(10, blocks))
    return "█" * blocks + "░" * (10 - blocks)


def format_epoch(epoch: int | float | None, with_date: bool = True) -> str:
    is_en = os.getenv("BOT_LANG") == "en"
    if not epoch:
        return "n/a" if is_en else "н/д"
    fmt = "%Y-%m-%d %H:%M" if with_date else "%H:%M"
    return datetime.fromtimestamp(int(epoch), LOCAL_TZ).strftime(fmt)


def format_relative_time(epoch: int | float | None) -> str:
    is_en = os.getenv("BOT_LANG") == "en"
    if not epoch:
        return "n/a" if is_en else "н/д"
    diff = int(time.time() - int(epoch))
    if diff < 60:
        return "just now" if is_en else "только что"
    diff_min = diff // 60
    if diff_min < 60:
        return f"{diff_min} min. ago" if is_en else f"{diff_min} мин. назад"
    diff_hours = diff_min // 60
    if diff_hours < 24:
        return f"{diff_hours} hr. ago" if is_en else f"{diff_hours} ч. назад"
    diff_days = diff_hours // 24
    if diff_days == 1:
        return "yesterday" if is_en else "вчера"
    return f"{diff_days} days ago" if is_en else f"{diff_days} дн. назад"


def format_minutes(minutes: int | float | None) -> str:
    is_en = os.getenv("BOT_LANG") == "en"
    if minutes is None:
        return "n/a" if is_en else "н/д"
    minutes = int(minutes)
    if is_en:
        return f"{minutes // 60} h {minutes % 60:02d} m"
    return f"{minutes // 60} ч {minutes % 60:02d} мин"


def step_goal_bar(steps: int | float | None, goal: int = DEFAULT_STEP_GOAL) -> str:
    steps_int = int(steps or 0)
    percent = min(100, round(steps_int / goal * 100)) if goal > 0 else 0
    filled = percent // 10
    bar = "█" * filled + "░" * (10 - filled)
    return f"<code>[{bar}]</code> {percent}%"


def step_goal_text(steps: int | float | None, goal: int = DEFAULT_STEP_GOAL) -> str:
    is_en = os.getenv("BOT_LANG") == "en"
    if steps is None:
        return f"Goal {goal:,} steps".replace(",", " ") if is_en else f"Цель {goal:,} шагов".replace(",", " ")
    steps_int = int(steps)
    left = max(0, goal - steps_int)
    if left:
        text = f"Goal {goal:,} · {left:,} steps left" if is_en else f"Цель {goal:,} · осталось {left:,} шагов"
    else:
        text = f"Goal {goal:,} · daily goal achieved! 🎉" if is_en else f"Цель {goal:,} · дневная цель выполнена! 🎉"
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


def relative_day_label(day_str: str | None) -> str:
    is_en = os.getenv("BOT_LANG") == "en"
    if not day_str:
        return "Last day" if is_en else "Последний день"
    try:
        day_value = parse_day(day_str)
    except ValueError:
        return f"Day: {day_str}" if is_en else f"День: {day_str}"
    today = datetime.now(LOCAL_TZ).date()
    if day_value == today:
        return "Today" if is_en else "Сегодня"
    if day_value == today - timedelta(days=1):
        return "Yesterday" if is_en else "Вчера"
    return day_str


def day_bounds(day_value: date) -> tuple[int, int]:
    start = datetime.combine(day_value, dt_time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def parse_day(day_str: str) -> date:
    return datetime.strptime(day_str, "%Y-%m-%d").date()


def sleep_total(sleep) -> int:
    total = int(sleep["total_duration_min"]) if sleep["total_duration_min"] else 0
    if total > 0:
        return total
    return int(sleep["light_sleep_min"] or 0) + int(sleep["deep_sleep_min"] or 0)


def sleep_quality_label(total_min: int, deep_min: int) -> str:
    is_en = os.getenv("BOT_LANG") == "en"
    if total_min >= 420 and deep_min >= 60:
        return "🟢 Excellent" if is_en else "🟢 Отличный"
    if total_min >= 360 and deep_min >= 40:
        return "🟡 Good" if is_en else "🟡 Хороший"
    if total_min >= 300:
        return "🟠 Average" if is_en else "🟠 Средний"
    return "🔴 Poor" if is_en else "🔴 Недостаточный"


def workout_type_label(sport_type: str) -> str:
    return SPORT_TYPE_LABELS.get(sport_type, sport_type.replace("_", " ").title())
