"""Headless interaction tests. Uses a fake agent and never accesses the API."""

import os
import threading
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from jarvis_gui import Window


class FakeAgent:
    def __init__(self):
        self.history = []
        self.release = threading.Event()
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        self.release.wait(3)
        return "**Resposta** de teste", "teste"

    def clear(self):
        self.history.clear()


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.agent = FakeAgent()
        self.window = Window(self.agent)
        self.window.show()
        QTest.qWait(20)

    def tearDown(self):
        self.agent.release.set()
        self.wait_idle()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_idle(self):
        deadline = time.monotonic() + 5
        while self.window.thread is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNone(self.window.thread)

    def test_suggestion_is_draft_and_shift_enter_inserts_newline(self):
        QTest.mouseClick(self.window.suggestions[0], Qt.MouseButton.LeftButton)
        self.assertIn("computador", self.window.input.toPlainText())
        self.assertEqual(self.agent.prompts, [])
        self.window.input.setPlainText("linha")
        QTest.keyClick(self.window.input, Qt.Key.Key_End)
        QTest.keyClick(
            self.window.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier
        )
        self.assertEqual(self.window.input.toPlainText(), "linha\n")

    def test_response_does_not_block_draft_or_allow_unsafe_close(self):
        self.window.input.setPlainText("oi")
        QTest.keyClick(self.window.input, Qt.Key.Key_Return)
        self.assertIsNotNone(self.window.thread)
        self.assertFalse(self.window.send_button.isEnabled())
        self.assertFalse(self.window.new_button.isEnabled())
        self.window.input.setPlainText("próximo pedido")
        self.window.send()
        self.window.close()
        self.assertTrue(self.window.isVisible())
        self.agent.release.set()
        self.wait_idle()
        self.assertEqual(self.agent.prompts, ["oi"])
        self.assertEqual(len(self.window.messages), 2)
        self.assertEqual(self.window.input.toPlainText(), "próximo pedido")
        self.assertTrue(self.window.send_button.isEnabled())
        card = self.window.messages[-1]
        self.assertIn("Resposta", card.body.toPlainText())
        copy = card.findChild(QPushButton)
        copy.click()
        self.assertEqual(self.app.clipboard().text(), "**Resposta** de teste")

    def test_history_and_compact_composer(self):
        self.window.resize(660, 540)
        QTest.qWait(20)
        self.assertFalse(self.window.sidebar.isVisible())
        self.assertTrue(self.window.compact_new.isVisible())
        self.assertTrue(self.window.send_button.isVisible())
        self.assertLessEqual(self.window.height(), 540)
        self.assertGreater(self.window.pages.height(), 100)
        self.assertFalse(self.window.send_button.isEnabled())

    def test_confirmation_bridge_returns_denial_from_main_thread(self):
        def dismiss():
            dialog = self.app.activeModalWidget()
            if isinstance(dialog, QMessageBox):
                dialog.close()
            else:
                QTimer.singleShot(10, dismiss)

        QTimer.singleShot(10, dismiss)
        self.window.start_job(
            lambda: (
                str(self.window.confirmation.ask("Teste de confirmação")),
                "teste",
            ),
            "chat",
        )
        self.wait_idle()
        self.assertEqual(self.window.messages[-1].body.toPlainText().strip(), "False")

    def test_recording_failure_cleans_file_and_keeps_controls_usable(self):
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "test"}),
            patch("jarvis_gui.subprocess.Popen", side_effect=OSError("sem microfone")),
            patch.object(self.window, "show_error") as error,
        ):
            self.window.start_recording()
            error.assert_called_once()
        self.assertIsNone(self.window.recorder)
        self.assertIsNone(self.window.audio_file)
        self.window.input.setPlainText("texto")
        self.assertTrue(self.window.send_button.isEnabled())

    def test_saved_history_is_rendered_and_copy_keeps_original_text(self):
        self.agent.history = [{"role": "assistant", "content": "**Salvo**"}]
        restored = Window(self.agent)
        try:
            self.assertEqual(len(restored.messages), 1)
            self.assertEqual(restored.messages[0].body.toPlainText().strip(), "Salvo")
        finally:
            restored.close()
            restored.deleteLater()

    def test_transcription_keeps_existing_draft(self):
        self.window.input.setPlainText("rascunho")
        self.window.start_job(lambda: ("fala reconhecida", "voz"), "voice")
        self.wait_idle()
        self.assertEqual(self.window.input.toPlainText(), "rascunho\nfala reconhecida")
        self.assertEqual(self.agent.prompts, [])
        self.assertEqual(self.window.messages, [])

    def test_new_conversation_needs_explicit_confirmation(self):
        self.window.append_message("user", "histórico")

        def choose(allow):
            dialog = self.app.activeModalWidget()
            if not isinstance(dialog, QMessageBox):
                QTimer.singleShot(10, lambda: choose(allow))
                return
            for control in dialog.buttons():
                if (control.text() == "Limpar e começar") == allow:
                    control.click()
                    return

        QTimer.singleShot(10, lambda: choose(False))
        self.window.new_conversation()
        self.assertEqual(len(self.window.messages), 1)
        self.window.open_search()
        self.window.search_input.setText("histórico")
        QTimer.singleShot(10, lambda: choose(True))
        self.window.new_conversation()
        self.assertEqual(self.window.messages, [])
        self.assertEqual(self.window.search_matches, [])
        self.assertFalse(self.window.search_bar.isVisible())
        self.assertFalse(self.window.export_action.isEnabled())
        self.assertEqual(self.window.pages.currentWidget(), self.window.welcome_scroll)

    def test_search_navigates_occurrences_and_restores_conversation(self):
        self.window.append_message("user", "Projeto e projeto")
        self.window.append_message("assistant", "**PROJETO** pronto")
        self.window.input.setPlainText("rascunho mantido")
        QTest.keyClick(self.window.input, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.search_bar.isVisible())
        self.window.search_input.setText("projeto")
        self.assertEqual(self.window.search_count.text(), "1 de 3")
        self.assertEqual(len(self.window.messages[0].body.extraSelections()), 2)
        QTest.keyClick(self.window.search_input, Qt.Key.Key_Return)
        self.assertEqual(self.window.search_count.text(), "2 de 3")
        QTest.keyClick(self.window.search_input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.search_count.text(), "1 de 3")
        self.window.search_previous.click()
        self.assertEqual(self.window.search_count.text(), "3 de 3")
        self.window.search_input.setText("ausente")
        self.assertEqual(self.window.search_count.text(), "Nenhum resultado")
        self.assertFalse(self.window.search_next.isEnabled())
        QTest.keyClick(self.window.search_input, Qt.Key.Key_Escape)
        self.assertFalse(self.window.search_bar.isVisible())
        self.assertTrue(all(not card.body.extraSelections() for card in self.window.messages))
        self.assertEqual(self.window.input.toPlainText(), "rascunho mantido")
        self.assertEqual(self.agent.prompts, [])

    def test_search_includes_new_responses_and_scrolls_to_match(self):
        self.window.resize(660, 540)
        self.window.append_message("assistant", "\n\n".join(f"Parágrafo {i}" for i in range(60)))
        self.window.open_search()
        self.window.search_input.setText("encontrado")
        self.window.append_message("assistant", "Alvo encontrado")
        QTest.qWait(100)
        self.assertEqual(self.window.search_count.text(), "1 de 1")
        self.assertGreater(self.window.scroll.verticalScrollBar().value(), 0)
        body, cursor = self.window.search_matches[0]
        point = body.viewport().mapTo(self.window.scroll.viewport(), body.cursorRect(cursor).center())
        self.assertTrue(self.window.scroll.viewport().rect().contains(point))

    def test_pending_auto_scroll_does_not_override_search(self):
        self.window.resize(660, 540)
        self.window.append_message("assistant", "Alvo no início\n\n" + "\n\n".join(f"Parágrafo {i}" for i in range(60)))
        self.window.open_search()
        self.window.search_input.setText("Alvo")
        QTest.qWait(100)
        self.assertGreater(self.window.scroll.verticalScrollBar().maximum(), 500)
        body, cursor = self.window.search_matches[0]
        point = body.viewport().mapTo(self.window.scroll.viewport(), body.cursorRect(cursor).center())
        self.assertTrue(self.window.scroll.viewport().rect().contains(point))

    def test_export_preserves_original_markdown_and_all_displayed_messages(self):
        self.assertFalse(self.window.export_action.isEnabled())
        self.window.append_message("user", "Explique ação e memória")
        markdown = "**Exemplo**\n\n```python\nprint('olá')\n```"
        self.window.append_message("assistant", markdown)
        self.window.open_search()
        self.window.search_input.setText("ausente")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "conversa.md"
            with patch("jarvis_gui.QFileDialog.getSaveFileName", return_value=(str(target), "")):
                self.window.export_conversation()
            self.assertEqual(target.read_text(), "# Conversa com Jarvis\n\n## Você\n\nExplique ação e memória\n\n---\n\n## Jarvis\n\n" + markdown + "\n")
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_cancelled_and_failed_exports_keep_conversation(self):
        self.window.append_message("user", "preservar")
        with (
            patch("jarvis_gui.QFileDialog.getSaveFileName", return_value=("", "")),
            patch("jarvis_gui._atomic_write") as write,
        ):
            self.window.export_conversation()
            write.assert_not_called()
        with (
            patch("jarvis_gui.QFileDialog.getSaveFileName", return_value=("/unused.md", "")),
            patch("jarvis_gui._atomic_write", side_effect=OSError("sem espaço")),
            patch.object(self.window, "show_error") as error,
        ):
            self.window.export_conversation()
            error.assert_called_once()
        self.assertEqual(len(self.window.messages), 1)
        self.assertEqual(self.window.messages[0].original_text, "preservar")


if __name__ == "__main__":
    unittest.main()
