"""SQLite-backed persistent memory and conversation history."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_created
                    ON conversation(created_at, id);
                """
            )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def load_history(self, limit: int = 40) -> list[dict[str, str]]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM conversation
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (limit,),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def replace_history(self, history: list[dict[str, str]], limit: int = 40) -> None:
        valid = [
            item
            for item in history[-limit:]
            if isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ]
        now = int(time.time())
        with self._connect() as db:
            db.execute("DELETE FROM conversation")
            db.executemany(
                "INSERT INTO conversation(role, content, created_at) VALUES (?, ?, ?)",
                [(item["role"], item["content"], now + index) for index, item in enumerate(valid)],
            )

    def load_memory(self, query: str = "") -> dict[str, dict[str, Any]]:
        query = str(query or "").strip().lower()
        with self._connect() as db:
            if query:
                pattern = f"%{query}%"
                rows = db.execute(
                    """
                    SELECT key, value, updated_at
                    FROM memory
                    WHERE lower(key) LIKE ? OR lower(value) LIKE ?
                    ORDER BY updated_at DESC, key
                    """,
                    (pattern, pattern),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT key, value, updated_at FROM memory ORDER BY updated_at DESC, key"
                ).fetchall()
        return {
            row["key"]: {"value": row["value"], "updated_at": row["updated_at"]}
            for row in rows
        }

    def remember(self, key: str, value: str, updated_at: int | None = None) -> None:
        timestamp = int(updated_at or time.time())
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO memory(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, timestamp),
            )

    def replace_memory(self, memory: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM memory")
        for key, item in memory.items():
            if isinstance(item, dict):
                value = item.get("value", "")
                updated_at = item.get("updated_at")
            else:
                value = item
                updated_at = None
            self.remember(str(key), str(value), updated_at)

    def migrate_legacy(self, history_file: Path, memory_file: Path, limit: int = 40) -> dict[str, int]:
        migrated = {"history": 0, "memory": 0}
        with self._connect() as db:
            history_count = db.execute("SELECT COUNT(*) FROM conversation").fetchone()[0]
            memory_count = db.execute("SELECT COUNT(*) FROM memory").fetchone()[0]

        if history_count == 0 and history_file.exists():
            try:
                raw = json.loads(history_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self.replace_history(raw, limit)
                    migrated["history"] = len(self.load_history(limit))
            except (OSError, ValueError, TypeError):
                pass

        if memory_count == 0 and memory_file.exists():
            try:
                raw = json.loads(memory_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.replace_memory(raw)
                    migrated["memory"] = len(self.load_memory())
            except (OSError, ValueError, TypeError):
                pass

        return migrated
