"""Echo script cho spike MT-003: giả kernel để thử đường truyền Godot ↔ Python. Không theo schema.

Dùng: python -u echo_kernel.py [--die-after N]
"""

import json
import sys

TEXT = "Linh cầu đã thức giấc: ỡ ặ ữ ư ơ đ"
STDERR_PER_REQUEST = "log " * 256 + "\n"  # 1 KB mỗi request: 100 ping ≈ 100 KB stderr

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
die_after = int(sys.argv[sys.argv.index("--die-after") + 1]) if "--die-after" in sys.argv else -1

for count, line in enumerate(sys.stdin, start=1):
    sys.stderr.write(STDERR_PER_REQUEST)
    sys.stderr.flush()
    sys.stdout.write(json.dumps({"id": json.loads(line)["id"], "text": TEXT}, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()
    if count == die_after:
        sys.exit(3)
