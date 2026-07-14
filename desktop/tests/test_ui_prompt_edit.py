import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6 import QtWidgets

from app.ui.main_window import MainWindow


def make_group(root: Path) -> Path:
    folder = root / "待质检" / "张三" / "000001"
    folder.mkdir(parents=True)
    Image.new("RGB", (64, 32), (10, 20, 30)).save(folder / "000001.jpg")
    Image.new("RGB", (80, 40), (40, 50, 60)).save(folder / "000001_edit.jpg")
    (folder / "000001_chn.txt").write_text("原中文", encoding="utf-8")
    (folder / "000001_eng.txt").write_text("Original English", encoding="utf-8")
    for status in ("质检完成", "待返修", "返修提交"):
        (root / status).mkdir(parents=True)
    return folder


def test_prompts_are_editable_saved_in_place_and_pixels_are_shown(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    folder = make_group(tmp_path)
    window = MainWindow()
    window.settings.remove("last_root")
    window.set_root(tmp_path)
    app.processEvents()

    assert window.chinese_text.isReadOnly() is False
    assert window.english_text.isReadOnly() is False
    assert window.original_pixel_label.text() == "JPEG | 64 × 32 px"
    assert window.result_pixel_label.text() == "JPEG | 80 × 40 px"

    window.chinese_text.setPlainText("修改后的中文")
    window.english_text.setPlainText("Edited English")
    window._flush_prompt_saves()

    assert (folder / "000001_chn.txt").read_text(encoding="utf-8") == "修改后的中文"
    assert (folder / "000001_eng.txt").read_text(encoding="utf-8") == "Edited English"
    window.close()


def test_delete_button_is_enabled_for_selected_group(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    make_group(tmp_path)
    window = MainWindow()
    window.settings.remove("last_root")
    window.set_root(tmp_path)
    app.processEvents()

    assert window.delete_button.isEnabled() is True
    assert window.delete_button.text() == "删除该组文件夹"
    window.close()


def test_delete_current_group_requires_confirmation_and_removes_queue_item(tmp_path: Path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    folder = make_group(tmp_path)
    window = MainWindow()
    window.settings.remove("last_root")
    window.set_root(tmp_path)
    app.processEvents()

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QtWidgets.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("000001", True),
    )

    def fake_delete(group):
        import shutil
        shutil.rmtree(group.folder)
        from app.models import OperationRecord
        return OperationRecord(
            timestamp="2026-07-14 20:00:00",
            action="删除",
            person=group.person,
            group_name=group.group_name,
            source_status=group.status,
            source_path=str(group.folder),
            destination_path="系统回收站",
        )

    monkeypatch.setattr(window.operations, "delete_group", fake_delete)
    window.delete_current_group()
    app.processEvents()

    assert not folder.exists()
    assert window.queue_list.count() == 0
    window.close()


def test_ai_model_button_uses_selected_cache_root(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    make_group(tmp_path)
    cache_root = tmp_path / "程序缓存"
    window = MainWindow(cache_root=cache_root)
    window.settings.remove("last_root")
    window.set_root(tmp_path)
    app.processEvents()

    assert window.model_button.isEnabled() is True
    assert window.model_manager is not None
    assert window.model_manager.models_root == cache_root / "models"
    window.close()
