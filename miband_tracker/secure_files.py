# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

SECRET_FILE_MODE = 0o600


def write_text_atomic(path: Path, text: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def write_json_atomic(path: Path, data: Any, *, mode: int | None = None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    write_text_atomic(path, text, mode=mode)


def write_secret_json(path: Path, data: dict[str, Any]) -> None:
    write_json_atomic(path, data, mode=SECRET_FILE_MODE)


def save_auth_token(token: Any, path: Path) -> None:
    current = _read_current_token_payload(path)
    if hasattr(token, "model_dump"):
        payload = token.model_dump()
    elif hasattr(token, "model_dump_json"):
        payload = json.loads(token.model_dump_json())
    else:
        payload = dict(token)

    for key in ("target_relative_uid",):
        if key in current and key not in payload:
            payload[key] = current[key]

    write_secret_json(path, payload)


def _read_current_token_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
