"""Màn giả lập chỉ dùng trong test (MT-012): kiểm khung màn chơi trước khi có màn thật.

Nằm ngoài `ma_thuat.levels` nên registry của game không bao giờ nạp nó.
"""

from ma_thuat.cost import StarRule
from ma_thuat.levels.base import Level, World
from ma_thuat.sandbox import Check
from ma_thuat.worlds.grid import GridWorld


def make_world(seed: int) -> GridWorld:
    # Đèn đổi chỗ theo seed để kiểm chọn seed phát lại.
    return GridWorld(width=3, height=1, golem=(0, 0), lanterns=[(1 + seed, 0)], action_budget=50)


def judge(world: World, seed: int) -> list[Check]:
    assert isinstance(world, GridWorld)
    lit, total = len(world.lit), len(world.lanterns)
    return [Check("all_lit", lit == total, f"Đã thắp {lit}/{total} đèn (seed {seed})")]


LEVEL = Level(
    id="xa_ngu/t0_thu",
    tower="xa_ngu",
    order=99,
    title="Hành lang thử",
    brief="Màn thử của bộ chấm.",
    concept="Kiểm khung màn chơi",
    features=frozenset({"loops", "conditionals"}),
    imports=frozenset(),
    max_lines=None,
    seeds=(0, 1),
    # Đo từ REFERENCE (max giữa hai seed): 16 mana; ★★ = ceil(1,5 × 16) = 24.
    stars=StarRule(metric="mana", three=16, two=24),
    starter_code="# Thắp đèn duy nhất.\n",
    make_world=make_world,
    judge=judge,
)

REFERENCE = """for x in range(world_size()):
    if is_lantern():
        light()
    if x < world_size() - 1:
        move(EAST)
"""

BAD = {
    "quen_thap": (
        "for x in range(world_size()):\n    if x < world_size() - 1:\n        move(EAST)\n",
        "all_lit",
    ),
    "dam_tuong": ("for x in range(world_size()):\n    move(EAST)\n", "no_backfire"),
    "dung_ham": ("def f():\n    light()\n", "features"),
}
