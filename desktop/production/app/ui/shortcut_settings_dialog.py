from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6 import QtCore, QtGui, QtWidgets

from ..shortcut_settings import (
    DEFAULT_SHORTCUTS,
    SHORTCUT_DEFINITION_BY_ID,
    SHORTCUT_DEFINITIONS,
    find_conflicts,
    normalize_shortcuts,
)


class ShortcutSettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        shortcuts: Mapping[str, Sequence[str]],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键设置")
        self.resize(760, 720)
        self.setMinimumSize(680, 560)
        self._editors: dict[str, tuple[QtWidgets.QKeySequenceEdit, QtWidgets.QKeySequenceEdit]] = {}
        self._shortcuts = normalize_shortcuts(shortcuts)
        self._build_ui()
        self._load_values(self._shortcuts)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "默认支持左手单键和数字键盘两套操作。点击输入框后直接按新按键；"
            "点击输入框右侧清除按钮可禁用该按键。输入指令或备注时，字母、数字和空格不会误触质检操作。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QtWidgets.QTableWidget(len(SHORTCUT_DEFINITIONS), 4)
        self.table.setHorizontalHeaderLabels(["分类", "功能", "主快捷键", "备用快捷键"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
        )

        for row, definition in enumerate(SHORTCUT_DEFINITIONS):
            category = QtWidgets.QTableWidgetItem(definition.category)
            label = QtWidgets.QTableWidgetItem(definition.label)
            category.setFlags(category.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            label.setFlags(label.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, category)
            self.table.setItem(row, 1, label)
            primary = self._sequence_editor()
            secondary = self._sequence_editor()
            self.table.setCellWidget(row, 2, primary)
            self.table.setCellWidget(row, 3, secondary)
            self._editors[definition.action_id] = (primary, secondary)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)

        hint = QtWidgets.QLabel(
            "返修备注中按 Enter 提交，Shift+Enter 换行。删除数据组仍会执行原有两次确认。"
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults).setText(
            "恢复默认"
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(lambda _checked=False: self._load_values(DEFAULT_SHORTCUTS))
        layout.addWidget(buttons)

    @staticmethod
    def _sequence_editor() -> QtWidgets.QKeySequenceEdit:
        editor = QtWidgets.QKeySequenceEdit()
        try:
            editor.setMaximumSequenceLength(1)
        except AttributeError:
            pass
        editor.setClearButtonEnabled(True)
        try:
            editor.setFinishingKeyCombinations([])
        except AttributeError:
            pass
        editor.setMinimumWidth(125)
        return editor

    def _load_values(self, mapping: Mapping[str, Sequence[str]]) -> None:
        normalized = normalize_shortcuts(mapping)
        for action_id, editors in self._editors.items():
            values = normalized[action_id]
            editors[0].setKeySequence(QtGui.QKeySequence(values[0]))
            editors[1].setKeySequence(QtGui.QKeySequence(values[1]))

    def shortcuts_value(self) -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        for action_id, editors in self._editors.items():
            result[action_id] = tuple(
                editor.keySequence().toString(
                    QtGui.QKeySequence.SequenceFormat.PortableText
                )
                for editor in editors
            )  # type: ignore[assignment]
        return normalize_shortcuts(result)

    def _validate_and_accept(self) -> None:
        values = self.shortcuts_value()
        conflicts = find_conflicts(values)
        if conflicts:
            lines = []
            for sequence, action_ids in conflicts.items():
                labels = [
                    SHORTCUT_DEFINITION_BY_ID[action_id].label
                    for action_id in action_ids
                    if action_id in SHORTCUT_DEFINITION_BY_ID
                ]
                lines.append(f"{sequence}：{'、'.join(labels)}")
            QtWidgets.QMessageBox.warning(
                self,
                "快捷键冲突",
                "以下快捷键被多个功能占用，请修改后再保存：\n\n" + "\n".join(lines),
            )
            return
        self._shortcuts = values
        self.accept()
