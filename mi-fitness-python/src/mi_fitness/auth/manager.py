"""小米账号认证管理器。

负责编排登录流程、token 持久化。具体登录实现委托给
``password``、``qr``、``passtoken`` 等子模块。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Self, TypeVar

from loguru import logger

from mi_fitness.exceptions import (
    AuthError,
    CaptchaRequiredError,
    DeviceUntrustedError,
    TokenExpiredError,
)
from mi_fitness.http import RetryAsyncClient
from mi_fitness.models import AuthToken

from . import passtoken as _pt
from . import password as _pwd
from . import qr as _qr
from . import sts as _sts
from ._helpers import create_login_http

_MAX_CAPTCHA_RETRIES = 3
_CaptchaStepT = TypeVar("_CaptchaStepT")


def _write_secret_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


class XiaomiAuth:
    """小米账号认证管理器。

    负责登录流程、token 持久化。通过 serviceLogin 获取 ssecurity
    和 serviceToken，后续 API 请求使用 RC4 加密。

    Attributes:
        username: 小米账号（手机号或邮箱）。
        token: 当前认证凭证。
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        *,
        device_id: str = "",
    ):
        """
        Args:
            username: 小米账号。
            password: 密码（仅登录时需要，不会被存储）。
            device_id: 设备标识符。留空则自动生成随机值。新设备首次登录
                会触发短信验证码验证，可通过 ``login()`` 的
                ``verification_code_handler`` 回调自动处理。
        """
        self.username = username
        self._password = password
        self.token = AuthToken()
        if device_id:
            self.token.device_id = device_id
        self._http: RetryAsyncClient | None = None
        self._ticket_token: str = ""
        self._token_path: Path | None = None

    @classmethod
    def from_token(cls, path: Path | str) -> Self:
        """从文件加载已有 token，一步完成初始化。

        Args:
            path: token 文件路径。

        Returns:
            已加载 token 的认证管理器。

        Raises:
            AuthError: 文件不存在或格式错误。
        """
        instance = cls()
        instance.load_token(path)
        return instance

    def _ensure_http(self) -> RetryAsyncClient:
        """确保 HTTP 客户端已初始化（惰性创建）。"""
        if self._http is None:
            self._http = create_login_http()
        return self._http

    def _ensure_device_cookie(self) -> RetryAsyncClient:
        """确保 deviceId 已生成并写入登录 cookie。"""
        http = self._ensure_http()
        if not self.token.device_id:
            self.token.device_id = f"an_{os.urandom(16).hex()}"
        http.cookies.set("deviceId", self.token.device_id)
        return http

    async def _run_with_captcha_retries(
        self,
        http: RetryAsyncClient,
        action: Callable[[str], Awaitable[_CaptchaStepT]],
        *,
        captcha_handler: Callable[[bytes], Awaitable[str]] | None = None,
    ) -> _CaptchaStepT:
        """统一处理图形验证码重试。"""
        captcha_code = ""
        for _ in range(_MAX_CAPTCHA_RETRIES):
            try:
                return await action(captcha_code)
            except CaptchaRequiredError as e:
                if captcha_handler is None:
                    raise
                image = await _pwd.fetch_captcha_image(http, e.captcha_url)
                captcha_code = await captcha_handler(image)
        raise AuthError(f"图形验证码验证失败：已连续重试 {_MAX_CAPTCHA_RETRIES} 次")

    # region 公共方法
    async def login(
        self,
        *,
        verification_code_handler: Callable[[str], Awaitable[str]] | None = None,
        captcha_handler: Callable[[bytes], Awaitable[str]] | None = None,
    ) -> AuthToken:
        """执行完整登录流程。

        Args:
            verification_code_handler: 短信验证码回调。接收脱敏手机号
                （如 ``"191******54"``），返回用户输入的 6 位验证码。
                新设备首次登录需要短信验证时自动调用。
                若未提供且需要验证，将抛出 ``DeviceUntrustedError``。
            captcha_handler: 图形验证码回调。接收验证码图片字节
                （PNG/JPEG），返回用户识别的验证码文本。
                当登录流程触发图形验证码风控时自动调用。
                若未提供且需要验证码，将抛出 ``CaptchaRequiredError``。

        Returns:
            登录成功后的 AuthToken。

        Raises:
            AuthError: 登录失败（密码错误等）。
            DeviceUntrustedError: 需要短信验证但未提供回调。
            CaptchaRequiredError: 需要图形验证码但未提供回调。
        """
        if not self.username or not self._password:
            raise AuthError("用户名和密码不能为空")

        http = self._ensure_device_cookie()

        logger.info("开始小米账号登录: {}", self.username)

        sign, callback = await _pwd.get_login_page(http)

        try:
            await _pwd.submit_login(
                http,
                self.token,
                self.username,
                self._password,
                sign,
                callback,
            )
        except DeviceUntrustedError:
            if verification_code_handler is None:
                raise
            phone = await self.send_verification_code(
                captcha_handler=captcha_handler,
            )
            code = await verification_code_handler(phone)
            await self.login_with_verification_code(code)
            return self.token

        await _sts.sts_exchange(http, self.token)

        self._password = ""
        logger.info("登录成功, user_id={}", self.token.user_id)
        return self.token

    def save_token(self, path: Path | str) -> None:
        """将 token 保存到 JSON 文件，便于下次免登录恢复。

        Args:
            path: 保存路径。
        """
        path = Path(path)
        _write_secret_text(path, self.token.model_dump_json(indent=2) + "\n")
        self._token_path = path
        logger.info("Token 已保存至 {}", path)

    def load_token(self, path: Path | str) -> AuthToken:
        """从文件加载 token。

        Args:
            path: token 文件路径。

        Returns:
            加载的 AuthToken。

        Raises:
            AuthError: 文件不存在或格式错误。
        """
        path = Path(path)
        if not path.exists():
            raise AuthError(f"Token 文件不存在: {path}")
        try:
            data = path.read_text(encoding="utf-8")
            self.token = AuthToken.model_validate_json(data)
            self._token_path = path
            logger.info("Token 已从 {} 加载, user_id={}", path, self.token.user_id)
            return self.token
        except Exception as e:
            raise AuthError(f"Token 文件解析失败: {e}") from e

    @property
    def is_authenticated(self) -> bool:
        """检查是否已登录。"""
        return bool(self.token.service_token and self.token.ssecurity)

    @property
    def can_refresh(self) -> bool:
        """当前 token 是否具备自动刷新条件。"""
        return bool(self.token.pass_token and self.token.user_id)

    async def close(self) -> None:
        """关闭 HTTP 客户端（如有）。"""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def refresh(self) -> AuthToken:
        """用已有 passToken 刷新 serviceToken / ssecurity。

        Returns:
            刷新后的 AuthToken。

        Raises:
            TokenExpiredError: 当前 token 无法刷新，或刷新失败。
        """
        if not self.can_refresh:
            raise TokenExpiredError("Token 已过期，且缺少 passToken 或 user_id，无法自动刷新")

        logger.info("开始刷新登录凭证, user_id={}", self.token.user_id)
        try:
            token = await self.login_passtoken(
                pass_token=self.token.pass_token,
                user_id=self.token.user_id,
                device_id=self.token.device_id,
            )
        except AuthError as e:
            raise TokenExpiredError(f"Token 已过期，自动刷新失败: {e}") from e

        if self._token_path is not None:
            self.save_token(self._token_path)

        logger.info("登录凭证刷新成功, user_id={}", token.user_id)
        return token

    async def send_verification_code(
        self,
        *,
        captcha_handler: Callable[[bytes], Awaitable[str]] | None = None,
    ) -> str:
        """发送短信验证码到用户手机。

        在 ``login()`` 抛出 ``DeviceUntrustedError`` 后调用此方法
        手动发起短信验证流程。

        Args:
            captcha_handler: 图形验证码回调。接收验证码图片字节，
                返回用户识别的验证码文本。未提供时触发验证码将直接抛出
                ``CaptchaRequiredError``。

        Returns:
            脱敏手机号（如 ``"191******54"``）。

        Raises:
            AuthError: 获取手机信息或发送验证码失败。
            CaptchaRequiredError: 需要图形验证码但未提供回调。
        """
        http = self._ensure_http()
        await _pwd.ensure_ticket_login_ready(http)

        await self._run_with_captcha_retries(
            http,
            lambda captcha_code: _pwd.send_ticket(
                http,
                self.username,
                captcha_code=captcha_code,
            ),
            captcha_handler=captcha_handler,
        )
        phone, ticket_token = await self._run_with_captcha_retries(
            http,
            lambda captcha_code: _pwd.get_phone_info(
                http,
                self.username,
                captcha_code=captcha_code,
            ),
            captcha_handler=captcha_handler,
        )

        self._ticket_token = ticket_token
        logger.info("验证码已发送至 {}", phone)
        return phone

    async def login_with_verification_code(self, code: str) -> AuthToken:
        """使用短信验证码完成登录。

        在 ``send_verification_code()`` 之后调用，提交用户收到的验证码。

        Args:
            code: 6 位短信验证码。

        Returns:
            登录成功后的 AuthToken。

        Raises:
            AuthError: 验证码错误或登录失败。
        """
        if not self._ticket_token:
            raise AuthError("请先调用 send_verification_code() 发送验证码")

        http = self._ensure_http()
        http.cookies.set("ticketToken", self._ticket_token)

        sign, callback = await _pwd.get_login_page(http, login_sign="ticket")
        await _pwd.submit_ticket_auth(http, self.token, code, sign, callback)
        await _sts.sts_exchange(http, self.token)

        self._password = ""
        self._ticket_token = ""
        logger.info("短信验证码登录成功, user_id={}", self.token.user_id)
        return self.token

    def __repr__(self) -> str:
        status = "已认证" if self.is_authenticated else "未认证"
        uid = self.token.user_id or "N/A"
        return f"XiaomiAuth(user={self.username or uid!r}, {status})"

    async def login_qr(
        self,
        *,
        qr_callback: Callable[[str, str], Awaitable[None]] | None = None,
        poll_interval: float = 2.0,
        max_wait: float = 300.0,
    ) -> AuthToken:
        """二维码扫码登录（无需密码，绕过验证码风控）。

        用户用小米账号 APP 扫描二维码完成登录，SDK 通过长轮询
        检测扫码结果并自动提取凭证。

        Args:
            qr_callback: 二维码展示回调。接收 ``(qr_image_url, login_url)``，
                其中 ``qr_image_url`` 是二维码图片 URL（可下载显示），
                ``login_url`` 是备选的浏览器登录链接。
                默认将信息打印到控制台。
            poll_interval: 长轮询间隔（秒）。
            max_wait: 扫码超时时间（秒）。

        Returns:
            登录成功后的 AuthToken。

        Raises:
            AuthError: 获取二维码失败或扫码超时。
        """
        http = self._ensure_device_cookie()

        await _qr.login_qr(
            http,
            self.token,
            qr_callback=qr_callback,
            poll_interval=poll_interval,
            max_wait=max_wait,
        )

        await _sts.sts_exchange(http, self.token)

        logger.info("二维码登录成功, user_id={}", self.token.user_id)
        return self.token

    async def login_passtoken(
        self,
        *,
        pass_token: str = "",
        user_id: str = "",
        device_id: str = "",
    ) -> AuthToken:
        """使用 passToken 换取完整登录凭证（无需密码）。

        passToken 可通过 ``migate.get_passtoken()`` 或浏览器登录小米账号
        后从 Cookie 中提取获取。此方法用 passToken 调用 ``serviceLogin``
        换取 ``ssecurity`` 和 ``serviceToken``。

        Args:
            pass_token: 小米账号 passToken。
            user_id: 小米账号 userId。
            device_id: 设备标识符（可选）。

        Returns:
            登录成功后的 AuthToken。

        Raises:
            AuthError: passToken 无效或换取凭证失败。
        """
        http = self._ensure_http()

        await _pt.login_passtoken(
            http,
            self.token,
            pass_token=pass_token,
            user_id=user_id,
            device_id=device_id,
        )

        await _sts.sts_exchange(http, self.token)

        logger.info("passToken 登录成功, user_id={}", self.token.user_id)
        return self.token

    # endregion

    # region 上下文管理器
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # endregion
