# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

import struct

from miband_tracker.fds import parse_all_day_sleep_bytes


def test_parse_all_day_sleep_bytes_reads_hr_and_spo2_records() -> None:
    blob = bytearray()
    blob += struct.pack("<I", 1_700_000_000)
    blob += bytes([12, 2, 0])
    blob += bytes([0b00000000, 0b11000000])
    blob += bytes([1])
    blob += struct.pack("<I", 1_700_000_100)
    blob += struct.pack("<I", 1_700_000_500)
    blob += bytes([80, 90])
    blob += struct.pack("<I", 120)
    blob += struct.pack("<I", 400)
    blob += struct.pack("<I", 1_700_000_090)
    blob += struct.pack("<I", 1_700_000_520)
    blob += struct.pack("<hhI", 60, 2, 1_700_000_100)
    blob += bytes([61, 62])
    blob += struct.pack("<hhI", 60, 2, 1_700_000_100)
    blob += bytes([97, 98])

    parsed = parse_all_day_sleep_bytes(bytes(blob))

    assert parsed is not None
    assert parsed["records"]["heart_rate"] == [(1_700_000_100, 61), (1_700_000_160, 62)]
    assert parsed["records"]["spo2"] == [(1_700_000_100, 97), (1_700_000_160, 98)]


def test_parse_all_day_sleep_bytes_rejects_malformed_payloads() -> None:
    for blob in (b"", bytes(9), bytes(10), bytes(20)):
        assert parse_all_day_sleep_bytes(blob) is None
