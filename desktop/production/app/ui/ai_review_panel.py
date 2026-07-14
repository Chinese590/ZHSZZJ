from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..ai_review_models import AiReviewResult, CHECK_NAMES, ReviewCheck


class AiReviewPanel(QtWidgets.QWidget):
    local_requested = QtCore.Signal()
    online_requested = QtCore.Signal()
    settings_requested = QtCore.Signal()
    adopt_tags_requested = QtCore.Signal()
    adopt_remark_requested = QtCore.Signal()
    clear_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.current_result: AiReviewResult | None = None
        self._build_ui()
        self.clear_result()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        cards = QtWidgets.QHBoxLayout()
        self.score_value = self._value_card(cards, "一致性评分")
        self.risk_value = self._value_card(cards, "风险等级")
        self.recommendation_value = self._value_card(cards, "AI建议")
        layout.addLayout(cards)

        source_row = QtWidgets.QHBoxLayout()
        source_row.addWidget(QtWidgets.QLabel("结果来源："))
        self.source_value = QtWidgets.QLabel("尚未检测")
        self.source_value.setObjectName("aiSource")
        source_row.addWidget(self.source_value)
        source_row.addStretch(1)
        layout.addLayout(source_row)

        self.summary_text = QtWidgets.QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setMaximumHeight(82)
        self.summary_text.setPlaceholderText("本地检测或在线复核完成后显示综合结论。")
        layout.addWidget(self.summary_text)

        self.check_table = QtWidgets.QTreeWidget()
        self.check_table.setHeaderLabels(["检测维度", "状态", "得分", "说明"])
        self.check_table.setRootIsDecorated(False)
        self.check_table.setAlternatingRowColors(True)
        self.check_table.setMinimumHeight(245)
        self.check_table.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.check_table.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.check_table.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.check_table.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.check_table, 1)

        findings_title = QtWidgets.QLabel("疑似问题与返修建议")
        findings_title.setObjectName("sectionTitle")
        layout.addWidget(findings_title)
        self.findings_text = QtWidgets.QPlainTextEdit()
        self.findings_text.setReadOnly(True)
        self.findings_text.setMaximumHeight(135)
        self.findings_text.setPlaceholderText("发现问题后显示具体位置、证据和返修建议。")
        layout.addWidget(self.findings_text)

        self.progress_label = QtWidgets.QLabel("")
        self.progress_label.setObjectName("hintLabel")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_label.hide()
        self.progress_bar.hide()
        layout.addWidget(self.progress_label)
        layout.addWidget(self.progress_bar)

        run_row = QtWidgets.QHBoxLayout()
        self.local_button = QtWidgets.QPushButton("本地AI检测")
        self.online_button = QtWidgets.QPushButton("在线深度复核")
        self.settings_button = QtWidgets.QPushButton("AI设置")
        self.local_button.clicked.connect(self.local_requested)
        self.online_button.clicked.connect(self.online_requested)
        self.settings_button.clicked.connect(self.settings_requested)
        run_row.addWidget(self.local_button)
        run_row.addWidget(self.online_button)
        run_row.addWidget(self.settings_button)
        layout.addLayout(run_row)

        adopt_row = QtWidgets.QHBoxLayout()
        self.adopt_tags_button = QtWidgets.QPushButton("采纳AI标签")
        self.adopt_remark_button = QtWidgets.QPushButton("采纳AI备注")
        self.clear_button = QtWidgets.QPushButton("清空AI结果")
        self.adopt_tags_button.clicked.connect(self.adopt_tags_requested)
        self.adopt_remark_button.clicked.connect(self.adopt_remark_requested)
        self.clear_button.clicked.connect(self.clear_requested)
        adopt_row.addWidget(self.adopt_tags_button)
        adopt_row.addWidget(self.adopt_remark_button)
        adopt_row.addStretch(1)
        adopt_row.addWidget(self.clear_button)
        layout.addLayout(adopt_row)

        hint = QtWidgets.QLabel("AI只提供辅助建议，不会自动通过、返修、删除或移动文件夹。")
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        layout.addWidget(hint)

    def _value_card(self, layout: QtWidgets.QHBoxLayout, title: str) -> QtWidgets.QLabel:
        frame = QtWidgets.QFrame()
        frame.setObjectName("aiMetricCard")
        box = QtWidgets.QVBoxLayout(frame)
        box.setContentsMargins(8, 6, 8, 6)
        heading = QtWidgets.QLabel(title)
        heading.setObjectName("hintLabel")
        value = QtWidgets.QLabel("--")
        value.setObjectName("aiMetricValue")
        value.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        box.addWidget(heading)
        box.addWidget(value)
        layout.addWidget(frame, 1)
        return value

    def set_result(self, result: AiReviewResult) -> None:
        self.current_result = result
        self.score_value.setText(f"{result.score:.1f}")
        self.risk_value.setText({"low": "低风险", "medium": "中风险", "high": "高风险"}.get(result.risk, result.risk))
        self.recommendation_value.setText(
            {"pass": "建议通过", "review": "建议复核", "repair": "建议返修"}.get(
                result.recommendation, result.recommendation
            )
        )
        provider = {
            "local": "本地规则",
            "openai": "OpenAI",
            "gemini": "Gemini",
            "custom": "自定义API",
        }.get(result.provider, result.provider)
        stage = "在线" if result.stage == "online" else "本地"
        self.source_value.setText(f"{stage} · {provider}")
        self.summary_text.setPlainText(result.summary)
        self.findings_text.setPlainText(result.remark.strip() or "未发现需要列出的疑似问题。")
        self._populate_checks(result)
        has_result = True
        self.adopt_tags_button.setEnabled(has_result and bool(result.issue_categories))
        self.adopt_remark_button.setEnabled(has_result and bool(result.remark.strip()))
        self.clear_button.setEnabled(True)

    def clear_result(self) -> None:
        self.current_result = None
        self.score_value.setText("--")
        self.risk_value.setText("未检测")
        self.recommendation_value.setText("等待检测")
        self.source_value.setText("尚未检测")
        self.summary_text.clear()
        self.findings_text.clear()
        self.check_table.clear()
        for name in CHECK_NAMES:
            item = QtWidgets.QTreeWidgetItem([name, "未检测", "--", "等待本地检测或在线复核。"])
            self.check_table.addTopLevelItem(item)
        self.adopt_tags_button.setEnabled(False)
        self.adopt_remark_button.setEnabled(False)
        self.clear_button.setEnabled(False)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.local_button.setEnabled(not busy)
        self.online_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        if busy:
            self.progress_label.setText(text or "AI正在分析……")
            self.progress_label.show()
            self.progress_bar.show()
        else:
            self.progress_label.hide()
            self.progress_bar.hide()

    def set_run_enabled(self, enabled: bool) -> None:
        self.local_button.setEnabled(enabled)
        self.online_button.setEnabled(enabled)

    def _populate_checks(self, result: AiReviewResult) -> None:
        self.check_table.clear()
        for name in CHECK_NAMES:
            check = result.checks.get(name) or ReviewCheck(name, "not_checked", None, "未返回该检测维度。")
            status_text = {
                "pass": "正常",
                "suspect": "疑似",
                "fail": "异常",
                "not_checked": "未检测",
                "not_applicable": "不适用",
            }.get(check.status, check.status)
            score_text = "--" if check.score is None else f"{check.score:.1f}"
            item = QtWidgets.QTreeWidgetItem([name, status_text, score_text, check.detail])
            color = {
                "pass": "#14804A",
                "suspect": "#B26A00",
                "fail": "#C43B3B",
                "not_checked": "#6F7882",
                "not_applicable": "#6F7882",
            }.get(check.status, "#20252B")
            item.setForeground(1, QtGui.QBrush(QtGui.QColor(color)))
            self.check_table.addTopLevelItem(item)
