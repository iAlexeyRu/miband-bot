"""测试加密模块 (crypto.py)。

覆盖：RC4、nonce、签名、加密/解密往返。
"""

from __future__ import annotations

import base64
import json

from mi_fitness.crypto import (
    _build_sig_message,
    _rc4_crypt,
    _sha1_b64,
    build_encrypted_params,
    compute_signed_nonce,
    decrypt_data,
    decrypt_response,
    encrypt_data,
    generate_nonce,
)


class TestRC4:
    """RC4 加密/解密测试。"""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """加密后解密应还原明文。"""
        key = b"test_key_123456"
        plaintext = b"Hello, MiSDK!"
        encrypted = _rc4_crypt(key, plaintext)
        decrypted = _rc4_crypt(key, encrypted)
        assert decrypted == plaintext

    def test_different_keys_produce_different_output(self) -> None:
        """不同密钥应产生不同密文。"""
        data = b"same data"
        enc1 = _rc4_crypt(b"key_aaa", data)
        enc2 = _rc4_crypt(b"key_bbb", data)
        assert enc1 != enc2

    def test_empty_data(self) -> None:
        """空数据加密应返回空。"""
        result = _rc4_crypt(b"key", b"")
        assert result == b""

    def test_skip_parameter(self) -> None:
        """skip=0 和 skip=1024 应产生不同结果。"""
        key = b"test"
        data = b"data"
        r1 = _rc4_crypt(key, data, skip=0)
        r2 = _rc4_crypt(key, data, skip=1024)
        assert r1 != r2

    def test_large_data(self) -> None:
        """大数据块也能正确往返。"""
        key = b"large_key"
        data = b"x" * 100_000
        assert _rc4_crypt(key, _rc4_crypt(key, data)) == data


class TestNonce:
    """nonce 生成测试。"""

    def test_nonce_is_base64(self) -> None:
        """nonce 应为有效的 base64 字符串。"""
        nonce = generate_nonce()
        decoded = base64.b64decode(nonce)
        assert len(decoded) == 12  # 8 random + 4 time

    def test_nonce_unique(self) -> None:
        """连续生成的 nonce 应不同（随机部分不同）。"""
        nonces = {generate_nonce() for _ in range(10)}
        assert len(nonces) == 10


class TestSignedNonce:
    """compute_signed_nonce 测试。"""

    def test_deterministic(self, ssecurity: str) -> None:
        """相同输入应产生相同结果。"""
        nonce = generate_nonce()
        r1 = compute_signed_nonce(ssecurity, nonce)
        r2 = compute_signed_nonce(ssecurity, nonce)
        assert r1 == r2

    def test_output_is_base64(self, ssecurity: str) -> None:
        """输出应为有效 base64。"""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        decoded = base64.b64decode(snonce)
        assert len(decoded) == 32  # SHA256


class TestSignature:
    """签名生成测试（纯 SHA1 + Base64）。"""

    def test_sha1_b64_output(self) -> None:
        """SHA1 base64 输出应为 28 字符。"""
        result = _sha1_b64("test message")
        decoded = base64.b64decode(result)
        assert len(decoded) == 20  # SHA1

    def test_sig_msg_format(self) -> None:
        """签名消息应为 METHOD&/path&k=v&signedNonce 格式。"""
        msg = _build_sig_message("GET", "/test/path", {"data": "hello"}, "snonce123")
        assert msg == "GET&/test/path&data=hello&snonce123"

    def test_sig_msg_method_uppercase(self) -> None:
        """方法名应转为大写。"""
        msg = _build_sig_message("get", "/path", {}, "sn")
        assert msg.startswith("GET&")

    def test_sig_msg_adds_leading_slash(self) -> None:
        """路径没有前导 / 时应自动添加。"""
        msg = _build_sig_message("GET", "path", {}, "sn")
        assert "&/path&" in msg

    def test_sig_msg_sorted_params(self) -> None:
        """参数应按 key 字典序排序。"""
        msg = _build_sig_message("GET", "/p", {"z": "1", "a": "2"}, "sn")
        assert msg == "GET&/p&a=2&z=1&sn"


class TestEncryptDecryptData:
    """encrypt_data / decrypt_data 测试。"""

    def test_roundtrip(self, ssecurity: str) -> None:
        """加密后解密应还原。"""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        plaintext = '{"key": "value", "中文": "测试"}'
        encrypted = encrypt_data(snonce, plaintext)
        decrypted = decrypt_data(snonce, encrypted)
        assert decrypted == plaintext

    def test_encrypted_is_base64(self, ssecurity: str) -> None:
        """密文应为 base64 编码。"""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        encrypted = encrypt_data(snonce, "test")
        base64.b64decode(encrypted)  # 不抛异常即可


class TestBuildEncryptedParams:
    """build_encrypted_params 集成测试。"""

    def test_has_required_keys(self, ssecurity: str) -> None:
        """返回应包含 data, _nonce, signature, rc4_hash__。"""
        result = build_encrypted_params(
            "GET",
            "/app/v1/relatives/get_relative_list",
            ssecurity,
            {"relative_uid": 123},
        )
        assert "data" in result
        assert "_nonce" in result
        assert "signature" in result
        assert "rc4_hash__" in result

    def test_no_params_no_data_key(self, ssecurity: str) -> None:
        """无参数时不应有 data 字段。"""
        result = build_encrypted_params(
            "GET",
            "/app/v1/relatives/get_relative_list",
            ssecurity,
        )
        assert "data" not in result
        assert "_nonce" in result

    def test_can_decrypt_own_params(self, ssecurity: str) -> None:
        """能解密自己加密的参数。"""
        params = {"test": "hello", "num": 42}
        result = build_encrypted_params("POST", "/test", ssecurity, params)
        snonce = compute_signed_nonce(ssecurity, result["_nonce"])
        decrypted = decrypt_data(snonce, result["data"])
        parsed = json.loads(decrypted)
        assert parsed == params


class TestDecryptResponse:
    """decrypt_response 集成测试。"""

    def test_roundtrip(self, ssecurity: str) -> None:
        """构造加密响应并解密。"""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        original = {"code": 0, "result": {"data": "test"}}
        encrypted = encrypt_data(snonce, json.dumps(original))
        decrypted = decrypt_response(ssecurity, nonce, encrypted)
        assert decrypted == original

    def test_non_json_returns_string(self, ssecurity: str) -> None:
        """非 JSON 响应应返回字符串。"""
        nonce = generate_nonce()
        snonce = compute_signed_nonce(ssecurity, nonce)
        encrypted = encrypt_data(snonce, "not json at all")
        result = decrypt_response(ssecurity, nonce, encrypted)
        assert result == "not json at all"
