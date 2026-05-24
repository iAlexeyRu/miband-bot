"""RC4 加密请求基础层。"""

from __future__ import annotations

import json
from typing import Any, NoReturn

from mi_fitness.const import (
    DEFAULT_USER_AGENT,
    ERR_NOT_RELATIVES,
    ERR_NOT_SHARED_DATA_TYPE,
    HEALTH_API_BASE,
    REGION_TAG,
)
from mi_fitness.crypto import build_encrypted_params, decrypt_response
from mi_fitness.exceptions import (
    APIError,
    AuthError,
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
    TokenExpiredError,
)
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken


def _coerce_api_code(value: Any, default: int = -1) -> int:
    """尽力兼容 int / str 形式的业务码。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_api_message(result: dict[str, Any]) -> str:
    """兼容不同字段名的错误消息。"""
    for key in ("message", "msg", "desc", "description"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "未知错误"


def _is_time_scope_error(message: str) -> bool:
    """识别“超出亲友共享时间范围”类错误。"""
    normalized = message.strip().lower()
    return "time out of data shared time scope" in normalized


def _extract_requested_data_type(params: dict[str, Any] | None) -> str:
    """从业务参数中提取当前请求的数据类型 key。"""
    if not isinstance(params, dict):
        return ""
    key = params.get("key")
    return str(key) if key is not None else ""


def _build_auth_cookies(token: AuthToken) -> dict[str, str]:
    """构造健康接口请求所需的认证 cookie。"""
    return {
        "cUserId": token.c_user_id,
        "serviceToken": token.service_token,
    }


async def _send_encrypted_http_request(
    http: RetryAsyncClient,
    method: str,
    url: str,
    enc_params: dict[str, Any],
    cookies: dict[str, str],
):
    """按 HTTP 方法发送已加密请求。"""
    if method.upper() == "GET":
        return await http.get(url, params=enc_params, cookies=cookies)
    return await http.post(url, data=enc_params, cookies=cookies)


def _raise_for_http_status(resp: Any, method: str, path: str) -> None:
    """将 HTTP 状态码转换为 SDK 异常。"""
    if resp.status_code == 401:
        raise TokenExpiredError(f"认证已过期: {method} {path} -> 401")
    if resp.status_code != 200:
        raise APIError(
            f"API 请求失败: {method} {path} -> {resp.status_code}",
            status_code=resp.status_code,
            response_body=resp.text,
        )


def _decrypt_result(ssecurity: str, nonce: str, resp: Any) -> dict[str, Any]:
    """解密并校验响应体。"""
    try:
        result = decrypt_response(ssecurity, nonce, resp.text)
    except Exception as e:
        raise APIError(
            f"响应解密失败: {e}",
            status_code=resp.status_code,
            response_body=resp.text[:200],
        ) from e

    if not isinstance(result, dict):
        raise APIError(
            f"解密后非 JSON 对象: {type(result)}",
            response_body=str(result)[:200],
        )
    return result


def _raise_for_business_code(
    code: int,
    result: dict[str, Any],
    *,
    params: dict[str, Any] | None = None,
) -> NoReturn:
    """将业务错误码映射为 SDK 异常。"""
    msg = _extract_api_message(result)
    body = json.dumps(result, ensure_ascii=False)

    if code == ERR_NOT_RELATIVES:
        raise FamilyMemberNotFoundError(f"非亲友关系 (code={code}): {msg}")

    if code == ERR_NOT_SHARED_DATA_TYPE:
        data_type = _extract_requested_data_type(params)
        suffix = f", key={data_type}" if data_type else ""
        if _is_time_scope_error(msg):
            raise DataOutOfSharedTimeScopeError(
                f"超出亲友共享时间范围 (code={code}{suffix}): {msg}",
                data_type=data_type,
            )
        raise DataNotSharedError(
            f"未共享该数据类型 (code={code}{suffix}): {msg}",
            data_type=data_type,
        )

    raise APIError(
        f"API 业务错误 (code={code}): {msg}",
        code=code,
        response_body=body,
    )


def create_api_http() -> RetryAsyncClient:
    """创建 API 请求专用的 HTTP 客户端。"""
    return RetryAsyncClient(
        timeout=30.0,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "region_tag": REGION_TAG,
            "handleparams": "true",
        },
    )


async def encrypted_request(
    http: RetryAsyncClient,
    token: AuthToken,
    method: str,
    path: str,
    base_url: str = HEALTH_API_BASE,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """发送 RC4 加密的 API 请求并解密响应。

    Args:
        http: HTTP 客户端。
        token: 已登录的 AuthToken。
        method: HTTP 方法（GET / POST）。
        path: API 路径。
        base_url: API 基础 URL。
        params: 业务参数。

    Returns:
        解密后的响应 JSON dict。

    Raises:
        APIError: 请求或解密失败。
        AuthError: 当前未登录。
        TokenExpiredError: 401 认证过期。
        FamilyMemberNotFoundError: 非亲友关系。
        DataNotSharedError: 亲友未共享当前请求的数据类型。
        DataOutOfSharedTimeScopeError: 请求日期超出亲友共享时间范围。
    """
    if not token.service_token or not token.ssecurity:
        raise AuthError("未登录，请先调用 auth.login()")

    ssecurity = token.ssecurity
    signing_path = path
    if path == "/healthapp/service/gen_download_url":
        signing_path = "/service/gen_download_url"
    enc_params = build_encrypted_params(method, signing_path, ssecurity, params)
    nonce = enc_params["_nonce"]
    cookies = _build_auth_cookies(token)
    url = base_url.rstrip("/") + path
    resp = await _send_encrypted_http_request(http, method, url, enc_params, cookies)
    _raise_for_http_status(resp, method, path)
    result = _decrypt_result(ssecurity, nonce, resp)

    code = _coerce_api_code(result.get("code"), default=-1)
    if code != 0:
        _raise_for_business_code(code, result, params=params)

    return result
