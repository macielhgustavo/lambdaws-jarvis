"""Local Unix-socket IPC for the Jarvis daemon."""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable


PROTOCOL_VERSION = 1


def socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        base = Path(runtime)
    else:
        base = Path("/tmp") / f"lambdaws-jarvis-{os.getuid()}"
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
    return base / "lambdaws-jarvis.sock"


def send_message(stream, payload: dict[str, Any]) -> None:
    stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    stream.flush()


def read_message(stream) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise ConnectionError("Conexão IPC encerrada.")
    payload = json.loads(line.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Mensagem IPC inválida.")
    return payload


class JarvisIPCServer:
    """Small local RPC server.

    One request is processed at a time by the shared state lock, keeping history
    deterministic while still allowing multiple desktop clients to connect.
    """

    def __init__(self, agent_factory: Callable[[Callable[[str], bool]], Any]) -> None:
        self.agent_factory = agent_factory
        self.path = socket_path()
        self._socket: socket.socket | None = None
        self._stop = threading.Event()
        self._state_lock = threading.RLock()

    def serve_forever(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket = server
        server.bind(str(self.path))
        os.chmod(self.path, 0o600)
        server.listen(8)
        server.settimeout(0.5)

        try:
            while not self._stop.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                thread = threading.Thread(
                    target=self._handle_connection,
                    args=(conn,),
                    daemon=True,
                )
                thread.start()
        finally:
            server.close()
            self.path.unlink(missing_ok=True)

    def shutdown(self) -> None:
        self._stop.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

    def _handle_connection(self, conn: socket.socket) -> None:
        with conn:
            stream = conn.makefile("rwb")

            def confirm(message: str) -> bool:
                send_message(
                    stream,
                    {
                        "type": "confirmation_required",
                        "message": message,
                    },
                )
                response = read_message(stream)
                return bool(
                    response.get("type") == "confirmation_response"
                    and response.get("allowed") is True
                )

            try:
                request = read_message(stream)
                with self._state_lock:
                    response = self._dispatch(request, confirm)
                send_message(stream, {"type": "response", **response})
            except Exception as error:  # IPC boundary
                try:
                    send_message(
                        stream,
                        {"type": "response", "ok": False, "error": str(error)},
                    )
                except Exception:
                    pass

    def _dispatch(self, request: dict[str, Any], confirm) -> dict[str, Any]:
        if request.get("protocol") != PROTOCOL_VERSION:
            return {"ok": False, "error": "Versão de protocolo incompatível."}

        method = request.get("method")
        if method == "ping":
            return {"ok": True, "result": {"status": "ready"}}

        agent = self.agent_factory(confirm)

        if method == "ask":
            answer, backend = agent.ask(str(request.get("prompt", "")))
            return {
                "ok": True,
                "result": {"answer": answer, "backend": backend},
            }

        if method == "clear":
            agent.clear()
            return {"ok": True, "result": {"cleared": True}}

        if method == "history":
            return {"ok": True, "result": {"history": agent.history}}

        return {"ok": False, "error": f"Método IPC desconhecido: {method}"}
