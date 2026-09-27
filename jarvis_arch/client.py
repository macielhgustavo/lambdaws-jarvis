"""Client facade for the local Jarvis daemon."""

from __future__ import annotations

import socket
import subprocess
import time
from typing import Callable

from .ipc import PROTOCOL_VERSION, read_message, send_message, socket_path


class DaemonUnavailable(RuntimeError):
    pass


class RemoteJarvis:
    """Jarvis-compatible client backed by jarvisd."""

    def __init__(
        self,
        confirm_callback: Callable[[str], bool],
        *,
        timeout: float = 190.0,
    ) -> None:
        self.confirm = confirm_callback
        self.timeout = timeout

    def _request(self, method: str, **payload):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(str(socket_path()))
        except OSError as error:
            sock.close()
            raise DaemonUnavailable(str(error)) from error

        with sock:
            stream = sock.makefile("rwb")
            send_message(
                stream,
                {
                    "protocol": PROTOCOL_VERSION,
                    "method": method,
                    **payload,
                },
            )
            while True:
                message = read_message(stream)
                if message.get("type") == "confirmation_required":
                    allowed = bool(self.confirm(str(message.get("message", ""))))
                    send_message(
                        stream,
                        {
                            "type": "confirmation_response",
                            "allowed": allowed,
                        },
                    )
                    continue
                if message.get("type") != "response":
                    raise DaemonUnavailable("Resposta IPC inválida.")
                if not message.get("ok"):
                    raise RuntimeError(message.get("error", "Falha no daemon Jarvis."))
                return message.get("result", {})

    @property
    def history(self):
        return self._request("history").get("history", [])

    def ask(self, prompt):
        result = self._request("ask", prompt=prompt)
        return result.get("answer", ""), result.get("backend", "jarvisd")

    def clear(self):
        self._request("clear")

    def ping(self) -> bool:
        try:
            return self._request("ping").get("status") == "ready"
        except Exception:
            return False


def try_start_daemon() -> None:
    """Best-effort activation of the user service; never requires sudo."""

    try:
        subprocess.run(
            ["systemctl", "--user", "start", "lambdaws-jarvis.service"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return


def connect_remote(confirm_callback, *, start: bool = True) -> RemoteJarvis | None:
    client = RemoteJarvis(confirm_callback)
    if client.ping():
        return client
    if start:
        try_start_daemon()
        for _ in range(8):
            time.sleep(0.15)
            if client.ping():
                return client
    return None
