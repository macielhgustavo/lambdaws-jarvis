"""Always-on LambdaWS Jarvis voice service."""

from __future__ import annotations

import signal
import sys

from core import Jarvis
from jarvis_arch.client import connect_remote
from jarvis_arch.voice import VoiceBackendUnavailable, VoiceRuntime


def deny_confirmation(message: str) -> bool:
    print(f"[voice] ação exige confirmação visual: {message}", file=sys.stderr)
    return False


def main() -> int:
    agent = connect_remote(deny_confirmation) or Jarvis(deny_confirmation)
    runtime = VoiceRuntime(
        agent,
        on_state=lambda state: print(f"[voice] {state}", flush=True),
        on_transcript=lambda text: print(f"[you] {text}", flush=True),
        on_response=lambda text: print(f"[jarvis] {text}", flush=True),
    )

    def stop(*_):
        runtime.stop()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        runtime.run_forever()
    except VoiceBackendUnavailable as error:
        print(f"jarvis-voice: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
