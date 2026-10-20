"""Spike MT-004: kiểm API PennyLane trên bản đã ghim, theo 6 mục của ADR-0004 (+ phần bổ sung).

Chạy: uv run python kernel/spikes/pennylane_api.py
Mỗi mục assert hành vi rồi in cách gọi chính xác; mục nào hỏng thì thoát mã 1.
"""

import subprocess
import sys
import time
import traceback
import warnings
from collections.abc import Callable

import numpy as np
import pennylane as qp

GAMMA = 0.05


def bell_sample(dev: qp.devices.Device, shots: int) -> qp.QNode:
    @qp.qnode(dev, shots=shots)
    def circuit():
        qp.H(0)
        qp.CNOT(wires=[0, 1])
        return qp.sample()

    return circuit


def item_shots() -> list[str]:
    dev = qp.device("default.qubit", wires=2, seed=1)
    assert bell_sample(dev, 100)().shape == (100, 2)

    @qp.qnode(dev, shots=100)
    def counted():
        qp.H(0)
        qp.CNOT(wires=[0, 1])
        return qp.counts()

    counts = counted()
    assert set(counts) <= {"00", "11"} and sum(counts.values()) == 100
    assert qp.set_shots(bell_sample(dev, 100), shots=50)().shape == (50, 2)

    @qp.set_shots(30)
    @qp.qnode(dev)
    def decorated():
        qp.H(0)
        return qp.sample()

    # sample() không chỉ dây thì lấy mẫu mọi dây của device (2 dây).
    assert decorated().shape == (30, 2)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        qp.device("default.qubit", wires=2, shots=100)
    assert any("deprecated" in str(w.message) for w in caught)
    warning_name = caught[0].category.__name__

    @qp.qnode(dev)
    def analytic_sample():
        qp.H(0)
        return qp.sample()

    analytic_error = ""
    try:
        analytic_sample()
    except qp.exceptions.DeviceError as exc:
        analytic_error = f"{type(exc).__name__}: {exc}"
    assert analytic_error, "sample() không shots phải lỗi"

    return [
        (
            "@qp.qnode(dev, shots=100) + qp.sample() → mảng (100, 2); qp.counts() → dict {'00': n, '11': m}"
            " (khoá np.str_, giá trị np.int64)"
        ),
        (
            "qp.set_shots(qnode, shots=50)() và @qp.set_shots(30) trên @qp.qnode(dev) đều đổi được shots;"
            " QNode.shots trả Shots(total_shots=...)"
        ),
        (
            f"qp.device(..., shots=100) KHÔNG lỗi, chỉ {warning_name} → tower.device() không bao giờ"
            " truyền shots"
        ),
        f"QNode không shots trả qp.sample() → {analytic_error}",
    ]


def item_operations() -> list[str]:
    dev = qp.device("default.qubit", wires=2)

    @qp.qnode(dev)
    def circuit():
        for _ in range(3):
            qp.X(0)
        qp.H(1)
        qp.CNOT(wires=[0, 1])
        qp.RY(1.0, wires=1)
        return qp.state()

    with qp.Tracker(dev) as tracker:
        tape = qp.workflow.construct_tape(circuit)()
    ops = [
        (op.name, op.wires.tolist(), [float(p) for p in op.parameters]) for op in tape.operations
    ]
    assert ops == [
        ("PauliX", [0], []),
        ("PauliX", [0], []),
        ("PauliX", [0], []),
        ("Hadamard", [1], []),
        ("CNOT", [0, 1], []),
        ("RY", [1], [1.0]),
    ]
    assert dict(tracker.totals) == {}, "construct_tape không được tính là một lần chạy"
    assert qp.workflow.construct_tape(bell_sample(dev, 100))().shots.total_shots == 100
    return [
        (
            "qp.workflow.construct_tape(qnode)(*args) → tape; tape.operations theo đúng thứ tự,"
            " vòng for trong thân QNode được trải phẳng"
        ),
        (
            "op.name: qp.X → 'PauliX', qp.H → 'Hadamard', qp.CNOT → 'CNOT', qp.RY → 'RY';"
            " op.wires.tolist(); op.parameters (list số)"
        ),
        "construct_tape không chạy device (Tracker trống); tape.shots.total_shots đọc được shots của QNode",
    ]


def item_tracker() -> list[str]:
    dev = qp.device("default.qubit", wires=2, seed=1)
    circuit = bell_sample(dev, 100)
    with qp.Tracker(dev) as tracker:
        circuit()
        circuit()
    assert tracker.totals["executions"] == 2 and tracker.totals["shots"] == 200

    @qp.qnode(dev)
    def analytic():
        qp.H(0)
        return qp.state()

    with qp.Tracker(dev) as analytic_tracker:
        analytic()
    assert analytic_tracker.totals == {"batches": 1, "simulations": 1, "executions": 1}
    return [
        "with qp.Tracker(dev) as tracker: ... → tracker.totals['executions'], tracker.totals['shots']",
        "2 lần chạy shots=100 → executions=2, shots=200; key có: batches, simulations, executions, shots",
        "chạy analytic: không có key 'shots' → đọc bằng tracker.totals.get('shots', 0)",
    ]


def item_seed() -> list[str]:
    def sampler(name: str, seed: int) -> qp.QNode:
        dev = qp.device(name, wires=2, seed=seed)

        @qp.qnode(dev, shots=50)
        def circuit():
            qp.H(0)
            qp.H(1)
            return qp.sample()

        return circuit

    for name in ("default.qubit", "default.mixed"):
        first, same, other = sampler(name, 123), sampler(name, 123), sampler(name, 7)
        a = first()
        assert np.array_equal(a, same()), f"{name}: cùng seed phải cho cùng mẫu"
        assert not np.array_equal(a, other()), f"{name}: seed khác phải cho mẫu khác"
        assert not np.array_equal(a, first()), f"{name}: RNG của device chạy tiếp giữa các lần gọi"
    return [
        (
            "qp.device('default.qubit' | 'default.mixed', wires=n, seed=s): cùng seed → cùng mẫu,"
            " seed khác → mẫu khác"
        ),
        (
            "gọi lại QNode trên CÙNG device cho mẫu khác (RNG chạy tiếp) → tất định đòi hỏi mỗi lần"
            " chạy chính thức tạo device mới từ seed"
        ),
    ]


def expected_p_one(n_gates: int) -> float:
    # Mỗi bước: X lật quần thể (p ← 1 − p), rồi tắt dần giữ lại (1 − γ) phần ở |1⟩.
    p = 0.0
    for _ in range(n_gates):
        p = (1 - GAMMA) * (1 - p)
    return p


def p_one(n_gates: int, model: qp.NoiseModel | None) -> float:
    dev = qp.device("default.mixed", wires=1, seed=0)

    @qp.qnode(dev)
    def circuit():
        for _ in range(n_gates):
            qp.X(0)
        return qp.density_matrix(0)

    qnode = qp.add_noise(circuit, model) if model else circuit
    return float(qnode()[1, 1].real)


def item_noise() -> list[str]:
    dev = qp.device("default.mixed", wires=1, seed=0)

    @qp.qnode(dev)
    def manual():
        qp.X(0)
        qp.AmplitudeDamping(GAMMA, wires=0)
        return qp.density_matrix(0)

    manual_p1 = float(manual()[1, 1].real)
    assert abs(manual_p1 - 0.95) < 1e-9

    model = qp.NoiseModel(
        {qp.BooleanFn(lambda op: True): qp.noise.partial_wires(qp.AmplitudeDamping, GAMMA)}
    )
    measured = {n: p_one(n, model) for n in (1, 3, 7)}
    for n, p in measured.items():
        assert abs(p - expected_p_one(n)) < 1e-9, (n, p)
    assert measured[1] >= 0.92 > measured[3], "ngưỡng fidelity 0,92 của Q3 phải tách 1 và 3 cổng"

    dev2 = qp.device("default.mixed", wires=2)

    @qp.qnode(dev2)
    def two_wire():
        qp.H(0)
        qp.CNOT(wires=[0, 1])
        return qp.state()

    noisy_ops = [
        (op.name, op.wires.tolist())
        for op in qp.workflow.construct_tape(qp.add_noise(two_wire, model))().operations
    ]
    assert noisy_ops == [
        ("Hadamard", [0]),
        ("AmplitudeDamping", [0]),
        ("CNOT", [0, 1]),
        ("AmplitudeDamping", [0]),
        ("AmplitudeDamping", [1]),
    ]
    assert [op.name for op in qp.workflow.construct_tape(two_wire)().operations] == [
        "Hadamard",
        "CNOT",
    ], "add_noise không được sửa QNode gốc"
    try:
        qp.AmplitudeDamping(GAMMA, wires=[0, 1])
        raise AssertionError("AmplitudeDamping 2 dây phải lỗi")
    except ValueError:
        pass
    return [
        (
            f"X rồi qp.AmplitudeDamping(0.05, wires=0) trên default.mixed, qp.density_matrix(0)"
            f" → ⟨1|ρ|1⟩ = {manual_p1:.6f}"
        ),
        (
            "model = qp.NoiseModel({qp.BooleanFn(lambda op: True):"
            " qp.noise.partial_wires(qp.AmplitudeDamping, γ)}); qp.add_noise(qnode, model)"
            " trả QNode mới, QNode gốc không đổi"
        ),
        (
            f"1 / 3 / 7 cổng X → {measured[1]:.6f} / {measured[3]:.6f} / {measured[7]:.6f}"
            " (khớp truy hồi p ← (1−γ)(1−p) và LEVEL-SPEC Q3: 0,95 / ≈0,905 / ≈0,83)"
        ),
        (
            "cổng 2 dây: partial_wires chèn một AmplitudeDamping cho từng dây; hàm nhiễu tự viết"
            " AmplitudeDamping(γ, wires=op.wires) HỎNG với CNOT (ValueError: 1 dây)"
        ),
    ]


def item_import_time() -> list[str]:
    seconds: list[float] = []
    for _ in range(3):
        start = time.perf_counter()
        subprocess.run([sys.executable, "-c", "import pennylane"], check=True)
        seconds.append(time.perf_counter() - start)
    shown = ", ".join(f"{s:.2f}" for s in seconds)
    return [
        (
            f"3 lần python -c 'import pennylane' (process mới, gồm khởi động Python): {shown} s;"
            f" trung bình {sum(seconds) / len(seconds):.2f} s (ngân sách ready ≤ 8 s)"
        ),
    ]


def item_extra() -> list[str]:
    dev = qp.device("default.qubit", wires=2, seed=0)

    @qp.qnode(dev)
    def an_chu():
        qp.X(0)
        qp.H(1)
        return qp.state()

    ops = qp.workflow.construct_tape(an_chu)().operations
    simulator = qp.device("default.qubit", wires=2)
    bloch_after: list[list[list[float]]] = []
    with qp.Tracker(dev) as tracker:
        for k in range(len(ops) + 1):
            tapes = [
                qp.tape.QuantumScript(ops[:k], [qp.expval(p(w)) for p in (qp.X, qp.Y, qp.Z)])
                for w in (0, 1)
            ]
            results = qp.execute(tapes, simulator)
            bloch_after.append([np.round(np.array(r, dtype=float), 6).tolist() for r in results])
    assert bloch_after[-1] == [[0.0, 0.0, -1.0], [1.0, 0.0, 0.0]], bloch_after
    assert dict(tracker.totals) == {}, "mô phỏng lại không được tính vào Tracker của bàn thờ"

    mixed = qp.device("default.mixed", wires=1)
    damped = qp.tape.QuantumScript(
        [qp.X(0), qp.AmplitudeDamping(GAMMA, wires=0)],
        [qp.expval(p(0)) for p in (qp.X, qp.Y, qp.Z)],
    )
    z = float(qp.execute([damped], mixed)[0][2])
    assert abs(z + 0.9) < 1e-9

    assert isinstance(an_chu, qp.QNode) and an_chu.device is dev
    assert not isinstance(lambda: None, qp.QNode)
    resized = qp.set_shots(an_chu, shots=5)
    assert isinstance(resized, qp.QNode) and resized.device is dev
    return [
        (
            "Bloch theo tiền tố: qp.tape.QuantumScript(ops[:k], [qp.expval(qp.X(w)), qp.expval(qp.Y(w)),"
            " qp.expval(qp.Z(w))]) + qp.execute(tapes, simulator); X(0), H(1) → (0,0,−1), (1,0,0)"
        ),
        "mô phỏng lại trên device riêng nên Tracker của bàn thờ không đếm (khớp ARCH §8)",
        f"default.mixed: X + AmplitudeDamping(0.05) → ⟨Z⟩ = {z:.6f}, |r| = 0,9 (linh cầu mờ)",
        "submit: isinstance(f, qp.QNode) và f.device is dev; qp.set_shots trả QNode cùng device",
    ]


ITEMS: list[tuple[str, Callable[[], list[str]]]] = [
    ("1. Shots ở QNode / qp.set_shots; device không nhận shots", item_shots),
    ("2. Danh sách operation của QNode", item_operations),
    ("3. qp.Tracker: số lần chạy và tổng shots", item_tracker),
    ("4. Seed của device cho mẫu lặp lại được", item_seed),
    ("5. default.mixed + AmplitudeDamping, chèn nhiễu sau mỗi cổng", item_noise),
    ("6. Thời gian import pennylane", item_import_time),
    ("Bổ sung. Bloch theo tiền tố mạch, nhận diện QNode", item_extra),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"PennyLane {qp.__version__} · Python {sys.version.split()[0]}")
    failed = 0
    for title, check in ITEMS:
        try:
            notes = check()
            print(f"\n[DÙNG ĐƯỢC] {title}")
            for note in notes:
                print(f"  - {note}")
        # Cố ý bắt mọi lỗi: API gãy kiểu nào cũng phải báo HỎNG rồi kiểm tiếp mục sau.
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"\n[HỎNG] {title}")
            print(traceback.format_exc())
    print(f"\n{len(ITEMS) - failed}/{len(ITEMS)} mục đạt")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
