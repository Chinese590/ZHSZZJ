from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from ..shortcut_settings import SHORTCUT_DEFINITION_BY_ID, SHORTCUT_DEFINITIONS


class ShortcutController(QtCore.QObject):
    """Bind user-configurable window shortcuts with text-editing protection."""

    def __init__(
        self,
        window: QtWidgets.QMainWindow,
        mapping: Mapping[str, Sequence[str]],
        callbacks: Mapping[str, Callable[[], None]],
        *,
        remark_editor: QtWidgets.QPlainTextEdit,
    ) -> None:
        super().__init__(window)
        self.window = window
        self.callbacks = dict(callbacks)
        self.remark_editor = remark_editor
        self.mapping: dict[str, tuple[str, str]] = {}
        self._shortcuts: list[tuple[QtGui.QShortcut, str]] = []
        self._sequence_to_action: dict[str, str] = {}
        self.remark_editor.installEventFilter(self)
        self.window.installEventFilter(self)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._focus_changed)
        self.rebind(mapping)

    def rebind(self, mapping: Mapping[str, Sequence[str]]) -> None:
        for shortcut, _action_id in self._shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._shortcuts.clear()
        self._sequence_to_action.clear()
        self.mapping = {}

        for definition in SHORTCUT_DEFINITIONS:
            raw_values = list(mapping.get(definition.action_id, definition.defaults))[:2]
            while len(raw_values) < 2:
                raw_values.append("")
            values = tuple(str(value).strip() for value in raw_values)
            self.mapping[definition.action_id] = (values[0], values[1])
            for sequence_text in values:
                if not sequence_text:
                    continue
                normalized = sequence_text.casefold()
                if normalized in self._sequence_to_action:
                    continue
                key_sequence = QtGui.QKeySequence(sequence_text)
                if key_sequence.isEmpty():
                    continue
                self._sequence_to_action[normalized] = definition.action_id
                shortcut = QtGui.QShortcut(key_sequence, self.window)
                shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
                shortcut.setAutoRepeat(definition.repeatable)
                shortcut.activated.connect(
                    lambda action_id=definition.action_id: self.trigger(action_id)
                )
                shortcut.activatedAmbiguously.connect(
                    lambda action_id=definition.action_id: self._show_ambiguous(action_id)
                )
                self._shortcuts.append((shortcut, definition.action_id))
        self._update_enabled_for_focus(QtWidgets.QApplication.focusWidget())

    @QtCore.Slot(object, object)
    def _focus_changed(
        self,
        _old: QtWidgets.QWidget | None,
        current: QtWidgets.QWidget | None,
    ) -> None:
        self._update_enabled_for_focus(current)

    def _update_enabled_for_focus(self, focus: QtWidgets.QWidget | None) -> None:
        editing = self._is_text_editor(focus)
        remark_active = self._belongs_to(self.remark_editor, focus)
        for shortcut, action_id in self._shortcuts:
            definition = SHORTCUT_DEFINITION_BY_ID[action_id]
            enabled = (
                not editing
                or definition.allow_while_editing
                or (action_id == "submit_repair" and remark_active)
            )
            shortcut.setEnabled(enabled)

    def trigger(self, action_id: str) -> bool:
        definition = SHORTCUT_DEFINITION_BY_ID.get(action_id)
        callback = self.callbacks.get(action_id)
        if definition is None or callback is None:
            return False

        focus = QtWidgets.QApplication.focusWidget()
        editing = self._is_text_editor(focus)
        is_remark_submit = action_id == "submit_repair" and self._belongs_to(
            self.remark_editor, focus
        )
        if editing and not definition.allow_while_editing and not is_remark_submit:
            return False

        callback()
        return True

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() != QtCore.QEvent.Type.KeyPress or not isinstance(event, QtGui.QKeyEvent):
            return super().eventFilter(watched, event)

        sequence_text = self._event_sequence(event)
        action_id = self._sequence_to_action.get(sequence_text.casefold())
        if action_id is None:
            return super().eventFilter(watched, event)

        # Return in the remark editor submits the repair. Shift+Return remains a
        # normal newline because it has a different portable key sequence.
        if watched is self.remark_editor and action_id == "submit_repair":
            return self.trigger(action_id)

        # Tab is normally consumed by focus traversal before QShortcut activates.
        if action_id == "toggle_image_focus" and not self._is_text_editor(
            QtWidgets.QApplication.focusWidget()
        ):
            return self.trigger(action_id)

        return super().eventFilter(watched, event)

    @staticmethod
    def _event_sequence(event: QtGui.QKeyEvent) -> str:
        try:
            sequence = QtGui.QKeySequence(event.keyCombination())
        except (AttributeError, TypeError):
            sequence = QtGui.QKeySequence(int(event.modifiers()) | event.key())
        return sequence.toString(QtGui.QKeySequence.SequenceFormat.PortableText)

    @staticmethod
    def _belongs_to(parent: QtWidgets.QWidget, widget: QtWidgets.QWidget | None) -> bool:
        return widget is parent or (widget is not None and parent.isAncestorOf(widget))

    @classmethod
    def _is_text_editor(cls, widget: QtWidgets.QWidget | None) -> bool:
        if widget is None:
            return False
        if isinstance(widget, QtWidgets.QLineEdit):
            return not widget.isReadOnly()
        if isinstance(widget, (QtWidgets.QPlainTextEdit, QtWidgets.QTextEdit)):
            return not widget.isReadOnly()
        if isinstance(widget, QtWidgets.QAbstractSpinBox):
            return True
        if isinstance(widget, QtWidgets.QComboBox):
            return widget.isEditable()
        return False

    def _show_ambiguous(self, action_id: str) -> None:
        definition = SHORTCUT_DEFINITION_BY_ID.get(action_id)
        label = definition.label if definition is not None else action_id
        self.window.statusBar().showMessage(
            f"快捷键冲突，未执行：{label}。请按 F1 修改快捷键。", 6000
        )
