import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis_arch import context


class ContextTests(unittest.TestCase):
    def test_active_window_uses_kdotool_when_available(self):
        def fake_which(name):
            return "/usr/bin/" + name if name == "kdotool" else None

        def fake_run(command, **_):
            if command == ["kdotool", "getactivewindow"]:
                return "42"
            if command == ["kdotool", "getactivewindow", "getwindowname"]:
                return "VS Code — projeto"
            return None

        with (
            patch("jarvis_arch.context.shutil.which", side_effect=fake_which),
            patch("jarvis_arch.context._run", side_effect=fake_run),
        ):
            result = context.active_window()

        self.assertEqual(result["source"], "kdotool")
        self.assertEqual(result["id"], "42")
        self.assertIn("VS Code", result["title"])

    def test_clipboard_is_bounded_and_marked_untrusted(self):
        with patch(
            "jarvis_arch.context._first_available",
            return_value="x" * 2000,
        ):
            result = context.clipboard_preview(limit=100)

        self.assertTrue(result["available"])
        self.assertEqual(len(result["content"]), 100)
        self.assertTrue(result["truncated"])
        self.assertTrue(result["untrusted_external_content"])

    def test_recent_projects_returns_git_context(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            repo = home / "Projects" / "demo"
            repo.mkdir(parents=True)
            (repo / ".git").mkdir()
            with patch(
                "jarvis_arch.context._git_info",
                return_value={
                    "path": str(repo),
                    "branch": "main",
                    "dirty": False,
                    "changes": [],
                },
            ):
                projects = context.recent_projects(home)

        self.assertEqual(projects[0]["branch"], "main")

    def test_workstation_context_does_not_read_clipboard_by_default(self):
        with (
            patch("jarvis_arch.context.kde_context", return_value={"session_type": "wayland"}),
            patch("jarvis_arch.context.active_window", return_value={"title": "Code"}),
            patch("jarvis_arch.context.media_context", return_value={"available": False}),
            patch("jarvis_arch.context.user_services", return_value={"jarvis": "active"}),
            patch("jarvis_arch.context.process_context", return_value={"vscode": ["1 code"]}),
            patch("jarvis_arch.context.recent_projects", return_value=[]),
            patch("jarvis_arch.context.clipboard_preview") as clipboard,
        ):
            result = context.workstation_context(Path.home())

        clipboard.assert_not_called()
        self.assertNotIn("clipboard", result)
        self.assertEqual(result["active_window"]["title"], "Code")

    def test_project_context_reports_non_git_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("jarvis_arch.context._git_info", return_value=None):
                result = context.project_context(Path(directory))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
