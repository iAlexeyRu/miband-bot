"""passToken 交换登录。"""

from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import quote

from loguru import logger

from mi_fitness.const import SERVICE_SID_HEALTH, XIAOMI_LOGIN_URL
from mi_fitness.exceptions import AuthError
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from ._helpers import extract_service_token, parse_mi_response, set_cookie_for_domains


async def login_passtoken(
    http: RetryAsyncClient,
    token: AuthToken,
    *,
    pass_token: str,
    user_id: str,
    device_id: str = "",
) -> None:
    """使用 passToken 换取完整登录凭证。

    Args:
        http: HTTP 客户端。
        token: 要写入的 AuthToken。
        pass_token: 小米账号 passToken。
        user_id: 小米账号 userId。
        device_id: 设备标识符（可选）。

    Raises:
        AuthError: passToken 无效或换取凭证失败。
    """
    if not pass_token:
        raise AuthError("passToken 不能为空")
    if not user_id:
        raise AuthError("userId 不能为空")

    token.pass_token = pass_token
    token.user_id = user_id
    if device_id:
        token.device_id = device_id
    elif not token.device_id:
        token.device_id = f"an_{os.urandom(16).hex()}"

    # 设置 cookies（passToken + deviceId + userId）
    for name, value in {
        "passToken": pass_token,
        "deviceId": token.device_id,
        "userId": user_id,
    }.items():
        set_cookie_for_domains(http, name, value)

    logger.info("使用 passToken 换取凭证, userId={}", user_id)

    # 调用 serviceLogin，带上 passToken cookie 会让服务端直接返回凭证
    resp = await http.get(
        XIAOMI_LOGIN_URL,
        params={"_json": "true", "sid": SERVICE_SID_HEALTH},
    )
    resp.raise_for_status()
    data = parse_mi_response(resp.text)

    ssecurity = data.get("ssecurity", "")
    location = data.get("location", "")
    nonce_val = data.get("nonce", "")
    c_user_id = data.get("cUserId", "")

    if not ssecurity:
        raise AuthError(
            "passToken 换取凭证失败：serviceLogin 未返回 ssecurity。"
            f"响应字段: {', '.join(sorted(data.keys()))}"
        )

    token.ssecurity = ssecurity
    token.c_user_id = c_user_id

    # 跟随 location 重定向获取 serviceToken
    if location:
        sign_text = f"nonce={nonce_val}&{ssecurity}"
        sha1_digest = hashlib.sha1(sign_text.encode()).digest()
        client_sign = quote(base64.b64encode(sha1_digest).decode())
        full_url = f"{location}&clientSign={client_sign}"
        token.service_token = await extract_service_token(http, full_url)

    logger.info("passToken 凭证交换完成, user_id={}", token.user_id)
