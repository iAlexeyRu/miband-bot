"""测试 CLI 入口与二维码登录。"""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar, Self
from uuid import uuid4

import pytest

import mi_fitness.cli as cli


def _workspace_tmp_dir() -> Path:
    root = Path(".test-tmp") / uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


class _FakeAuth:
    instances: ClassVar[list["_FakeAuth"]] = []

    def __init__(self, *args: object):
        self.args = args
        self.token = SimpleNamespace(user_id="3188565001")
        self.saved_path: Path | None = None
        self.login_calls: list[tuple[object, ...]] = []
        _FakeAuth.instances.append(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def login_qr(self, qr_callback=None) -> None:  # type: ignore[no-untyped-def]
        self.login_calls.append(("qr",))
        if qr_callback is not None:
            await qr_callback("https://example.com/qr.png", "https://example.com/login")

    def save_token(self, path: Path | str) -> None:
        self.saved_path = Path(path)


@pytest.mark.asyncio
async def test_qr_login_saves_token(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _FakeAuth.instances.clear()
    tmp_dir = _workspace_tmp_dir()
    monkeypatch.setattr(cli, "XiaomiAuth", _FakeAuth)
    monkeypatch.setattr(cli, "TOKEN_FILE", tmp_dir / "token.json")
    try:
        await cli._qr_login()
        auth = _FakeAuth.instances[-1]
        assert auth.login_calls == [("qr",)]
        assert auth.saved_path == tmp_dir / "token.json"
        stdout = capsys.readouterr().out
        assert "https://example.com/login" not in stdout
        assert "https://example.com/qr.png" not in stdout
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_main_runs_without_args(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_qr_login() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli, "_qr_login", fake_qr_login)
    cli.main()
    assert called
