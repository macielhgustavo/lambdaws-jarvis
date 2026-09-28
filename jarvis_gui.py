"""Jarvis desktop: native Qt interface and background network operations."""

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

from groq import Groq
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut, QTextDocument, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import VERSION, Jarvis, recall_memory, _atomic_write
from jarvis_arch.client import connect_remote

STYLE = """
QWidget { background: #090e1c; color: #e9f2ff; font-family: "Inter", "Noto Sans", "DejaVu Sans"; font-size: 13px; }
QWidget#sidebar { background: #0b1224; border-right: 1px solid #24344d; }
QLabel { background: transparent; }
QLabel#brand { color: #eafaff; font-size: 22px; font-weight: 800; letter-spacing: 3px; }
QLabel#eyebrow { color: #69dbe9; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#muted { color: #9caec7; font-size: 12px; }
QLabel#hero { color: #f3f8ff; font-size: 36px; font-weight: 700; }
QLabel#sectionTitle { color: #e8f4ff; font-size: 16px; font-weight: 700; }
QLabel#badge { background: #123a43; color: #8df7df; border: 1px solid #286b71; border-radius: 10px; padding: 7px 12px; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QPushButton { background: #151f35; color: #dcecff; border: 1px solid #2d405c; border-radius: 11px; padding: 10px 14px; text-align: left; }
QPushButton:hover { background: #203252; border-color: #67d9f0; color: #ffffff; }
QPushButton:pressed { background: #2a4267; }
QPushButton:focus { border: 1px solid #9aeefa; }
QPushButton:disabled { color: #70819b; background: #111a2b; border-color: #243047; }
QPushButton#primary { background: #8cecf3; color: #092030; border-color: #a8f4f7; font-weight: 800; text-align: center; }
QPushButton#primary:hover { background: #c0f8f8; border-color: #ffffff; }
QPushButton#primary:disabled { background: #26404b; color: #819eaa; border-color: #26404b; }
QPushButton#quiet { background: transparent; border-color: transparent; color: #a8bed6; }
QPushButton#quiet:hover { background: #1b2a44; color: #f3fcff; }
QPushButton#nav { background: #193147; color: #9ff4f3; border-color: #36647a; }
QPushButton#card { background: #111e35; border: 1px solid #2a4563; border-radius: 16px; padding: 20px; font-size: 13px; font-weight: 600; }
QPushButton#card:hover { background: #1c3152; border-color: #7ce4f5; }
QPushButton#recording { background: #552a4d; color: #ffe0ee; border-color: #ee8ac3; }
QFrame#composer { background: #121f35; border: 1px solid #426583; border-radius: 18px; }
QFrame#assistant { background: #121d32; border: 1px solid #2c4966; border-radius: 16px; }
QFrame#user { background: #1d2e4b; border: 1px solid #3b617f; border-radius: 16px; }
QPlainTextEdit { background: transparent; border: none; padding: 5px; color: #eff8ff; font-size: 14px; selection-background-color: #315d80; }
QTextBrowser { background: transparent; border: none; color: #e7f1fc; font-size: 14px; selection-background-color: #315d80; }
QLineEdit { background: #15243a; border: 1px solid #34516e; border-radius: 10px; padding: 9px; color: #eefaff; }
QLineEdit:focus { border-color: #89eafa; }
QScrollArea, QStackedWidget { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: #395673; border-radius: 3px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { border: none; background: #1e344e; max-height: 3px; }
QProgressBar::chunk { background: #7deaf3; }
QMenu { background: #14233a; border: 1px solid #45617e; padding: 6px; }
QMenu::item { padding: 8px 16px; }
QMenu::item:selected { background: #285071; }
QToolTip { color: #effaff; background: #1b3651; border: 1px solid #559ab0; padding: 6px; }
"""


class NeuralOrb(QWidget):
    """Lightweight painted animation; no network or GPU dependency."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(138, 138)
        self._phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def tick(self):
        if self.isVisible():
            self._phase = (self._phase + 0.025) % 6.283
            self.update()

    def paintEvent(self, event):
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        halo = QRadialGradient(center, 66)
        halo.setColorAt(0, QColor(58, 207, 238, 85))
        halo.setColorAt(0.48, QColor(91, 112, 237, 37))
        halo.setColorAt(1, QColor(9, 14, 28, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        for radius, width, alpha in ((51, 1, 90), (39, 2, 135), (26, 2, 205)):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(123, 219, 249, alpha), width))
            painter.drawEllipse(center, radius, radius)
        for offset in (0, 2.094, 4.188):
            angle = self._phase + offset
            radius = 39
            x = center.x() + math.cos(angle) * radius
            y = center.y() + math.sin(angle) * radius
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#a0faff'))
            painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)
        core = QRadialGradient(center, 25)
        core.setColorAt(0, QColor('#efffff'))
        core.setColorAt(0.38, QColor('#87eafa'))
        core.setColorAt(1, QColor('#4261d5'))
        painter.setBrush(core)
        painter.drawEllipse(center, 20, 20)



def label(text, name="muted"):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


def button(text, callback, name="quiet", tip=None):
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(callback)
    widget.setAccessibleName(text)
    if tip:
        widget.setToolTip(tip)
    return widget


class Composer(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class MessageBody(QTextBrowser):
    """Markdown with no automatic file/image loads from generated content."""

    def __init__(self, text, markdown=False):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self.open_link)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().setDefaultStyleSheet(
            "pre { background-color: #0b1728; color: #d2f4ff; white-space: pre-wrap; }"
            "code { font-family: monospace; color: #9deffa; }"
            "a { color: #84e9fa; } p { margin-top: 6px; margin-bottom: 10px; }"
        )
        if markdown:
            self.document().setMarkdown(
                text, QTextDocument.MarkdownFeature.MarkdownNoHTML
            )
        else:
            self.setPlainText(text)
        self.document().documentLayout().documentSizeChanged.connect(self.fit_height)

    def loadResource(self, resource_type, url):
        return None

    @Slot()
    def fit_height(self, *_):
        height = int(self.document().size().height()) + 12
        if self.height() != max(38, height):
            self.setFixedHeight(max(38, height))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(max(100, self.viewport().width()))
        self.fit_height()

    @Slot(object)
    def open_link(self, url):
        if url.scheme() in {"https", "http"} and url.host():
            QDesktopServices.openUrl(url)


class MessageCard(QFrame):
    def __init__(self, role, text):
        super().__init__()
        self.role = role
        self.original_text = text
        self.setObjectName("user" if role == "user" else "assistant")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 16)
        heading = QHBoxLayout()
        heading.addWidget(label("VOCÊ" if role == "user" else "JARVIS", "eyebrow"))
        heading.addStretch()
        copy = button("Copiar", lambda: self.copy_text(text, copy))
        copy.setAccessibleName("Copiar mensagem")
        heading.addWidget(copy)
        layout.addLayout(heading)
        self.body = MessageBody(text, markdown=role == "assistant")
        layout.addWidget(self.body)

    def copy_text(self, text, control):
        QApplication.clipboard().setText(text)
        control.setText("Copiado")
        QTimer.singleShot(1800, control, lambda: control.setText("Copiar"))


class ConfirmationBridge(QObject):
    requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event = threading.Event()
        self._result = False
        self.requested.connect(
            self.show_confirmation, Qt.ConnectionType.QueuedConnection
        )

    def ask(self, text):
        self._result = False
        self._event.clear()
        self.requested.emit(text)
        self._event.wait()
        return self._result

    @Slot(str)
    def show_confirmation(self, text):
        dialog = QMessageBox(self.parent())
        dialog.setWindowTitle("Revisar ação")
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText("O Jarvis precisa da sua autorização.")
        dialog.setInformativeText(text)
        allow = dialog.addButton("Autorizar ação", QMessageBox.ButtonRole.AcceptRole)
        deny = dialog.addButton("Não autorizar", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(deny)
        dialog.exec()
        self._result = dialog.clickedButton() is allow
        self._event.set()


class Worker(QObject):
    finished = Signal(str, str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    @Slot()
    def run(self):
        try:
            text, backend = self.operation()
        except Exception as error:  # noqa: BLE001 - UI must recover after worker errors
            text, backend = str(error), "erro"
        self.finished.emit(text, backend)


class Window(QWidget):
    def __init__(self, agent=None):
        super().__init__()
        self.thread = None
        self.worker = None
        self.recorder = None
        self.audio_file = None
        self.job = None
        self.started_at = 0
        self.messages = []
        self.search_matches = []
        self.search_index = -1
        self.setWindowTitle("Jarvis · Assistente pessoal")
        self.setMinimumSize(660, 540)
        self.resize(1120, 800)
        self.setStyleSheet(STYLE)
        self.confirmation = ConfirmationBridge(self)
        if agent is not None:
            self.agent = agent
        else:
            self.agent = (
                connect_remote(self.confirmation.ask)
                or Jarvis(self.confirmation.ask)
            )
        self.build_ui()
        self.pulse = QTimer(self)
        self.pulse.setInterval(1000)
        self.pulse.timeout.connect(self.update_elapsed)
        self.record_limit = QTimer(self)
        self.record_limit.setSingleShot(True)
        self.record_limit.timeout.connect(self.stop_recording)
        for sequence, callback in (
            ("Ctrl+L", self.input.setFocus),
            ("Ctrl+N", self.new_conversation),
            ("Ctrl+F", self.open_search),
            ("Ctrl+Shift+S", self.export_conversation),
            ("Ctrl+Shift+M", self.toggle_recording),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        for item in self.agent.history[-40:]:
            if item.get("role") in {"user", "assistant"}:
                self.append_message(item["role"], item.get("content", ""))
        self.refresh_controls()
        self.input.setFocus()
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.resize(min(1120, area.width()), min(800, area.height() - 40))
            self.move(area.center() - self.rect().center())

    def build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(22, 30, 22, 24)
        side.setSpacing(12)
        side.addWidget(label("◈  JARVIS", "brand"))
        side.addWidget(label("LAMBDAWS  /  NEURAL OS", "eyebrow"))
        side.addSpacing(28)
        self.new_button = button(
            "+  Nova conversa",
            self.new_conversation,
            "primary",
            "Limpar a conversa atual · Ctrl+N",
        )
        side.addWidget(self.new_button)
        side.addSpacing(22)
        side.addWidget(label("CENTRAL DE COMANDO", "eyebrow"))
        side.addWidget(button("◉  Conversa", lambda: self.input.setFocus(), "nav"))
        side.addWidget(button("◇  Memória", self.show_memory))
        side.addWidget(button("⌘  Atalhos", self.show_shortcuts))
        side.addStretch()
        side.addWidget(label("SISTEMA ONLINE", "sectionTitle"))
        side.addWidget(label("Alterações em arquivos e Git\nsão revisadas por você."))
        side.addSpacing(20)
        side.addWidget(label(f"LAMBDAWS   /   V{VERSION.split('.')[0]}", "eyebrow"))
        outer.addWidget(self.sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(30, 24, 30, 18)
        main.setSpacing(16)
        outer.addLayout(main, 1)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label("Central de inteligência", "sectionTitle"))
        titles.addWidget(label("Sua workstation, projetos e ideias em sintonia."))
        header.addLayout(titles, 1)
        self.badge = label("●  SISTEMA PRONTO", "badge")
        header.addWidget(self.badge)
        self.compact_new = button(
            "+ Nova", self.new_conversation, tip="Nova conversa · Ctrl+N"
        )
        header.addWidget(self.compact_new)
        options = QPushButton("⋯")
        options.setAccessibleName("Opções da conversa")
        options.setToolTip("Buscar, exportar, memória e atalhos")
        menu = QMenu(options)
        menu.addAction("Buscar na conversa · Ctrl+F", self.open_search)
        self.export_action = menu.addAction(
            "Exportar conversa · Ctrl+Shift+S", self.export_conversation
        )
        menu.addSeparator()
        menu.addAction("Sua memória", self.show_memory)
        menu.addAction("Atalhos", self.show_shortcuts)
        menu.addSeparator()
        pin = menu.addAction("Manter acima das outras janelas")
        pin.setCheckable(True)
        pin.toggled.connect(self.set_pinned)
        options.setMenu(menu)
        header.addWidget(options)
        main.addLayout(header)

        self.search_bar = QWidget()
        search = QHBoxLayout(self.search_bar)
        search.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar na conversa…")
        self.search_input.setAccessibleName("Buscar na conversa")
        self.search_input.textChanged.connect(self.update_search)
        self.search_input.returnPressed.connect(lambda: self.move_search(1))
        search.addWidget(self.search_input, 1)
        self.search_count = label("Digite para buscar")
        search.addWidget(self.search_count)
        self.search_previous = button("↑", lambda: self.move_search(-1), tip="Anterior · Shift+Enter")
        self.search_next = button("↓", lambda: self.move_search(1), tip="Próxima · Enter")
        self.search_previous.setAccessibleName("Ocorrência anterior")
        self.search_next.setAccessibleName("Próxima ocorrência")
        search.addWidget(self.search_previous)
        search.addWidget(self.search_next)
        search.addWidget(button("Fechar", self.close_search, tip="Fechar busca · Esc"))
        for sequence, callback in (("Escape", self.close_search), ("Shift+Return", lambda: self.move_search(-1))):
            shortcut = QShortcut(QKeySequence(sequence), self.search_bar)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
        self.search_bar.hide()
        main.addWidget(self.search_bar)

        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)
        self.welcome = QWidget()
        welcome = QVBoxLayout(self.welcome)
        welcome.setContentsMargins(12, 16, 12, 16)
        welcome.setSpacing(16)
        welcome.addStretch()
        self.orb = NeuralOrb()
        welcome.addWidget(self.orb)
        welcome.addWidget(label("LAMBDAWS  /  INTERFACE NEURAL", "eyebrow"))
        welcome.addWidget(label("O futuro começa aqui.", "hero"))
        welcome.addWidget(
            label(
                "Um espaço para pensar, criar e comandar.\n"
                "Escolha uma direção ou comece sua própria conversa."
            )
        )
        cards = QGridLayout()
        cards.setSpacing(12)
        self.suggestions = []
        suggestions = (
            (
                "01  /  EXPLORAR",
                "Como está meu computador?",
                "Verifique as informações reais do meu computador e resuma o estado atual.",
            ),
            (
                "02  /  CONSTRUIR",
                "Avançar em um projeto",
                "Quero avançar em um projeto. Liste as pastas em Projects para começarmos.",
            ),
            (
                "03  /  APRENDER",
                "Entender algo novo",
                "Quero estudar um assunto. Pergunte o tema e meu nível antes de explicar.",
            ),
            (
                "04  /  ORGANIZAR",
                "Planejar meu próximo passo",
                "Me ajude a organizar as prioridades de hoje. Comece perguntando o que preciso fazer.",
            ),
        )
        for index, (category, title, prompt) in enumerate(suggestions):
            control = button(
                f"{category}\n\n{title}  ↗",
                lambda checked=False, p=prompt: self.fill_prompt(p),
                "card",
            )
            control.setMinimumHeight(100)
            cards.addWidget(control, index // 2, index % 2)
            self.suggestions.append(control)
        welcome.addLayout(cards)
        welcome.addStretch()
        self.welcome_scroll = QScrollArea()
        self.welcome_scroll.setWidgetResizable(True)
        self.welcome_scroll.setWidget(self.welcome)
        self.welcome_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.pages.addWidget(self.welcome_scroll)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.transcript = QWidget()
        self.message_layout = QVBoxLayout(self.transcript)
        self.message_layout.setContentsMargins(0, 4, 8, 10)
        self.message_layout.setSpacing(16)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.transcript)
        self.pages.addWidget(self.scroll)
        self.to_bottom = button("↓  Ir para a última mensagem", self.scroll_to_bottom)
        self.to_bottom.hide()
        main.addWidget(self.to_bottom, 0, Qt.AlignmentFlag.AlignRight)
        self.scroll.verticalScrollBar().valueChanged.connect(self.update_scroll_hint)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda *_: QTimer.singleShot(0, self.reveal_search_match)
        )

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        main.addWidget(self.progress)
        composer = QFrame()
        composer.setObjectName("composer")
        compose = QVBoxLayout(composer)
        compose.setContentsMargins(14, 12, 14, 12)
        self.input = Composer()
        self.input.setAccessibleName("Mensagem para o Jarvis")
        self.input.setPlaceholderText("O que vamos construir hoje?")
        self.input.setFixedHeight(74)
        self.input.submitted.connect(self.send)
        self.input.textChanged.connect(self.refresh_controls)
        compose.addWidget(self.input)
        controls = QHBoxLayout()
        self.mic = button(
            "◉  Usar voz", self.toggle_recording, tip="Gravar / parar · Ctrl+Shift+M"
        )
        controls.addWidget(self.mic)
        controls.addStretch()
        self.send_button = button("Enviar  ↑", self.send, "primary")
        controls.addWidget(self.send_button)
        compose.addLayout(controls)
        main.addWidget(composer)
        footer = QHBoxLayout()
        self.status = label("Pronto para começar")
        self.status.setAccessibleName("Estado do Jarvis")
        footer.addWidget(self.status, 1)
        self.key_hint = label("Enter envia  ·  Shift+Enter quebra linha")
        self.key_hint.setWordWrap(False)
        footer.addWidget(self.key_hint)
        main.addLayout(footer)

    def fill_prompt(self, prompt):
        self.input.setPlainText(prompt)
        self.input.setFocus()

    def set_pinned(self, enabled):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()

    def append_message(self, role, text):
        bar = self.scroll.verticalScrollBar()
        at_bottom = bar.maximum() - bar.value() < 80
        card = MessageCard(role, text)
        self.messages.append(card)
        self.message_layout.insertWidget(self.message_layout.count() - 1, card)
        self.pages.setCurrentWidget(self.scroll)
        if not QApplication.instance().property("reduceMotion"):
            effect = QGraphicsOpacityEffect(card)
            card.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", card)
            animation.setDuration(280)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            card._entrance_animation = animation
            animation.start()
        self.export_action.setEnabled(True)
        if not self.search_bar.isHidden():
            self.update_search()
        elif at_bottom or role == "user":
            QTimer.singleShot(50, self.follow_latest_message)
        else:
            self.to_bottom.show()

    def follow_latest_message(self):
        if self.search_bar.isHidden():
            self.scroll_to_bottom()

    def open_search(self):
        self.search_bar.show()
        self.update_search()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def close_search(self):
        self.search_input.clear()
        self.search_bar.hide()
        self.input.setFocus()

    def update_search(self):
        query = self.search_input.text()
        self.search_matches = []
        for card in self.messages:
            if query:
                cursor = card.body.document().find(query)
                while not cursor.isNull():
                    self.search_matches.append((card.body, cursor))
                    cursor = card.body.document().find(query, cursor)
        self.search_index = 0 if self.search_matches else -1
        self.render_search()

    def move_search(self, step):
        if self.search_matches:
            self.search_index = (self.search_index + step) % len(self.search_matches)
            self.render_search()

    def render_search(self):
        highlights = {card.body: [] for card in self.messages}
        for index, (body, cursor) in enumerate(self.search_matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setBackground(QColor("#b4e8c6" if index == self.search_index else "#405e49"))
            selection.format.setForeground(QColor("#111617" if index == self.search_index else "#ffffff"))
            highlights[body].append(selection)
        for body, selections in highlights.items():
            body.setExtraSelections(selections)
        found = bool(self.search_matches)
        self.search_previous.setEnabled(found)
        self.search_next.setEnabled(found)
        self.search_count.setText(
            f"{self.search_index + 1} de {len(self.search_matches)}" if found
            else "Nenhum resultado" if self.search_input.text() else "Digite para buscar"
        )
        if found:
            QTimer.singleShot(0, self.reveal_search_match)

    def reveal_search_match(self):
        if self.search_index < 0 or self.search_bar.isHidden():
            return
        body, cursor = self.search_matches[self.search_index]
        position = body.viewport().mapTo(self.transcript, body.cursorRect(cursor).center())
        self.scroll.ensureVisible(position.x(), position.y(), 0, 60)

    def export_conversation(self):
        if not self.messages:
            self.status.setText("Envie uma mensagem antes de exportar a conversa.")
            return
        # Capture what was visible when export was requested, even if a reply arrives.
        content = "# Conversa com Jarvis\n\n" + "\n\n---\n\n".join(
            f"## {'Você' if card.role == 'user' else 'Jarvis'}\n\n{card.original_text}"
            for card in self.messages
        ) + "\n"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exportar conversa", f"jarvis-{datetime.now():%Y%m%d-%H%M%S}.md",
            "Markdown (*.md)",
        )
        if not filename:
            return
        try:
            _atomic_write(Path(filename), content)
        except OSError as error:
            self.show_error("Não foi possível exportar a conversa", str(error))
            return
        self.status.setText(f"Conversa exportada: {Path(filename).name}")

    def scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.to_bottom.hide()

    def update_scroll_hint(self):
        bar = self.scroll.verticalScrollBar()
        self.to_bottom.setVisible(bar.maximum() - bar.value() > 100)

    def refresh_controls(self):
        if not hasattr(self, "send_button"):
            return
        busy = self.thread is not None or self.recorder is not None
        self.send_button.setEnabled(bool(self.input.toPlainText().strip()) and not busy)
        self.new_button.setEnabled(not busy)
        self.compact_new.setEnabled(not busy)
        self.export_action.setEnabled(bool(self.messages))
        self.mic.setEnabled(
            self.thread is None and shutil.which("pw-record") is not None
        )
        if not shutil.which("pw-record"):
            self.mic.setToolTip("Instale pipewire-utils para usar o microfone.")

    def start_job(self, operation, job):
        self.job = job
        self.started_at = time.monotonic()
        self.thread = QThread(self)
        self.worker = Worker(operation)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_result)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.job_finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.progress.show()
        self.badge.setText("TRANSCREVENDO" if job == "voice" else "PENSANDO")
        self.update_elapsed()
        self.pulse.start()
        self.refresh_controls()
        self.thread.start()

    def send(self):
        if self.thread is not None or self.recorder is not None:
            return
        prompt = self.input.toPlainText().strip()
        if not prompt:
            return
        self.input.clear()
        self.append_message("user", prompt)
        self.start_job(lambda: self.agent.ask(prompt), "chat")

    @Slot(str, str)
    def on_result(self, text, backend):
        self.pulse.stop()
        self.progress.hide()
        elapsed = max(1, int(time.monotonic() - self.started_at))
        if self.job == "voice":
            if backend == "erro":
                self.show_error("Não foi possível transcrever", text)
            else:
                # Preserve anything typed while transcription was running.
                draft = self.input.toPlainText()
                self.input.setPlainText((draft + "\n" + text).strip())
                self.status.setText("Voz transcrita. Revise o texto antes de enviar.")
        else:
            self.append_message(
                "assistant",
                text
                if backend != "erro"
                else f"Não consegui concluir este pedido.\n\n{text}",
            )
            self.status.setText(f"{backend}  ·  {elapsed}s")
        self.badge.setText("REVISAR" if backend in {"erro", "offline"} else "PRONTO")

    @Slot()
    def job_finished(self):
        self.thread = None
        self.worker = None
        self.job = None
        self.refresh_controls()
        self.input.setFocus()

    def update_elapsed(self):
        elapsed = int(time.monotonic() - self.started_at)
        activity = (
            "Transcrevendo sua voz" if self.job == "voice" else "Preparando a resposta"
        )
        self.status.setText(f"{activity}…  {elapsed}s")

    def new_conversation(self):
        if self.thread is not None or self.recorder is not None:
            return
        if self.messages:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Nova conversa")
            dialog.setText("Limpar o histórico desta conversa?")
            dialog.setInformativeText(
                "As preferências salvas na memória serão mantidas."
            )
            clear = dialog.addButton(
                "Limpar e começar", QMessageBox.ButtonRole.AcceptRole
            )
            cancel = dialog.addButton("Voltar", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(cancel)
            dialog.exec()
            if dialog.clickedButton() is not clear:
                return
        self.agent.clear()
        self.close_search()
        for card in self.messages:
            self.message_layout.removeWidget(card)
            card.deleteLater()
        self.messages.clear()
        self.refresh_controls()
        self.pages.setCurrentWidget(self.welcome_scroll)
        self.to_bottom.hide()
        self.status.setText("Nova conversa. Por onde começamos?")
        self.input.setFocus()

    def show_panel(self, title, text):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(540, 440)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(label(title, "sectionTitle"))
        content = QTextBrowser()
        content.setPlainText(text)
        layout.addWidget(content)
        layout.addWidget(button("Fechar", dialog.accept, "primary"))
        dialog.exec()

    def show_memory(self):
        memory = recall_memory()["memory"]
        lines = []
        for key, item in memory.items():
            value = item.get("value", "") if isinstance(item, dict) else item
            lines.append(f"{key}\n{value}")
        self.show_panel(
            "Sua memória",
            "\n\n".join(lines)
            if lines
            else "Nada salvo ainda.\n\nPeça ao Jarvis para lembrar uma preferência. "
            "Você revisa e autoriza antes do salvamento.",
        )

    def show_shortcuts(self):
        self.show_panel(
            "Atalhos e controles",
            "Enter — enviar mensagem\nShift+Enter — nova linha\n"
            "Ctrl+L — focar o campo de mensagem\nCtrl+N — nova conversa\n"
            "Ctrl+F — buscar na conversa\n"
            "Enter / Shift+Enter na busca — próxima / anterior\n"
            "Esc na busca — fechar busca\n"
            "Ctrl+Shift+S — exportar conversa em Markdown\n"
            "Ctrl+Shift+M — iniciar ou parar a gravação\n\n"
            "Copiar — copia o texto original da mensagem\n\n"
            "A gravação para automaticamente após 60 segundos. "
            "A transcrição aparece como rascunho para sua revisão.",
        )

    def show_error(self, title, detail):
        self.status.setText(title)
        self.status.setToolTip(detail)
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(title)
        dialog.setInformativeText(detail)
        dialog.exec()

    def toggle_recording(self):
        if self.recorder is not None:
            self.stop_recording()
        elif self.thread is None:
            self.start_recording()

    def start_recording(self):
        if not os.environ.get("GROQ_API_KEY"):
            self.show_error(
                "Voz indisponível", "Configure a chave Groq para transcrever áudio."
            )
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temporary:
            self.audio_file = Path(temporary.name)
        try:
            self.recorder = subprocess.Popen(
                ["pw-record", str(self.audio_file)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self.audio_file.unlink(missing_ok=True)
            self.audio_file = None
            self.show_error("Microfone indisponível", str(error))
            return
        self.mic.setText("■  Parar gravação")
        self.mic.setObjectName("recording")
        self.mic.style().unpolish(self.mic)
        self.mic.style().polish(self.mic)
        self.badge.setText("GRAVANDO")
        self.status.setText("Ouvindo… Clique em Parar gravação quando terminar.")
        self.record_limit.start(60_000)
        self.refresh_controls()

    def stop_recording(self):
        if self.recorder is None:
            return
        self.record_limit.stop()
        recorder, audio_path = self.recorder, self.audio_file
        self.recorder = self.audio_file = None
        self.mic.setText("◉  Usar voz")
        self.mic.setObjectName("quiet")
        self.mic.style().unpolish(self.mic)
        self.mic.style().polish(self.mic)

        def transcribe():
            try:
                if recorder.poll() is None:
                    recorder.send_signal(signal.SIGINT)
                try:
                    recorder.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    recorder.kill()
                    recorder.wait(timeout=3)
                if recorder.returncode not in (0, -signal.SIGINT):
                    raise ValueError(
                        "A gravação falhou. Confira o dispositivo de entrada."
                    )
                if audio_path.stat().st_size <= 44:
                    raise ValueError(
                        "Nenhum áudio capturado. Confira o microfone e tente novamente."
                    )
                with (
                    Groq(timeout=45, max_retries=0) as client,
                    audio_path.open("rb") as audio,
                ):
                    result = client.audio.transcriptions.create(
                        file=audio,
                        model="whisper-large-v3-turbo",
                        language="pt",
                        response_format="text",
                    )
                text = result if isinstance(result, str) else str(result)
                if not text.strip():
                    raise ValueError("Não reconheci fala. Tente gravar novamente.")
                return text.strip(), "voz"
            finally:
                audio_path.unlink(missing_ok=True)

        self.start_job(transcribe, "voice")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            compact = self.width() < 950
            self.sidebar.setVisible(not compact)
            self.compact_new.setVisible(compact)
            self.key_hint.setVisible(self.width() >= 850)

    def closeEvent(self, event):
        if self.thread is not None:
            self.status.setText("Aguarde a operação terminar antes de fechar.")
            event.ignore()
            return
        if self.recorder is not None:
            self.record_limit.stop()
            self.recorder.terminate()
            try:
                self.recorder.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.recorder.kill()
                self.recorder.wait(timeout=1)
            self.audio_file.unlink(missing_ok=True)
            self.recorder = self.audio_file = None
        event.accept()


def main():
    app = QApplication([])
    app.setApplicationName("Jarvis")
    app.setApplicationVersion(VERSION)
    window = Window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
