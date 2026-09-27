"""LambdaWS Jarvis daemon entry point."""

from __future__ import annotations

import signal
import sys

from core import Jarvis, VERSION
from jarvis_arch.ipc import JarvisIPCServer


def main() -> int:
    server = JarvisIPCServer(lambda confirm: Jarvis(confirm))

    def stop(*_):
        server.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    print(f"Jarvis daemon v{VERSION} ready", flush=True)
    try:
        server.serve_forever()
    except OSError as error:
        print(f"jarvisd: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
