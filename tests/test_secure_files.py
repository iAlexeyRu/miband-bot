import json
import os
from pathlib import Path

from mi_fitness.models import AuthToken

from miband_tracker.secure_files import save_auth_token, write_secret_json


def test_write_secret_json_uses_private_file_mode(tmp_path: Path) -> None:
    path = tmp_path / "token.json"

    write_secret_json(path, {"service_token": "secret"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"service_token": "secret"}
    assert stat_mode(path) == 0o600


def test_save_auth_token_preserves_target_relative_uid(tmp_path: Path) -> None:
    path = tmp_path / "token.json"
    write_secret_json(path, {"target_relative_uid": "42"})

    save_auth_token(AuthToken(user_id="11", service_token="svc", ssecurity="sec"), path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["user_id"] == "11"
    assert data["target_relative_uid"] == "42"
    assert stat_mode(path) == 0o600


def stat_mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777
