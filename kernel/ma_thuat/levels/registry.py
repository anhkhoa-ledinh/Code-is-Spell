"""Tự nạp mọi module màn trong levels/<tower>/ và dựng metadata cho list_levels."""

import importlib
import importlib.util
import pkgutil
from types import ModuleType
from typing import Any

from ma_thuat.levels.base import TOWERS, Level


class LevelError(ValueError):
    """Module màn khai báo sai cấu trúc LEVEL-SPEC §1."""


def _validate(module: ModuleType, tower: str) -> Level:
    name = module.__name__
    level = getattr(module, "LEVEL", None)
    if not isinstance(level, Level):
        raise LevelError(f"{name}: thiếu LEVEL (ma_thuat.levels.base.Level)")
    if not isinstance(getattr(module, "REFERENCE", None), str):
        raise LevelError(f"{name}: thiếu REFERENCE (str)")
    bad = getattr(module, "BAD", None)
    if not isinstance(bad, dict) or not bad:
        raise LevelError(f"{name}: thiếu BAD (dict tên → (code, check id))")
    if level.tower != tower or not level.id.startswith(f"{tower}/"):
        raise LevelError(f"{name}: màn '{level.id}' không thuộc tháp '{tower}'")
    if not level.seeds:
        raise LevelError(f"{name}: màn '{level.id}' phải có ít nhất một seed")
    return level


def load_levels(package: str = "ma_thuat.levels") -> dict[str, ModuleType]:
    """id màn → module màn, gom từ mọi module trong `<package>.<tower>`."""
    modules: dict[str, ModuleType] = {}
    for tower in TOWERS:
        tower_package = f"{package}.{tower}"
        if importlib.util.find_spec(tower_package) is None:
            continue
        package_module = importlib.import_module(tower_package)
        for info in sorted(pkgutil.iter_modules(package_module.__path__), key=lambda i: i.name):
            module = importlib.import_module(f"{tower_package}.{info.name}")
            level = _validate(module, tower)
            if level.id in modules:
                raise LevelError(f"Trùng id màn '{level.id}'")
            modules[level.id] = module
    return modules


def sorted_levels(modules: dict[str, ModuleType]) -> list[Level]:
    """Theo tháp (thứ tự TOWERS) rồi theo `order`."""
    levels = [module.LEVEL for module in modules.values()]
    return sorted(levels, key=lambda level: (TOWERS.index(level.tower), level.order))


def level_meta(level: Level) -> dict[str, Any]:
    """Metadata `level_meta` của schema; `preview` là thế giới của seed đầu."""
    return {
        "id": level.id,
        "tower": level.tower,
        "order": level.order,
        "title": level.title,
        "brief": level.brief,
        "concept": level.concept,
        "starter_code": level.starter_code,
        "features": sorted(level.features),
        "imports": sorted(level.imports),
        "max_lines": level.max_lines,
        "stars": {
            "metric": level.stars.metric,
            "three": level.stars.three,
            "two": level.stars.two,
        },
        "preview": level.make_world(level.seeds[0]).snapshot(),
    }
