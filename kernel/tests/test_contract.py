"""Hợp đồng giao thức: fixtures khớp schema, và schema thật sự từ chối message hỏng."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
CONTRACTS = REPO / "contracts"
SCHEMA = json.loads((CONTRACTS / "protocol.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
FIXTURES = sorted((CONTRACTS / "fixtures").glob("*.json"))


def load(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))


def test_schema_itself_is_valid() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_fixtures_exist() -> None:
    assert len(FIXTURES) == 10


@pytest.mark.parametrize("path", FIXTURES, ids=lambda path: path.stem)
def test_fixture_is_valid(path: Path) -> None:
    message = json.loads(path.read_text(encoding="utf-8"))
    errors = [error.message for error in VALIDATOR.iter_errors(message)]
    assert not errors, errors


def set_path(message: dict[str, Any], path: list[str | int], value: Any) -> None:
    target: Any = message
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def mutate(name: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    message = copy.deepcopy(load(name))
    change(message)
    return message


BROKEN: dict[str, dict[str, Any]] = {
    "request_id_zero": mutate("request_ping", lambda m: set_path(m, ["id"], 0)),
    "request_unknown_method": mutate("request_ping", lambda m: set_path(m, ["method"], "bay")),
    "ping_with_params": mutate("request_ping", lambda m: set_path(m, ["params"], {"x": 1})),
    "run_level_missing_code": mutate("request_run_level", lambda m: m["params"].pop("code")),
    "ready_protocol_2": mutate("ready", lambda m: set_path(m, ["params", "protocol"], 2)),
    "result_and_error": mutate(
        "response_pong", lambda m: set_path(m, ["error"], {"code": "internal", "message": "x"})
    ),
    "unknown_error_code": mutate(
        "response_error", lambda m: set_path(m, ["error", "code"], "timeout")
    ),
    "run_result_missing_stars": mutate(
        "response_run_level_passed", lambda m: m["result"].pop("stars")
    ),
    "stars_above_3": mutate(
        "response_run_level_passed", lambda m: set_path(m, ["result", "stars"], 4)
    ),
    "event_unknown_type": mutate(
        "response_run_level_passed",
        lambda m: set_path(m, ["result", "events", 0, "type"], "teleport"),
    ),
    "event_wrong_school": mutate(
        "response_run_level_passed",
        lambda m: set_path(m, ["result", "events", 0, "school"], "luong_tu"),
    ),
    "bloch_out_of_range": mutate(
        "response_run_level_quantum",
        lambda m: set_path(m, ["result", "events", 1, "bloch"], [0, 0, 1.5]),
    ),
    "unknown_school_in_mana": mutate(
        "response_run_level_passed",
        lambda m: set_path(m, ["result", "mana", "by_school", "hoa_thuat"], 1),
    ),
}


@pytest.mark.parametrize("name", BROKEN)
def test_schema_rejects_broken_message(name: str) -> None:
    assert not VALIDATOR.is_valid(BROKEN[name])
