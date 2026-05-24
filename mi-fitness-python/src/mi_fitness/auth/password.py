"""密码登录 + 短信验证码流程。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger

from mi_fitness.const import (
    APP_NAME,
    ERR_DEVICE_UNTRUST,
    SERVICE_SID_HEALTH,
    XIAOMI_LOGIN_AUTH_URL,
    XIAOMI_LOGIN_URL,
    XIAOMI_PHONE_INFO_URL,
    XIAOMI_PREFERENCE_URL,
    XIAOMI_SEND_TICKET_URL,
    XIAOMI_TICKET_AUTH_URL,
)
from mi_fitness.exceptions import AuthError, CaptchaRequiredError, DeviceUntrustedError
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from ._helpers import extract_credentials, normalize_captcha_url, parse_mi_response


# region 登录页
async def get_login_page(
    http: RetryAsyncClient,
    *,
    login_sign: str = "",
) -> tuple[str, str]:
    """请求登录页，获取 _sign 和 callback。

    Args:
        http: HTTP 客户端。
        login_sign: 登录签名类型。``""`` 为密码登录，
            ``"ticket"`` 为短信验证码登录。

    Returns:
        (sign, callback) 元组。
    """
    import re

    params: dict[str, str] = {
        "_json": "true",
        "appName": APP_NAME,
        "sid": SERVICE_SID_HEALTH,
        "_locale": "zh_CN",
    }
    if login_sign:
        params["_loginSign"] = login_sign

    resp = await http.get(XIAOMI_LOGIN_URL, params=params)
    resp.raise_for_status()

    body = resp.text
    if body.startswith("&&&START&&&"):
        body = body[len("&&&START&&&") :]

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        sign_match = re.search(r'"_sign"\s*:\s*"([^"]+)"', resp.text)
        callback_match = re.search(r'"callback"\s*:\s*"([^"]+)"', resp.text)
        sign = sign_match.group(1) if sign_match else ""
        callback = callback_match.group(1) if callback_match else ""
        return sign, callback

    sign = data.get("_sign", "")
    callback = data.get("callback", "")
    return sign, callback


# endregion


# region 密码提交
async def submit_login(
    http: RetryAsyncClient,
    token: AuthToken,
    username: str,
    password: str,
    sign: str,
    callback: str,
) -> None:
    """提交密码并处理登录响应。

    成功时直接写入 token；设备未信任时抛出 DeviceUntrustedError。

    Raises:
        AuthError: 密码错误。
        DeviceUntrustedError: 设备未信任，需短信验证。
    """
    data = await _raw_submit_login(http, username, password, sign, callback)

    if data.get("ssecurity"):
        await extract_credentials(http, data, token)
        return

    if data.get("code") == ERR_DEVICE_UNTRUST:
        raise DeviceUntrustedError(
            f"登录需要二次验证（code={ERR_DEVICE_UNTRUST}）。将自动进入短信验证码流程。",
            security_status=16,
        )

    security_status = data.get("securityStatus", 0)
    if security_status != 0:
        raise DeviceUntrustedError(
            f"设备未受信任 (securityStatus={security_status})，"
            f"需要短信验证码完成登录。\n"
            f"请传入 verification_code_handler 回调，"
            f"或手动调用 send_verification_code() + "
            f"login_with_verification_code()。",
            security_status=security_status,
        )

    keys = ", ".join(sorted(data.keys()))
    raise AuthError(f"登录异常：密码正确但未返回凭证。响应字段: {keys}")


async def _raw_submit_login(
    http: RetryAsyncClient,
    username: str,
    password: str,
    sign: str,
    callback: str,
) -> dict:
    """提交密码到 serviceLoginAuth2 并返回解析后的响应。"""
    pwd_hash = hashlib.md5(password.encode()).hexdigest().upper()

    form_data = {
        "sid": SERVICE_SID_HEALTH,
        "_json": "true",
        "_sign": sign,
        "callback": callback,
        "user": username,
        "hash": pwd_hash,
        "qs": f"%3Fsid%3D{SERVICE_SID_HEALTH}",
        "_locale": "zh_CN",
    }

    resp = await http.post(
        XIAOMI_LOGIN_AUTH_URL,
        data=form_data,
        headers={"Referer": XIAOMI_LOGIN_URL},
    )
    resp.raise_for_status()

    data = parse_mi_response(resp.text)

    code = data.get("code", -1)
    if code == ERR_DEVICE_UNTRUST:
        return data
    if code != 0:
        desc = data.get("desc", "未知错误")
        raise AuthError(f"登录失败 (code={code}): {desc}")

    return data


# endregion


# region 短信验证码
async def ensure_ticket_login_ready(http: RetryAsyncClient) -> None:
    """请求 preference 页准备 ticket 登录上下文。"""
    resp = await http.get(XIAOMI_PREFERENCE_URL, params={"_locale": "zh_CN"})
    resp.raise_for_status()
    data = parse_mi_response(resp.text)
    if data.get("code", -1) != 0:
        raise AuthError(f"登录偏好初始化失败: {data.get('description', '未知错误')}")


def _build_ticket_form_data(username: str, *, captcha_code: str = "") -> dict[str, str]:
    """构造短信验证相关接口的公共表单。"""
    form_data: dict[str, str] = {
        "sid": SERVICE_SID_HEALTH,
        "_json": "true",
        "_locale": "zh_CN",
        "user": username,
    }
    if captcha_code:
        form_data["captCode"] = captcha_code
    return form_data


async def _post_ticket_request(
    http: RetryAsyncClient,
    url: str,
    username: str,
    *,
    captcha_code: str = "",
    error_prefix: str,
) -> dict[str, Any]:
    """提交短信验证相关请求并统一处理验证码风控。"""
    resp = await http.post(
        url,
        data=_build_ticket_form_data(username, captcha_code=captcha_code),
    )
    resp.raise_for_status()
    data = parse_mi_response(resp.text)

    if data.get("code", -1) == 0:
        return data

    desc = data.get("description", "未知错误")
    captcha_url = normalize_captcha_url(data.get("captchaUrl", ""))
    if captcha_url:
        raise CaptchaRequiredError(
            f"{error_prefix}：触发了图形验证码风控 (code={data.get('code')})",
            captcha_url=captcha_url,
        )
    raise AuthError(f"{error_prefix}: {desc}")


async def send_ticket(
    http: RetryAsyncClient,
    username: str,
    *,
    captcha_code: str = "",
) -> None:
    """发送短信验证码到用户手机。

    Raises:
        CaptchaRequiredError: 触发图形验证码风控。
        AuthError: 发送失败。
    """
    data = await _post_ticket_request(
        http,
        XIAOMI_SEND_TICKET_URL,
        username,
        captcha_code=captcha_code,
        error_prefix="验证码发送失败",
    )

    logger.debug("验证码已发送, vCodeLen={}", data.get("data", {}).get("vCodeLen"))


async def get_phone_info(
    http: RetryAsyncClient,
    username: str,
    *,
    captcha_code: str = "",
) -> tuple[str, str]:
    """获取手机号信息和 ticketToken。

    Returns:
        (脱敏手机号, ticketToken) 元组。

    Raises:
        CaptchaRequiredError: 触发图形验证码风控。
        AuthError: 获取失败。
    """
    data = await _post_ticket_request(
        http,
        XIAOMI_PHONE_INFO_URL,
        username,
        captcha_code=captcha_code,
        error_prefix="获取手机信息失败",
    )

    info = data.get("data", {})
    phone = info.get("phone", "未知号码")
    ticket_token = info.get("ticketToken", "")
    if not ticket_token:
        raise AuthError("服务端未返回 ticketToken，无法发送验证码")
    return phone, ticket_token


async def fetch_captcha_image(http: RetryAsyncClient, captcha_url: str) -> bytes:
    """下载图形验证码图片。"""
    logger.debug("下载图形验证码: {}", captcha_url)
    resp = await http.get(captcha_url)
    resp.raise_for_status()
    return resp.content


async def submit_ticket_auth(
    http: RetryAsyncClient,
    token: AuthToken,
    code: str,
    sign: str,
    callback: str,
) -> None:
    """使用验证码完成 serviceLoginTicketAuth 登录。

    Args:
        http: HTTP 客户端。
        token: 要写入的 AuthToken。
        code: 用户输入的 6 位短信验证码。
        sign: 登录页获取的 _sign。
        callback: 回调 URL。
    """
    form_data = {
        "sid": SERVICE_SID_HEALTH,
        "_json": "true",
        "_sign": sign,
        "callback": callback,
        "ticket": code,
        "qs": (
            f"%3F_loginSign%3Dticket%26_json%3Dtrue%26sid%3D{SERVICE_SID_HEALTH}%26_locale%3Dzh_CN"
        ),
        "_locale": "zh_CN",
    }

    resp = await http.post(
        XIAOMI_TICKET_AUTH_URL,
        data=form_data,
        headers={"Referer": XIAOMI_LOGIN_URL},
    )
    resp.raise_for_status()
    data = parse_mi_response(resp.text)

    code_val = data.get("code", -1)
    if code_val != 0:
        desc = data.get("desc", "未知错误")
        raise AuthError(f"验证码验证失败 (code={code_val}): {desc}")

    if not data.get("ssecurity"):
        raise AuthError("验证码验证成功但未返回凭证")

    await extract_credentials(http, data, token)


# endregion
