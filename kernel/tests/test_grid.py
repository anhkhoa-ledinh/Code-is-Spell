import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from ma_thuat import cost
from ma_thuat.sandbox import FEATURES, SpellResult, SpellRun
from ma_thuat.worlds import SpellBackfire
from ma_thuat.worlds.grid import EAST, NORTH, SOUTH, WEST, GolemHitWall, GridWorld, NoLanternHere

REPO = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((REPO / "contracts" / "protocol.schema.json").read_text(encoding="utf-8"))


def validator_for(definition: str) -> Draft202012Validator:
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": SCHEMA["$defs"]})


EVENT = validator_for("event")
WORLD_GRID = validator_for("world_grid")


def corridor(
    width: int = 5,
    lanterns: tuple[tuple[int, int], ...] = ((1, 0), (2, 0), (3, 0)),
    action_budget: int = 5000,
) -> GridWorld:
    return GridWorld(
        width=width, height=1, golem=(0, 0), lanterns=lanterns, action_budget=action_budget
    )


def cast(world: GridWorld, code: str, tick_budget: int = 5000) -> SpellResult:
    run = SpellRun(code, features=frozenset(FEATURES), imports=frozenset(), tick_budget=tick_budget)
    return run.run(world.api(run))


def test_directions_match_level_spec() -> None:
    assert (NORTH, SOUTH, EAST, WEST) == ((0, -1), (0, 1), (1, 0), (-1, 0))


def test_backfires_inherit_spell_backfire() -> None:
    assert issubclass(GolemHitWall, SpellBackfire)
    assert issubclass(NoLanternHere, SpellBackfire)


def test_snapshot_is_valid_world_grid() -> None:
    world = corridor(lanterns=((3, 0), (1, 0), (2, 0)))
    snapshot = world.snapshot()
    assert snapshot == {
        "kind": "grid",
        "width": 5,
        "height": 1,
        "golem": [0, 0],
        "lanterns": [[1, 0], [2, 0], [3, 0]],
    }
    assert WORLD_GRID.is_valid(snapshot)


def test_f1_reference_matches_passed_fixture() -> None:
    world = corridor()
    result = cast(world, "move(EAST)\nlight()\nmove(EAST)\nlight()\nmove(EAST)\nlight()\n")
    assert result.bug is None
    fixture = json.loads(
        (REPO / "contracts/fixtures/response_run_level_passed.json").read_text(encoding="utf-8")
    )["result"]
    assert world.events == fixture["events"]
    assert world.lit == {(1, 0), (2, 0), (3, 0)}
    assert cost.tick_mana(result.ticks) + world.action_mana == fixture["mana"]["total"] == 12
    for event in world.events:
        assert EVENT.is_valid(event), event


def test_move_event_carries_tick_and_line() -> None:
    world = corridor()
    result = cast(world, "x = 1\ndef go():\n    move(EAST)\ngo()\n")
    assert result.bug is None
    assert world.events == [
        {"t": 4, "type": "move", "line": 3, "school": "xa_ngu", "from": [0, 0], "to": [1, 0]}
    ]
    assert world.golem == (1, 0)


def test_queries_are_free_and_correct() -> None:
    world = corridor()
    code = (
        "print(is_lantern(), get_pos(), world_size())\nmove(EAST)\nprint(is_lantern(), get_pos())\n"
    )
    result = cast(world, code)
    assert result.bug is None
    assert result.stdout == "False (0, 0) 5\nTrue (1, 0)\n"
    assert world.action_mana == cost.MOVE_MANA
    assert world.actions == 1


def test_is_lantern_is_false_once_lit() -> None:
    world = corridor()
    result = cast(world, "move(EAST)\nlight()\nprint(is_lantern())\n")
    assert result.bug is None and result.stdout == "False\n"


def test_hitting_wall_backfires_and_still_costs() -> None:
    world = corridor()
    result = cast(world, "move(WEST)\n")
    assert result.bug is not None
    assert result.bug.exc == "GolemHitWall"
    assert result.bug.message == "Golem đâm vào tường khi đi về WEST từ (0, 0)"
    assert result.bug.line == 1
    assert world.golem == (0, 0)
    assert world.events == []
    assert world.action_mana == cost.MOVE_MANA


@pytest.mark.parametrize(("direction", "name"), [("NORTH", "NORTH"), ("SOUTH", "SOUTH")])
def test_corridor_height_one_blocks_north_and_south(direction: str, name: str) -> None:
    result = cast(corridor(), f"move({direction})\n")
    assert result.bug is not None and result.bug.exc == "GolemHitWall"
    assert f"đi về {name}" in result.bug.message


def test_east_wall_backfires_at_the_end() -> None:
    world = corridor(width=2, lanterns=((1, 0),))
    result = cast(world, "move(EAST)\nmove(EAST)\n")
    assert result.bug is not None and result.bug.line == 2
    assert result.bug.message == "Golem đâm vào tường khi đi về EAST từ (1, 0)"
    assert world.action_mana == 2 * cost.MOVE_MANA


def test_light_without_lantern_backfires_and_still_costs() -> None:
    world = corridor()
    result = cast(world, "light()\n")
    assert result.bug is not None
    assert result.bug.exc == "NoLanternHere"
    assert result.bug.message == "Không có đèn ở ô (0, 0)"
    assert world.action_mana == cost.LIGHT_MANA
    assert world.events == []


def test_lighting_twice_does_nothing_but_costs() -> None:
    world = corridor()
    result = cast(world, "move(EAST)\nlight()\nlight()\n")
    assert result.bug is None
    assert [event["type"] for event in world.events] == ["move", "light"]
    assert world.action_mana == cost.MOVE_MANA + 2 * cost.LIGHT_MANA


def test_player_can_catch_backfire_when_taught() -> None:
    world = corridor()
    code = "try:\n    move(WEST)\nexcept Exception:\n    print('đỡ')\n"
    result = cast(world, code)
    assert result.bug is None and result.stdout == "đỡ\n"


def test_invalid_direction_is_a_value_error_without_cost() -> None:
    world = corridor()
    result = cast(world, "move('EAST')\n")
    assert result.bug is not None and result.bug.exc == "ValueError"
    assert world.action_mana == 0


def test_action_budget_raises_sticky_vortex() -> None:
    world = corridor(width=1000, lanterns=(), action_budget=10)
    code = "x = [move(EAST) for _ in range(50)]\n"
    result = cast(world, code)
    assert result.bug is not None
    assert result.bug.exc == "ManaVortex"
    assert result.bug.message == "Vòng xoáy mana: câu chú vượt ngân sách 10 hành động"
    assert world.actions == 10
    assert len(world.events) == 10


def test_action_vortex_cannot_be_swallowed() -> None:
    world = corridor(width=1000, lanterns=(), action_budget=3)
    code = "while True:\n    try:\n        move(EAST)\n    except:\n        pass\n"
    result = cast(world, code, tick_budget=100_000)
    assert result.bug is not None and result.bug.exc == "ManaVortex"
    assert "hành động" in result.bug.message


def test_world_must_be_bound_before_actions() -> None:
    with pytest.raises(RuntimeError):
        corridor().move(EAST)


def test_events_are_all_valid_against_schema() -> None:
    world = corridor(width=21, lanterns=tuple((x, 0) for x in range(1, 21)))
    result = cast(world, "for _ in range(20):\n    move(EAST)\n    light()\n")
    assert result.bug is None
    assert len(world.events) == 40
    assert all(EVENT.is_valid(event) for event in world.events)
    lines: list[Any] = [event["line"] for event in world.events]
    assert lines == [2, 3] * 20
