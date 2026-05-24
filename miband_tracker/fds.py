from __future__ import annotations

import base64
import hashlib
import struct

import httpx
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def normalize_timezone_to_15min(timezone_value: int) -> int:
    # Xiaomi sleep segments already use 15-minute units; token/bootstrap paths may use seconds.
    if abs(timezone_value) <= 96:
        return int(timezone_value)
    return int(timezone_value / 900)

def gen_data_id_key_bytes(timestamp: int, tz_in_15min: int, daily_type: int, file_type: int, data_type: int = 0, sport_type: int = 0) -> bytes:
    data_type_byte = (data_type << 7) + (sport_type << 2) + (daily_type << 2) + file_type
    return struct.pack("<IbB", timestamp, tz_in_15min, data_type_byte)

def parse_sleep_assist_info(b, pos, byte_count, is_float, is_unsigned, version):
    if pos + 4 > len(b):
        return None, pos
    
    interval = struct.unpack_from("<h", b, pos)[0]
    record_count = struct.unpack_from("<h", b, pos + 2)[0]
    pos += 4
    
    if record_count <= 0:
        return None, pos
        
    actual_byte_count = byte_count * record_count
    if version >= 2:
        actual_byte_count += 4
        
    if pos + actual_byte_count > len(b):
        return None, pos
        
    start_time = 0
    if version >= 2:
        start_time = struct.unpack_from("<I", b, pos)[0]
        pos += 4
        
    values = []
    for _ in range(record_count):
        if byte_count == 1:
            val = b[pos]
            pos += 1
        elif byte_count == 2:
            val = struct.unpack_from("<H" if is_unsigned else "<h", b, pos)[0]
            pos += 2
        elif byte_count == 4:
            if is_float:
                val = struct.unpack_from("<f", b, pos)[0]
            else:
                val = struct.unpack_from("<I" if is_unsigned else "<i", b, pos)[0]
            pos += 4
        else:
            val = b[pos:pos+byte_count]
            pos += byte_count
        values.append(val)
        
    return {
        "start_time": start_time,
        "interval": interval,
        "record_count": record_count,
        "values": values
    }, pos

def parse_all_day_sleep_bytes(b: bytes):
    if len(b) < 9:
        return None

    try:
        return _parse_all_day_sleep_bytes(b)
    except (IndexError, struct.error):
        return None


def _parse_all_day_sleep_bytes(b: bytes):
    _ = struct.unpack_from("<I", b, 0)[0]
    _ = b[4]
    version = b[5]
    _ = b[6]
    
    data_valid = b[7:9]
    
    valid_map = {}
    i = 0
    types_to_check = [0, 1, 2, 6, 7, 8, 9, 10, 3, 4, 5]
    for t in types_to_check:
        byte_idx = i // 8
        bit_idx = i % 8
        val = (data_valid[byte_idx] & (1 << (7 - bit_idx))) > 0
        valid_map[t] = val
        i += 1
        
    pos = 9
    report_data = {
        "sleepFinish": bool(b[pos] == 1)
    }
    pos += 1
    
    # type=0 (deviceBedTime)
    report_data["deviceBedTime"] = struct.unpack_from("<I", b, pos)[0]
    pos += 4
    
    # type=1 (deviceWakeupTime)
    report_data["deviceWakeupTime"] = struct.unpack_from("<I", b, pos)[0]
    pos += 4
    
    # type=2 (sleepQuality)
    val = b[pos]
    if valid_map[2]:
        report_data["sleepQuality"] = val
    pos += 1
    
    # type=6 (sleepEfficiency)
    val = b[pos]
    if valid_map[6]:
        report_data["sleepEfficiency"] = val
    pos += 1
    
    # type=7 (entrySleepDuration)
    val = struct.unpack_from("<I", b, pos)[0]
    if valid_map[7]:
        report_data["entrySleepDuration"] = val
    pos += 4
    
    # type=8 (linBedDuration)
    val = struct.unpack_from("<I", b, pos)[0]
    if valid_map[8]:
        report_data["linBedDuration"] = val
    pos += 4
    
    # type=9 (goBedTime)
    val = struct.unpack_from("<I", b, pos)[0]
    if valid_map[9]:
        report_data["goBedTime"] = val
    pos += 4
    
    # type=10 (leaveBedTime)
    val = struct.unpack_from("<I", b, pos)[0]
    if valid_map[10]:
        report_data["leaveBedTime"] = val
    pos += 4
    
    records = {
        "heart_rate": [],
        "spo2": []
    }
    
    # type 3: hr
    if valid_map[3]:
        hr_data, pos = parse_sleep_assist_info(b, pos, 1, False, False, version)
        if hr_data:
            start_t = hr_data["start_time"]
            interval = hr_data["interval"]
            for idx, val in enumerate(hr_data["values"]):
                if val > 0 and val < 255:
                    records["heart_rate"].append((start_t + idx * interval, val))
                
    # type 4: spo2
    if valid_map[4]:
        spo2_data, pos = parse_sleep_assist_info(b, pos, 1, False, False, version)
        if spo2_data:
            start_t = spo2_data["start_time"]
            interval = spo2_data["interval"]
            for idx, val in enumerate(spo2_data["values"]):
                if val > 0 and val <= 100:
                    records["spo2"].append((start_t + idx * interval, val))
                    
    return {
        "report": report_data,
        "records": records
    }

async def download_and_decrypt_sleep_details(client, relative_uid: int, timestamp: int, timezone_value: int, log_fn=print):
    tz_in_15min = normalize_timezone_to_15min(timezone_value)
    
    # 1. Generate FDSItem
    sid = str(relative_uid)
    key_bytes = gen_data_id_key_bytes(timestamp, tz_in_15min, daily_type=8, file_type=0)
    suffix_b64 = base64.urlsafe_b64encode(key_bytes).decode().rstrip("=")
    
    sha1_sid = hashlib.sha1(sid.encode()).digest()
    sha1_b64 = base64.urlsafe_b64encode(sha1_sid).decode().rstrip("=")
    
    suffix = f"{suffix_b64}_{sha1_b64}"
    
    # 2. Prepare request params
    param_dict = {
        "did": sid,
        "relative_uid": relative_uid,
        "items": [
            {
                "timestamp": timestamp,
                "suffix": suffix
            }
        ]
    }
    
    # 3. Call service/gen_download_url
    resp = await client._request(
        "GET",
        "/healthapp/service/gen_download_url",
        params=param_dict
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
        
    # 4. Download file
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        file_resp = await http_client.get(url)
        if file_resp.status_code != 200:
            log_fn(f"Optional FDS sleep detail unavailable: HTTP {file_resp.status_code}; skipping.")
            return None
            
        enc_content = file_resp.content
        
    log_fn(f"Downloaded FDS content length: {len(enc_content)}")
    
    # 5. Decrypt or decompress content
    def android_base64_urlsafe(s):
        if isinstance(s, bytes):
            s = s.decode("utf-8", "ignore")
        s = s.strip().replace("\n", "").replace("\r", "")
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s)
        
    if obj_key_b64:
        try:
            encrypted_bytes = android_base64_urlsafe(enc_content)
            obj_key_bytes = android_base64_urlsafe(obj_key_b64)
            
            if len(obj_key_bytes) != 16:
                log_fn(f"Invalid obj_key length: {len(obj_key_bytes)}")
                return None
                
            cipher = AES.new(obj_key_bytes, AES.MODE_CBC, b"1234567887654321")
            decrypted = cipher.decrypt(encrypted_bytes)
            decrypted = unpad(decrypted, 16)
            return decrypted
        except Exception as e:
            log_fn(f"AES decryption or unpadding failed: {e}")
            return None
    else:
        log_fn("No obj_key in file_info. Checking if content is compressed (gzip/zlib) or raw...")
        # Check for GZIP header (1f 8b)
        if enc_content.startswith(b"\x1f\x8b"):
            try:
                import gzip
                decompressed = gzip.decompress(enc_content)
                log_fn(f"Successfully decompressed GZIP FDS content. Length: {len(decompressed)}")
                return decompressed
            except Exception as e:
                log_fn(f"Failed to decompress GZIP FDS content: {e}")
        # Check for ZLIB header (78 9c or 78 01 or 78 5e etc.)
        elif enc_content.startswith(b"\x78\x9c") or enc_content.startswith(b"\x78\x01"):
            try:
                import zlib
                decompressed = zlib.decompress(enc_content)
                log_fn(f"Successfully decompressed ZLIB FDS content. Length: {len(decompressed)}")
                return decompressed
            except Exception as e:
                log_fn(f"Failed to decompress ZLIB FDS content: {e}")
                
        # If not compressed, return as is
        return enc_content
