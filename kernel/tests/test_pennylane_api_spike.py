"""Chạy lại spike MT-004 để lần nâng PennyLane sau tự lộ API đã gãy (ADR-0004)."""

import subprocess
import sys
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[1] / "spikes" / "pennylane_api.py"


def test_pennylane_api_spike_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SPIKE)], capture_output=True, check=False, timeout=180
    )
    output = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, output + result.stderr.decode("utf-8", "replace")
    assert "7/7 mục đạt" in output
