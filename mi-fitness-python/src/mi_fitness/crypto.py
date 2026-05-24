"""小米云服务加密模块。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import time
from typing import Any


def _rc4_crypt(key: bytes, data: bytes, *, skip: int = 1024) -> bytes:
    """RC4 加密/解密（带前 N 字节跳过，防止密钥流弱点）。

    Args:
        key: RC4 密钥。
        data: 待加密/解密的数据。
        skip: 跳过前 N 字节的密钥流（默认 1024）。

    Returns:
        加密/解密后的字节数据。
    """
    s = list(range(256))
    j = 0

    # KSA (Key-Scheduling Algorithm)
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]

    # PRGA (Pseudo-Random Generation Algorithm)
    i = 0
    j = 0

    # 跳过前 skip 字节密钥流
    for _ in range(skip):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]

    # 加密/解密
    result = bytearray(len(data))
    for idx in range(len(data)):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        result[idx] = data[idx] ^ s[(s[i] + s[j]) & 0xFF]

    return bytes(result)


def generate_nonce() -> str:
    """生成请求 nonce。

    格式: base64(random_8_bytes + minutes_since_epoch_4bytes_BE)

    Returns:
        Base64 编码的 nonce 字符串。
    """
    random_part = os.urandom(8)
    minutes = int(time.time() / 60)
    time_part = struct.pack(">I", minutes)
    return base64.b64encode(random_part + time_part).decode()


def compute_signed_nonce(ssecurity: str, nonce: str) -> str:
    """计算签名 nonce（用于密钥派生）。

    signed_nonce = base64(SHA256(b64decode(ssecurity) + b64decode(nonce)))

    Args:
        ssecurity: 登录时获取的 ssecurity（base64 编码）。
        nonce: 请求 nonce。

    Returns:
        Base64 编码的 signed_nonce（同时作为 RC4 和 HMAC 的密钥）。
    """
    hash_val = hashlib.sha256(base64.b64decode(ssecurity) + base64.b64decode(nonce)).digest()
    return base64.b64encode(hash_val).decode()


# endregion


# region 签名生成
def _sha1_b64(message: str) -> str:
    """纯 SHA1 哈希 → Base64 编码。

    App 使用 MessageDigest("SHA1") 而非 HMAC 来生成签名。

    Args:
        message: 待哈希的 UTF-8 字符串。

    Returns:
        Base64 编码的 SHA1 摘要（28 字符）。
    """
    digest = hashlib.sha1(message.encode("utf-8")).digest()
    return base64.b64encode(digest).decode()


def _build_sig_message(
    method: str,
    url_path: str,
    params: dict[str, str],
    signed_nonce: str,
) -> str:
    """构建签名消息字符串（z94.b 格式）。

    格式: METHOD&/path&k1=v1&k2=v2&...&signedNonce_b64
    - method 大写
    - path 带前导 /
    - params 按 key 字典序（TreeMap）排序
    - 最后追加 signedNonce 的 base64 字符串

    Args:
        method: HTTP 方法。
        url_path: URL 路径（须含前导 /）。
        params: 参数字典（已排除空 key/value）。
        signed_nonce: Base64 编码的 signed_nonce。

    Returns:
        用 & 连接的签名消息。
    """
    parts: list[str] = [method.upper()]
    if not url_path.startswith("/"):
        url_path = "/" + url_path
    parts.append(url_path)
    for k in sorted(params.keys()):
        parts.append(f"{k}={params[k]}")
    parts.append(signed_nonce)
    return "&".join(parts)


def _rc4_stream_encrypt_values(
    key_bytes: bytes,
    sorted_entries: list[tuple[str, str]],
) -> dict[str, str]:
    """用连续 RC4 流加密多个值。

    模拟 App 中 d8k 的行为：构造时 drop 1024 字节，
    然后对 TreeMap 中每个 entry 的 value 按排序顺序
    依次加密，共用同一个 RC4 密钥流。

    Args:
        key_bytes: RC4 密钥（signed_nonce 的原始字节）。
        sorted_entries: 按 key 排序的 (key, value) 对列表。

    Returns:
        {key: base64(encrypted_value)} 字典。
    """
    # 将所有 value 拼接，一次性过 RC4 流
    all_bytes = b"".join(v.encode("utf-8") for _, v in sorted_entries)
    encrypted_all = _rc4_crypt(key_bytes, all_bytes, skip=1024)

    result: dict[str, str] = {}
    pos = 0
    for k, v in sorted_entries:
        vlen = len(v.encode("utf-8"))
        result[k] = base64.b64encode(encrypted_all[pos : pos + vlen]).decode()
        pos += vlen
    return result


# endregion


# region 数据加密/解密
def encrypt_data(signed_nonce: str, plaintext: str) -> str:
    """用 RC4 加密数据。

    Args:
        signed_nonce: 密钥（base64 编码的 SHA256 哈希）。
        plaintext: 明文 JSON 字符串。

    Returns:
        Base64 编码的密文。
    """
    key = base64.b64decode(signed_nonce)
    encrypted = _rc4_crypt(key, plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode()


def decrypt_data(signed_nonce: str, ciphertext_b64: str) -> str:
    """用 RC4 解密数据。

    Args:
        signed_nonce: 密钥（base64 编码的 SHA256 哈希）。
        ciphertext_b64: Base64 编码的密文。

    Returns:
        解密后的明文字符串。
    """
    key = base64.b64decode(signed_nonce)
    decrypted = _rc4_crypt(key, base64.b64decode(ciphertext_b64))
    return decrypted.decode("utf-8")


# endregion


# region 封装：构建加密请求参数
def build_encrypted_params(
    method: str,
    url_path: str,
    ssecurity: str,
    params: dict[str, Any] | None = None,
) -> dict[str, str]:
    """构建完整的加密请求参数。

    流程（对应 App 中 ua4.c 方法）:
      1. 计算 signed_nonce = base64(SHA256(ssecurity + nonce))
      2. 构建原始参数 TreeMap（排除空 key/value）
      3. rc4_hash__ = SHA1(METHOD&/path&k=v&...&signedNonce) → base64
      4. 将 rc4_hash__ 加入 TreeMap
      5. 用连续 RC4 流加密所有 TreeMap 值（按 key 排序，drop 1024）
      6. signature = SHA1(METHOD&/path&k=enc_v&...&signedNonce) → base64
      7. 返回 {加密后各参数, signature, _nonce}

    Args:
        method: HTTP 方法。
        url_path: API 路径（如 /app/v1/relatives/get_relative_list）。
        ssecurity: 登录时获取的 ssecurity。
        params: 要发送的参数字典（将被 JSON 序列化后加密）。

    Returns:
        包含 data, signature, rc4_hash__, _nonce 的参数字典。
    """
    nonce = generate_nonce()
    snonce = compute_signed_nonce(ssecurity, nonce)
    snonce_bytes = base64.b64decode(snonce)

    # Step 1: 构建原始参数 TreeMap（排除空 key/value）
    raw_tree: dict[str, str] = {}
    if params:
        plaintext = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
        raw_tree["data"] = plaintext

    # Step 2: 计算 rc4_hash__（基于原始参数）
    rc4_msg = _build_sig_message(method, url_path, raw_tree, snonce)
    rc4_hash_raw = _sha1_b64(rc4_msg)

    # Step 3: 将 rc4_hash__ 插入 TreeMap
    raw_tree["rc4_hash__"] = rc4_hash_raw

    # Step 4: 用连续 RC4 流加密所有值
    sorted_entries = sorted(raw_tree.items())
    encrypted_values = _rc4_stream_encrypt_values(snonce_bytes, sorted_entries)

    # Step 5: 构建加密后参数 TreeMap，计算 signature
    sig_msg = _build_sig_message(method, url_path, encrypted_values, snonce)
    signature = _sha1_b64(sig_msg)

    # Step 6: 组装最终结果
    result: dict[str, str] = {}
    for k, v in encrypted_values.items():
        result[k] = v
    result["signature"] = signature
    result["_nonce"] = nonce
    return result


def decrypt_response(
    ssecurity: str,
    nonce: str,
    ciphertext_b64: str,
) -> Any:
    """解密 API 响应。

    Args:
        ssecurity: 登录时获取的 ssecurity。
        nonce: 请求时使用的 nonce。
        ciphertext_b64: Base64 编码的响应密文。

    Returns:
        解密后的 JSON 对象。
    """
    snonce = compute_signed_nonce(ssecurity, nonce)
    plaintext = decrypt_data(snonce, ciphertext_b64)

    try:
        return json.loads(plaintext)
    except json.JSONDecodeError:
        # 可能不是 JSON，返回原始字符串
        return plaintext


# endregion
