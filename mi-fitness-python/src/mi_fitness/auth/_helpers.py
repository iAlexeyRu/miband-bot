"""认证模块内部工具函数。"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING

from loguru import logger

from mi_fitness.const import DEFAULT_LOGIN_USER_AGENT
from mi_fitness.exceptions import AuthError
from mi_fitness.http import RetryAsyncClient

if TYPE_CHECKING:
    from mi_fitness.models import AuthToken

_COOKIE_DOMAINS = ("xiaomi.com", "mi.com")


def parse_mi_response(text: str) -> dict:
    """解析小米 API ``&&&START&&&`` 前缀的 JSON 响应。"""
    body = text
    if body.startswith("&&&START&&&"):
        body = body[len("&&&START&&&") :]
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise AuthError(f"响应解析失败: {text[:200]}") from e


def create_login_http() -> RetryAsyncClient:
    """创建登录流程专用的 HTTP 客户端。"""
    return RetryAsyncClient(
        follow_redirects=False,
        timeout=30.0,
        headers={
            "User-Agent": DEFAULT_LOGIN_USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )


def normalize_captcha_url(captcha_url: str) -> str:
    """补全图形验证码 URL。"""
    if captcha_url.startswith("/"):
        return f"https://account.xiaomi.com{captcha_url}"
    return captcha_url


def set_cookie_for_domains(
    http: RetryAsyncClient,
    name: str,
    value: str,
) -> None:
    """为小米登录相关域名批量写入 cookie。"""
    for domain in _COOKIE_DOMAINS:
        http.cookies.set(name, value, domain=domain)


async def extract_service_token(http: RetryAsyncClient, location: str) -> str:
    """跟随登录重定向，从响应 cookie 中提取 serviceToken。

    Args:
        http: HTTP 客户端。
        location: 登录返回的重定向 URL。

    Returns:
        serviceToken 值。
    """
    resp = await http.get(location)
    service_token = ""
    for header_val in resp.headers.get_list("set-cookie"):
        if "serviceToken=" in header_val:
            match = re.search(r"serviceToken=([^;]+)", header_val)
            if match:
                service_token = match.group(1)
                break

    if not service_token:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(str(resp.headers.get("location", location)))
        qs = parse_qs(parsed.query)
        service_token = qs.get("serviceToken", [""])[0]

    if not service_token:
        service_token = str(http.cookies.get("serviceToken", "") or "")

    if not service_token:
        raise AuthError("未能获取 serviceToken")

    return service_token


async def extract_credentials(
    http: RetryAsyncClient,
    data: dict,
    token: "AuthToken",
) -> None:
    """从登录响应中提取并保存凭证到 token。

    Args:
        http: HTTP 客户端。
        data: 登录接口返回的 JSON dict。
        token: 要写入的 AuthToken 实例。
    """
    token.ssecurity = data["ssecurity"]
    token.user_id = str(data.get("userId", ""))
    token.pass_token = data.get("passToken", "")
    token.c_user_id = data.get("cUserId", "")

    location = data.get("location", "")
    if location:
        service_token = await extract_service_token(http, location)
        token.service_token = service_token

    logger.debug("凭证提取完成, user_id={}", token.user_id)


async def async_sleep(seconds: float) -> None:
    """异步等待，方便测试时 mock。"""
    await asyncio.sleep(seconds)
