#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey
"""
Local launcher: runs miband_sync and fitness_bot in parallel,
redirecting their output to data/sync.log and data/bot.log.
Handles Ctrl+C and window close gracefully.
"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

from miband_tracker.lock import LockUnavailable, exclusive_file_lock
from miband_tracker.stdio import configure_utf8_stdio, safe_print

configure_utf8_stdio()


def python_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def stop_processes(procs: list[subprocess.Popen[bytes]]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()

    for proc in procs:
        if proc.poll() is None:
            with suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)

    for proc in procs:
        if proc.poll() is None:
            proc.kill()


def run_processes(data_dir: Path) -> int:
    procs: list[subprocess.Popen[bytes]] = []
    exit_code = 0
    child_env = python_env()

    with (data_dir / "sync.log").open("w", encoding="utf-8") as sync_log, (
        data_dir / "bot.log"
    ).open("w", encoding="utf-8") as bot_log:
        try:
            sync_proc = subprocess.Popen(
                [sys.executable, "-u", "miband_sync.py"],
                stdout=sync_log,
                stderr=sync_log,
                env=child_env,
            )
            procs.append(sync_proc)

            bot_proc = subprocess.Popen(
                [sys.executable, "-u", "fitness_bot.py"],
                stdout=bot_log,
                stderr=bot_log,
                env=child_env,
            )
            procs.append(bot_proc)

            exit_code = bot_proc.wait()
        except KeyboardInterrupt:
            exit_code = 130
        finally:
            stop_processes(procs)

    return exit_code


def main() -> None:
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    try:
        with exclusive_file_lock(data_dir / "run.lock"):
            exit_code = run_processes(data_dir)
    except LockUnavailable:
        safe_print("miband-bot уже запущен. Закройте старое окно перед повторным запуском.", flush=True)
        exit_code = 2

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
