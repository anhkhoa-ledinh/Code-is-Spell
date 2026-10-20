import dataclasses
import json
from pathlib import Path

import fake_level
import pytest
from jsonschema import Draft202012Validator

from ma_thuat.cost import StarRule, stars_for
from ma_thuat.judge import run_level

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "contracts" / "fixtures"
SCHEMA = json.loads((REPO / "contracts" / "protocol.schema.json").read_text(encoding="utf-8"))
RUN_RESULT = Draft202012Validator({"$ref": "#/$defs/run_result", "$defs": SCHEMA["$defs"]})
LEVEL = fake_level.LEVEL


def fixture_result(name: str) -> dict:
    path = FIXTURES / f"response_run_level_{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))["result"]


def judged(code: str, level: object = LEVEL) -> dict:
    result = run_level(level, code)  # type: ignore[arg-type]
    errors = [error.message for error in RUN_RESULT.iter_errors(result)]
    assert not errors, errors
    return result


@pytest.mark.parametrize(
    ("passed", "value", "expected"),
    [(False, 1, 0), (True, 25, 1), (True, 24, 2), (True, 17, 2), (True, 16, 3), (True, 0, 3)],
)
def test_star_rule_boundaries(passed: bool, value: int, expected: int) -> None:
    assert stars_for(StarRule("mana", three=16, two=24), passed, value) == expected


def test_rejected_result_has_fixture_shape() -> None:
    result = judged("for x in range(3):\n    def f():\n        pass\n")
    fixture = fixture_result("rejected")
    assert result["status"] == "rejected"
    assert result["checks"] == [
        {"id": "syntax", "passed": True, "message": "Cú pháp hợp lệ"},
        {"id": "features", "passed": False, "message": "Dòng 2: tầng này chưa dạy định nghĩa hàm"},
    ]
    assert result["events"] == fixture["events"] == []
    assert result["mana"] == fixture["mana"]
    assert result["metrics"] == {**fixture["metrics"], "lines": 3}
    assert result["stars"] == 0
    assert result["seed"] == 0
    assert result["world"] == fake_level.make_world(0).snapshot()


def test_bug_result_matches_fixture() -> None:
    result = judged("move(WEST)\n")
    fixture = fixture_result("bug")
    assert result["status"] == "failed"
    # Cùng câu chú lỗi như fixture (F1) nên event bug, mana và no_backfire phải trùng nguyên văn.
    assert result["events"] == fixture["events"]
    assert result["mana"] == fixture["mana"]
    assert result["checks"][-1] == fixture["checks"][-1]
    assert result["checks"][0] == {
        "id": "all_lit",
        "passed": False,
        "message": "Đã thắp 0/1 đèn (seed 0)",
    }


def test_replay_seed_is_the_first_failing_seed() -> None:
    # Đạt ở seed 0 (đèn ở x = 1), phản phệ ở seed 1 (đèn ở x = 2).
    result = judged("move(EAST)\nlight()\n")
    assert result["status"] == "failed"
    assert result["seed"] == 1
    assert result["world"] == fake_level.make_world(1).snapshot()
    assert result["events"][-1]["exc"] == "NoLanternHere"
    assert result["stars"] == 0


def test_replay_seed_is_the_first_seed_when_all_pass() -> None:
    result = judged(fake_level.REFERENCE)
    assert result["status"] == "passed"
    assert result["seed"] == 0
    assert result["checks"] == [
        {"id": "all_lit", "passed": True, "message": "Đã thắp 1/1 đèn (seed 0)"},
        {"id": "no_backfire", "passed": True, "message": "Không có phản phệ"},
    ]


def test_stars_use_the_worst_seed() -> None:
    # Dừng ngay khi thắp: seed 0 rẻ hơn seed 1 (đèn xa hơn một ô).
    code = "for x in range(world_size()):\n    if is_lantern():\n        light()\n        break\n    move(EAST)\n"
    cheap = run_level(LEVEL, code)
    costs = {}
    for seed in (0, 1):
        single = dataclasses.replace(LEVEL, seeds=(seed,))
        costs[seed] = run_level(single, code)["mana"]["total"]
    assert costs[0] < costs[1]
    strict = dataclasses.replace(LEVEL, stars=StarRule("mana", three=costs[0], two=costs[1]))
    result = judged(code, strict)
    assert result["status"] == "passed"
    assert result["stars"] == 2
    assert cheap["stars"] == 3


def test_log_events_interleave_with_world_events() -> None:
    seed_zero = dataclasses.replace(LEVEL, seeds=(0,))
    result = judged("move(EAST)\nprint('Golem tới')\nlight()\n", seed_zero)
    assert result["status"] == "passed"
    assert [(e["type"], e["t"], e["line"]) for e in result["events"]] == [
        ("move", 1, 1),
        ("log", 2, 2),
        ("light", 3, 3),
    ]
    assert result["events"][1]["text"] == "Golem tới\n"
    assert result["events"][1]["school"] == "xa_ngu"
    assert result["stdout"] == "Golem tới\n"


def test_mana_is_ticks_plus_actions() -> None:
    result = judged(fake_level.REFERENCE)
    actions = sum(1 for e in result["events"] if e["type"] in {"move", "light"})
    assert result["mana"] == {
        "total": result["metrics"]["ticks"] + actions,
        "by_school": {"xa_ngu": result["metrics"]["ticks"] + actions},
    }
    assert result["metrics"]["lines"] == 5


def test_run_level_is_deterministic() -> None:
    assert run_level(LEVEL, fake_level.REFERENCE) == run_level(LEVEL, fake_level.REFERENCE)
    assert run_level(LEVEL, "move(EAST)\nlight()\n") == run_level(LEVEL, "move(EAST)\nlight()\n")


def test_vortex_fails_no_backfire() -> None:
    result = judged("while True:\n    move(EAST)\n    move(WEST)\n")
    assert result["status"] == "failed"
    bug = result["events"][-1]
    assert bug["type"] == "bug" and bug["exc"] == "ManaVortex"
    assert result["checks"][-1]["passed"] is False
