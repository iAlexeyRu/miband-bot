"""测试异常类 (exceptions.py)。"""

from __future__ import annotations

from mi_fitness.exceptions import (
    APIError,
    AuthError,
    CaptchaRequiredError,
    DataNotSharedError,
    DataOutOfSharedTimeScopeError,
    FamilyMemberNotFoundError,
    MiSDKError,
    TokenExpiredError,
)


class TestExceptionHierarchy:
    """异常继承关系测试。"""

    def test_base_exception(self) -> None:
        e = MiSDKError("test")
        assert str(e) == "test"
        assert isinstance(e, Exception)

    def test_auth_error_inherits(self) -> None:
        e = AuthError("auth fail")
        assert isinstance(e, MiSDKError)

    def test_token_expired_inherits_auth(self) -> None:
        e = TokenExpiredError("expired")
        assert isinstance(e, AuthError)
        assert isinstance(e, MiSDKError)

    def test_api_error_attributes(self) -> None:
        e = APIError(
            "api fail",
            status_code=500,
            code=1001,
            response_body='{"error": true}',
        )
        assert isinstance(e, MiSDKError)
        assert e.status_code == 500
        assert e.code == 1001
        assert e.response_body == '{"error": true}'
        assert str(e) == "api fail"

    def test_api_error_defaults(self) -> None:
        e = APIError("msg")
        assert e.status_code == 0
        assert e.code == 0
        assert e.response_body == ""

    def test_family_member_not_found(self) -> None:
        e = FamilyMemberNotFoundError("未找到")
        assert isinstance(e, MiSDKError)

    def test_captcha_required_inherits_auth(self) -> None:
        e = CaptchaRequiredError("需要验证码")
        assert isinstance(e, AuthError)
        assert isinstance(e, MiSDKError)

    def test_captcha_required_url(self) -> None:
        url = "https://account.xiaomi.com/pass/getCode?icodeType=login"
        e = CaptchaRequiredError("验证码风控", captcha_url=url)
        assert e.captcha_url == url
        assert str(e) == "验证码风控"

    def test_captcha_required_default_url(self) -> None:
        e = CaptchaRequiredError("msg")
        assert e.captcha_url == ""

    def test_data_not_shared_error(self) -> None:
        e = DataNotSharedError("未共享", data_type="heart_rate")
        assert isinstance(e, MiSDKError)
        assert e.data_type == "heart_rate"

    def test_time_scope_error_inherits_data_not_shared(self) -> None:
        e = DataOutOfSharedTimeScopeError("超出范围", data_type="steps")
        assert isinstance(e, DataNotSharedError)
        assert e.data_type == "steps"
