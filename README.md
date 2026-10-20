## Ý Tưởng

> **Sẽ ra sao nếu ta xem những đoạn code là thần chú , và việc code là đang cast phép ?**

Đó chính là ý tưởng cho tựa Game lập trình này, game được lấy cảm hứng từ *The Farmer Was Replaced*: người chơi niệm phép bằng Python thật, rồi sau đó mở rộng ra đại số tuyến tính, PennyLane và quantum machine learning trong Học viện Ma Thuật. Client làm bằng Godot; mọi luật chơi chạy trong một kernel Python riêng, Godot chỉ hiển thị và phát lại kết quả.

## Trạng thái

Đang ở giai đoạn nền móng (M0): đã có khung repo, lệnh phát triển, kernel nói giao thức qua stdio, hợp đồng giao thức ở hai phía, CI, và hai spike gỡ rủi ro (đường pipe Godot <-> Python, API PennyLane). Chưa có màn chơi.

Nền tảng: **Windows** trước. Linux là phần mở rộng làm sau; CI có job ubuntu nhưng không bắt buộc xanh.

## Công nghệ

- Godot 4.7.2 + GDScript có kiểu tĩnh, test bằng GUT 9.7.0.
- Python 3.12 quản lý bằng uv; PennyLane 0.45.x (`import pennylane as qp`); pytest, ruff.
- Kernel là process Python riêng, trao đổi JSON Lines (UTF-8) qua stdin/stdout với Godot.
- Kernel chạy và chấm trọn câu chú trước, Godot phát lại dòng thời gian sự kiện sau.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `kernel/ma_thuat/` | kernel Python (`python -m ma_thuat`): vòng lặp giao thức |
| `kernel/tests/` | pytest: giao thức, hợp đồng, lệnh dev, spike |
| `kernel/spikes/` | script thử nghiệm: echo kernel giả, kiểm API PennyLane |
| `game/` | project Godot; `scripts/protocol.gd`, `tests/unit/`, `spikes/` |
| `game/addons/gut/` | GUT 9.7.0 (bên thứ ba, không sửa) |
| `contracts/` | JSON Schema của giao thức và 10 message mẫu, dùng chung cho cả hai phía |
| `scripts/dev.py` | mọi lệnh phát triển (chỉ dùng thư viện chuẩn) |
| `.github/workflows/ci.yml` | CI: ruff, pytest, GUT |

## Phát triển (Windows)

1. Cài [uv](https://docs.astral.sh/uv/). uv tự tải Python 3.12 nếu máy chưa có.
2. Cài Godot **4.7.2** stable bản thường (không .NET). GUT đã nằm sẵn trong `game/addons/gut/`.
3. Đặt biến môi trường `GODOT_BIN` trỏ tới bản `_console.exe` (để thấy output test), rồi mở lại terminal hoặc editor. Ví dụ trong PowerShell:
   ```
   [Environment]::SetEnvironmentVariable("GODOT_BIN", "C:\Tools\Godot\Godot_v4.7.2-stable_win64_console.exe", "User")
   ```
   Giữ file `_console.exe` cạnh file `.exe` cùng tên: bản console chỉ là wrapper gọi sang nó.
4. Ở gốc repo:
   ```
   uv sync
   uv run python scripts/dev.py check
   ```
   `check` chạy ruff, pytest và test Godot (GUT headless). Thiếu `GODOT_BIN` thì phần Godot bị bỏ qua kèm cảnh báo.

## Lệnh

| Lệnh (`uv run python scripts/dev.py ...`) | Việc |
|---|---|
| `check` | cổng chất lượng: ruff check, ruff format --check, pytest, test Godot |
| `test-godot` | chỉ test Godot (cần `GODOT_BIN`) |
| `kernel` | chạy kernel để debug tay: gõ từng dòng JSON vào stdin, ví dụ `{"id": 1, "method": "ping", "params": {}}` |
| `smoke`, `run-level` | chưa có |

Chạy lại các spike:

```
uv run python kernel/spikes/pennylane_api.py
& $env:GODOT_BIN --path game --disable-vsync res://spikes/pipe_spike.tscn -- --mode=ping
```

Chế độ của spike pipe: `ping`, `burst`, `die`, `kill`, `no-drain`.

## Lưu ý

Sandbox chạy code người chơi là lồng **luật chơi**, không phải lồng bảo mật: Vì thế chỉ chạy code bạn tin tưởng trên máy của bạn!!!
