import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from ma_thuat import server

REPO = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((REPO / "contracts" / "protocol.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
KERNEL_TIMEOUT_S = 60


def assert_valid(message: dict[str, Any]) -> None:
    errors = [error.message for error in VALIDATOR.iter_errors(message)]
    assert not errors, f"{message} không khớp schema: {errors}"


def request(request_id: int, method: str) -> str:
    return json.dumps({"id": request_id, "method": method, "params": {}}, ensure_ascii=False)


# --- handle_line / serve (trong process) ---


def test_ping_returns_pong() -> None:
    response, keep_running = server.handle_line(request(1, "ping"))
    assert response == {"id": 1, "result": {"pong": True}}
    assert keep_running
    assert_valid(response)


def test_shutdown_returns_ok_and_stops() -> None:
    response, keep_running = server.handle_line(request(2, "shutdown"))
    assert response == {"id": 2, "result": {"ok": True}}
    assert not keep_running
    assert_valid(response)


def test_unknown_method_keeps_vietnamese_name() -> None:
    response, keep_running = server.handle_line(request(3, "phép_lạ"))
    assert response["id"] == 3
    assert response["error"]["code"] == "unknown_method"
    assert "phép_lạ" in response["error"]["message"]
    assert keep_running
    assert_valid(response)


@pytest.mark.parametrize(
    "line",
    [
        "{không phải json",
        "[1, 2]",
        '{"method": "ping", "params": {}}',
        '{"id": 0, "method": "ping", "params": {}}',
        '{"id": true, "method": "ping", "params": {}}',
    ],
)
def test_unreadable_request_is_bad_params_with_null_id(line: str) -> None:
    response, keep_running = server.handle_line(line)
    assert response["id"] is None
    assert response["error"]["code"] == "bad_params"
    assert keep_running
    assert_valid(response)


def test_missing_params_is_bad_params_with_id() -> None:
    response, _ = server.handle_line('{"id": 4, "method": "ping"}')
    assert response["id"] == 4
    assert response["error"]["code"] == "bad_params"
    assert_valid(response)


def test_handler_exception_is_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(params: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("hỏng")

    monkeypatch.setitem(server.HANDLERS, "ping", broken)
    response, keep_running = server.handle_line(request(5, "ping"))
    assert response["error"]["code"] == "internal"
    assert keep_running
    assert_valid(response)


def test_serve_survives_errors_and_stops_at_shutdown() -> None:
    sent: list[dict[str, Any]] = []
    lines = ["{hỏng\n", request(1, "phép_lạ"), "\n", request(2, "ping"), request(3, "shutdown")]
    exit_code = server.serve([*lines, request(4, "ping")], sent.append)
    assert exit_code == 0
    assert [m.get("error", {}).get("code") for m in sent] == [
        "bad_params",
        "unknown_method",
        None,
        None,
    ]
    assert sent[-2:] == [{"id": 2, "result": {"pong": True}}, {"id": 3, "result": {"ok": True}}]


def test_serve_returns_zero_on_eof() -> None:
    assert server.serve([], lambda message: None) == 0


# --- kernel thật qua subprocess ---


def run_kernel(
    stdin_lines: list[str], args: list[str] | None = None
) -> subprocess.CompletedProcess:
    stdin = "".join(line + "\n" for line in stdin_lines)
    return subprocess.run(
        [sys.executable, "-u", *(args or ["-m", "ma_thuat"])],
        input=stdin.encode("utf-8"),
        capture_output=True,
        check=False,
        timeout=KERNEL_TIMEOUT_S,
        cwd=REPO,
    )


def protocol_lines(result: subprocess.CompletedProcess) -> list[dict[str, Any]]:
    # Giải mã bằng UTF-8 tường minh: kernel phải tự ép UTF-8 dù code page của Windows là gì.
    messages = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]
    for message in messages:
        assert_valid(message)
    return messages


def test_kernel_ready_ping_shutdown() -> None:
    result = run_kernel([request(1, "ping"), request(2, "shutdown"), request(3, "ping")])
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    messages = protocol_lines(result)
    assert messages[0]["method"] == "ready"
    assert messages[0]["params"]["protocol"] == 1
    assert messages[0]["params"]["pennylane"].startswith("0.45.")
    assert messages[1:] == [{"id": 1, "result": {"pong": True}}, {"id": 2, "result": {"ok": True}}]


def test_kernel_sends_exactly_one_ready_then_exits_zero_on_eof() -> None:
    result = run_kernel([])
    assert result.returncode == 0
    assert [m["method"] for m in protocol_lines(result)] == ["ready"]


def test_kernel_survives_bad_lines_and_keeps_vietnamese() -> None:
    result = run_kernel(["{hỏng", request(1, "phép_lạ"), request(2, "ping")])
    assert result.returncode == 0
    _, bad_json, unknown, pong = protocol_lines(result)
    assert bad_json["id"] is None and bad_json["error"]["code"] == "bad_params"
    assert unknown["error"]["code"] == "unknown_method"
    assert "phép_lạ" in unknown["error"]["message"]
    assert pong == {"id": 2, "result": {"pong": True}}


NOISY_KERNEL = """
import sys
from ma_thuat import __main__ as kernel, server

original = server.HANDLERS["ping"]


def noisy(params):
    print("print lạc từ handler")
    return original(params)


server.HANDLERS["ping"] = noisy
sys.exit(kernel.main())
"""


def test_stray_print_goes_to_stderr_not_protocol() -> None:
    result = run_kernel([request(1, "ping"), request(2, "shutdown")], ["-c", NOISY_KERNEL])
    assert result.returncode == 0
    messages = protocol_lines(result)
    assert messages[1] == {"id": 1, "result": {"pong": True}}
    assert "print lạc từ handler" in result.stderr.decode("utf-8")
