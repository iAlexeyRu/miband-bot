"""HTTP 客户端扩展。"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

_DEFAULT_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


class _RetryableStatusError(Exception):
    """内部异常：用于触发 tenacity 的状态码重试。"""

    def __init__(self, response: httpx.Response):
        super().__init__(f"retryable status: {response.status_code}")
        self.response = response


def _is_retryable_error(exc: BaseException) -> bool:
    """判断异常是否可重试。"""
    if isinstance(exc, _RetryableStatusError):
        return True
    return isinstance(exc, (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError))


class RetryAsyncClient(httpx.AsyncClient):
    """带重试能力的异步 HTTP 客户端。

    继承 ``httpx.AsyncClient``，在 ``request`` 上增加 tenacity 退避重试。
    默认仅对幂等方法启用重试，避免对发送短信/提交表单等非幂等请求重复提交。

    Attributes:
            retry_attempts: 最大重试次数（含首轮请求）。
            retry_wait_min: 指数退避最小等待秒数。
            retry_wait_max: 指数退避最大等待秒数。
            retry_wait_multiplier: 指数退避倍率。
            retry_statuses: 触发重试的 HTTP 状态码集合。
            retry_non_idempotent: 是否允许对非幂等方法重试。
    """

    def __init__(
        self,
        *args: Any,
        retry_attempts: int = 3,
        retry_wait_min: float = 0.2,
        retry_wait_max: float = 2.0,
        retry_wait_multiplier: float = 0.5,
        retry_statuses: Collection[int] = _DEFAULT_RETRY_STATUSES,
        retry_non_idempotent: bool = False,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.retry_attempts = retry_attempts
        self.retry_wait_min = retry_wait_min
        self.retry_wait_max = retry_wait_max
        self.retry_wait_multiplier = retry_wait_multiplier
        self.retry_statuses = frozenset(retry_statuses)
        self.retry_non_idempotent = retry_non_idempotent

    async def request(
        self, method: str, url: str | httpx.URL, *args: Any, **kwargs: Any
    ) -> httpx.Response:
        """发送请求并按策略自动重试。"""
        method_upper = method.upper()
        allow_retry = self.retry_non_idempotent or method_upper in _IDEMPOTENT_METHODS
        if self.retry_attempts <= 1 or not allow_retry:
            return await super().request(method, url, *args, **kwargs)

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.retry_attempts),
                wait=wait_exponential(
                    multiplier=self.retry_wait_multiplier,
                    min=self.retry_wait_min,
                    max=self.retry_wait_max,
                ),
                retry=retry_if_exception(_is_retryable_error),
                reraise=True,
            ):
                with attempt:
                    response = await super().request(method, url, *args, **kwargs)
                    if response.status_code in self.retry_statuses:
                        raise _RetryableStatusError(response)
                    return response
        except _RetryableStatusError as exc:
            return exc.response

        # 理论上不会到达这里，保留兜底以满足类型检查。
        return await super().request(method, url, *args, **kwargs)
