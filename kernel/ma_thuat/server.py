"""Vòng lặp request/response: đọc từng dòng JSON, điều phối tới handler, trả đúng một response."""

import json
import logging
from collections.abc import Callable, Iterable
from types import ModuleType
from typing import Any

from ma_thuat import judge, protocol
from ma_thuat.levels import registry

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], dict[str, Any]]
MAX_CODE_LENGTH = 20_000

# id màn → module màn. Nạp bằng load() sau khi protocol.install() (kernel/__main__.py) để print
# lạc lúc import thư viện của màn cũng sang stderr.
LEVELS: dict[str, ModuleType] = {}


class ProtocolError(Exception):
    """Lỗi do request, trả về cho Godot với mã lỗi của giao thức."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load() -> None:
    LEVELS.clear()
    LEVELS.update(registry.load_levels())


def _ping(params: dict[str, Any]) -> dict[str, Any]:
    return {"pong": True}


def _shutdown(params: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True}


def _list_levels(params: dict[str, Any]) -> dict[str, Any]:
    return {"levels": [registry.level_meta(level) for level in registry.sorted_levels(LEVELS)]}


def _run_level(params: dict[str, Any]) -> dict[str, Any]:
    level_id = params.get("level_id")
    code = params.get("code")
    if not isinstance(level_id, str) or not isinstance(code, str):
        raise ProtocolError("bad_params", "run_level cần 'level_id' và 'code' là chuỗi")
    if len(code) > MAX_CODE_LENGTH:
        raise ProtocolError("bad_params", f"Câu chú dài quá {MAX_CODE_LENGTH} ký tự")
    module = LEVELS.get(level_id)
    if module is None:
        raise ProtocolError("unknown_level", f"Không có tầng '{level_id}'")
    return judge.run_level(module.LEVEL, code)


HANDLERS: dict[str, Handler] = {
    "ping": _ping,
    "list_levels": _list_levels,
    "run_level": _run_level,
    "shutdown": _shutdown,
}


def handle_line(line: str) -> tuple[dict[str, Any], bool]:
    """Xử lý một dòng request. Trả (response, còn chạy tiếp hay không)."""
    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        return protocol.error(None, "bad_params", f"Dòng không phải JSON hợp lệ: {exc}"), True
    if not isinstance(request, dict):
        return protocol.error(None, "bad_params", "Request phải là một object JSON"), True

    request_id = request.get("id")
    if not isinstance(request_id, int) or isinstance(request_id, bool) or request_id < 1:
        return protocol.error(None, "bad_params", "Request thiếu 'id' nguyên dương"), True
    method = request.get("method")
    params = request.get("params")
    if not isinstance(method, str) or not isinstance(params, dict):
        message = "Request phải có 'method' (chuỗi) và 'params' (object)"
        return protocol.error(request_id, "bad_params", message), True

    handler = HANDLERS.get(method)
    if handler is None:
        return protocol.error(request_id, "unknown_method", f"Không có phép '{method}'"), True
    try:
        payload = handler(params)
    except ProtocolError as exc:
        return protocol.error(request_id, exc.code, exc.message), True
    except Exception:
        log.exception("handler %s lỗi", method)
        message = f"Kernel gặp lỗi nội bộ khi xử lý '{method}'"
        return protocol.error(request_id, "internal", message), True
    return protocol.result(request_id, payload), method != "shutdown"


def serve(lines: Iterable[str], send: Callable[[dict[str, Any]], None]) -> int:
    """Phục vụ tới khi nhận `shutdown` hoặc hết input (EOF). Trả mã thoát."""
    for line in lines:
        if not line.strip():
            continue
        response, keep_running = handle_line(line)
        send(response)
        if not keep_running:
            break
    return 0
