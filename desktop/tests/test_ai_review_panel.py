import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from app.ai_review_models import AiReviewResult, ReviewCheck, ReviewFinding
from app.ui.ai_review_panel import AiReviewPanel


def sample_result():
    return AiReviewResult(
        stage="online",
        provider="openai",
        score=63.5,
        risk="high",
        recommendation="repair",
        summary="主体结构存在异常。",
        checks={
            "主体一致性": ReviewCheck("主体一致性", "suspect", 68, "主体相近"),
            "结构完整性": ReviewCheck("结构完整性", "fail", 35, "右侧畸形"),
        },
        findings=[ReviewFinding("结构变形", "high", 95, "右侧结构畸形", "主体右侧", "恢复结构")],
        remark="请恢复主体右侧结构。",
    )


def test_panel_renders_score_risk_recommendation_and_checks():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = AiReviewPanel()

    panel.set_result(sample_result())
    app.processEvents()

    assert panel.score_value.text() == "63.5"
    assert panel.risk_value.text() == "高风险"
    assert panel.recommendation_value.text() == "建议返修"
    assert panel.source_value.text() == "在线 · OpenAI"
    assert panel.check_table.topLevelItemCount() == 8
    assert "主体结构存在异常" in panel.summary_text.toPlainText()
    assert "请恢复主体右侧结构" in panel.findings_text.toPlainText()
    panel.close()


def test_panel_buttons_emit_requested_actions():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = AiReviewPanel()
    panel.set_result(sample_result())
    calls = []
    panel.local_requested.connect(lambda: calls.append("local"))
    panel.online_requested.connect(lambda: calls.append("online"))
    panel.adopt_tags_requested.connect(lambda: calls.append("tags"))
    panel.adopt_remark_requested.connect(lambda: calls.append("remark"))

    panel.local_button.click()
    panel.online_button.click()
    panel.adopt_tags_button.click()
    panel.adopt_remark_button.click()
    app.processEvents()

    assert calls == ["local", "online", "tags", "remark"]
    panel.close()


def test_busy_state_disables_run_buttons_and_shows_progress():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = AiReviewPanel()
    panel.show()

    panel.set_busy(True, "正在进行本地一致性检测……")
    app.processEvents()

    assert panel.local_button.isEnabled() is False
    assert panel.online_button.isEnabled() is False
    assert panel.progress_bar.isVisible() is True
    assert "本地" in panel.progress_label.text()

    panel.set_busy(False)
    app.processEvents()
    assert panel.local_button.isEnabled() is True
    panel.close()
