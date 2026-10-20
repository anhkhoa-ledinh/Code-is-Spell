"""Kiểm phía Python của spike MT-003, để lỗi đường truyền ở Godot không bị đổ nhầm cho echo script."""

import json
import subprocess
import sys
from pathlib import Path

ECHO = Path(__file__).resolve().parents[1] / "spikes" / "echo_kernel.py"
TEXT = "Linh cầu đã thức giấc: ỡ ặ ữ ư ơ đ"


def run_echo(requests: int, *args: str) -> subprocess.CompletedProcess[bytes]:
    stdin = "".join(json.dumps({"id": i, "method": "ping"}) + "\n" for i in range(1, requests + 1))
    return subprocess.run(
        [sys.executable, "-u", str(ECHO), *args],
        input=stdin.encode("utf-8"),
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_echo_returns_same_id_and_intact_vietnamese() -> None:
    result = run_echo(100)
    assert result.returncode == 0
    replies = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]
    assert [reply["id"] for reply in replies] == list(range(1, 101))
    assert all(reply["text"] == TEXT for reply in replies)


def test_echo_writes_about_100_kb_to_stderr_for_100_requests() -> None:
    assert len(run_echo(100).stderr) >= 100 * 1024


def test_die_after_exits_after_n_replies() -> None:
    result = run_echo(10, "--die-after", "3")
    assert result.returncode == 3
    assert len(result.stdout.decode("utf-8").splitlines()) == 3
