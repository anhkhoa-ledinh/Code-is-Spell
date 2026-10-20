import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ma_thuat import cost
from ma_thuat.sandbox import (
    FEATURES,
    PRINT_LIMIT_BYTES,
    Check,
    SpellResult,
    SpellRun,
    count_code_lines,
    precheck,
)

ALL_FEATURES = frozenset(FEATURES)
F1_REFERENCE = "move(EAST)\nlight()\nmove(EAST)\nlight()\nmove(EAST)\nlight()\n"
HANG_TIMEOUT_S = 10


def check_ids(checks: list[Check]) -> list[tuple[str, bool]]:
    return [(check.id, check.passed) for check in checks]


def spell(
    code: str,
    *,
    features: frozenset[str] = ALL_FEATURES,
    imports: frozenset[str] = frozenset(),
    tick_budget: int = 1000,
    api: dict[str, Any] | None = None,
    on_print: Callable[[str], None] | None = None,
) -> tuple[SpellRun, SpellResult]:
    run = SpellRun(
        code, features=features, imports=imports, tick_budget=tick_budget, on_print=on_print
    )
    return run, run.run(api or {})


def spell_with_timeout(code: str, **kwargs: Any) -> SpellResult:
    """Chạy trong thread: nếu sandbox để câu chú treo thì test đỏ thay vì làm pytest đứng."""
    results: list[SpellResult] = []
    thread = threading.Thread(target=lambda: results.append(spell(code, **kwargs)[1]), daemon=True)
    thread.start()
    thread.join(HANG_TIMEOUT_S)
    assert not thread.is_alive(), "câu chú treo, ManaVortex không chặn được"
    return results[0]


# --- Tiền kiểm ---


def test_f1_reference_passes_every_precheck() -> None:
    checks = precheck(F1_REFERENCE, features=frozenset(), max_lines=None)
    assert check_ids(checks) == [
        ("syntax", True),
        ("features", True),
        ("one_statement_per_line", True),
    ]


def test_precheck_does_not_run_code() -> None:
    checks = precheck("x = 1 / 0\n", features=frozenset({"assign"}), max_lines=None)
    assert all(check.passed for check in checks)


def test_syntax_error_reports_line_and_column_and_stops() -> None:
    checks = precheck("move(EAST)\nlight(\n", features=frozenset(), max_lines=1)
    assert check_ids(checks) == [("syntax", False)]
    assert "dòng 2, cột 6" in checks[0].message


def test_compile_only_errors_are_syntax_errors() -> None:
    checks = precheck("return 1\n", features=frozenset({"functions"}), max_lines=None)
    assert check_ids(checks) == [("syntax", False)]


def test_untaught_feature_matches_fixture_message() -> None:
    code = "for i in range(3):\n    move(EAST)\n"
    checks = precheck(code, features=frozenset(), max_lines=None)
    assert check_ids(checks) == [("syntax", True), ("features", False)]
    assert checks[1].message == "Dòng 1: tầng này chưa dạy vòng lặp"


FEATURE_SAMPLES = {
    "assign": ("x = 1\n", "gán biến"),
    "loops": ("while False:\n    pass\n", "vòng lặp"),
    "conditionals": ("if 1 < 2:\n    pass\n", "rẽ nhánh"),
    "functions": ("def f():\n    pass\n", "định nghĩa hàm"),
    "imports": ("import math\n", "nạp thư viện"),
    "data": ("print([1, 2])\n", "cấu trúc dữ liệu"),
    "comprehensions": ("print({i for i in range(2)})\n", "comprehension"),
    "classes": ("class A:\n    pass\n", "lớp"),
    "exceptions": ("raise ValueError\n", "bắt và ném ngoại lệ"),
}


@pytest.mark.parametrize("feature", FEATURE_SAMPLES)
def test_each_feature_is_blocked_until_taught(feature: str) -> None:
    code, display = FEATURE_SAMPLES[feature]
    # Mở mọi feature khác để chắc chỉ feature đang xét bị chặn.
    others = ALL_FEATURES - {feature}
    blocked = precheck(code, features=others, max_lines=None)
    assert ("features", False) in check_ids(blocked)
    assert blocked[-1].message == f"Dòng 1: tầng này chưa dạy {display}"
    allowed = precheck(code, features=ALL_FEATURES, max_lines=None)
    assert all(check.passed for check in allowed)


@pytest.mark.parametrize(
    ("code", "line"),
    [
        ("with x:\n    pass\n", 1),
        ("x = 1\nmatch x:\n    case 1:\n        pass\n", 2),
        ("global x\n", 1),
        ("x = 1\nprint((y := 1))\n", 2),
        ("assert True\n", 1),
        ("x = 1\ndel x\n", 2),
    ],
)
def test_structures_outside_the_table_are_never_taught(code: str, line: int) -> None:
    checks = precheck(code, features=ALL_FEATURES, max_lines=None)
    assert checks[-1] == Check("features", False, f"Dòng {line}: cấu trúc chưa được dạy ở học viện")


def test_first_untaught_structure_is_reported_by_line() -> None:
    code = "move(EAST)\nx = 1\nfor i in range(2):\n    pass\n"
    checks = precheck(code, features=frozenset(), max_lines=None)
    assert checks[-1].message == "Dòng 2: tầng này chưa dạy gán biến"


def test_count_code_lines_ignores_blank_and_comment_lines() -> None:
    code = "# đầu\n\nmove(EAST)\n   # thụt lề\nlight()  # cuối dòng vẫn tính\n\n"
    assert count_code_lines(code) == 2


def test_max_lines_is_skipped_when_none_and_enforced_otherwise() -> None:
    code = "move(EAST)\n# comment\n\nlight()\nmove(EAST)\n"
    assert "max_lines" not in [c.id for c in precheck(code, features=frozenset(), max_lines=None)]
    assert ("max_lines", True) in check_ids(precheck(code, features=frozenset(), max_lines=3))
    over = precheck(code, features=frozenset(), max_lines=2)
    assert check_ids(over)[-1] == ("max_lines", False)
    assert over[-1].message == "Câu chú có 3 dòng, tầng này cho tối đa 2 dòng"


@pytest.mark.parametrize(
    ("code", "line"),
    [
        ("move(EAST); light()\n", 1),
        ("x = 1\nif x: light()\n", 2),
        ("if 1:\n    pass\nelse: light()\n", 3),
        ("try:\n    pass\nexcept: light()\n", 3),
        ("def f(): return 1\n", 1),
        ("for i in range(2): light()\n", 1),
    ],
)
def test_two_statements_on_one_line_are_rejected(code: str, line: int) -> None:
    checks = precheck(code, features=ALL_FEATURES, max_lines=None)
    assert check_ids(checks)[-1] == ("one_statement_per_line", False)
    assert checks[-1].message == f"Dòng {line}: mỗi dòng chỉ được viết một câu lệnh"


def test_multiline_statements_are_one_statement() -> None:
    code = "move(\n    EAST,\n)\nx = [\n    1,\n    2,\n]\nif x:\n    light()\n"
    checks = precheck(code, features=ALL_FEATURES, max_lines=None)
    assert all(check.passed for check in checks)


# --- Tick và ManaVortex ---


def test_each_line_costs_one_tick() -> None:
    _, result = spell("x = 1\nx = 2\nx = 3\n")
    assert result.ticks == 3
    assert result.bug is None
    assert cost.tick_mana(result.ticks) == 3


def test_player_functions_are_counted_but_library_code_is_not() -> None:
    def library_work() -> int:
        total = 0
        for i in range(1000):
            total += i
        return total

    code = "def f():\n    work()\n    work()\nf()\n"
    _, result = spell(code, api={"work": library_work})
    # dòng 1 (def), 4 (gọi f), 2 và 3 bên trong f: thư viện không tốn tick.
    assert result.ticks == 4


def test_one_line_comprehension_pays_per_iteration() -> None:
    _, result = spell("x = [i for i in range(100)]\n")
    assert result.ticks == 101


def test_infinite_loop_on_two_lines_stops_at_tick_budget() -> None:
    result = spell_with_timeout("while True:\n    pass\n", tick_budget=200)
    assert result.ticks == 200
    assert result.bug is not None
    assert result.bug.exc == "ManaVortex"
    assert "200" in result.bug.message


def test_code_within_budget_runs_to_the_end() -> None:
    _, result = spell("x = 1\nx = 2\n", tick_budget=2)
    assert result.bug is None and result.ticks == 2


@pytest.mark.parametrize("budget", range(50, 58))
def test_bare_except_cannot_swallow_vortex(budget: int) -> None:
    code = "n = 0\nwhile True:\n    try:\n        n += 1\n        n += 1\n    except:\n        n += 1\n"
    result = spell_with_timeout(code, tick_budget=budget)
    assert result.bug is not None and result.bug.exc == "ManaVortex"
    assert result.ticks == budget


def test_except_exception_does_not_catch_vortex() -> None:
    code = "while True:\n    try:\n        pass\n    except Exception:\n        pass\n"
    result = spell_with_timeout(code, tick_budget=100)
    assert result.bug is not None and result.bug.exc == "ManaVortex"


def test_loop_in_finally_cannot_escape_vortex() -> None:
    code = "try:\n    while True:\n        pass\nfinally:\n    while True:\n        pass\n"
    result = spell_with_timeout(code, tick_budget=100)
    assert result.bug is not None and result.bug.exc == "ManaVortex"


def test_infinite_generator_on_one_line_stops() -> None:
    result = spell_with_timeout("x = sum(1 for _ in range(10**12))\n", tick_budget=500)
    assert result.bug is not None and result.bug.exc == "ManaVortex"


def test_world_can_raise_sticky_vortex() -> None:
    holder: dict[str, SpellRun] = {}

    def act() -> None:
        holder["run"].raise_vortex("Vòng xoáy mana: quá nhiều hành động")

    code = "while True:\n    try:\n        act()\n    except:\n        pass\n"
    run = SpellRun(code, features=ALL_FEATURES, imports=frozenset(), tick_budget=10_000)
    holder["run"] = run
    result = run.run({"act": act})
    assert result.bug is not None
    assert result.bug.message == "Vòng xoáy mana: quá nhiều hành động"
    assert result.ticks < 10


def test_monitoring_is_released_after_run() -> None:
    before = [sys.monitoring.get_tool(i) for i in range(6)]
    spell("x = 1\n")
    spell_with_timeout("while True:\n    pass\n", tick_budget=10)
    assert [sys.monitoring.get_tool(i) for i in range(6)] == before


# --- World đọc tick và dòng ---


def test_world_reads_tick_and_line_at_call_time() -> None:
    seen: list[tuple[int, int | None]] = []
    holder: dict[str, SpellRun] = {}

    def probe() -> None:
        run = holder["run"]
        seen.append((run.tick, run.current_line()))

    code = "x = 1\nprobe()\ndef f():\n    probe()\nf()\nprobe(\n)\n"
    run = SpellRun(code, features=ALL_FEATURES, imports=frozenset(), tick_budget=100)
    holder["run"] = run
    result = run.run({"probe": probe})
    assert result.bug is None
    assert seen == [(2, 2), (5, 4), (6, 6)]


# --- Builtins và import ---


def test_unsafe_builtins_are_missing() -> None:
    for code in ("open('x')\n", "getattr(1, 'real')\n", "type(1)\n", "eval('1')\n"):
        _, result = spell(code)
        assert result.bug is not None and result.bug.exc == "NameError", code


def test_safe_builtins_work() -> None:
    _, result = spell("print(len([1, 2]), sorted({3, 1}), max(range(4)))\n")
    assert result.bug is None
    assert result.stdout == "2 [1, 3] 3\n"


def test_classes_and_exceptions_need_their_feature() -> None:
    _, no_classes = spell("class A:\n    pass\n", features=ALL_FEATURES - {"classes"})
    assert no_classes.bug is not None and no_classes.bug.exc == "NameError"
    _, with_classes = spell("class A:\n    pass\nprint(A.__name__)\n")
    assert with_classes.bug is None and with_classes.stdout == "A\n"
    _, no_exceptions = spell("x = ValueError\n", features=ALL_FEATURES - {"exceptions"})
    assert no_exceptions.bug is not None and no_exceptions.bug.exc == "NameError"
    code = "try:\n    int('a')\nexcept ValueError:\n    print('đỡ')\n"
    _, caught = spell(code)
    assert caught.bug is None and caught.stdout == "đỡ\n"


def test_allowed_import_works() -> None:
    _, result = spell("import math\nprint(math.floor(2.5))\n", imports=frozenset({"math"}))
    assert result.bug is None and result.stdout == "2\n"


@pytest.mark.parametrize(
    "code",
    ["import os\n", "from os import path\n", "import os.path\n", "__import__('os')\n"],
)
def test_forbidden_import_is_blocked_in_vietnamese(code: str) -> None:
    _, result = spell(code, imports=frozenset({"math"}))
    assert result.bug is not None
    assert result.bug.exc == "ForbiddenImport"
    assert result.bug.message == "Học viện chưa cho phép nạp 'os' ở tầng này"


def test_allowed_library_may_import_its_own_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "spellbook_helper.py").write_text("VALUE = 7\n", encoding="utf-8")
    (tmp_path / "spellbook.py").write_text(
        "import spellbook_helper\nimport json\nVALUE = spellbook_helper.VALUE\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "spellbook", raising=False)
    monkeypatch.delitem(sys.modules, "spellbook_helper", raising=False)
    code = "import spellbook\nprint(spellbook.VALUE)\n"
    _, result = spell(code, imports=frozenset({"spellbook"}))
    assert result.bug is None, result.bug
    assert result.stdout == "7\n"


# --- print ---


def test_print_goes_to_buffer_not_kernel_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    pieces: list[str] = []
    _, result = spell("print('a', 'b', sep='-', end='!')\nprint('Golem')\n", on_print=pieces.append)
    assert result.stdout == "a-b!Golem\n"
    assert pieces == ["a-b!", "Golem\n"]
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_print_is_truncated_at_64_kb_with_a_note() -> None:
    code = "for i in range(100):\n    print('ữ' * 1000)\n"
    _, result = spell(code, tick_budget=10_000)
    assert result.bug is None
    body, note = result.stdout.rsplit("\n…", 1)
    assert len(body.encode("utf-8")) <= PRINT_LIMIT_BYTES
    assert "đã cắt bớt" in note


def test_print_rejects_file_argument() -> None:
    _, result = spell("print('x', file=None)\n")
    assert result.bug is not None and result.bug.exc == "TypeError"


# --- Lỗi của người chơi ---


class GolemHitWall(Exception):
    pass


def test_bug_traceback_matches_fixture_format() -> None:
    def move(direction: str) -> None:
        raise GolemHitWall("Golem đâm vào tường khi đi về WEST từ (0, 0)")

    _, result = spell("move('WEST')\n", api={"move": move})
    assert result.bug is not None
    assert result.bug.exc == "GolemHitWall"
    assert result.bug.line == 1
    assert result.bug.traceback == (
        "Traceback (most recent call last):\n"
        '  File "<spell>", line 1, in <module>\n'
        "GolemHitWall: Golem đâm vào tường khi đi về WEST từ (0, 0)"
    )


def test_bug_keeps_only_spell_frames_and_last_spell_line() -> None:
    code = "def f(n):\n    return 10 // n\nx = 1\nf(0)\n"
    _, result = spell(code)
    assert result.bug is not None
    assert result.bug.exc == "ZeroDivisionError"
    assert result.bug.line == 2
    assert result.bug.traceback == (
        "Traceback (most recent call last):\n"
        '  File "<spell>", line 4, in <module>\n'
        '  File "<spell>", line 2, in f\n'
        "ZeroDivisionError: integer division or modulo by zero"
    )


def test_bug_does_not_leak_kernel_paths() -> None:
    _, result = spell("while True:\n    pass\n", tick_budget=5)
    assert result.bug is not None
    assert "ma_thuat" not in result.bug.traceback
    assert ".py" not in result.bug.traceback
    assert result.bug.traceback.endswith("ManaVortex: " + result.bug.message)


def test_recursion_error_is_a_normal_bug() -> None:
    code = "def f():\n    f()\nf()\n"
    _, result = spell(code, tick_budget=100_000)
    assert result.bug is not None
    assert result.bug.exc == "RecursionError"
    assert result.bug.line == 2
