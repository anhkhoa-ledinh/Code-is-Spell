"""Luồng "Niệm" (ARCHITECTURE §3): tiền kiểm → chạy từng seed → chấm → gộp thành run_result."""

from dataclasses import dataclass
from typing import Any

from ma_thuat.cost import stars_for, tick_mana
from ma_thuat.levels.base import Level
from ma_thuat.sandbox import Check, SpellRun, count_code_lines, precheck

TICK_SCHOOL = "xa_ngu"
BUG_SCHOOL = "bug"
LOG_SCHOOL = "xa_ngu"


@dataclass(frozen=True)
class SeedRun:
    seed: int
    world: dict[str, Any]
    checks: list[Check]
    events: list[dict[str, Any]]
    mana_by_school: dict[str, int]
    metrics: dict[str, int]
    stdout: str

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def mana_total(self) -> int:
        return sum(self.mana_by_school.values())

    def metric(self, name: str) -> int:
        return self.mana_total if name == "mana" else self.metrics[name]


def _no_backfire(bug_line: int | None, bug_exc: str | None) -> Check:
    if bug_exc is None:
        return Check("no_backfire", True, "Không có phản phệ")
    where = f"ở dòng {bug_line}" if bug_line is not None else "trong câu chú"
    return Check("no_backfire", False, f"Phản phệ {where}: {bug_exc}")


def _metrics(lines: int, ticks: int, world_metrics: dict[str, int]) -> dict[str, int]:
    metrics = {"lines": lines, "ticks": ticks, "shots": 0, "executions": 0, "depth": 0, "gates": 0}
    metrics.update(world_metrics)
    return metrics


def _run_seed(level: Level, code: str, seed: int, lines: int) -> SeedRun:
    world = level.make_world(seed)
    initial = world.snapshot()

    def log(text: str) -> None:
        # Gọi trong lúc câu chú chạy nên tick và dòng là của lệnh print đó; nối vào cùng danh
        # sách event của world để giữ đúng thứ tự với move/light.
        event = {"t": run.tick, "type": "log", "line": run.current_line(), "school": LOG_SCHOOL}
        world.events.append(event | {"text": text})

    run = SpellRun(
        code,
        features=level.features,
        imports=level.imports,
        tick_budget=level.tick_budget,
        on_print=log,
    )
    result = run.run(world.api(run))
    bug = result.bug
    if bug is not None:
        world.events.append(
            {
                "t": result.ticks,
                "type": "bug",
                "line": bug.line,
                "school": BUG_SCHOOL,
                "exc": bug.exc,
                "message": bug.message,
                "traceback": bug.traceback,
            }
        )
    checks = [
        *level.judge(world, seed),
        _no_backfire(bug.line if bug else None, bug.exc if bug else None),
    ]
    mana = {TICK_SCHOOL: tick_mana(result.ticks)}
    for school, amount in world.mana().items():
        mana[school] = mana.get(school, 0) + amount
    return SeedRun(
        seed=seed,
        world=initial,
        checks=checks,
        events=world.events,
        mana_by_school={school: amount for school, amount in mana.items() if amount > 0},
        metrics=_metrics(lines, result.ticks, world.metrics()),
        stdout=result.stdout,
    )


def _result(status: str, seed_run: SeedRun, stars: int) -> dict[str, Any]:
    return {
        "status": status,
        "seed": seed_run.seed,
        "world": seed_run.world,
        "checks": [{"id": c.id, "passed": c.passed, "message": c.message} for c in seed_run.checks],
        "events": seed_run.events,
        "mana": {"total": seed_run.mana_total, "by_school": seed_run.mana_by_school},
        "metrics": seed_run.metrics,
        "stars": stars,
        "stdout": seed_run.stdout,
    }


def run_level(level: Level, code: str) -> dict[str, Any]:
    """Chạy và chấm một câu chú trên mọi seed của màn; trả `run_result` của schema."""
    lines = count_code_lines(code)
    prechecks = precheck(code, features=level.features, max_lines=level.max_lines)
    if not all(check.passed for check in prechecks):
        first = level.seeds[0]
        rejected = SeedRun(
            seed=first,
            world=level.make_world(first).snapshot(),
            checks=prechecks,
            events=[],
            mana_by_school={},
            metrics=_metrics(lines, 0, {}),
            stdout="",
        )
        return _result("rejected", rejected, stars=0)

    runs = [_run_seed(level, code, seed, lines) for seed in level.seeds]
    passed = all(seed_run.passed for seed_run in runs)
    replay = next((seed_run for seed_run in runs if not seed_run.passed), runs[0])
    value = max(seed_run.metric(level.stars.metric) for seed_run in runs)
    return _result("passed" if passed else "failed", replay, stars_for(level.stars, passed, value))
