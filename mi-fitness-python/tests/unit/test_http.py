"""测试重试 HTTP 客户端 (http.py)。"""

from __future__ import annotations

import httpx
import pytest

from mi_fitness.http import RetryAsyncClient

pytestmark = pytest.mark.asyncio


async def test_retries_on_idempotent_get_status_code() -> None:
    """GET 遇到可重试状态码时应自动重试。"""
    call_count = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(status_code=503, json={"message": "busy"})
        return httpx.Response(status_code=200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with RetryAsyncClient(
        transport=transport,
        retry_attempts=3,
        retry_wait_min=0.0,
        retry_wait_max=0.0,
        retry_wait_multiplier=0.0,
    ) as client:
        resp = await client.get("https://example.com/ping")

    assert resp.status_code == 200
    assert call_count == 3


async def test_does_not_retry_non_idempotent_post_by_default() -> None:
    """POST 默认不重试，避免非幂等接口重复提交。"""
    call_count = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code=503, json={"message": "busy"})

    transport = httpx.MockTransport(handler)
    async with RetryAsyncClient(
        transport=transport,
        retry_attempts=3,
        retry_wait_min=0.0,
        retry_wait_max=0.0,
        retry_wait_multiplier=0.0,
    ) as client:
        resp = await client.post("https://example.com/send", data={"a": "1"})

    assert resp.status_code == 503
    assert call_count == 1


async def test_retries_on_network_error_for_get() -> None:
    """GET 遇到网络异常时应自动重试。"""
    call_count = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise httpx.ConnectError("connect failed")
        return httpx.Response(status_code=200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    async with RetryAsyncClient(
        transport=transport,
        retry_attempts=3,
        retry_wait_min=0.0,
        retry_wait_max=0.0,
        retry_wait_multiplier=0.0,
    ) as client:
        resp = await client.get("https://example.com/health")

    assert resp.status_code == 200
    assert call_count == 2
