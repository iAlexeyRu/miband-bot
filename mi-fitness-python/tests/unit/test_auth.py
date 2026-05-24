"""测试认证模块的内部编排逻辑。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mi_fitness.auth import XiaomiAuth
from mi_fitness.auth import manager as auth_manager
from mi_fitness.auth import passtoken as passtoken_module
from mi_fitness.auth import password as password_module
from mi_fitness.auth import qr as qr_module
from mi_fitness.exceptions import (
    AuthError,
    CaptchaRequiredError,
    DeviceUntrustedError,
    TokenExpiredError,
)
from mi_fitness.models import AuthToken

pytestmark = pytest.mark.asyncio


class _DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        """测试响应默认视为成功。"""


def _http_response(text: str, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://example.com/test")
    return httpx.Response(status_code=status_code, text=text, request=request)


def _make_auth() -> XiaomiAuth:
    auth = XiaomiAuth("13800138000", "secret")
    auth._http = MagicMock()
    auth._http.cookies = MagicMock()
    return auth


async def test_send_verification_code_retries_captcha_once(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()

    ensure_ready = AsyncMock()
    send_ticket = AsyncMock(
        side_effect=[
            CaptchaRequiredError("需要图形验证码", captcha_url="https://example.com/captcha.png"),
            None,
        ]
    )
    get_phone_info = AsyncMock(return_value=("191******54", "ticket-token"))
    fetch_captcha = AsyncMock(return_value=b"captcha-image")
    captcha_handler = AsyncMock(return_value="ABCD")

    monkeypatch.setattr(auth_manager._pwd, "ensure_ticket_login_ready", ensure_ready)
    monkeypatch.setattr(auth_manager._pwd, "send_ticket", send_ticket)
    monkeypatch.setattr(auth_manager._pwd, "get_phone_info", get_phone_info)
    monkeypatch.setattr(auth_manager._pwd, "fetch_captcha_image", fetch_captcha)

    phone = await auth.send_verification_code(captcha_handler=captcha_handler)

    assert phone == "191******54"
    assert auth._ticket_token == "ticket-token"
    ensure_ready.assert_awaited_once_with(auth._http)
    assert [call.kwargs["captcha_code"] for call in send_ticket.await_args_list] == ["", "ABCD"]
    get_phone_info.assert_awaited_once_with(auth._http, auth.username, captcha_code="")
    fetch_captcha.assert_awaited_once_with(auth._http, "https://example.com/captcha.png")
    captcha_handler.assert_awaited_once_with(b"captcha-image")


async def test_send_verification_code_stops_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _make_auth()

    captcha_error = CaptchaRequiredError(
        "需要图形验证码",
        captcha_url="https://example.com/captcha.png",
    )
    send_ticket = AsyncMock(side_effect=[captcha_error] * auth_manager._MAX_CAPTCHA_RETRIES)
    get_phone_info = AsyncMock()
    fetch_captcha = AsyncMock(return_value=b"captcha-image")
    captcha_handler = AsyncMock(return_value="ABCD")

    monkeypatch.setattr(auth_manager._pwd, "ensure_ticket_login_ready", AsyncMock())
    monkeypatch.setattr(auth_manager._pwd, "send_ticket", send_ticket)
    monkeypatch.setattr(auth_manager._pwd, "get_phone_info", get_phone_info)
    monkeypatch.setattr(auth_manager._pwd, "fetch_captcha_image", fetch_captcha)

    with pytest.raises(AuthError, match="已连续重试 3 次"):
        await auth.send_verification_code(captcha_handler=captcha_handler)

    assert send_ticket.await_count == auth_manager._MAX_CAPTCHA_RETRIES
    assert fetch_captcha.await_count == auth_manager._MAX_CAPTCHA_RETRIES
    assert captcha_handler.await_count == auth_manager._MAX_CAPTCHA_RETRIES
    get_phone_info.assert_not_awaited()


async def test_login_passtoken_uses_shared_service_token_extractor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http = MagicMock()
    http.cookies = MagicMock()
    http.get = AsyncMock(
        return_value=_DummyResponse(
            '&&&START&&&{"ssecurity":"sec","location":"https://example.com/cb?foo=1","nonce":"nonce","cUserId":"cid"}'
        )
    )
    extract_service_token = AsyncMock(return_value="service-token")
    monkeypatch.setattr(passtoken_module, "extract_service_token", extract_service_token)

    token = AuthToken()
    await passtoken_module.login_passtoken(
        http,
        token,
        pass_token="pass-token",
        user_id="user-id",
        device_id="an_device",
    )

    assert token.ssecurity == "sec"
    assert token.c_user_id == "cid"
    assert token.service_token == "service-token"
    extract_service_token.assert_awaited_once()
    await_args = extract_service_token.await_args
    assert await_args is not None
    redirect_url = await_args.args[1]
    assert redirect_url.startswith("https://example.com/cb?foo=1&clientSign=")


async def test_refresh_reuses_existing_token_and_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    auth = _make_auth()
    auth.token = AuthToken(
        user_id="user-id",
        pass_token="pass-token",
        device_id="an_device",
        service_token="old-token",
        ssecurity="old-sec",
    )
    auth._token_path = Path("token.json")
    save_token = MagicMock()
    auth.save_token = save_token  # type: ignore[method-assign]

    async def fake_login_passtoken(*args, **kwargs) -> None:
        auth.token.service_token = "new-token"
        auth.token.ssecurity = "new-sec"

    login_passtoken = AsyncMock(side_effect=fake_login_passtoken)
    monkeypatch.setattr(auth_manager, "_pt", MagicMock(login_passtoken=login_passtoken))
    monkeypatch.setattr(auth_manager, "_sts", MagicMock(sts_exchange=AsyncMock()))

    token = await auth.refresh()

    assert token.service_token == "new-token"
    assert token.ssecurity == "new-sec"
    login_passtoken.assert_awaited_once_with(
        auth._http,
        auth.token,
        pass_token="pass-token",
        user_id="user-id",
        device_id="an_device",
    )
    save_token.assert_called_once_with(Path("token.json"))


async def test_refresh_requires_pass_token() -> None:
    auth = _make_auth()
    auth.token = AuthToken(user_id="user-id", pass_token="")

    with pytest.raises(TokenExpiredError, match="无法自动刷新"):
        await auth.refresh()


async def test_password_login_wrong_password_raises_auth_error() -> None:
    http = MagicMock()
    http.post = AsyncMock(
        return_value=_http_response('&&&START&&&{"code":70002,"desc":"invalid credential"}')
    )

    with pytest.raises(AuthError, match="登录失败"):
        await password_module._raw_submit_login(http, "13800138000", "bad", "sign", "callback")


async def test_submit_login_requires_device_verification() -> None:
    http = MagicMock()
    token = AuthToken()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            password_module,
            "_raw_submit_login",
            AsyncMock(return_value={"code": 70016}),
        )

        with pytest.raises(DeviceUntrustedError, match="二次验证"):
            await password_module.submit_login(
                http, token, "13800138000", "secret", "sign", "callback"
            )


async def test_submit_login_requires_trusted_device_when_security_status_non_zero() -> None:
    http = MagicMock()
    token = AuthToken()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            password_module,
            "_raw_submit_login",
            AsyncMock(return_value={"code": 0, "securityStatus": 8}),
        )

        with pytest.raises(DeviceUntrustedError, match="设备未受信任"):
            await password_module.submit_login(
                http, token, "13800138000", "secret", "sign", "callback"
            )


async def test_qr_login_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    http = MagicMock()
    http.get = AsyncMock(
        return_value=_http_response(
            '&&&START&&&{"qr":"https://example.com/qr.png","lp":"https://example.com/poll","timeout":0}'
        )
    )
    time_values = iter([0.0, 0.0, 1.0])
    monkeypatch.setattr(qr_module.time, "time", lambda: next(time_values))

    with pytest.raises(AuthError, match="二维码扫码超时"):
        await qr_module.login_qr(http, AuthToken(), max_wait=0)


async def test_login_passtoken_requires_non_empty_inputs() -> None:
    http = MagicMock()
    http.cookies = MagicMock()
    token = AuthToken()

    with pytest.raises(AuthError, match="passToken 不能为空"):
        await passtoken_module.login_passtoken(http, token, pass_token="", user_id="uid")

    with pytest.raises(AuthError, match="userId 不能为空"):
        await passtoken_module.login_passtoken(http, token, pass_token="pt", user_id="")
