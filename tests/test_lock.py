from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from miband_tracker.lock import LockUnavailable, exclusive_file_lock


def test_exclusive_file_lock_rejects_second_process(tmp_path: Path) -> None:
    lock_path = tmp_path / "sync.lock"
    script = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from miband_tracker.lock import exclusive_file_lock\n"
        "with exclusive_file_lock(Path(sys.argv[1])):\n"
        "    print('ready', flush=True)\n"
        "    time.sleep(5)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "ready"
        with pytest.raises(LockUnavailable):
            with exclusive_file_lock(lock_path):
                pass
    finally:
        proc.terminate()
        proc.wait(timeout=5)
