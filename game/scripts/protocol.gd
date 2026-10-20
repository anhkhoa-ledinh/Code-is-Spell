class_name Protocol
extends RefCounted
## Tách/ghép message JSON Lines của giao thức kernel (contracts/protocol.schema.json).
## Chỉ kiểm trường bắt buộc tối thiểu; schema đầy đủ được kiểm ở phía kernel (pytest).
## Godot đọc mọi số JSON thành float: `id` được đổi về int (hoặc null) để so khớp request.

const KIND_REQUEST: String = "request"
const KIND_READY: String = "ready"
const KIND_RESULT: String = "result"
const KIND_ERROR: String = "error"


class Decoded:
	extends RefCounted
	var ok: bool = false
	var kind: String = ""
	var message: Dictionary = {}
	var error: String = ""


static func encode_request(id: int, method: String, params: Dictionary = {}) -> String:
	return JSON.stringify({"id": id, "method": method, "params": params})


static func decode(line: String) -> Decoded:
	var json: JSON = JSON.new()
	if json.parse(line) != OK:
		return _fail(
			"JSON hỏng ở dòng %d: %s" % [json.get_error_line(), json.get_error_message()]
		)
	if typeof(json.data) != TYPE_DICTIONARY:
		return _fail("message phải là object JSON")
	var message: Dictionary = json.data
	if message.has("method"):
		return _decode_method(message)
	return _decode_response(message)


static func _decode_method(message: Dictionary) -> Decoded:
	if typeof(message["method"]) != TYPE_STRING:
		return _fail("'method' phải là chuỗi")
	if typeof(message.get("params")) != TYPE_DICTIONARY:
		return _fail("'params' phải là object")
	if message["method"] == "ready":
		return _succeed(KIND_READY, message)
	if not _normalize_id(message, false):
		return _fail("request thiếu 'id' nguyên dương")
	return _succeed(KIND_REQUEST, message)


static func _decode_response(message: Dictionary) -> Decoded:
	var has_result: bool = message.has("result")
	if has_result == message.has("error"):
		return _fail("response phải có đúng một trong 'result' hoặc 'error'")
	if not _normalize_id(message, not has_result):
		return _fail("response thiếu 'id' hợp lệ")
	if not has_result:
		var error: Variant = message["error"]
		if typeof(error) != TYPE_DICTIONARY or typeof(error.get("code")) != TYPE_STRING:
			return _fail("'error' phải là object có 'code'")
		return _succeed(KIND_ERROR, message)
	var result: Variant = message["result"]
	if typeof(result) != TYPE_DICTIONARY:
		return _fail("'result' phải là object")
	if result.has("events"):
		var events_error: String = _check_events(result["events"])
		if not events_error.is_empty():
			return _fail(events_error)
	return _succeed(KIND_RESULT, message)


static func _check_events(events: Variant) -> String:
	if typeof(events) != TYPE_ARRAY:
		return "'events' phải là mảng"
	var index: int = 0
	for event: Variant in events:
		if typeof(event) != TYPE_DICTIONARY or typeof(event.get("type")) != TYPE_STRING:
			return "event %d thiếu 'type'" % index
		index += 1
	return ""


# Đổi id float → int. Response lỗi được phép id null (kernel không đọc được id của request).
static func _normalize_id(message: Dictionary, allow_null: bool) -> bool:
	var id: Variant = message.get("id")
	if id == null:
		return allow_null and message.has("id")
	if typeof(id) != TYPE_FLOAT and typeof(id) != TYPE_INT:
		return false
	if float(id) != floorf(float(id)) or float(id) < 1.0:
		return false
	message["id"] = int(id)
	return true


static func _succeed(kind: String, message: Dictionary) -> Decoded:
	var decoded: Decoded = Decoded.new()
	decoded.ok = true
	decoded.kind = kind
	decoded.message = message
	return decoded


static func _fail(reason: String) -> Decoded:
	var decoded: Decoded = Decoded.new()
	decoded.error = reason
	return decoded
