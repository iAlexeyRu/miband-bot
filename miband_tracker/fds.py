# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import base64
import hashlib
import struct
from collections.abc import Callable
from typing import Any

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

FDS_SLEEP_DAILY_TYPE = 8
FDS_ALL_DAY_FILE_TYPE = 0
TIMEZONE_15MIN_LIMIT = 96
SECONDS_PER_15_MINUTES = 900
SLEEP_ASSIST_HEADER_LEN = 4
AES_KEY_LEN = 16
XIAOMI_FDS_AES_IV = b"1234567887654321"
GZIP_MAGIC = b"\x1f\x8b"
ZLIB_MAGICS = (b"\x78\x9c", b"\x78\x01")

# Xiaomi FDS sleep detail payloads are reverse-engineered and parsed as best-effort.
SLEEP_VALID_TYPES = (0, 1, 2, 6, 7, 8, 9, 10, 3, 4, 5)


def normalize_timezone_to_15min(timezone_value: int) -> int:
    # Xiaomi sleep segments already use 15-minute units; token/bootstrap paths may use seconds.
    if abs(timezone_value) <= TIMEZONE_15MIN_LIMIT:
        return int(timezone_value)
    return int(timezone_value / SECONDS_PER_15_MINUTES)


def gen_data_id_key_bytes(
    timestamp: int,
    tz_in_15min: int,
    daily_type: int,
    file_type: int,
    data_type: int = 0,
    sport_type: int = 0,
) -> bytes:
    data_type_byte = (data_type << 7) + (sport_type << 2) + (daily_type << 2) + file_type
    return struct.pack("<IbB", timestamp, tz_in_15min, data_type_byte)


def parse_sleep_assist_info(
    payload: bytes,
    pos: int,
    byte_count: int,
    is_float: bool,
    is_unsigned: bool,
    version: int,
) -> tuple[dict[str, Any] | None, int]:
    if pos + SLEEP_ASSIST_HEADER_LEN > len(payload):
        return None, pos

    interval = struct.unpack_from("<h", payload, pos)[0]
    record_count = struct.unpack_from("<h", payload, pos + 2)[0]
    pos += SLEEP_ASSIST_HEADER_LEN

    if record_count <= 0:
        return None, pos

    actual_byte_count = byte_count * record_count
    if version >= 2:
        actual_byte_count += 4

    if pos + actual_byte_count > len(payload):
        return None, pos

    start_time = 0
    if version >= 2:
        start_time = struct.unpack_from("<I", payload, pos)[0]
        pos += 4

    values: list[int | float | bytes] = []
    for _ in range(record_count):
        if byte_count == 1:
            value = payload[pos]
            pos += 1
        elif byte_count == 2:
            value = struct.unpack_from("<H" if is_unsigned else "<h", payload, pos)[0]
            pos += 2
        elif byte_count == 4:
            if is_float:
                value = struct.unpack_from("<f", payload, pos)[0]
            else:
                value = struct.unpack_from("<I" if is_unsigned else "<i", payload, pos)[0]
            pos += 4
        else:
            value = payload[pos : pos + byte_count]
            pos += byte_count
        values.append(value)

    return {
        "start_time": start_time,
        "interval": interval,
        "record_count": record_count,
        "values": values,
    }, pos


def parse_all_day_sleep_bytes(payload: bytes) -> dict[str, Any] | None:
    if len(payload) < 9:
        return None

    try:
        return _parse_all_day_sleep_bytes(payload)
    except (IndexError, struct.error):
        return None


def _parse_all_day_sleep_bytes(payload: bytes) -> dict[str, Any]:
    _ = struct.unpack_from("<I", payload, 0)[0]
    _ = payload[4]
    version = payload[5]
    _ = payload[6]

    data_valid = payload[7:9]

    valid_map = {}
    for index, valid_type in enumerate(SLEEP_VALID_TYPES):
        byte_idx = index // 8
        bit_idx = index % 8
        valid_map[valid_type] = (data_valid[byte_idx] & (1 << (7 - bit_idx))) > 0

    pos = 9
    report_data = {"sleepFinish": payload[pos] == 1}
    pos += 1

    report_data["deviceBedTime"] = struct.unpack_from("<I", payload, pos)[0]
    pos += 4

    report_data["deviceWakeupTime"] = struct.unpack_from("<I", payload, pos)[0]
    pos += 4

    value = payload[pos]
    if valid_map[2]:
        report_data["sleepQuality"] = value
    pos += 1

    value = payload[pos]
    if valid_map[6]:
        report_data["sleepEfficiency"] = value
    pos += 1

    value = struct.unpack_from("<I", payload, pos)[0]
    if valid_map[7]:
        report_data["entrySleepDuration"] = value
    pos += 4

    value = struct.unpack_from("<I", payload, pos)[0]
    if valid_map[8]:
        report_data["linBedDuration"] = value
    pos += 4

    value = struct.unpack_from("<I", payload, pos)[0]
    if valid_map[9]:
        report_data["goBedTime"] = value
    pos += 4

    value = struct.unpack_from("<I", payload, pos)[0]
    if valid_map[10]:
        report_data["leaveBedTime"] = value
    pos += 4

    records: dict[str, list[tuple[int, int | float | bytes]]] = {
        "heart_rate": [],
        "spo2": [],
    }

    if valid_map[3]:
        hr_data, pos = parse_sleep_assist_info(payload, pos, 1, False, False, version)
        if hr_data:
            start_time = int(hr_data["start_time"])
            interval = int(hr_data["interval"])
            for index, value in enumerate(hr_data["values"]):
                if isinstance(value, int) and 0 < value < 255:
                    records["heart_rate"].append((start_time + index * interval, value))

    if valid_map[4]:
        spo2_data, pos = parse_sleep_assist_info(payload, pos, 1, False, False, version)
        if spo2_data:
            start_time = int(spo2_data["start_time"])
            interval = int(spo2_data["interval"])
            for index, value in enumerate(spo2_data["values"]):
                if isinstance(value, int) and 0 < value <= 100:
                    records["spo2"].append((start_time + index * interval, value))

    return {
        "report": report_data,
        "records": records,
    }


async def download_and_decrypt_sleep_details(
    client: Any,
    relative_uid: int,
    timestamp: int,
    timezone_value: int,
    log_fn: Callable[[str], object] = print,
) -> bytes | None:
    tz_in_15min = normalize_timezone_to_15min(timezone_value)

    sid = str(relative_uid)
    key_bytes = gen_data_id_key_bytes(
        timestamp,
        tz_in_15min,
        daily_type=FDS_SLEEP_DAILY_TYPE,
        file_type=FDS_ALL_DAY_FILE_TYPE,
    )
    suffix_b64 = base64.urlsafe_b64encode(key_bytes).decode().rstrip("=")

    sha1_sid = hashlib.sha1(sid.encode()).digest()
    sha1_b64 = base64.urlsafe_b64encode(sha1_sid).decode().rstrip("=")
    suffix = f"{suffix_b64}_{sha1_b64}"

    param_dict = {
        "did": sid,
        "relative_uid": relative_uid,
        "items": [
            {
                "timestamp": timestamp,
                "suffix": suffix,
            }
        ],
    }

    resp = await client._request(
        "GET",
        "/healthapp/service/gen_download_url",
        params=param_dict,
    )

    result = resp.get("result", {})
    log_fn(
        "gen_download_url returned "
        f"code={resp.get('code')} message={resp.get('message')} "
        f"result_keys_count={len(result)}"
    )
    server_key = f"{suffix}_{timestamp}"
    file_info = result.get(server_key)
    if not file_info:
        log_fn("No FDS info found for requested sleep segment.")
        return None

    url = file_info.get("url")
    obj_key_b64 = file_info.get("obj_key")
    if not url:
        log_fn("FDS info missing download URL.")
        return None

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        file_resp = await http_client.get(url)
        if file_resp.status_code != 200:
            log_fn(f"Optional FDS sleep detail unavailable: HTTP {file_resp.status_code}; skipping.")
            return None

        enc_content = file_resp.content

    log_fn(f"Downloaded FDS content length: {len(enc_content)}")

    if obj_key_b64:
        try:
            encrypted_bytes = android_base64_urlsafe(enc_content)
            obj_key_bytes = android_base64_urlsafe(obj_key_b64)

            if len(obj_key_bytes) != AES_KEY_LEN:
                log_fn(f"Invalid obj_key length: {len(obj_key_bytes)}")
                return None

            cipher = AES.new(obj_key_bytes, AES.MODE_CBC, XIAOMI_FDS_AES_IV)
            decrypted = cipher.decrypt(encrypted_bytes)
            return unpad(decrypted, AES.block_size)
        except Exception as exc:
            log_fn(f"AES decryption or unpadding failed: {exc}")
            return None

    log_fn("No obj_key in file_info. Checking if content is compressed (gzip/zlib) or raw...")
    return decompress_or_raw_fds_content(enc_content, log_fn)


def android_base64_urlsafe(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    value = value.strip().replace("\n", "").replace("\r", "")
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value)


def decompress_or_raw_fds_content(content: bytes, log_fn: Callable[[str], object] = print) -> bytes:
    if content.startswith(GZIP_MAGIC):
        try:
            import gzip

            decompressed = gzip.decompress(content)
            log_fn(f"Successfully decompressed GZIP FDS content. Length: {len(decompressed)}")
            return decompressed
        except Exception as exc:
            log_fn(f"Failed to decompress GZIP FDS content: {exc}")

    elif content.startswith(ZLIB_MAGICS):
        try:
            import zlib

            decompressed = zlib.decompress(content)
            log_fn(f"Successfully decompressed ZLIB FDS content. Length: {len(decompressed)}")
            return decompressed
        except Exception as exc:
            log_fn(f"Failed to decompress ZLIB FDS content: {exc}")

    return content
