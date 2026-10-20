"""Công thức mana và quy tắc sao (ARCHITECTURE §6). Mọi con số mana chỉ nằm ở file này."""

from dataclasses import dataclass
from typing import Literal

MANA_PER_TICK = 1

# Chi phí hành động của thế giới lưới (LEVEL-SPEC §3). Truy vấn (is_lantern, get_pos,
# world_size) miễn phí.
MOVE_MANA = 1
LIGHT_MANA = 1

StarMetric = Literal["mana", "gates", "lines"]


@dataclass(frozen=True)
class StarRule:
    """Ngưỡng sao của một màn: metric ≤ `two` được 2 sao, ≤ `three` được 3 sao."""

    metric: StarMetric
    three: int
    two: int


def tick_mana(ticks: int) -> int:
    """Mana Xà Ngữ cho phần dòng code đã chạy (chưa gồm chi phí hành động của world)."""
    return ticks * MANA_PER_TICK


def stars_for(rule: StarRule, passed: bool, value: int) -> int:
    """Trượt → 0; đạt → 1; metric ≤ two → 2; metric ≤ three → 3."""
    if not passed:
        return 0
    if value <= rule.three:
        return 3
    if value <= rule.two:
        return 2
    return 1
