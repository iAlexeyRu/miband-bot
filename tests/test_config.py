from pathlib import Path

import pytest

from miband_tracker.config import ConfigError, Settings, parse_single_user_id


def test_parse_single_user_id_rejects_multiple_values() -> None:
    with pytest.raises(ConfigError):
        parse_single_user_id("1,2", required=True)


def test_settings_user_paths_prefer_existing_user_files(tmp_path: Path) -> None:
    user_id = 123
    (tmp_path / f"miband_{user_id}.db").write_text("", encoding="utf-8")
    (tmp_path / f"status_{user_id}.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"token_{user_id}.json").write_text("{}", encoding="utf-8")

    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "miband.db",
        status_path=tmp_path / "status.json",
        bot_state_db_path=tmp_path / "fitness_bot_state.db",
        telegram_bot_token="token",
        telegram_allowed_user_id=user_id,
        sync_interval=900,
        query_duration=2,
        enable_fds_sleep_details=True,
    )

    assert settings.user_db_path() == tmp_path / f"miband_{user_id}.db"
    assert settings.user_status_path() == tmp_path / f"status_{user_id}.json"
    assert settings.token_path() == tmp_path / f"token_{user_id}.json"


def test_settings_falls_back_to_legacy_db_and_status(tmp_path: Path) -> None:
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

    assert settings.user_db_path() == tmp_path / "miband.db"
    assert settings.user_status_path() == tmp_path / "status.json"
    assert settings.canonical_user_db_path() == tmp_path / "miband_123.db"


def test_settings_from_env_rejects_invalid_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setenv("SYNC_INTERVAL", "soon")

    with pytest.raises(ConfigError, match="SYNC_INTERVAL"):
        Settings.from_env()


def test_settings_from_env_rejects_zero_query_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setenv("QUERY_DURATION", "0")

    with pytest.raises(ConfigError, match="QUERY_DURATION"):
        Settings.from_env()
