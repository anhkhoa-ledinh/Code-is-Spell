"""Thế giới lưới của tháp Xà Ngữ: golem đi trong hành lang và thắp đèn (LEVEL-SPEC §3)."""

from collections.abc import Iterable
from typing import Any

from ma_thuat import cost
from ma_thuat.sandbox import SpellRun
from ma_thuat.worlds import SpellBackfire

Pos = tuple[int, int]

# x tăng sang phải, y tăng xuống dưới.
NORTH: Pos = (0, -1)
SOUTH: Pos = (0, 1)
EAST: Pos = (1, 0)
WEST: Pos = (-1, 0)
DIRECTION_NAMES: dict[Pos, str] = {NORTH: "NORTH", SOUTH: "SOUTH", EAST: "EAST", WEST: "WEST"}
SCHOOL = "xa_ngu"


class GolemHitWall(SpellBackfire):
    pass


class NoLanternHere(SpellBackfire):
    pass


class GridWorld:
    """Trạng thái một hành lang. Gắn với một SpellRun để đọc tick và dòng cho từng event."""

    def __init__(
        self,
        *,
        width: int,
        height: int,
        golem: Pos,
        lanterns: Iterable[Pos],
        action_budget: int,
    ) -> None:
        self.width = width
        self.height = height
        self.golem: Pos = golem
        self.lanterns: frozenset[Pos] = frozenset(lanterns)
        self.lit: set[Pos] = set()
        self.action_budget = action_budget
        self.actions = 0
        self.action_mana = 0
        self.events: list[dict[str, Any]] = []
        self._run: SpellRun | None = None

    def snapshot(self) -> dict[str, Any]:
        """Thế giới dạng `world_grid` của schema (đèn liệt kê theo thứ tự toạ độ)."""
        return {
            "kind": "grid",
            "width": self.width,
            "height": self.height,
            "golem": list(self.golem),
            "lanterns": [list(pos) for pos in sorted(self.lanterns, key=lambda p: (p[1], p[0]))],
        }

    def mana(self) -> dict[str, int]:
        """Mana của các hành động (chưa gồm tick), theo trường phái."""
        return {SCHOOL: self.action_mana}

    def metrics(self) -> dict[str, int]:
        """Metric lượng tử của run_result; thế giới lưới không chạy mạch."""
        return {"shots": 0, "executions": 0, "depth": 0, "gates": 0}

    def api(self, run: SpellRun) -> dict[str, Any]:
        """Các tên người chơi gọi được trong câu chú."""
        self._run = run
        return {
            "NORTH": NORTH,
            "SOUTH": SOUTH,
            "EAST": EAST,
            "WEST": WEST,
            "move": self.move,
            "light": self.light,
            "is_lantern": self.is_lantern,
            "get_pos": self.get_pos,
            "world_size": self.world_size,
        }

    def move(self, direction: Pos) -> None:
        name = DIRECTION_NAMES.get(direction)
        if name is None:
            raise ValueError("move chỉ nhận NORTH, SOUTH, EAST hoặc WEST")
        self._spend(cost.MOVE_MANA)
        start = self.golem
        target = (start[0] + direction[0], start[1] + direction[1])
        if not (0 <= target[0] < self.width and 0 <= target[1] < self.height):
            raise GolemHitWall(f"Golem đâm vào tường khi đi về {name} từ {start}")
        self.golem = target
        self._emit("move", **{"from": list(start), "to": list(target)})

    def light(self) -> None:
        self._spend(cost.LIGHT_MANA)
        if self.golem not in self.lanterns:
            raise NoLanternHere(f"Không có đèn ở ô {self.golem}")
        if self.golem in self.lit:
            return
        self.lit.add(self.golem)
        self._emit("light", pos=list(self.golem))

    def is_lantern(self) -> bool:
        return self.golem in self.lanterns and self.golem not in self.lit

    def get_pos(self) -> Pos:
        return self.golem

    def world_size(self) -> int:
        return self.width

    def _spend(self, mana: int) -> None:
        # Tính phí trước khi làm: hành động thất bại vẫn tốn mana.
        if self.actions >= self.action_budget:
            self._bound_run().raise_vortex(
                f"Vòng xoáy mana: câu chú vượt ngân sách {self.action_budget} hành động"
            )
        self.actions += 1
        self.action_mana += mana

    def _emit(self, event_type: str, **fields: Any) -> None:
        run = self._bound_run()
        self.events.append(
            {"t": run.tick, "type": event_type, "line": run.current_line(), "school": SCHOOL}
            | fields
        )

    def _bound_run(self) -> SpellRun:
        if self._run is None:
            raise RuntimeError("GridWorld chưa được gắn với SpellRun (gọi api(run) trước)")
        return self._run
