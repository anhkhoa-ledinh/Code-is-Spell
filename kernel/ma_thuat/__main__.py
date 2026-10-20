"""Điểm vào kernel: `python -u -m ma_thuat`."""

import logging
import sys

from ma_thuat import protocol, server


def main() -> int:
    # install() phải chạy trước mọi import nặng để print lạc lúc import cũng sang stderr.
    protocol.install()
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
    )
    import pennylane as qp

    server.load()
    protocol.send(protocol.ready(qp.__version__))
    return server.serve(sys.stdin, protocol.send)


if __name__ == "__main__":
    sys.exit(main())
