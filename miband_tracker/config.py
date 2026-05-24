from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Invalid runtime configuration."""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должен быть целым числом") from exc
    if min_value is not None and value < min_value:
        raise ConfigError(f"{name} должен быть не меньше {min_value}")
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    status_path: Path
    bot_state_db_path: Path
    telegram_bot_token: str
    telegram_allowed_user_id: int | None
    sync_interval: int
    query_duration: int
    enable_fds_sleep_details: bool

    @classmethod
    def from_env(cls, *, require_bot: bool = False) -> "Settings":
        data_dir = Path(os.environ.get("DATA_DIR", "/opt/miband-tracker/data"))
        allowed_user_id = parse_single_user_id(
            os.environ.get("TELEGRAM_ALLOWED_USER_ID", ""), required=require_bot
        )
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if require_bot and not bot_token:
            raise ConfigError("TELEGRAM_BOT_TOKEN не задан")
        return cls(
            data_dir=data_dir,
            db_path=Path(os.environ.get("DB_PATH", str(data_dir / "miband.db"))),
            status_path=Path(os.environ.get("STATUS_PATH", str(data_dir / "status.json"))),
            bot_state_db_path=Path(
                os.environ.get(
                    "BOT_STATE_DB_PATH",
                    str(data_dir / "fitness_bot_state.db"),
                )
            ),
            telegram_bot_token=bot_token,
            telegram_allowed_user_id=allowed_user_id,
            sync_interval=_env_int("SYNC_INTERVAL", 900, min_value=0),
            query_duration=_env_int("QUERY_DURATION", 2, min_value=1),
            enable_fds_sleep_details=_env_bool("ENABLE_FDS_SLEEP_DETAILS", default=True),
        )

    def require_user_id(self, user_id: int | None = None) -> int:
        resolved = user_id if user_id is not None else self.telegram_allowed_user_id
        if resolved is None:
            raise ConfigError("TELEGRAM_ALLOWED_USER_ID должен содержать ровно один user id")
        return int(resolved)

    def token_path(self, user_id: int | None = None) -> Path:
        uid = self.require_user_id(user_id)
        preferred = self.data_dir / f"token_{uid}.json"
        legacy = self.data_dir / "token.json"
        if preferred.exists() or not legacy.exists():
            return preferred
        return legacy

    def user_db_path(self, user_id: int | None = None) -> Path:
        uid = self.require_user_id(user_id)
        preferred = self.data_dir / f"miband_{uid}.db"
        if preferred.exists():
            return preferred
        return self.db_path

    def user_status_path(self, user_id: int | None = None) -> Path:
        uid = self.require_user_id(user_id)
        preferred = self.data_dir / f"status_{uid}.json"
        if preferred.exists():
            return preferred
        return self.status_path

    def canonical_user_db_path(self, user_id: int | None = None) -> Path:
        return self.data_dir / f"miband_{self.require_user_id(user_id)}.db"

    def canonical_user_status_path(self, user_id: int | None = None) -> Path:
        return self.data_dir / f"status_{self.require_user_id(user_id)}.json"


def parse_single_user_id(raw: str, *, required: bool = False) -> int | None:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        if required:
            raise ConfigError("TELEGRAM_ALLOWED_USER_ID не задан или пуст")
        return None
    if len(values) > 1:
        raise ConfigError("TELEGRAM_ALLOWED_USER_ID должен содержать ровно один user id")
    try:
        return int(values[0])
    except ValueError as exc:
        raise ConfigError("TELEGRAM_ALLOWED_USER_ID должен быть целым числом") from exc
