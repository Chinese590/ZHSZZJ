import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6 import QtWidgets

from app.ai_review_models import AiReviewResult, ReviewCheck, ReviewFinding
from app.ai_review_store import image_pair_signature
from app.ui.main_window import MainWindow


def make_group(root: Path) -> Path:
    folder = root / "待质检" / "张三" / "000001"
    folder.mkdir(parents=True)
    Image.new("RGB", (100, 100), "red").save(folder / "000001.jpg")
    Image.new("RGB", (100, 100), "blue").save(folder / "000001_edit.jpg")
    (folder / "000001_chn.txt").write_text("保持主体一致", encoding="utf-8")
    (folder / "000001_eng.txt").write_text("Keep subject consistent", encoding="utf-8")
    for status in ("质检完成", "待返修", "返修提交"):
        (root / status).mkdir(parents=True)
    return folder


def online_result():
    return AiReviewResult(
        stage="online",
        provider="openai",
        score=42,
        risk="high",
        recommendation="repair",
        summary="主体右侧结构与Logo异常。",
        checks={
            "结构完整性": ReviewCheck("结构完整性", "fail", 30, "右侧畸形"),
            "文字与Logo": ReviewCheck("文字与Logo", "fail", 25, "Logo错误"),
        },
        findings=[
            ReviewFinding("结构变形", "high", 95, "右侧结构畸形", "主体右侧", "恢复原结构"),
            ReviewFinding("文字或Logo错误", "high", 92, "Logo字符错误", "Logo区域", "恢复原Logo"),
        ],
        remark="1. 修复主体右侧结构。\n2. 恢复原Logo文字。",
    )


def build_window(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    make_group(tmp_path)
    window = MainWindow(cache_root=tmp_path / "cache")
    window.settings.remove("last_root")
    window.online_settings.auto_local = False
    window.online_settings.smart_trigger = False
    window.set_root(tmp_path)
    app.processEvents()
    return app, window


def test_main_window_contains_ai_consistency_panel(tmp_path: Path):
    app, window = build_window(tmp_path)

    assert window.ai_review_panel.local_button.text().startswith("本地AI检测")
    assert window.ai_review_panel.online_button.text().startswith("在线深度复核")
    assert window.ai_review_panel.isEnabled()
    window.close()


def test_online_result_auto_fills_labels_and_empty_remark_without_moving_files(tmp_path: Path):
    app, window = build_window(tmp_path)
    group = window.current_group()
    signature = image_pair_signature(group.original_image, group.result_image)
    window._current_ai_signature = signature

    window._apply_ai_result(online_result(), signature, auto_fill=True)
    app.processEvents()

    checked = {item.text() for item in window.issue_checks if item.isChecked()}
    assert {"结构变形", "文字或Logo错误"} <= checked
    assert "恢复原Logo" in window.remark_edit.toPlainText()
    assert group.folder.exists()
    assert window.queue_list.count() == 1
    window.close()


def test_stale_ai_result_is_not_applied_to_new_selection(tmp_path: Path):
    app, window = build_window(tmp_path)
    window._current_ai_signature = "current-signature"

    applied = window._apply_ai_result(online_result(), "old-signature", auto_fill=True)

    assert applied is False
    assert window._current_ai_result is None
    assert window.remark_edit.toPlainText() == ""
    window.close()


def test_adopt_ai_remark_preserves_existing_manual_text(tmp_path: Path):
    app, window = build_window(tmp_path)
    result = online_result()
    window._current_ai_result = result
    window.ai_review_panel.set_result(result)
    window.remark_edit.setPlainText("人工备注")

    window.adopt_ai_remark()

    text = window.remark_edit.toPlainText()
    assert text.startswith("人工备注")
    assert "恢复原Logo" in text
    window.close()
