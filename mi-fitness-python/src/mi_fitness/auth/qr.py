"""二维码扫码登录。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx
from loguru import logger

from mi_fitness.const import SERVICE_SID_HEALTH, STS_HEALTH_URL, XIAOMI_QR_LOGIN_URL
from mi_fitness.exceptions import AuthError
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from ._helpers import async_sleep, extract_credentials, parse_mi_response


async def login_qr(
    http: RetryAsyncClient,
    token: AuthToken,
    *,
    qr_callback: Callable[[str, str], Awaitable[None]] | None = None,
    poll_interval: float = 2.0,
    max_wait: float = 300.0,
) -> None:
    """执行二维码扫码登录流程。

    Args:
        http: HTTP 客户端。
        token: 要写入的 AuthToken。
        qr_callback: 二维码展示回调。接收 ``(qr_image_url, login_url)``。
        poll_interval: 长轮询间隔（秒）。
        max_wait: 扫码超时时间（秒）。

    Raises:
        AuthError: 获取二维码失败或扫码超时。
    """
    logger.info("开始二维码扫码登录")

    # Step 1: 获取二维码信息
    qr_params = {
        "_qrsize": "480",
        "qs": f"%3Fsid%3D{SERVICE_SID_HEALTH}%26_json%3Dtrue",
        "callback": STS_HEALTH_URL,
        "_hasLogo": "false",
        "sid": SERVICE_SID_HEALTH,
        "serviceParam": "",
        "_locale": "zh_CN",
        "_dc": str(int(time.time() * 1000)),
    }
    resp = await http.get(XIAOMI_QR_LOGIN_URL, params=qr_params)
    resp.raise_for_status()
    qr_data = parse_mi_response(resp.text)

    qr_image_url = qr_data.get("qr", "")
    login_url = qr_data.get("loginUrl", "")
    long_polling_url = qr_data.get("lp", "")
    qr_timeout = qr_data.get("timeout", max_wait)

    if not qr_image_url or not long_polling_url:
        raise AuthError(f"获取二维码失败: {qr_data}")

    # 通知调用方展示二维码
    if qr_callback:
        await qr_callback(qr_image_url, login_url)
    else:
        logger.info("请使用小米账号 APP 扫描二维码登录")
        logger.info("二维码图片: {}", qr_image_url)
        if login_url:
            logger.info("或在浏览器打开: {}", login_url)

    # Step 2: 长轮询等待扫码
    effective_timeout = min(float(qr_timeout), max_wait)
    poll_request_timeout = 60.0
    logger.debug(
        "二维码长轮询开始: effective_timeout={}s, request_timeout={}s",
        f"{effective_timeout:.0f}",
        f"{poll_request_timeout:.0f}",
    )
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > effective_timeout:
            raise AuthError(f"二维码扫码超时（{effective_timeout:.0f}s），请重新获取")

        try:
            # 直接调用 httpx.AsyncClient.get 绕过 RetryAsyncClient 的重试
            resp = await httpx.AsyncClient.request(
                http, "GET", long_polling_url, timeout=poll_request_timeout
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.warning("二维码登录轮询被中断")
            raise
        except httpx.TimeoutException:
            logger.debug("长轮询超时，继续等待...")
            continue
        except httpx.RequestError as e:
            logger.warning("长轮询请求失败: {}", e)
            await async_sleep(poll_interval)
            continue

        if resp.status_code != 200:
            logger.debug("长轮询返回 {}，继续等待...", resp.status_code)
            await async_sleep(poll_interval)
            continue

        break

    data = parse_mi_response(resp.text)
    logger.info("扫码成功, userId={}", data.get("userId"))

    # Step 3: 提取凭证
    await extract_credentials(http, data, token)
