"""测试认证辅助函数与 STS 交换。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mi_fitness.auth import _helpers as auth_helpers
from mi_fitness.auth import sts as auth_sts
from mi_fitness.exceptions import AuthError
from mi_fitness.models import AuthToken


def _response(
    *,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/test")
    return httpx.Response(200, text=text, headers=headers, request=request)


def test_parse_mi_response_supports_start_prefix() -> None:
    parsed = auth_helpers.parse_mi_response('&&&START&&&{"code":0,"desc":"ok"}')
    assert parsed == {"code": 0, "desc": "ok"}


def test_parse_mi_response_raises_auth_error_for_invalid_json() -> None:
    with pytest.raises(AuthError, match="响应解析失败"):
        auth_helpers.parse_mi_response("&&&START&&&not-json")


def test_normalize_captcha_url_prepends_account_domain() -> None:
    assert (
        auth_helpers.normalize_captcha_url("/pass/getCode?id=1")
        == "https://account.xiaomi.com/pass/getCode?id=1"
    )
    assert (
        auth_helpers.normalize_captcha_url("https://example.com/captcha")
        == "https://example.com/captcha"
    )


def test_set_cookie_for_domains_writes_both_domains() -> None:
    http = MagicMock()
    http.cookies = MagicMock()

    auth_helpers.set_cookie_for_domains(http, "serviceToken", "st")

    assert http.cookies.set.call_count == 2
    assert http.cookies.set.call_args_list[0].args == ("serviceToken", "st")
    assert http.cookies.set.call_args_list[0].kwargs["domain"] == "xiaomi.com"
    assert http.cookies.set.call_args_list[1].kwargs["domain"] == "mi.com"


@pytest.mark.asyncio
async def test_extract_service_token_prefers_set_cookie_header() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_response(
            headers={
                "set-cookie": "serviceToken=header-token; Path=/; HttpOnly",
            }
        )
    )
    http.cookies.get.return_value = ""

    token = await auth_helpers.extract_service_token(http, "https://example.com/login")

    assert token == "header-token"


@pytest.mark.asyncio
async def test_extract_service_token_falls_back_to_redirect_query() -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_response(
            headers={
                "location": "https://example.com/callback?serviceToken=query-token",
            }
        )
    )
    http.cookies.get.return_value = ""

    token = await auth_helpers.extract_service_token(http, "https://example.com/login")

    assert token == "query-token"


@pytest.mark.asyncio
async def test_extract_service_token_falls_back_to_cookie_jar() -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_response())
    http.cookies.get.return_value = "cookie-token"

    token = await auth_helpers.extract_service_token(http, "https://example.com/login")

    assert token == "cookie-token"


@pytest.mark.asyncio
async def test_extract_service_token_raises_when_missing_everywhere() -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_response())
    http.cookies.get.return_value = ""

    with pytest.raises(AuthError, match="未能获取 serviceToken"):
        await auth_helpers.extract_service_token(http, "https://example.com/login")


@pytest.mark.asyncio
async def test_extract_credentials_populates_token_and_service_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    token = AuthToken()
    extract_service_token = AsyncMock(return_value="service-token")
    monkeypatch.setattr(auth_helpers, "extract_service_token", extract_service_token)

    await auth_helpers.extract_credentials(
        http,
        {
            "ssecurity": "sec",
            "userId": "3188565001",
            "passToken": "pt",
            "cUserId": "cid",
            "location": "https://example.com/callback",
        },
        token,
    )

    assert token.ssecurity == "sec"
    assert token.user_id == "3188565001"
    assert token.pass_token == "pt"
    assert token.c_user_id == "cid"
    assert token.service_token == "service-token"
    extract_service_token.assert_awaited_once_with(http, "https://example.com/callback")


@pytest.mark.asyncio
async def test_sts_exchange_uses_device_id_and_accepts_ok_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.get = AsyncMock(return_value=_response(text="ok"))
    token = AuthToken(device_id="an_device")
    monkeypatch.setattr(auth_sts.time, "time", lambda: 1.234)

    await auth_sts.sts_exchange(http, token)

    http.get.assert_awaited_once()
    params = http.get.await_args.kwargs["params"]
    assert params["d"] == "an_device"
    assert params["p_ts"] == "1234"


@pytest.mark.asyncio
async def test_sts_exchange_swallows_network_failure() -> None:
    http = MagicMock()
    http.get = AsyncMock(side_effect=RuntimeError("boom"))
    token = AuthToken(device_id="an_device")

    await auth_sts.sts_exchange(http, token)
