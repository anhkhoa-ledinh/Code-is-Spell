"""Vòng lặp request/response: đọc từng dòng JSON, điều phối tới handler, trả đúng một response."""

import json
import logging
from collections.abc import Callable, Iterable
from typing import Any

from ma_thuat import protocol

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], dict[str, Any]]


def _ping(params: dict[str, Any]) -> dict[str, Any]:
    return {"pong": True}


def _shutdown(params: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True}


HANDLERS: dict[str, Handler] = {"ping": _ping, "shutdown": _shutdown}


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
