import argparse
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
NO_ARGS = argparse.Namespace()


def load_dev() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dev", REPO / "scripts" / "dev.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dev() -> ModuleType:
    return load_dev()


def test_ma_thuat_imports_from_any_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import ma_thuat; print(ma_thuat.__file__)"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).parent == REPO / "kernel" / "ma_thuat"


def test_smoke_is_still_a_placeholder(dev: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    args = dev.build_parser().parse_args(["smoke"])
    assert args.func(args) == 0
    assert "chưa có (MT-018)" in capsys.readouterr().out


def test_format_run_result_on_passed_fixture(dev: ModuleType) -> None:
    fixture = REPO / "contracts" / "fixtures" / "response_run_level_passed.json"
    result = json.loads(fixture.read_text(encoding="utf-8"))["result"]
    assert dev.format_run_result(result) == (
        "Trạng thái: passed · seed 0 · ★★★\n"
        "  ✓ all_lit: Đã thắp 3/3 đèn\n"
        "  ✓ no_backfire: Không có phản phệ\n"
        "Mana: 12 (xa_ngu 12)\n"
        "Tick: 6 · dòng: 6 · event: 6"
    )


def test_run_level_reports_unknown_level_through_real_kernel(
    dev: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    spell = tmp_path / "spell.py"
    spell.write_text("move(EAST)\n", encoding="utf-8")
    args = dev.build_parser().parse_args(["run-level", "xa_ngu/khong_co", str(spell)])
    assert args.func(args) == 1
    assert "Lỗi unknown_level: Không có tầng 'xa_ngu/khong_co'" in capsys.readouterr().out


def test_run_level_reports_missing_file(
    dev: ModuleType, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    args = dev.build_parser().parse_args(["run-level", "xa_ngu/f1", str(tmp_path / "khong.py")])
    assert args.func(args) == 1
    assert "không đọc được" in capsys.readouterr().out


def test_kernel_without_main_prints_placeholder(
    dev: ModuleType,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(dev, "KERNEL_MAIN", tmp_path / "__main__.py")
    assert dev.cmd_kernel(NO_ARGS) == 0
    assert "chưa có (MT-002)" in capsys.readouterr().out


def test_kernel_with_main_runs_unbuffered_module(
    dev: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    main = tmp_path / "__main__.py"
    main.write_text("", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(dev, "KERNEL_MAIN", main)
    monkeypatch.setattr(dev, "run", lambda args: calls.append(args) or 7)
    assert dev.cmd_kernel(NO_ARGS) == 7
    assert calls == [[sys.executable, "-u", "-m", "ma_thuat"]]


def fake_steps(*codes: int) -> list[tuple[str, list[str]]]:
    return [
        (f"step{i}", [sys.executable, "-c", f"raise SystemExit({code})"])
        for i, code in enumerate(codes)
    ]


def test_check_without_godot_bin_warns_and_passes(
    dev: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev, "CHECK_STEPS", fake_steps(0, 0))
    monkeypatch.delenv("GODOT_BIN", raising=False)
    assert dev.cmd_check(NO_ARGS) == 0
    out = capsys.readouterr().out
    assert "CẢNH BÁO" in out and "GODOT_BIN" in out


def test_check_fails_when_any_step_fails_and_runs_the_rest(
    dev: ModuleType, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev, "CHECK_STEPS", fake_steps(1, 0))
    monkeypatch.delenv("GODOT_BIN", raising=False)
    assert dev.cmd_check(NO_ARGS) != 0
    out = capsys.readouterr().out
    assert "== step1" in out and "step0" in out.splitlines()[-1]


def test_check_fails_when_godot_tests_fail(
    dev: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dev, "CHECK_STEPS", fake_steps(0))
    monkeypatch.setenv("GODOT_BIN", "godot")
    monkeypatch.setattr(dev, "cmd_test_godot", lambda _: 1)
    assert dev.cmd_check(NO_ARGS) != 0


def test_check_runs_steps_in_order(dev: ModuleType) -> None:
    names = [name for name, _ in dev.CHECK_STEPS]
    assert names == ["ruff check", "ruff format --check", "pytest"]


def test_test_godot_imports_then_runs_gut_headless(
    dev: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("GODOT_BIN", "godot")
    monkeypatch.setattr(dev, "run", lambda args: calls.append(args) or 0)
    assert dev.cmd_test_godot(NO_ARGS) == 0
    importing, gut = calls
    assert importing[0] == "godot" and "--headless" in importing and "--import" in importing
    assert gut[0] == "godot" and "--headless" in gut
    assert "addons/gut/gut_cmdln.gd" in gut
    assert {"-gdir=res://tests", "-ginclude_subdirs", "-gexit"} <= set(gut)


def test_test_godot_without_godot_bin_fails(
    dev: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GODOT_BIN", raising=False)
    assert dev.cmd_test_godot(NO_ARGS) != 0


def test_dev_script_uses_stdlib_only_and_no_shell() -> None:
    source = (REPO / "scripts" / "dev.py").read_text(encoding="utf-8")
    assert "shell=True" not in source
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= sys.stdlib_module_names | {"__future__"}
