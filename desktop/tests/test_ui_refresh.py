import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from app.ui.main_window import MainWindow


def make_group(root: Path) -> None:
    folder = root / "待质检" / "张三" / "000001"
    folder.mkdir(parents=True)
    (folder / "000001.jpg").write_bytes(b"image")
    (folder / "000001_edit.jpg").write_bytes(b"image")
    (folder / "000001_chn.txt").write_text("中文", encoding="utf-8")
    (folder / "000001_eng.txt").write_text("English", encoding="utf-8")
    for status in ("质检完成", "待返修", "返修提交"):
        (root / status).mkdir(parents=True)


def test_unchanged_refresh_preserves_review_inputs(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    make_group(tmp_path)
    window = MainWindow()
    window.settings.remove("last_root")
    window.online_settings.auto_local = False
    window.set_root(tmp_path)
    app.processEvents()

    window.remark_edit.setPlainText("正在填写的返修说明")
    window.issue_checks[0].setChecked(True)
    window.refresh_queue()
    app.processEvents()

    assert window.remark_edit.toPlainText() == "正在填写的返修说明"
    assert window.issue_checks[0].isChecked()
    window.close()
