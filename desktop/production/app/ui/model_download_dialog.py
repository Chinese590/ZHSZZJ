from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..model_manager import DEFAULT_MODEL, ModelDownloadError, ModelManager


class _DownloadWorker(QtCore.QObject):
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, manager: ModelManager, endpoint: str | None):
        super().__init__()
        self.manager = manager
        self.endpoint = endpoint

    @QtCore.Slot()
    def run(self) -> None:
        try:
            path = self.manager.install(DEFAULT_MODEL, endpoint=self.endpoint)
        except ModelDownloadError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(str(path))


class ModelDownloadDialog(QtWidgets.QDialog):
    def __init__(self, manager: ModelManager, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.manager = manager
        self.settings = QtCore.QSettings("DataTang", "QualityControlTool")
        self._thread: QtCore.QThread | None = None
        self._worker: _DownloadWorker | None = None
        self.setWindowTitle("AI 辅助模型")
        self.resize(560, 330)
        self._build_ui()
        self._refresh_state()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(DEFAULT_MODEL.display_name)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)
        description = QtWidgets.QLabel(
            "模型来自 Hugging Face，仅用于提示原图与结果图的视觉相似度。\n"
            "它不会自动决定质检通过或不通过。"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QtWidgets.QFormLayout()
        self.model_id_label = QtWidgets.QLabel(DEFAULT_MODEL.model_id)
        self.model_id_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("模型 ID：", self.model_id_label)
        self.path_label = QtWidgets.QLabel(str(self.manager.model_directory(DEFAULT_MODEL.model_id)))
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("保存位置：", self.path_label)
        self.endpoint_edit = QtWidgets.QLineEdit()
        self.endpoint_edit.setPlaceholderText("留空使用 https://huggingface.co")
        self.endpoint_edit.setText(str(self.settings.value("hf_endpoint", "")))
        form.addRow("自定义 Endpoint：", self.endpoint_edit)
        layout.addLayout(form)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.delete_button = QtWidgets.QPushButton("删除模型")
        self.delete_button.clicked.connect(self._delete_model)
        self.download_button = QtWidgets.QPushButton("下载 / 修复模型")
        self.download_button.clicked.connect(self._download_model)
        self.close_button = QtWidgets.QPushButton("关闭")
        self.close_button.clicked.connect(self.accept)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.download_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

    def _refresh_state(self) -> None:
        installed = self.manager.is_installed(DEFAULT_MODEL.model_id)
        self.status_label.setText("状态：已安装，可进行 AI 辅助比较。" if installed else "状态：未安装。基础质检功能不受影响。")
        self.delete_button.setEnabled(installed and self._thread is None)
        self.download_button.setEnabled(self._thread is None)
        self.close_button.setEnabled(self._thread is None)

    def _download_model(self) -> None:
        if self._thread is not None:
            return
        endpoint = self.endpoint_edit.text().strip() or None
        self.settings.setValue("hf_endpoint", endpoint or "")
        self.status_label.setText("正在从 Hugging Face 下载模型，请保持网络连接……")
        self.progress.setRange(0, 0)
        self._thread = QtCore.QThread(self)
        self._worker = _DownloadWorker(self.manager, endpoint)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._download_finished)
        self._worker.failed.connect(self._download_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.start()
        self._refresh_state()

    @QtCore.Slot(str)
    def _download_finished(self, path: str) -> None:
        self.status_label.setText(f"模型下载完成：{path}")

    @QtCore.Slot(str)
    def _download_failed(self, message: str) -> None:
        self.status_label.setText(message)
        QtWidgets.QMessageBox.warning(self, "模型下载失败", message)

    @QtCore.Slot()
    def _thread_finished(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if self.manager.is_installed(DEFAULT_MODEL.model_id) else 0)
        self._thread = None
        self._worker = None
        self._refresh_state()

    def _delete_model(self) -> None:
        answer = QtWidgets.QMessageBox.question(
            self,
            "删除 AI 模型",
            "确定删除已下载的 AI 辅助模型吗？基础质检功能不会受到影响。",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.manager.delete(DEFAULT_MODEL.model_id)
        self.progress.setValue(0)
        self._refresh_state()

    def reject(self) -> None:
        if self._thread is not None:
            QtWidgets.QMessageBox.information(self, "模型下载中", "模型正在下载，请等待完成后再关闭窗口。")
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._thread is not None:
            event.ignore()
            QtWidgets.QMessageBox.information(self, "模型下载中", "模型正在下载，请等待完成后再关闭窗口。")
            return
        super().closeEvent(event)
