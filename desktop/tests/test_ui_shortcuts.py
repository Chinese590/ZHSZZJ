import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6 import QtCore, QtTest, QtWidgets

from app.ui.main_window import MainWindow


def make_group(root: Path, number: str = "000001") -> Path:
    folder = root / "待质检" / "张三" / number
    folder.mkdir(parents=True)
    Image.new("RGB", (120, 100), "red").save(folder / f"{number}.jpg")
    Image.new("RGB", (120, 100), "blue").save(folder / f"{number}_edit.jpg")
    (folder / f"{number}_chn.txt").write_text("保持主体一致", encoding="utf-8")
    (folder / f"{number}_eng.txt").write_text("Keep subject consistent", encoding="utf-8")
    return folder


def build_window(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for status in ("质检完成", "待返修", "待质检", "返修提交"):
        (tmp_path / status).mkdir(parents=True, exist_ok=True)
    make_group(tmp_path)
    settings = QtCore.QSettings("DataTang", "QualityControlTool")
    settings.remove("last_root")
    settings.remove("shortcuts/json")
    window = MainWindow(cache_root=tmp_path / "cache")
    window.online_settings.auto_local = False
    window.online_settings.smart_trigger = False
    window.set_root(tmp_path)
    window.show()
    app.processEvents()
    return app, window


def test_default_shortcut_labels_show_left_hand_keys(tmp_path: Path):
    app, window = build_window(tmp_path)

    assert "A" in window.previous_button.text()
    assert "D" in window.next_button.text()
    assert "Space" in window.pass_button.text()
    assert "Return" in window.fail_button.text()
    assert "F1" in window.shortcut_button.text()

    window.close()


def test_text_editor_focus_blocks_shortcuts_and_keeps_normal_typing(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.chinese_text.setPlainText("")
    window.chinese_text.setFocus()
    app.processEvents()

    QtTest.QTest.keyClick(window.chinese_text, QtCore.Qt.Key.Key_A)
    QtTest.QTest.keyClick(window.chinese_text, QtCore.Qt.Key.Key_Space)
    app.processEvents()

    assert window.chinese_text.toPlainText() == "a "
    assert window.queue_list.currentRow() == 0
    assert (tmp_path / "待质检" / "张三" / "000001").is_dir()
    window.close()


def test_prepare_repair_focuses_remark_and_enter_submits(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.queue_list.setFocus()
    app.processEvents()

    QtTest.QTest.keyClick(window.queue_list, QtCore.Qt.Key.Key_X)
    app.processEvents()
    assert window.remark_edit.hasFocus()

    window.remark_edit.setPlainText("主体右侧结构变形")
    QtTest.QTest.keyClick(window.remark_edit, QtCore.Qt.Key.Key_Return)
    app.processEvents()

    assert (tmp_path / "待返修" / "张三" / "000001").is_dir()
    window.close()


def test_space_action_uses_existing_safe_pass_flow(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.queue_list.setFocus()
    app.processEvents()

    QtTest.QTest.keyClick(window.queue_list, QtCore.Qt.Key.Key_Space)
    app.processEvents()

    assert (tmp_path / "质检完成" / "张三" / "000001").is_dir()
    window.close()


def test_image_shortcuts_switch_focus_fit_and_zoom(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.original_view.setFocus()
    app.processEvents()

    before = window.result_view.transform().m11()
    window.toggle_image_focus()
    app.processEvents()
    assert window.result_view.hasFocus()

    window.zoom_current_image(True)
    assert window.result_view.transform().m11() > before

    window.fit_both_images()
    assert window.original_view.fit_mode is True
    assert window.result_view.fit_mode is True
    window.close()


def test_numeric_keypad_five_also_passes_current_group(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.queue_list.setFocus()
    app.processEvents()

    QtTest.QTest.keyClick(
        window.queue_list,
        QtCore.Qt.Key.Key_5,
        QtCore.Qt.KeyboardModifier.KeypadModifier,
    )
    app.processEvents()

    assert (tmp_path / "质检完成" / "张三" / "000001").is_dir()
    window.close()


def test_shift_enter_in_remark_inserts_newline_without_submitting(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.prepare_repair()
    window.remark_edit.setPlainText("第一行")
    cursor = window.remark_edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    window.remark_edit.setTextCursor(cursor)
    app.processEvents()

    QtTest.QTest.keyClick(
        window.remark_edit,
        QtCore.Qt.Key.Key_Return,
        QtCore.Qt.KeyboardModifier.ShiftModifier,
    )
    app.processEvents()

    assert (tmp_path / "待质检" / "张三" / "000001").is_dir()
    assert "\n" in window.remark_edit.toPlainText()
    window.close()


def test_tab_shortcut_switches_between_original_and_result_views(tmp_path: Path):
    app, window = build_window(tmp_path)
    window.original_view.setFocus()
    app.processEvents()
    assert window.original_view.hasFocus()

    QtTest.QTest.keyClick(window.original_view, QtCore.Qt.Key.Key_Tab)
    app.processEvents()

    assert window.result_view.hasFocus()
    window.close()
