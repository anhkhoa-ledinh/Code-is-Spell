"""Lệnh phát triển của Mã Thuật. Chạy bằng: uv run python scripts/dev.py <lệnh>.

Chỉ dùng thư viện chuẩn; tiến trình con gọi bằng list args, không qua shell.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAME = REPO / "game"
KERNEL_MAIN = REPO / "kernel" / "ma_thuat" / "__main__.py"

PY = sys.executable
CHECK_STEPS: list[tuple[str, list[str]]] = [
    ("ruff check", [PY, "-m", "ruff", "check", "."]),
    ("ruff format --check", [PY, "-m", "ruff", "format", "--check", "."]),
    ("pytest", [PY, "-m", "pytest"]),
]


def run(args: list[str]) -> int:
    return subprocess.run(args, cwd=REPO, check=False).returncode


def cmd_check(_: argparse.Namespace) -> int:
    failed: list[str] = []
    for name, args in CHECK_STEPS:
        print(f"== {name}", flush=True)
        if run(args) != 0:
            failed.append(name)
    print("== test-godot", flush=True)
    if os.environ.get("GODOT_BIN"):
        if cmd_test_godot(argparse.Namespace()) != 0:
            failed.append("test-godot")
    else:
        print("CẢNH BÁO: chưa đặt GODOT_BIN, bỏ qua test Godot (phần Godot CHƯA được kiểm).")
    if failed:
        print(f"check: ĐỎ ({', '.join(failed)})")
        return 1
    print("check: xanh")
    return 0


def cmd_test_godot(_: argparse.Namespace) -> int:
    godot = os.environ.get("GODOT_BIN")
    if not godot:
        print("Lỗi: chưa đặt biến môi trường GODOT_BIN (đường dẫn tới file chạy Godot 4.7.2).")
        return 1
    # Project mới clone chưa có .godot/: phải import trước thì class_name của GUT mới nạp được.
    imported = run([godot, "--headless", "--path", str(GAME), "--import"])
    if imported != 0:
        print(f"Lỗi: Godot --import thất bại (mã {imported}).")
        return imported
    gut = [
        godot,
        "--headless",
        "--path",
        str(GAME),
        "-s",
        "addons/gut/gut_cmdln.gd",
        "-gdir=res://tests",
        "-ginclude_subdirs",
        "-gexit",
    ]
    return run(gut)


def cmd_smoke(_: argparse.Namespace) -> int:
    print("smoke: chưa có (MT-018)")
    return 0


def cmd_kernel(_: argparse.Namespace) -> int:
    if not KERNEL_MAIN.exists():
        print("kernel: chưa có (MT-002)")
        return 0
    return run([PY, "-u", "-m", "ma_thuat"])


def cmd_run_level(args: argparse.Namespace) -> int:
    print("run-level: chưa có (MT-012)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev.py", description="Lệnh phát triển của Mã Thuật.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="ruff + pytest + test Godot (nếu có GODOT_BIN)").set_defaults(
        func=cmd_check
    )
    sub.add_parser("test-godot", help="chạy GUT headless").set_defaults(func=cmd_test_godot)
    sub.add_parser("smoke", help="end-to-end Godot + kernel thật").set_defaults(func=cmd_smoke)
    sub.add_parser("kernel", help="chạy kernel để debug tay qua stdin").set_defaults(
        func=cmd_kernel
    )
    run_level = sub.add_parser("run-level", help="chạy một câu chú trên một màn")
    run_level.add_argument("level_id")
    run_level.add_argument("spell")
    run_level.set_defaults(func=cmd_run_level)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Console Windows mặc định không phải UTF-8; chuỗi tiếng Việt sẽ vỡ nếu không ép.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
