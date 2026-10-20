import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fake_level
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


# --- list_levels / run_level (registry thay bằng màn giả lập) ---


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "LEVELS", {fake_level.LEVEL.id: fake_level})


def call(request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    line = json.dumps({"id": request_id, "method": method, "params": params}, ensure_ascii=False)
    response, keep_running = server.handle_line(line)
    assert keep_running
    assert_valid(response)
    return response


def test_list_levels_returns_valid_metadata(fake_registry: None) -> None:
    levels = call(1, "list_levels", {})["result"]["levels"]
    assert [level["id"] for level in levels] == ["xa_ngu/t0_thu"]
    meta = levels[0]
    assert meta["features"] == ["conditionals", "loops"]
    assert meta["preview"] == fake_level.make_world(0).snapshot()
    assert meta["stars"] == {"metric": "mana", "three": 16, "two": 24}


def test_list_levels_sorts_by_tower_then_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def variant(level_id: str, tower: str, order: int) -> SimpleNamespace:
        level = dataclasses.replace(fake_level.LEVEL, id=level_id, tower=tower, order=order)
        return SimpleNamespace(LEVEL=level)

    modules = {
        "luong_tu/q1": variant("luong_tu/q1", "luong_tu", 1),
        "xa_ngu/f2": variant("xa_ngu/f2", "xa_ngu", 2),
        "xa_ngu/f1": variant("xa_ngu/f1", "xa_ngu", 1),
    }
    monkeypatch.setattr(server, "LEVELS", modules)
    levels = call(1, "list_levels", {})["result"]["levels"]
    assert [level["id"] for level in levels] == ["xa_ngu/f1", "xa_ngu/f2", "luong_tu/q1"]


def test_run_level_returns_run_result(fake_registry: None) -> None:
    params = {"level_id": "xa_ngu/t0_thu", "code": fake_level.REFERENCE}
    result = call(2, "run_level", params)["result"]
    assert result["status"] == "passed" and result["stars"] == 3


def test_unknown_level_matches_fixture_wording(fake_registry: None) -> None:
    error = call(7, "run_level", {"level_id": "xa_ngu/f9", "code": ""})["error"]
    fixture = json.loads((REPO / "contracts/fixtures/response_error.json").read_text("utf-8"))
    assert error == fixture["error"]


@pytest.mark.parametrize(
    "params",
    [
        {"code": "move(EAST)\n"},
        {"level_id": "xa_ngu/t0_thu"},
        {"level_id": "xa_ngu/t0_thu", "code": 3},
        {"level_id": 1, "code": ""},
        {"level_id": "xa_ngu/t0_thu", "code": "x" * 20_001},
    ],
)
def test_run_level_bad_params(fake_registry: None, params: dict[str, Any]) -> None:
    error = call(3, "run_level", params)["error"]
    assert error["code"] == "bad_params"


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


def test_kernel_answers_list_levels() -> None:
    result = run_kernel([request(1, "list_levels"), request(2, "shutdown")])
    assert result.returncode == 0
    _, levels, _ = protocol_lines(result)
    assert levels["id"] == 1 and "levels" in levels["result"]


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
