import stat
import tempfile
import unittest
from pathlib import Path

import core


class CoreSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.previous = {
            "HOME": core.HOME,
            "DATA": core.DATA,
            "HISTORY_FILE": core.HISTORY_FILE,
            "MEMORY_FILE": core.MEMORY_FILE,
        }
        core.HOME = self.root
        core.DATA = self.root / "data"
        core.HISTORY_FILE = core.DATA / "history.json"
        core.MEMORY_FILE = core.DATA / "memory.json"

    def tearDown(self):
        for name, value in self.previous.items():
            setattr(core, name, value)
        self.temp_dir.cleanup()

    def test_safe_path_rejects_secrets_and_escape(self):
        with self.assertRaises(ValueError):
            core.safe_path("/etc/passwd")
        with self.assertRaises(ValueError):
            core.safe_path(".env.local")
        with self.assertRaises(ValueError):
            core.safe_path(".ssh/id_ed25519")

    def test_history_is_validated_and_written_private(self):
        core.save_history([
            {"role": "user", "content": "ok"},
            {"role": "system", "content": "discard"},
            {"role": "assistant", "content": "resposta"},
        ])
        self.assertEqual(
            core.load_history(),
            [
                {"role": "user", "content": "ok"},
                {"role": "assistant", "content": "resposta"},
            ],
        )
        mode = stat.S_IMODE(core.HISTORY_FILE.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_memory_requires_confirmation(self):
        denied = core.remember("editor", "neovim", lambda _: False)
        self.assertEqual(denied, {"cancelled": True})
        self.assertFalse(core.MEMORY_FILE.exists())

        saved = core.remember("editor", "neovim", lambda _: True)
        self.assertTrue(saved["success"])
        self.assertEqual(core.recall_memory("NEO")["memory"]["editor"]["value"], "neovim")

    def test_memory_query_tolerates_legacy_values(self):
        core.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        core.MEMORY_FILE.write_text('{"idioma": "pt-BR"}', encoding="utf-8")
        self.assertIn("idioma", core.recall_memory("pt")["memory"])

    def test_git_action_validates_required_argument(self):
        result = core.git_action(str(self.root), "commit", "", lambda _: True)
        self.assertIn("exige um argumento", result["error"])

    def test_write_uses_backup_and_atomic_file(self):
        target = self.root / "notes.txt"
        self.assertEqual(
            core.write_text_file(str(target), "primeiro", lambda _: True)["success"],
            True,
        )
        core.write_text_file(str(target), "segundo", lambda _: True)
        self.assertEqual(target.read_text(encoding="utf-8"), "segundo")
        self.assertEqual(
            target.with_suffix(".txt.jarvis-backup").read_text(encoding="utf-8"),
            "primeiro",
        )


if __name__ == "__main__":
    unittest.main()
