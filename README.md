# Mã Thuật

> **Code là ma thuật, dev là pháp sư.**

Game lập trình lấy cảm hứng từ *The Farmer Was Replaced*: người chơi niệm phép bằng Python thật, rồi tiến lên đại số tuyến tính, PennyLane và quantum machine learning trong Học viện Mã Thuật. Client làm bằng Godot 4; luật chơi chạy trong một kernel Python riêng.

## Trạng thái

Giai đoạn khởi động: repo mới có tài liệu và cấu hình cho Claude Code. Code bắt đầu từ task MT-001. Cách bắt đầu: xem `KICKOFF.md`.

## Bộ khởi động gồm gì

| File | Ai đọc | Nội dung |
|---|---|---|
| `CLAUDE.md` | Claude Code (tự nạp mỗi phiên) | stack, lệnh, bất biến kiến trúc, quy trình, Definition of Done |
| `KICKOFF.md` | bạn | cài đặt, prompt cho từng giai đoạn, cách xử lý khi Claude đi lệch |
| `docs/01-GDD.md` | cả hai | tầm nhìn, trụ cột, thế giới, bảng màu trường phái, phạm vi MVP |
| `docs/02-ARCHITECTURE.md` | cả hai | thành phần, luồng niệm phép, giao thức, sandbox, mana, rủi ro |
| `docs/03-LEVEL-SPEC.md` | cả hai | 6 tầng MVP: thế giới, check, lời giải mẫu, lời giải sai |
| `docs/04-BACKLOG.md` | cả hai | 23 task MT-xxx theo milestone M0–M3, mỗi task có tiêu chí chấp nhận |
| `docs/05-QUALITY.md` | cả hai | các tầng test, DoD, quy ước git, CI nháp, checklist chơi thử |
| `docs/adr/` | cả hai | 6 quyết định kiến trúc và lý do |
| `contracts/` | Claude Code | JSON Schema giao thức Godot ↔ kernel và 10 message mẫu đã kiểm hợp lệ |
| `.claude/settings.json` | Claude Code | cho chạy test, lint, commit không cần hỏi; cấm push |
| `.claude/rules/` | Claude Code | quy tắc riêng cho kernel, Godot, màn chơi; chỉ nạp khi đụng file liên quan |
| `.claude/skills/` | Claude Code | `/task MT-xxx`, `verify` (tự chạy trước mỗi commit), `/new-level` |
| `.claude/agents/reviewer.md` | Claude Code | subagent rà soát chỉ đọc |

## Đã chốt (muốn đổi thì viết ADR mới)

- Godot 4.7.2 + GDScript, test bằng GUT 9.7.0.
- Python 3.12 + uv, PennyLane 0.45.x (`import pennylane as qp`), pytest, ruff.
- Kernel là process riêng, JSON Lines qua stdio (spike MT-003 xác nhận).
- Kernel mô phỏng trước, Godot phát lại sau.
- MVP: 3 tầng Xà Ngữ + 3 tầng Lượng Tử, desktop Windows và Linux.

## Giả định (sửa nếu sai)

- Một người làm cùng Claude Code; máy dev chạy Windows hoặc Linux.
- Chưa phát hành, chưa có tính năng online.
- Không có hạn chót cứng: milestone xong khi checklist chơi thử đạt.

## Phát triển

1. Cài [uv](https://docs.astral.sh/uv/). uv tự tải Python 3.12 nếu máy chưa có.
2. Cài Godot **4.7.2** stable bản thường (không .NET). GUT 9.7.0 đã nằm sẵn trong `game/addons/gut/`.
3. Đặt biến môi trường `GODOT_BIN` trỏ tới file chạy Godot, rồi mở lại terminal hoặc editor:
   - Windows (PowerShell), dùng bản `_console.exe` để thấy output test:
     `[Environment]::SetEnvironmentVariable("GODOT_BIN", "C:\Tools\Godot\Godot_v4.7.2-stable_win64_console.exe", "User")`
   - Linux: thêm `export GODOT_BIN="$HOME/tools/Godot_v4.7.2-stable_linux.x86_64"` vào `~/.bashrc`.
4. Ở gốc repo:
   ```
   uv sync
   uv run python scripts/dev.py check
   ```
   `check` chạy ruff, pytest và test Godot (GUT headless). Thiếu `GODOT_BIN` thì phần Godot bị bỏ qua kèm cảnh báo.

Các lệnh khác: `uv run python scripts/dev.py --help`.
