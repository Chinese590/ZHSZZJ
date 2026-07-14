from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..online_review import OnlineReviewSettings


class AiSettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings: OnlineReviewSettings, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("AI一致性质检设置")
        self.setMinimumWidth(560)
        self._build_ui()
        self.set_settings(settings)

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()

        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.addItem("OpenAI", "openai")
        self.provider_combo.addItem("Gemini", "gemini")
        self.provider_combo.addItem("OpenAI兼容自定义API", "custom")
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        form.addRow("在线提供商：", self.provider_combo)

        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("API Key 仅保存在当前 Windows 用户设置中")
        form.addRow("API Key：", self.api_key_edit)

        self.model_edit = QtWidgets.QLineEdit()
        self.model_edit.setPlaceholderText("例如 gpt-5.6、gemini-3.5-flash 或自定义模型名")
        form.addRow("模型名称：", self.model_edit)

        self.base_url_edit = QtWidgets.QLineEdit()
        self.base_url_edit.setPlaceholderText("自定义接口必填；OpenAI/Gemini 留空使用官方地址")
        form.addRow("Base URL：", self.base_url_edit)

        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(15, 600)
        self.timeout_spin.setSuffix(" 秒")
        form.addRow("请求超时：", self.timeout_spin)

        self.max_edge_spin = QtWidgets.QSpinBox()
        self.max_edge_spin.setRange(512, 4096)
        self.max_edge_spin.setSingleStep(128)
        self.max_edge_spin.setSuffix(" px")
        form.addRow("上传图片最长边：", self.max_edge_spin)

        layout.addLayout(form)

        self.auto_local_check = QtWidgets.QCheckBox("切换数据组时自动执行本地检测")
        self.smart_trigger_check = QtWidgets.QCheckBox("本地判定中高风险时自动执行在线深度复核")
        layout.addWidget(self.auto_local_check)
        layout.addWidget(self.smart_trigger_check)

        privacy = QtWidgets.QLabel(
            "在线复核会把原图、结果图和指令发送到所选服务商。API Key 不写入项目日志和质检报表。"
        )
        privacy.setWordWrap(True)
        privacy.setObjectName("hintLabel")
        layout.addWidget(privacy)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_settings(self, settings: OnlineReviewSettings) -> None:
        index = self.provider_combo.findData(settings.provider)
        self.provider_combo.setCurrentIndex(max(0, index))
        self.api_key_edit.setText(settings.api_key)
        self.model_edit.setText(settings.model)
        self.base_url_edit.setText(settings.base_url)
        self.timeout_spin.setValue(settings.timeout_seconds)
        self.max_edge_spin.setValue(settings.max_image_edge)
        self.auto_local_check.setChecked(settings.auto_local)
        self.smart_trigger_check.setChecked(settings.smart_trigger)
        self._provider_changed()

    def settings_value(self) -> OnlineReviewSettings:
        return OnlineReviewSettings(
            provider=str(self.provider_combo.currentData()),
            api_key=self.api_key_edit.text().strip(),
            model=self.model_edit.text().strip(),
            base_url=self.base_url_edit.text().strip(),
            timeout_seconds=self.timeout_spin.value(),
            max_image_edge=self.max_edge_spin.value(),
            auto_local=self.auto_local_check.isChecked(),
            smart_trigger=self.smart_trigger_check.isChecked(),
        )

    @QtCore.Slot()
    def _provider_changed(self) -> None:
        provider = str(self.provider_combo.currentData())
        self.base_url_edit.setEnabled(True)
        if provider == "openai":
            self.base_url_edit.setPlaceholderText("留空使用 https://api.openai.com/v1")
        elif provider == "gemini":
            self.base_url_edit.setPlaceholderText("留空使用 https://generativelanguage.googleapis.com")
        else:
            self.base_url_edit.setPlaceholderText("必填，例如 https://example.com/v1")

    def _validate_and_accept(self) -> None:
        config = self.settings_value()
        if config.smart_trigger and not config.is_configured:
            answer = QtWidgets.QMessageBox.question(
                self,
                "在线配置不完整",
                "当前在线配置不完整，智能在线复核不会运行。\n\n是否仍保存本地检测设置？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.Yes,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        self.accept()
