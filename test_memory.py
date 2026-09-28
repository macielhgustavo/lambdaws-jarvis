import json
import stat
import tempfile
import unittest
from pathlib import Path

from jarvis_arch.memory import MemoryStore


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = MemoryStore(self.root / "jarvis.db")

    def tearDown(self):
        self.temp.cleanup()

    def test_memory_round_trip_and_case_insensitive_search(self):
        self.store.remember("Editor", "Neovim")
        self.store.remember("Idioma", "pt-BR")
        result = self.store.load_memory("NEO")
        self.assertEqual(result["Editor"]["value"], "Neovim")
        self.assertNotIn("Idioma", result)

    def test_history_keeps_order_and_limit(self):
        history = [
            {"role": "user", "content": f"u-{i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"a-{i}"}
            for i in range(8)
        ]
        self.store.replace_history(history, limit=4)
        loaded = self.store.load_history(10)
        self.assertEqual(len(loaded), 4)
        self.assertEqual(loaded[0]["content"], "u-4")
        self.assertEqual(loaded[-1]["content"], "a-7")

    def test_legacy_json_is_migrated_only_into_empty_tables(self):
        history_file = self.root / "history.json"
        memory_file = self.root / "memory.json"
        history_file.write_text(
            json.dumps([
                {"role": "user", "content": "antigo"},
                {"role": "assistant", "content": "resposta"},
            ]),
            encoding="utf-8",
        )
        memory_file.write_text(
            json.dumps({"tema": {"value": "energia", "updated_at": 123}}),
            encoding="utf-8",
        )

        migrated = self.store.migrate_legacy(history_file, memory_file)
        self.assertEqual(migrated, {"history": 2, "memory": 1})
        self.assertEqual(self.store.load_history()[-1]["content"], "resposta")
        self.assertEqual(self.store.load_memory()["tema"]["value"], "energia")

        history_file.write_text("[]", encoding="utf-8")
        memory_file.write_text("{}", encoding="utf-8")
        migrated_again = self.store.migrate_legacy(history_file, memory_file)
        self.assertEqual(migrated_again, {"history": 0, "memory": 0})
        self.assertIn("tema", self.store.load_memory())

    def test_database_is_private(self):
        mode = stat.S_IMODE((self.root / "jarvis.db").stat().st_mode)
        self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
