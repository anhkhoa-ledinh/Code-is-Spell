"""Dữ liệu một màn chơi (LEVEL-SPEC §1) và giao diện thế giới mà bộ chấm cần."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ma_thuat.cost import StarRule
from ma_thuat.sandbox import Check, SpellRun

TOWERS: tuple[str, ...] = ("xa_ngu", "luong_tu")
DEFAULT_BUDGET = 5000


class World(Protocol):
    events: list[dict[str, Any]]

    def api(self, run: SpellRun) -> dict[str, Any]: ...

    def snapshot(self) -> dict[str, Any]: ...

    def mana(self) -> dict[str, int]: ...

    def metrics(self) -> dict[str, int]: ...


@dataclass(frozen=True)
class Level:
    id: str
    tower: str
    order: int
    title: str
    brief: str
    concept: str
    features: frozenset[str]
    imports: frozenset[str]
    max_lines: int | None
    seeds: tuple[int, ...]
    stars: StarRule
    starter_code: str
    make_world: Callable[[int], World]
    # judge nhận cả seed để thông điệp nêu được seed (LEVEL-SPEC §4, F3).
    judge: Callable[[World, int], Sequence[Check]]
    tick_budget: int = DEFAULT_BUDGET
    action_budget: int = DEFAULT_BUDGET
