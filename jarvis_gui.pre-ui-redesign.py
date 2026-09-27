import signal
import subprocess
import tempfile
import threading
from pathlib import Path

from groq import Groq
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core import Jarvis


class ConfirmationBridge(QObject):
    """Permite confirmar ações do agente no thread seguro da interface."""

    requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event = threading.Event()
        self._result = False
        self._lock = threading.Lock()
        self.requested.connect(self._show, Qt.ConnectionType.QueuedConnection)

    def ask(self, text):
        with self._lock:
            self._result = False
            self._event.clear()
            self.requested.emit(text)
            self._event.wait(timeout=300)
            return self._result

    @Slot(str)
    def _show(self, text):
        result = QMessageBox.question(
            None,
            "Jarvis pede autorização",
            text,
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        self._result = result == QMessageBox.StandardButton.Yes
        self._event.set()


class AskWorker(QObject):
    finished = Signal(str, str)

    def __init__(self, agent, prompt):
        super().__init__()
        self.agent = agent
        self.prompt = prompt

    @Slot()
    def run(self):
        try:
            answer, backend = self.agent.ask(self.prompt)
        except Exception as error:  # noqa: BLE001 - report worker failures
            answer, backend = f"Erro inesperado: {error}", "erro"
        self.finished.emit(answer, backend)


class Window(QWidget):

    def __init__(self):

        super().__init__()

        self.recorder = None
        self.audio_file = None
        self.thread = None
        self.worker = None

        self.setWindowTitle("Jarvis")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        self.resize(760, 520)

        self.confirmation = ConfirmationBridge(self)
        self.agent = Jarvis(self.confirmation.ask)

        self.build_ui()

        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry()

        self.move(
            geo.center().x() - self.width() // 2,
            geo.center().y() - self.height() // 2
        )


    def build_ui(self):

        root = QWidget(self)
        root.setObjectName("root")

        root.setStyleSheet("""
        QWidget#root {
            background: #1e1e2e;
            border: 1px solid #45475a;
            border-radius: 18px;
        }

        QLabel {
            color: #cdd6f4;
        }

        QTextBrowser {
            background: #181825;
            color: #cdd6f4;
            border: none;
            border-radius: 12px;
            padding: 12px;
            font-size: 14px;
        }

        QLineEdit {
            background: #313244;
            color: #cdd6f4;
            border: 1px solid #45475a;
            border-radius: 10px;
            padding: 12px;
            font-size: 14px;
        }

        QPushButton {
            background: #45475a;
            color: #cdd6f4;
            border: none;
            border-radius: 10px;
            padding: 10px 16px;
        }

        QPushButton:hover {
            background: #585b70;
        }

        QPushButton#send {
            background: #cba6f7;
            color: #11111b;
            font-weight: bold;
        }

        QPushButton#mic {
            background: #f38ba8;
            color: #11111b;
        }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(
            18,18,18,18
        )

        # Header

        header = QHBoxLayout()

        title = QLabel(
            "◉  JARVIS"
        )

        title.setStyleSheet(
            "font-size: 18px; font-weight: bold;"
        )

        self.status = QLabel(
            "Groq · GPT-OSS 120B"
        )

        self.status.setStyleSheet(
            "color: #a6adc8;"
        )

        close = QPushButton("✕")
        close.setFixedWidth(40)
        close.clicked.connect(self.close)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        header.addWidget(close)

        layout.addLayout(header)

        # Chat

        self.chat = QTextBrowser()

        self.chat.setHtml(
            "<b>Jarvis:</b> Online. O que fazemos?"
        )

        layout.addWidget(self.chat, 1)

        # Input

        row = QHBoxLayout()

        self.input = QLineEdit()

        self.input.setPlaceholderText(
            "Digite uma ordem ou pergunta..."
        )

        self.input.returnPressed.connect(
            self.send
        )

        mic = QPushButton("🎙")
        mic.setObjectName("mic")
        mic.setToolTip(
            "Segure para falar"
        )

        mic.pressed.connect(
            self.start_recording
        )

        mic.released.connect(
            self.stop_recording
        )

        send = QPushButton("Enviar")
        send.setObjectName("send")
        send.clicked.connect(self.send)

        row.addWidget(self.input, 1)
        row.addWidget(mic)
        row.addWidget(send)

        layout.addLayout(row)

        self.input.setFocus()


    def confirm_action(self, text):

        result = QMessageBox.question(
            self,
            "Jarvis pede autorização",
            text,
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        return (
            result ==
            QMessageBox.StandardButton.Yes
        )


    def append(self, speaker, text):

        safe = (
            text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

        self.chat.append(
            f"<p><b>{speaker}:</b><br>{safe}</p>"
        )

        self.chat.verticalScrollBar().setValue(
            self.chat.verticalScrollBar().maximum()
        )


    def send(self):

        if self.thread is not None:
            return

        prompt = self.input.text().strip()

        if not prompt:
            return

        self.input.clear()

        self.append(
            "Você",
            prompt
        )

        self.status.setText("Pensando...")
        self.input.setEnabled(False)

        self.thread = QThread(self)
        self.worker = AskWorker(self.agent, prompt)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_answer)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.start()


    @Slot(str, str)
    def on_answer(self, answer, backend):
        self.append("Jarvis", answer)
        self.status.setText(backend)


    @Slot()
    def on_thread_finished(self):
        self.thread = None
        self.worker = None
        self.input.setEnabled(True)
        self.input.setFocus()


    def start_recording(self):

        if self.recorder:
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            self.audio_file = Path(tmp.name)

        try:

            self.recorder = subprocess.Popen(
                [
                    "pw-record",
                    str(self.audio_file)
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.status.setText(
                "🎙 Ouvindo..."
            )

        except Exception as e:  # noqa: BLE001 - report recorder failures
            self.audio_file.unlink(missing_ok=True)
            self.audio_file = None
            self.status.setText(
                f"Erro no microfone: {e}"
            )


    def stop_recording(self):

        if not self.recorder:
            return

        try:

            self.recorder.send_signal(
                signal.SIGINT
            )

            self.recorder.wait(
                timeout=3
            )

        except Exception:  # noqa: BLE001 - terminate a failed recorder

            self.recorder.kill()

        self.recorder = None

        QApplication.processEvents()

        self.status.setText(
            "Transcrevendo..."
        )

        QApplication.processEvents()

        try:

            client = Groq()

            with open(
                self.audio_file,
                "rb"
            ) as audio:

                result = (
                    client.audio.transcriptions.create(
                        file=audio,
                        model="whisper-large-v3-turbo",
                        language="pt",
                        response_format="text"
                    )
                )

            text = (
                result
                if isinstance(result, str)
                else str(result)
            )

            self.input.setText(
                text.strip()
            )

            self.status.setText(
                "Voz reconhecida"
            )

        except Exception as e:  # noqa: BLE001 - report transcription failures

            self.status.setText(
                f"Erro STT: {e}"
            )

        finally:

            try:
                self.audio_file.unlink(
                    missing_ok=True
                )
            except OSError:
                pass


    def keyPressEvent(self, event):

        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return

        super().keyPressEvent(event)


def main():
    app = QApplication([])
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
