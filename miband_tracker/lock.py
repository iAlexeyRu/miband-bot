# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alexey

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Попытка импорта fcntl (для Unix-систем) или msvcrt (для Windows)
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
    try:
        import msvcrt
        _HAS_MSVCRT = True
    except ImportError:
        _HAS_MSVCRT = False


class LockUnavailable(RuntimeError):
    """Raised when another process already owns the sync lock."""


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        fd = lock_file.fileno()

        if _HAS_FCNTL:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise LockUnavailable(f"Lock is already held: {path}") from exc
        elif _HAS_MSVCRT:
            try:
                lock_file.seek(0)
                # Блокируем первые 64 байта файла без ожидания (non-blocking)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 64)
            except OSError as exc:
                raise LockUnavailable(f"Lock is already held: {path}") from exc
        else:
            # Резервный вариант, если блокировки недоступны на платформе
            pass

        try:
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(f"pid={os.getpid()} time={int(time.time())}\n")
            lock_file.flush()
            yield
        finally:
            if _HAS_FCNTL:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception:
                    pass
            elif _HAS_MSVCRT:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 64)
                except Exception:
                    pass
