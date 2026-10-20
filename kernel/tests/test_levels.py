"""LEVEL-SPEC §2: mọi màn trong registry (cộng màn giả lập) tự được kiểm, không cần test riêng."""

import json
import math
from pathlib import Path
from types import ModuleType

import fake_level
import pytest
from jsonschema import Draft202012Validator

from ma_thuat.judge import run_level
from ma_thuat.levels.registry import LevelError, load_levels

REPO = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((REPO / "contracts" / "protocol.schema.json").read_text(encoding="utf-8"))
RUN_RESULT = Draft202012Validator({"$ref": "#/$defs/run_result", "$defs": SCHEMA["$defs"]})

# Màn giả lập luôn có mặt để khung được kiểm cả khi chưa có màn thật (không bao giờ bị skip).
LEVELS: dict[str, ModuleType] = {**load_levels(), fake_level.LEVEL.id: fake_level}
BAD_CASES = [(level_id, name) for level_id, module in LEVELS.items() for name in module.BAD]


def assert_valid(result: dict) -> None:
    errors = [error.message for error in RUN_RESULT.iter_errors(result)]
    assert not errors, errors


@pytest.mark.parametrize("level_id", LEVELS)
def test_reference_passes_with_three_stars(level_id: str) -> None:
    module = LEVELS[level_id]
    result = run_level(module.LEVEL, module.REFERENCE)
    assert_valid(result)
    assert result["status"] == "passed", result["checks"]
    assert result["stars"] == 3


@pytest.mark.parametrize("level_id", LEVELS)
def test_star_thresholds_are_measured_from_reference(level_id: str) -> None:
    module = LEVELS[level_id]
    rule = module.LEVEL.stars
    result = run_level(module.LEVEL, module.REFERENCE)
    # Đơn seed: run_result mang đúng metric của REFERENCE. Nhiều seed: ★★★ là max giữa các seed,
    # nên metric của seed phát lại không được vượt ngưỡng.
    measured = {"mana": result["mana"]["total"], **result["metrics"]}[rule.metric]
    if len(module.LEVEL.seeds) == 1:
        assert rule.three == measured
    else:
        assert measured <= rule.three
    assert rule.two == math.ceil(1.5 * rule.three)


@pytest.mark.parametrize(("level_id", "bad_name"), BAD_CASES)
def test_bad_fails_the_declared_check(level_id: str, bad_name: str) -> None:
    module = LEVELS[level_id]
    code, check_id = module.BAD[bad_name]
    result = run_level(module.LEVEL, code)
    assert_valid(result)
    assert result["status"] != "passed"
    failed = {check["id"] for check in result["checks"] if not check["passed"]}
    assert check_id in failed, result["checks"]


def test_fake_level_is_not_in_the_game_registry() -> None:
    assert fake_level.LEVEL.id not in load_levels()


def write_package(root: Path, name: str, module_source: str) -> None:
    (root / name / "xa_ngu").mkdir(parents=True)
    (root / name / "__init__.py").write_text("", encoding="utf-8")
    (root / name / "xa_ngu" / "__init__.py").write_text("", encoding="utf-8")
    (root / name / "xa_ngu" / "lvl.py").write_text(module_source, encoding="utf-8")


def test_registry_loads_every_module_of_each_tower(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_package(tmp_path, "pkg_ok", "from fake_level import LEVEL, REFERENCE, BAD\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    modules = load_levels("pkg_ok")
    assert list(modules) == ["xa_ngu/t0_thu"]
    assert modules["xa_ngu/t0_thu"].REFERENCE == fake_level.REFERENCE


def test_registry_rejects_module_without_bad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_package(tmp_path, "pkg_no_bad", "from fake_level import LEVEL, REFERENCE\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(LevelError, match="BAD"):
        load_levels("pkg_no_bad")


def test_registry_rejects_level_in_wrong_tower(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = (
        "import dataclasses\nimport fake_level\n"
        "LEVEL = dataclasses.replace(fake_level.LEVEL, id='luong_tu/q9', tower='luong_tu')\n"
        "REFERENCE = fake_level.REFERENCE\nBAD = fake_level.BAD\n"
    )
    write_package(tmp_path, "pkg_wrong_tower", source)
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(LevelError, match="không thuộc tháp"):
        load_levels("pkg_wrong_tower")
