"""测试基础请求层的边界容错。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import mi_fitness.client.base as client_base
from mi_fitness.client.base import encrypted_request
from mi_fitness.const import ERR_NOT_RELATIVES, ERR_NOT_SHARED_DATA_TYPE
from mi_fitness.exceptions import (
    AuthError,
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
)

pytestmark = pytest.mark.asyncio


def _mock_response(status_code: int = 200, text: str = "encrypted") -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/test")
    return httpx.Response(status_code=status_code, text=text, request=request)


async def test_encrypted_request_accepts_string_zero_code(
    monkeypatch: pytest.MonkeyPatch,
    auth_token,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_mock_response())

    monkeypatch.setattr(
        client_base, "build_encrypted_params", lambda *args, **kwargs: {"_nonce": "nonce"}
    )
    monkeypatch.setattr(
        client_base,
        "decrypt_response",
        lambda *args, **kwargs: {"code": "0", "result": {"ok": True}},
    )

    result = await encrypted_request(http, auth_token, "GET", "/app/v1/test")
    assert result["result"]["ok"] is True


async def test_encrypted_request_uses_string_code_for_not_relatives(
    monkeypatch: pytest.MonkeyPatch,
    auth_token,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_mock_response())

    monkeypatch.setattr(
        client_base, "build_encrypted_params", lambda *args, **kwargs: {"_nonce": "nonce"}
    )
    monkeypatch.setattr(
        client_base,
        "decrypt_response",
        lambda *args, **kwargs: {
            "code": str(ERR_NOT_RELATIVES),
            "desc": "not relatives",
        },
    )

    with pytest.raises(FamilyMemberNotFoundError, match="not relatives"):
        await encrypted_request(http, auth_token, "GET", "/app/v1/test")


async def test_encrypted_request_requires_authenticated_token(auth_token) -> None:
    http = MagicMock()
    auth_token.service_token = ""

    with pytest.raises(AuthError, match="未登录"):
        await encrypted_request(http, auth_token, "GET", "/app/v1/test")


async def test_encrypted_request_uses_string_code_for_data_not_shared(
    monkeypatch: pytest.MonkeyPatch,
    auth_token,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_mock_response())

    monkeypatch.setattr(
        client_base, "build_encrypted_params", lambda *args, **kwargs: {"_nonce": "nonce"}
    )
    monkeypatch.setattr(
        client_base,
        "decrypt_response",
        lambda *args, **kwargs: {
            "code": str(ERR_NOT_SHARED_DATA_TYPE),
            "desc": "not shared data type",
        },
    )

    with pytest.raises(DataNotSharedError, match="not shared data type") as exc_info:
        await encrypted_request(
            http,
            auth_token,
            "GET",
            "/app/v1/relatives/get_aggregated_data",
            params={"relative_uid": 1, "key": "heart_rate"},
        )

    assert exc_info.value.data_type == "heart_rate"


async def test_encrypted_request_raises_time_scope_error_for_out_of_range_dates(
    monkeypatch: pytest.MonkeyPatch,
    auth_token,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_mock_response())

    monkeypatch.setattr(
        client_base, "build_encrypted_params", lambda *args, **kwargs: {"_nonce": "nonce"}
    )
    monkeypatch.setattr(
        client_base,
        "decrypt_response",
        lambda *args, **kwargs: {
            "code": str(ERR_NOT_SHARED_DATA_TYPE),
            "message": "time out of data shared time scope",
        },
    )

    with pytest.raises(DataOutOfSharedTimeScopeError, match="超出亲友共享时间范围") as exc_info:
        await encrypted_request(
            http,
            auth_token,
            "GET",
            "/app/v1/relatives/get_aggregated_data",
            params={"relative_uid": 1, "key": "steps"},
        )

    assert exc_info.value.data_type == "steps"
