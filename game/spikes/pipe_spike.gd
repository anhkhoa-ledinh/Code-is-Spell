extends Node
## Spike MT-003: thử OS.execute_with_pipe + Thread đọc pipe với echo script (không phải kernel thật).
## Chạy: $GODOT_BIN --path game [--headless | --disable-vsync] res://spikes/pipe_spike.tscn
##       -- --mode=ping|burst|die|kill|no-drain
## Đo FPS cần chạy có cửa sổ; màn hình dưới 60 Hz thì thêm --disable-vsync (max_fps vẫn là 60).
## In một dòng "SPIKE {json}" rồi thoát (mã 0 nếu chế độ đạt kỳ vọng, 1 nếu không).

const EXPECTED_TEXT: String = "Linh cầu đã thức giấc: ỡ ặ ữ ư ơ đ"
const PING_COUNT: int = 100
const DIE_AFTER: int = 50
const POLL_INTERVAL_MS: int = 100
const MODE_TIMEOUT_MS: int = 10000
const DETECT_LIMIT_MS: int = 2000
const MIN_FPS: float = 55.0
const LOG_DIR: String = "user://logs"
const LOG_PATH: String = "user://logs/kernel.log"

var _mode: String = "ping"
var _stdio: FileAccess
var _stderr: FileAccess
var _pid: int = -1
var _stdout_thread: Thread = Thread.new()
var _stderr_thread: Thread = Thread.new()
var _sent_usec: Dictionary[int, int] = {}
var _pipe_latencies_ms: Array[float] = []
var _main_latencies_ms: Array[float] = []
var _first_ms: float = 0.0
var _received: int = 0
var _utf8_ok: bool = true
var _next_id: int = 1
var _start_ms: int = 0
var _death_ms: int = -1
var _detected_ms: int = -1
var _detected_by: String = ""
var _last_poll_ms: int = 0
var _frame_ms: Array[float] = []
var _errors: Array[String] = []
var _finished: bool = false


func _ready() -> void:
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--mode="):
			_mode = arg.trim_prefix("--mode=")
	Engine.max_fps = 60
	var repo: String = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var python: String = _find_python(repo)
	if python.is_empty():
		_errors.append("không tìm thấy Python (.venv hoặc MA_THUAT_PYTHON)")
		_finish()
		return
	var args: PackedStringArray = ["-u", repo.path_join("kernel/spikes/echo_kernel.py")]
	if _mode == "die":
		args.append_array(["--die-after", str(DIE_AFTER)])
	var proc: Dictionary = OS.execute_with_pipe(python, args)
	if proc.is_empty():
		_errors.append("execute_with_pipe trả về rỗng")
		_finish()
		return
	_stdio = proc["stdio"]
	_stderr = proc["stderr"]
	_pid = proc["pid"]
	_stdout_thread.start(_read_stdout)
	if _mode != "no-drain":
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(LOG_DIR))
		_stderr_thread.start(_drain_stderr)
	_start_ms = Time.get_ticks_msec()
	if _mode == "burst":
		for i: int in PING_COUNT:
			_send_ping()
	else:
		_send_ping()


func _find_python(repo: String) -> String:
	var from_env: String = OS.get_environment("MA_THUAT_PYTHON")
	if not from_env.is_empty():
		return from_env
	var candidates: Array[String] = [
		repo.path_join(".venv/Scripts/python.exe"), repo.path_join(".venv/bin/python")
	]
	for candidate: String in candidates:
		if FileAccess.file_exists(candidate):
			return candidate
	return ""


func _send_ping() -> void:
	var id: int = _next_id
	_next_id += 1
	_sent_usec[id] = Time.get_ticks_usec()
	_stdio.store_line(JSON.stringify({"id": id, "method": "ping"}))


# Chạy trên _stdout_thread: chặn ở get_line(), mỗi dòng đẩy về main thread.
func _read_stdout() -> void:
	while true:
		var line: String = _stdio.get_line()
		var at_usec: int = Time.get_ticks_usec()
		if line.is_empty() and (_stdio.eof_reached() or _stdio.get_error() != OK):
			_on_stdout_closed.call_deferred()
			return
		_on_line.call_deferred(line, at_usec)


# Chạy trên _stderr_thread: xả liên tục để buffer pipe stderr không bao giờ đầy.
func _drain_stderr() -> void:
	var log_file: FileAccess = FileAccess.open(LOG_PATH, FileAccess.WRITE)
	while true:
		var chunk: PackedByteArray = _stderr.get_buffer(4096)
		if chunk.is_empty():
			break
		log_file.store_buffer(chunk)
		log_file.flush()
	log_file.close()


func _on_line(line: String, at_usec: int) -> void:
	if _finished:
		return
	var reply: Variant = JSON.parse_string(line)
	if not reply is Dictionary:
		_errors.append("dòng không phải JSON: %s" % line.left(80))
		return
	var id: int = int(reply["id"])
	var now_usec: int = Time.get_ticks_usec()
	if id == 1:
		# Ping đầu gồm cả thời gian Python khởi động: ghi riêng để không làm lệch trung bình.
		_first_ms = (at_usec - _sent_usec[id]) / 1000.0
	else:
		_pipe_latencies_ms.append((at_usec - _sent_usec[id]) / 1000.0)
		_main_latencies_ms.append((now_usec - _sent_usec[id]) / 1000.0)
	if reply["text"] != EXPECTED_TEXT:
		_utf8_ok = false
		_errors.append("chuỗi lệch: %s" % reply["text"])
	_received += 1
	if _mode == "kill" and _received == DIE_AFTER:
		_death_ms = Time.get_ticks_msec()
		OS.kill(_pid)
		return
	if _mode == "die" and _received == DIE_AFTER:
		_death_ms = Time.get_ticks_msec()
		return
	if _received == PING_COUNT:
		_finish()
	elif _mode != "burst":
		_send_ping()


func _on_stdout_closed() -> void:
	_mark_detected("stdout_eof")


func _mark_detected(by: String) -> void:
	if _detected_ms >= 0 or _finished:
		return
	_detected_ms = Time.get_ticks_msec()
	_detected_by = by
	_finish()


func _process(delta: float) -> void:
	if _finished:
		return
	_frame_ms.append(delta * 1000.0)
	var now: int = Time.get_ticks_msec()
	if _pid > 0 and now - _last_poll_ms >= POLL_INTERVAL_MS:
		_last_poll_ms = now
		if not OS.is_process_running(_pid):
			_mark_detected("poll_is_process_running")
	if now - _start_ms > MODE_TIMEOUT_MS:
		_errors.append("quá %d ms" % MODE_TIMEOUT_MS)
		_finish()


func _finish() -> void:
	if _finished:
		return
	_finished = true
	var timed_out: bool = _start_ms > 0 and Time.get_ticks_msec() - _start_ms > MODE_TIMEOUT_MS
	var was_running: bool = _pid > 0 and OS.is_process_running(_pid)
	var exit_code: int = -1 if was_running or _pid <= 0 else OS.get_process_exit_code(_pid)
	if was_running:
		OS.kill(_pid)
	var cleanup_start: int = Time.get_ticks_msec()
	if _stdout_thread.is_started():
		_stdout_thread.wait_to_finish()
	if _stderr_thread.is_started():
		_stderr_thread.wait_to_finish()
	var cleanup_ms: int = Time.get_ticks_msec() - cleanup_start
	var detect_ms: int = _detected_ms - _death_ms if _death_ms >= 0 and _detected_ms >= 0 else -1
	var result: Dictionary = {
		"mode": _mode,
		"os": OS.get_name(),
		"godot": Engine.get_version_info()["string"],
		"headless": DisplayServer.get_name() == "headless",
		"received": _received,
		"utf8_ok": _utf8_ok and _received > 0,
		"first_ping_ms": snappedf(_first_ms, 0.001),
		"pipe_avg_ms": _avg(_pipe_latencies_ms),
		"pipe_p95_ms": _p95(_pipe_latencies_ms),
		"main_avg_ms": _avg(_main_latencies_ms),
		"main_p95_ms": _p95(_main_latencies_ms),
		"elapsed_ms": Time.get_ticks_msec() - _start_ms,
		"min_fps_1s": _min_fps_1s(),
		"max_frame_ms": _frame_ms.max() if not _frame_ms.is_empty() else 0.0,
		"detect_ms": detect_ms,
		"detected_by": _detected_by,
		"exit_code": exit_code,
		"timed_out": timed_out,
		"killed_at_end": was_running,
		"cleanup_ms": cleanup_ms,
		"stderr_log_bytes": _log_bytes(),
		"errors": _errors,
	}
	result["pass"] = _passed(result)
	print("SPIKE ", JSON.stringify(result))
	get_tree().quit(0 if result["pass"] else 1)


func _passed(r: Dictionary) -> bool:
	match _mode:
		"ping":
			# Headless không có vsync thật nên chỉ xét FPS khi chạy có cửa sổ.
			var fps_ok: bool = r["headless"] or r["min_fps_1s"] >= MIN_FPS
			return _all_replies_ok(r) and fps_ok
		"burst":
			return _all_replies_ok(r)
		"die", "kill":
			return r["received"] == DIE_AFTER and r["detect_ms"] in range(0, DETECT_LIMIT_MS + 1)
		"no-drain":
			# Đối chứng: không xả stderr thì phải treo trước khi đủ 100 phản hồi.
			return r["timed_out"] and r["received"] < PING_COUNT
	return false


func _all_replies_ok(r: Dictionary) -> bool:
	return r["received"] == PING_COUNT and r["utf8_ok"] and r["stderr_log_bytes"] >= 100 * 1024


func _avg(values: Array[float]) -> float:
	if values.is_empty():
		return 0.0
	var total: float = 0.0
	for v: float in values:
		total += v
	return snappedf(total / values.size(), 0.001)


func _p95(values: Array[float]) -> float:
	if values.is_empty():
		return 0.0
	var sorted: Array[float] = values.duplicate()
	sorted.sort()
	return snappedf(sorted[mini(sorted.size() - 1, int(ceil(sorted.size() * 0.95)) - 1)], 0.001)


# FPS thấp nhất trong mọi cửa sổ 1 s liên tiếp (bỏ frame đầu vì gồm thời gian nạp scene).
func _min_fps_1s() -> float:
	var lowest: float = INF
	var window_ms: float = 0.0
	var frames: int = 0
	for i: int in range(1, _frame_ms.size()):
		window_ms += _frame_ms[i]
		frames += 1
		if window_ms >= 1000.0:
			lowest = minf(lowest, frames * 1000.0 / window_ms)
			window_ms = 0.0
			frames = 0
	return -1.0 if lowest == INF else snappedf(lowest, 0.1)


func _log_bytes() -> int:
	if not FileAccess.file_exists(LOG_PATH) or _mode == "no-drain":
		return 0
	return FileAccess.get_file_as_bytes(LOG_PATH).size()
