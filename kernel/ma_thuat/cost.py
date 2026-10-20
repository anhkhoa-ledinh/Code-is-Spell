"""Công thức mana và quy tắc sao (ARCHITECTURE §6). Mọi con số mana chỉ nằm ở file này."""

MANA_PER_TICK = 1


def tick_mana(ticks: int) -> int:
    """Mana Xà Ngữ cho phần dòng code đã chạy (chưa gồm chi phí hành động của world)."""
    return ticks * MANA_PER_TICK
