import os
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from jarvis_arch.client import RemoteJarvis
from jarvis_arch.ipc import JarvisIPCServer, socket_path


class FakeAgent:
    shared_history = []

    def __init__(self, confirm):
        self.confirm = confirm
        self.history = self.shared_history

    def ask(self, prompt):
        if prompt == "mutate":
            allowed = self.confirm("Autorizar mutação de teste?")
            return ("allowed" if allowed else "denied", "fake")
        self.shared_history.extend(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "pong"},
            ]
        )
        return "pong", "fake"

    def clear(self):
        self.shared_history.clear()


class IPCTests(unittest.TestCase):
    def setUp(self):
        FakeAgent.shared_history = []
        self.temp = tempfile.TemporaryDirectory()
        self.patch = patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name})
        self.patch.start()
        self.server = JarvisIPCServer(lambda confirm: FakeAgent(confirm))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 2
        while not socket_path().exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(socket_path().exists())

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.patch.stop()
        self.temp.cleanup()

    def test_ping_ask_history_and_clear(self):
        client = RemoteJarvis(lambda _: False, timeout=2)
        self.assertTrue(client.ping())
        self.assertEqual(client.ask("hello"), ("pong", "fake"))
        self.assertEqual(client.history[-1]["content"], "pong")
        client.clear()
        self.assertEqual(client.history, [])

    def test_confirmation_round_trip(self):
        allowed = RemoteJarvis(lambda message: "mutação" in message, timeout=2)
        denied = RemoteJarvis(lambda _: False, timeout=2)
        self.assertEqual(allowed.ask("mutate")[0], "allowed")
        self.assertEqual(denied.ask("mutate")[0], "denied")

    def test_socket_permissions_are_private(self):
        mode = socket_path().stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
