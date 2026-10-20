"""Chạy câu chú của người chơi theo luật chơi (ARCHITECTURE §5).

Sandbox là lồng luật chơi, không phải lồng bảo mật (ADR-0003): nó giới hạn cú pháp được dạy, đếm
tick làm mana và bắt lỗi thành dữ liệu cho bảng tin. Code người chơi vẫn chạy trong process kernel.
"""

import ast
import builtins
import re
import sys
import traceback
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from types import CodeType, FrameType
from typing import Any, NoReturn

SPELL_FILENAME = "<spell>"
PRINT_LIMIT_BYTES = 64 * 1024
PRINT_TRUNCATED_NOTE = "\n… (bảng tin đã cắt bớt, chỉ giữ 64 KB)\n"
UNTAUGHT = "cấu trúc chưa được dạy ở học viện"

# Phần nền luôn được dùng; lớp trừu tượng (operator, …) khớp mọi lớp con nhờ isinstance.
BASE_NODES: tuple[type[ast.AST], ...] = (
    ast.Module,
    ast.Expr,
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Constant,
    ast.keyword,
    ast.BinOp,
    ast.UnaryOp,
    ast.Pass,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.operator,
    ast.unaryop,
    ast.expr_context,
)

# feature → (node AST, tên hiển thị). Nguồn: bảng FEATURES ở ARCHITECTURE §5.1.
FEATURES: dict[str, tuple[tuple[type[ast.AST], ...], str]] = {
    "assign": ((ast.Assign, ast.AugAssign, ast.AnnAssign), "gán biến"),
    "loops": ((ast.For, ast.While, ast.Break, ast.Continue), "vòng lặp"),
    "conditionals": (
        (ast.If, ast.IfExp, ast.Compare, ast.BoolOp, ast.cmpop, ast.boolop),
        "rẽ nhánh",
    ),
    "functions": (
        (ast.FunctionDef, ast.Return, ast.Lambda, ast.arguments, ast.arg),
        "định nghĩa hàm",
    ),
    "imports": ((ast.Import, ast.ImportFrom, ast.alias), "nạp thư viện"),
    "data": (
        (ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Subscript, ast.Slice, ast.Starred),
        "cấu trúc dữ liệu",
    ),
    "comprehensions": (
        (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension),
        "comprehension",
    ),
    "classes": ((ast.ClassDef,), "lớp"),
    "exceptions": ((ast.Try, ast.ExceptHandler, ast.Raise), "bắt và ném ngoại lệ"),
}

SAFE_BUILTIN_NAMES: tuple[str, ...] = (
    "range",
    "len",
    "abs",
    "min",
    "max",
    "sum",
    "round",
    "int",
    "float",
    "str",
    "bool",
    "list",
    "tuple",
    "dict",
    "set",
    "enumerate",
    "zip",
    "sorted",
    "reversed",
    "isinstance",
)

# Lớp ngoại lệ chuẩn, chỉ có khi màn mở feature `exceptions`.
EXCEPTION_NAMES: tuple[str, ...] = (
    "Exception",
    "ArithmeticError",
    "AttributeError",
    "ImportError",
    "IndexError",
    "KeyError",
    "LookupError",
    "NameError",
    "NotImplementedError",
    "OverflowError",
    "RecursionError",
    "RuntimeError",
    "StopIteration",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
)


@dataclass(frozen=True)
class Check:
    id: str
    passed: bool
    message: str


@dataclass(frozen=True)
class SpellBug:
    exc: str
    message: str
    line: int | None
    traceback: str


@dataclass(frozen=True)
class SpellResult:
    ticks: int
    stdout: str
    bug: SpellBug | None


class ManaVortex(BaseException):
    """Câu chú vượt ngân sách. Kế thừa BaseException để `except Exception` không nuốt được."""


class ForbiddenImport(ImportError):
    """Import module ngoài danh sách `imports` của màn."""


# --- Tiền kiểm ---


def _source_lines(code: str) -> list[str]:
    # Cùng quy ước xuống dòng với tokenizer của Python (không dùng str.splitlines).
    return re.split(r"\r\n|\r|\n", code)


def count_code_lines(code: str) -> int:
    """Số dòng không trống, không phải comment (dùng cho `max_lines` và metric `lines`)."""
    return sum(
        1 for line in _source_lines(code) if line.strip() and not line.lstrip().startswith("#")
    )


def _walk_with_lines(node: ast.AST, line: int) -> Iterator[tuple[ast.AST, int]]:
    # Một số node (arguments, comprehension, toán tử) không có lineno: mượn dòng của node cha.
    line = getattr(node, "lineno", line)
    yield node, line
    for child in ast.iter_child_nodes(node):
        yield from _walk_with_lines(child, line)


def _first_untaught(tree: ast.AST, features: frozenset[str]) -> tuple[int, str] | None:
    offenders: list[tuple[int, str]] = []
    for node, line in _walk_with_lines(tree, 1):
        if isinstance(node, BASE_NODES):
            continue
        for feature, (nodes, display) in FEATURES.items():
            if isinstance(node, nodes):
                if feature not in features:
                    offenders.append((line, f"tầng này chưa dạy {display}"))
                break
        else:
            offenders.append((line, UNTAUGHT))
    return min(offenders, key=lambda item: item[0]) if offenders else None


def _first_shared_line(tree: ast.AST, code: str) -> int | None:
    # Câu lệnh nào không bắt đầu ngay ở thụt lề của dòng mình thì có thứ đứng trước nó trên cùng
    # dòng: `a; b`, `if x: y`, `else: y`, `def f(): return 1`, …
    lines = _source_lines(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            text = lines[node.lineno - 1]
            if node.col_offset != len(text) - len(text.lstrip()):
                return node.lineno
    return None


def precheck(code: str, *, features: frozenset[str], max_lines: int | None) -> list[Check]:
    """Tiền kiểm không chạy code. Dừng ở check trượt đầu tiên, giữ các check đã đạt trước nó."""
    try:
        tree = ast.parse(code, SPELL_FILENAME)
        # compile bắt thêm lỗi chỉ lộ khi biên dịch (`return` ngoài hàm, `break` ngoài vòng lặp).
        compile(tree, SPELL_FILENAME, "exec", dont_inherit=True)
    except SyntaxError as exc:
        where = f"dòng {exc.lineno}, cột {exc.offset}" if exc.lineno else "câu chú"
        return [Check("syntax", False, f"Lỗi cú pháp ở {where}: {exc.msg}")]
    except (ValueError, RecursionError, MemoryError):
        return [Check("syntax", False, "Câu chú chứa ký tự hoặc cấu trúc không đọc được")]
    checks = [Check("syntax", True, "Cú pháp hợp lệ")]

    untaught = _first_untaught(tree, features)
    if untaught is not None:
        line, reason = untaught
        return [*checks, Check("features", False, f"Dòng {line}: {reason}")]
    checks.append(Check("features", True, "Chỉ dùng cấu trúc đã học"))

    if max_lines is not None:
        lines = count_code_lines(code)
        if lines > max_lines:
            message = f"Câu chú có {lines} dòng, tầng này cho tối đa {max_lines} dòng"
            return [*checks, Check("max_lines", False, message)]
        checks.append(Check("max_lines", True, f"{lines}/{max_lines} dòng"))

    shared = _first_shared_line(tree, code)
    if shared is not None:
        message = f"Dòng {shared}: mỗi dòng chỉ được viết một câu lệnh"
        return [*checks, Check("one_statement_per_line", False, message)]
    checks.append(Check("one_statement_per_line", True, "Mỗi dòng một câu lệnh"))
    return checks


# --- Chạy ---


def _spell_code_objects(code: CodeType) -> Iterator[CodeType]:
    # Hàm, lambda, generator, thân lớp của câu chú đều là code object lồng trong co_consts.
    yield code
    for const in code.co_consts:
        if isinstance(const, CodeType):
            yield from _spell_code_objects(const)


def _offset_lines(code: CodeType) -> dict[int, int | None]:
    return {offset: line for start, end, line in code.co_lines() for offset in range(start, end, 2)}


def _free_tool_id() -> int:
    monitoring = sys.monitoring
    for tool_id in (3, 4, monitoring.OPTIMIZER_ID, monitoring.PROFILER_ID):
        if monitoring.get_tool(tool_id) is None:
            return tool_id
    raise RuntimeError("sys.monitoring không còn tool id trống cho sandbox")


class _TickCounter:
    """Đếm tick bằng sys.monitoring, chỉ trên code object của câu chú (code thư viện không bị
    theo dõi). Một tick = một sự kiện LINE, cộng một tick cho mỗi cú nhảy ngược về cùng dòng
    (vòng lặp gói trong một dòng như comprehension), nên số tick giống hệt cách đếm sự kiện `line`
    của sys.settrace. Không dùng settrace: Python gỡ hàm trace khi nó ném lỗi, nên câu chú nuốt
    ManaVortex bằng `except:` hay chạy vòng lặp trong `finally` sẽ treo vĩnh viễn.
    """

    def __init__(self, code: CodeType, on_tick: Callable[[], None]) -> None:
        self._on_tick = on_tick
        self._lines = {c: _offset_lines(c) for c in _spell_code_objects(code)}
        self._tool_id = -1

    def __enter__(self) -> None:
        monitoring = sys.monitoring
        events = monitoring.events
        self._tool_id = _free_tool_id()
        monitoring.use_tool_id(self._tool_id, "ma_thuat.sandbox")
        monitoring.register_callback(self._tool_id, events.LINE, self._line)
        monitoring.register_callback(self._tool_id, events.JUMP, self._jump)
        for code in self._lines:
            monitoring.set_local_events(self._tool_id, code, events.LINE | events.JUMP)

    def __exit__(self, *exc_info: object) -> None:
        monitoring = sys.monitoring
        for code in self._lines:
            monitoring.set_local_events(self._tool_id, code, 0)
        monitoring.register_callback(self._tool_id, monitoring.events.LINE, None)
        monitoring.register_callback(self._tool_id, monitoring.events.JUMP, None)
        monitoring.free_tool_id(self._tool_id)

    def _line(self, code: CodeType, line: int) -> None:
        self._on_tick()

    def _jump(self, code: CodeType, source: int, destination: int) -> None:
        if destination < source:
            lines = self._lines[code]
            line = lines.get(destination)
            if line is not None and line == lines.get(source):
                self._on_tick()


def _bug_from(exc: BaseException) -> SpellBug:
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == SPELL_FILENAME]
    try:
        message = str(exc)
    except Exception:  # noqa: BLE001 - __str__ do người chơi viết có thể tự hỏng
        message = ""
    name = type(exc).__name__
    # Chỉ in tên lớp, không in module: không lộ đường dẫn kernel (ma_thuat.sandbox.ManaVortex).
    last = f"{name}: {message}" if message else name
    text = "Traceback (most recent call last):\n" + "".join(traceback.format_list(frames)) + last
    return SpellBug(
        exc=name,
        message=message,
        line=frames[-1].lineno if frames else None,
        traceback=text,
    )


class SpellRun:
    """Một lần chạy câu chú. World giữ đối tượng này để đọc `tick` và `current_line()`."""

    def __init__(
        self,
        code: str,
        *,
        features: frozenset[str],
        imports: frozenset[str],
        tick_budget: int,
        on_print: Callable[[str], None] | None = None,
    ) -> None:
        self._code = code
        self._features = features
        self._imports = imports
        self._tick_budget = tick_budget
        self._on_print = on_print
        self._ticks = 0
        self._vortex_message: str | None = None
        self._stdout: list[str] = []
        self._stdout_bytes = 0
        self._truncated = False

    @property
    def tick(self) -> int:
        return self._ticks

    def current_line(self) -> int | None:
        """Dòng `<spell>` đang chạy: frame câu chú trong cùng trên stack."""
        frame: FrameType | None = sys._getframe(1)
        while frame is not None:
            if frame.f_code.co_filename == SPELL_FILENAME:
                return frame.f_lineno
            frame = frame.f_back
        return None

    def raise_vortex(self, message: str) -> NoReturn:
        """Ném ManaVortex và giữ nó: mọi dòng câu chú chạy sau đó cũng nổ lại."""
        self._vortex_message = message
        raise ManaVortex(message)

    def run(self, api: Mapping[str, Any]) -> SpellResult:
        """Chạy câu chú đã qua tiền kiểm với API của world. Lỗi của người chơi nằm trong `bug`."""
        code = compile(self._code, SPELL_FILENAME, "exec", dont_inherit=True)
        spell_globals: dict[str, Any] = {
            "__builtins__": self._builtins(),
            "__name__": "__spell__",
            **api,
        }
        bug: SpellBug | None = None
        try:
            with _TickCounter(code, self._on_tick):
                # Chạy code người chơi là việc của sandbox; đây là lồng luật chơi (ADR-0003).
                exec(code, spell_globals)  # noqa: S102
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001 - mọi lỗi của câu chú thành event bug
            bug = _bug_from(exc)
        return SpellResult(ticks=self._ticks, stdout="".join(self._stdout), bug=bug)

    def _on_tick(self) -> None:
        # Ném từ callback của sys.monitoring không gỡ việc theo dõi, nên vortex "dính" được:
        # câu chú nuốt ManaVortex bằng `except:` trơn thì dòng kế tiếp lại nổ.
        if self._vortex_message is not None:
            raise ManaVortex(self._vortex_message)
        if self._ticks >= self._tick_budget:
            self.raise_vortex(f"Vòng xoáy mana: câu chú vượt ngân sách {self._tick_budget} tick")
        self._ticks += 1

    def _builtins(self) -> dict[str, Any]:
        names = list(SAFE_BUILTIN_NAMES)
        if "classes" in self._features:
            names.append("__build_class__")
        if "exceptions" in self._features:
            names.extend(EXCEPTION_NAMES)
        safe = {name: getattr(builtins, name) for name in names}
        safe["print"] = self._print
        safe["__import__"] = self._import
        return safe

    def _import(
        self,
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: tuple[str, ...] | list[str] | None = (),
        level: int = 0,
    ) -> object:
        root = name.partition(".")[0]
        if level != 0:
            raise ForbiddenImport("Học viện không cho phép import tương đối")
        if root not in self._imports:
            raise ForbiddenImport(f"Học viện chưa cho phép nạp '{root}' ở tầng này")
        return builtins.__import__(name, globals, locals, fromlist or (), level)

    def _print(
        self, *args: object, sep: str | None = " ", end: str | None = "\n", flush: bool = False
    ) -> None:
        sep = " " if sep is None else sep
        end = "\n" if end is None else end
        if not isinstance(sep, str) or not isinstance(end, str):
            raise TypeError("sep và end của print phải là chuỗi")
        self._write(sep.join(str(arg) for arg in args) + end)

    def _write(self, text: str) -> None:
        if self._truncated:
            return
        data = text.encode("utf-8")
        room = PRINT_LIMIT_BYTES - self._stdout_bytes
        if len(data) > room:
            text = data[:room].decode("utf-8", "ignore") + PRINT_TRUNCATED_NOTE
            self._truncated = True
        self._stdout.append(text)
        self._stdout_bytes += len(data)
        if self._on_print is not None:
            self._on_print(text)
