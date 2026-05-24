"""STS 安全令牌交换。"""

from __future__ import annotations

import time
import os

from loguru import logger

from mi_fitness.const import STS_HEALTH_URL
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken


async def sts_exchange(http: RetryAsyncClient, token: AuthToken) -> None:
    """STS 安全令牌交换。

    使用 deviceId 完成 STS 验证。此步骤非致命，失败仅打印警告。

    Args:
        http: HTTP 客户端。
        token: 已有 device_id 的 AuthToken。
    """
    params = {
        "d": token.device_id,
        "ticket": "0",
        "pwd": "0",
        "p_ts": str(int(time.time() * 1000)),
        "fid": "0",
        "p_lm": "2",
        "p_ur": "CN",
        "sid": "hlth.io.mi.com",
    }
    client_sign = os.environ.get("MI_CLIENT_SIGN")
    if client_sign:
        params["clientSign"] = client_sign
    cookies = {}
    if token.user_id:
        cookies["userId"] = token.user_id
    if token.c_user_id:
        cookies["cUserId"] = token.c_user_id
    if token.pass_token:
        cookies["passToken"] = token.pass_token

    try:
        resp = await http.get(STS_HEALTH_URL, params=params, cookies=cookies)
        if resp.text.strip() == "ok":
            logger.debug("STS 交换成功")
            # Extract STS serviceToken from cookies and save it to AuthToken
            logger.debug("Куки в клиенте во время STS:")
            for cookie in http.cookies.jar:
                logger.debug(f"  Cookie: {cookie.name}, Domain: {cookie.domain}, Value: {cookie.value[:15]}...")
            sts_token = None
            for cookie in http.cookies.jar:
                if cookie.name == "serviceToken" and "hlth.io.mi.com" in (cookie.domain or ""):
                    sts_token = cookie.value
                    break
            if not sts_token:
                sts_token = http.cookies.get("serviceToken")
            
            if sts_token:
                token.service_token = sts_token
                logger.debug("STS serviceToken успешно сохранен в AuthToken: {}", sts_token[:15] + "...")
        else:
            logger.warning("STS 交换响应: {}", resp.text[:100])
    except Exception as e:
        logger.warning("STS 交换失败（非致命）: {}", e)
