extends GutTest
## Hợp đồng giao thức phía Godot: parse mọi fixture trong contracts/fixtures/.

const EXPECTED_KINDS: Dictionary[String, String] = {
	"ready.json": Protocol.KIND_READY,
	"request_ping.json": Protocol.KIND_REQUEST,
	"request_run_level.json": Protocol.KIND_REQUEST,
	"response_error.json": Protocol.KIND_ERROR,
	"response_list_levels.json": Protocol.KIND_RESULT,
	"response_pong.json": Protocol.KIND_RESULT,
	"response_run_level_bug.json": Protocol.KIND_RESULT,
	"response_run_level_passed.json": Protocol.KIND_RESULT,
	"response_run_level_quantum.json": Protocol.KIND_RESULT,
	"response_run_level_rejected.json": Protocol.KIND_RESULT,
}


func _fixtures_dir() -> String:
	var repo: String = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	return repo.path_join("contracts/fixtures")


# Fixture được viết nhiều dòng cho dễ đọc; bỏ xuống dòng để thành đúng một dòng JSON Lines
# (xuống dòng bên trong chuỗi JSON luôn ở dạng "\n" escape nên không bị ảnh hưởng).
func _fixture_line(file_name: String) -> String:
	var text: String = FileAccess.get_file_as_string(_fixtures_dir().path_join(file_name))
	assert_false(text.is_empty(), "đọc được %s" % file_name)
	return text.replace("\r", "").replace("\n", "")


func test_fixture_list_matches_directory() -> void:
	var files: Array[String] = []
	for file_name: String in DirAccess.get_files_at(_fixtures_dir()):
		if file_name.ends_with(".json"):
			files.append(file_name)
	files.sort()
	var expected: Array[String] = []
	expected.assign(EXPECTED_KINDS.keys())
	expected.sort()
	assert_eq(files, expected)


func test_every_fixture_decodes_to_expected_kind() -> void:
	for file_name: String in EXPECTED_KINDS:
		var decoded: Protocol.Decoded = Protocol.decode(_fixture_line(file_name))
		assert_true(decoded.ok, "%s: %s" % [file_name, decoded.error])
		assert_eq(decoded.kind, EXPECTED_KINDS[file_name], file_name)
		assert_typeof(decoded.message, TYPE_DICTIONARY, file_name)


func test_ids_become_int() -> void:
	var pong: Protocol.Decoded = Protocol.decode(_fixture_line("response_pong.json"))
	assert_typeof(pong.message["id"], TYPE_INT)
	assert_eq(pong.message["id"], 1)


func test_vietnamese_text_survives() -> void:
	var decoded: Protocol.Decoded = Protocol.decode(_fixture_line("response_error.json"))
	assert_eq(decoded.message["error"]["message"], "Không có tầng 'xa_ngu/f9'")


func test_event_order_is_preserved() -> void:
	var decoded: Protocol.Decoded = Protocol.decode(_fixture_line("response_run_level_quantum.json"))
	var types: Array[String] = []
	for event: Dictionary in decoded.message["result"]["events"]:
		types.append(event["type"])
	assert_eq(types, ["gate", "orb", "orb", "gate", "orb", "orb", "measure"])
	var passed: Protocol.Decoded = Protocol.decode(_fixture_line("response_run_level_passed.json"))
	var lines: Array[int] = []
	for event: Dictionary in passed.message["result"]["events"]:
		lines.append(int(event["line"]))
	assert_eq(lines, [1, 2, 3, 4, 5, 6])


func test_error_response_may_have_null_id() -> void:
	var line: String = '{"id": null, "error": {"code": "bad_params", "message": "JSON hỏng"}}'
	var decoded: Protocol.Decoded = Protocol.decode(line)
	assert_true(decoded.ok, decoded.error)
	assert_eq(decoded.kind, Protocol.KIND_ERROR)
	assert_null(decoded.message["id"])


func test_broken_lines_return_clear_errors() -> void:
	var broken: Dictionary[String, String] = {
		'{"id": 1, "result": ': "JSON hỏng",
		"[1, 2]": "object",
		'{"id": 1}': "result",
		'{"id": 1, "result": {}, "error": {"code": "internal"}}': "đúng một",
		'{"result": {"pong": true}}': "id",
		'{"id": null, "result": {"pong": true}}': "id",
		'{"id": 1.5, "result": {"pong": true}}': "id",
		'{"id": 1, "error": "hỏng"}': "code",
		'{"id": 1, "result": {"events": {}}}': "mảng",
		'{"id": 1, "result": {"events": [{"t": 1}]}}': "event 0",
		'{"method": "ping", "params": {}}': "id",
		'{"method": "ready"}': "params",
	}
	for line: String in broken:
		var decoded: Protocol.Decoded = Protocol.decode(line)
		assert_false(decoded.ok, line)
		assert_string_contains(decoded.error, broken[line], false)


func test_encode_request_round_trips() -> void:
	var line: String = Protocol.encode_request(7, "ping")
	assert_false(line.contains("\n"), "đúng một dòng")
	var decoded: Protocol.Decoded = Protocol.decode(line)
	assert_true(decoded.ok, decoded.error)
	assert_eq(decoded.kind, Protocol.KIND_REQUEST)
	assert_eq(decoded.message, {"id": 7, "method": "ping", "params": {}})
