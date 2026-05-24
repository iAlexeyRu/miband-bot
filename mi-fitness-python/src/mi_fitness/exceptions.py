"""自定义异常。"""


class MiSDKError(Exception):
    """MiSDK 基础异常。"""


class AuthError(MiSDKError):
    """认证相关错误（登录失败、token 过期等）。"""


class APIError(MiSDKError):
    """API 请求返回非预期结果。

    Attributes:
        status_code: HTTP 状态码。
        code: 业务错误码（``result["code"]``，仅业务层错误时有值）。
        response_body: 原始响应体。
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        code: int = 0,
        response_body: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.response_body = response_body

    def __repr__(self) -> str:
        return f"APIError(status_code={self.status_code}, code={self.code}, message={str(self)!r})"


class DeviceUntrustedError(AuthError):
    """设备未信任，需要短信验证码完成登录。

    新设备首次登录时触发 ``securityStatus != 0``，需要通过短信验证码
    完成身份验证。可通过 ``login(verification_code_handler=...)`` 自动
    处理，或手动调用 ``send_verification_code()`` +
    ``login_with_verification_code()``。

    Attributes:
        security_status: 服务端返回的安全状态码。
    """

    def __init__(self, message: str, *, security_status: int = 0):
        super().__init__(message)
        self.security_status = security_status


class CaptchaRequiredError(AuthError):
    """触发图形验证码风控，需要人工识别通过。

    在登录流程中服务端可能要求完成图形验证码验证（错误码 87001）。
    可通过 ``login(captcha_handler=...)`` 自动处理，
    或捕获此异常后自行下载 ``captcha_url`` 的验证码图片并重试。

    Attributes:
        captcha_url: 验证码图片完整 URL。
    """

    def __init__(self, message: str, *, captcha_url: str = ""):
        super().__init__(message)
        self.captcha_url = captcha_url


class TokenExpiredError(AuthError):
    """Token 已过期，需要重新登录。"""


class DataNotSharedError(MiSDKError):
    """亲友未共享当前请求的数据类型。"""

    def __init__(self, message: str, *, data_type: str = ""):
        super().__init__(message)
        self.data_type = data_type


class DataOutOfSharedTimeScopeError(DataNotSharedError):
    """请求日期超出亲友允许共享的时间范围。"""


class FamilyMemberNotFoundError(MiSDKError):
    """找不到指定的亲友。"""
