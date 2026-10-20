"""Kênh giao thức JSON Lines (ARCHITECTURE §4, contracts/protocol.schema.json).

Stdout gốc là kênh giao thức duy nhất. Sau `install()`, `sys.stdout` trỏ sang stderr nên print lạc
của thư viện hay của kernel không làm hỏng luồng message.
"""

import json
import platform
import sys
from importlib.metadata import version
from typing import Any, TextIO

PROTOCOL_VERSION = 1

_channel: TextIO | None = None


def install() -> None:
    """Ép UTF-8 cho stdio, giữ stdout gốc làm kênh giao thức, chuyển `sys.stdout` sang stderr."""
    global _channel
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    _channel = sys.stdout
    sys.stdout = sys.stderr


def send(message: dict[str, Any]) -> None:
    """Ghi một message thành đúng một dòng trên kênh giao thức rồi flush ngay."""
    if _channel is None:
        raise RuntimeError("protocol.install() chưa được gọi")
    _channel.write(json.dumps(message, ensure_ascii=False) + "\n")
    _channel.flush()


def ready(pennylane_version: str | None) -> dict[str, Any]:
    return {
        "method": "ready",
        "params": {
            "protocol": PROTOCOL_VERSION,
            "kernel_version": version("ma-thuat"),
            "python": platform.python_version(),
            "pennylane": pennylane_version,
        },
    }


def result(request_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": request_id, "result": payload}


def error(request_id: int | None, code: str, message: str) -> dict[str, Any]:
    return {"id": request_id, "error": {"code": code, "message": message}}
