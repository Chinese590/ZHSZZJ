import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui, QtWidgets

from app.shortcut_settings import DEFAULT_SHORTCUTS
from app.ui.shortcut_settings_dialog import ShortcutSettingsDialog


def test_dialog_loads_default_primary_and_numeric_keypad_bindings():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = ShortcutSettingsDialog(DEFAULT_SHORTCUTS)

    values = dialog.shortcuts_value()

    assert values["previous"] == ("A", "Num+4")
    assert values["pass"] == ("Space", "Num+5")
    assert values["toggle_image_focus"] == ("Tab", "")
    dialog.close()


def test_dialog_rejects_duplicate_shortcuts(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    dialog = ShortcutSettingsDialog(DEFAULT_SHORTCUTS)
    warning_calls = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: warning_calls.append((args, kwargs)),
    )
    previous_primary, _ = dialog._editors["previous"]
    previous_primary.setKeySequence(QtGui.QKeySequence("D"))

    dialog._validate_and_accept()

    assert warning_calls
    assert dialog.result() != QtWidgets.QDialog.DialogCode.Accepted
    dialog.close()
