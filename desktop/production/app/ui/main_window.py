from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..history import load_effective_records
from ..models import DataGroup
from ..model_manager import ModelManager
from ..operations import DestinationExistsError, QualityOperationError, QualityOperations
from ..reports import export_report
from ..scanner import (
    STATUS_FOLDERS,
    scan_all_counts,
    scan_queue,
    validate_root,
    write_text_compatible,
)
from ..watcher import DirectoryWatcher
from .image_viewer import ZoomableImageView
from .ai_compare_worker import AiCompareWorker
from .model_download_dialog import ModelDownloadDialog


ISSUE_OPTIONS = (
    "主体不一致",
    "结构变形",
    "细节丢失",
    "颜色错误",
    "文字或Logo错误",
    "背景不符合要求",
    "画面瑕疵",
    "版面不协调",
    "文件缺失",
    "其他问题",
)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, cache_root: Path | str | None = None):
        super().__init__()
        self.cache_root = Path(cache_root).resolve() if cache_root else None
        self.model_manager = ModelManager(self.cache_root) if self.cache_root is not None else None
        self.setWindowTitle("数据堂质检工具 在线运行库版")
        self.resize(1680, 940)
        self.setMinimumSize(1280, 760)

        self.root_path: Path | None = None
        self.groups: list[DataGroup] = []
        self.operations: QualityOperations | None = None
        self._queue_signature: tuple | None = None
        self._displayed_group: DataGroup | None = None
        self._loading_prompts = False
        self._dirty_prompt_fields: set[str] = set()
        self._current_images_ok = False
        self._ai_thread: QtCore.QThread | None = None
        self._ai_worker: AiCompareWorker | None = None
        self.watcher = DirectoryWatcher(self)
        self.watcher.changed.connect(self._schedule_refresh)
        self.settings = QtCore.QSettings("DataTang", "QualityControlTool")

        self.refresh_debounce = QtCore.QTimer(self)
        self.refresh_debounce.setSingleShot(True)
        self.refresh_debounce.setInterval(650)
        self.refresh_debounce.timeout.connect(self.refresh_queue)

        self.periodic_timer = QtCore.QTimer(self)
        self.periodic_timer.setInterval(3000)
        self.periodic_timer.timeout.connect(self._periodic_refresh)
        self.periodic_timer.start()

        self.prompt_save_timer = QtCore.QTimer(self)
        self.prompt_save_timer.setSingleShot(True)
        self.prompt_save_timer.setInterval(650)
        self.prompt_save_timer.timeout.connect(self._flush_prompt_saves)

        self._build_ui()
        self._apply_style()
        QtCore.QTimer.singleShot(0, self._restore_last_root)
        if self.cache_root is not None:
            self.statusBar().showMessage(f"程序缓存：{self.cache_root}", 8000)

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        top_bar = QtWidgets.QHBoxLayout()
        self.root_edit = QtWidgets.QLineEdit()
        self.root_edit.setReadOnly(True)
        self.root_edit.setPlaceholderText("请选择包含四个状态文件夹的项目总目录")
        browse_button = QtWidgets.QPushButton("选择项目总目录")
        browse_button.clicked.connect(self.choose_root)
        refresh_button = QtWidgets.QPushButton("立即刷新")
        refresh_button.clicked.connect(self.refresh_queue)
        self.open_root_button = QtWidgets.QPushButton("打开目录")
        self.open_root_button.clicked.connect(self.open_root_folder)
        self.open_root_button.setEnabled(False)
        top_bar.addWidget(QtWidgets.QLabel("项目目录："))
        top_bar.addWidget(self.root_edit, 1)
        top_bar.addWidget(browse_button)
        top_bar.addWidget(refresh_button)
        top_bar.addWidget(self.open_root_button)
        outer.addLayout(top_bar)

        summary_bar = QtWidgets.QHBoxLayout()
        self.queue_count_label = self._summary_label("待检队列 0")
        self.completed_count_label = self._summary_label("质检完成 0")
        self.repair_count_label = self._summary_label("待返修 0")
        self.pending_count_label = self._summary_label("待质检 0")
        self.submitted_count_label = self._summary_label("返修提交 0")
        for widget in (
            self.queue_count_label,
            self.completed_count_label,
            self.repair_count_label,
            self.pending_count_label,
            self.submitted_count_label,
        ):
            summary_bar.addWidget(widget)
        summary_bar.addStretch(1)
        outer.addLayout(summary_bar)

        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        outer.addWidget(main_splitter, 1)

        # Queue panel
        queue_panel = QtWidgets.QWidget()
        queue_layout = QtWidgets.QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_title_row = QtWidgets.QHBoxLayout()
        queue_title = QtWidgets.QLabel("质检队列")
        queue_title.setObjectName("sectionTitle")
        self.progress_label = QtWidgets.QLabel("0 / 0")
        queue_title_row.addWidget(queue_title)
        queue_title_row.addStretch(1)
        queue_title_row.addWidget(self.progress_label)
        queue_layout.addLayout(queue_title_row)
        self.queue_list = QtWidgets.QListWidget()
        self.queue_list.setAlternatingRowColors(True)
        self.queue_list.currentRowChanged.connect(self.display_group)
        queue_layout.addWidget(self.queue_list, 1)
        queue_hint = QtWidgets.QLabel("队列来源：待质检 + 待返修\n红色项目表示文件不完整")
        queue_hint.setObjectName("hintLabel")
        queue_layout.addWidget(queue_hint)
        main_splitter.addWidget(queue_panel)

        # Image comparison panel
        image_panel = QtWidgets.QWidget()
        image_layout = QtWidgets.QVBoxLayout(image_panel)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.group_meta_label = QtWidgets.QLabel("尚未选择数据")
        self.group_meta_label.setObjectName("groupMeta")
        self.group_meta_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        image_layout.addWidget(self.group_meta_label)

        image_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        (
            self.original_view,
            original_card,
            self.original_pixel_label,
        ) = self._create_image_card("原图")
        (
            self.result_view,
            result_card,
            self.result_pixel_label,
        ) = self._create_image_card("结果图")
        image_splitter.addWidget(original_card)
        image_splitter.addWidget(result_card)
        image_splitter.setSizes([620, 620])
        image_layout.addWidget(image_splitter, 1)
        main_splitter.addWidget(image_panel)

        # Instruction and failure panel
        info_scroll = QtWidgets.QScrollArea()
        info_scroll.setWidgetResizable(True)
        info_content = QtWidgets.QWidget()
        info_layout = QtWidgets.QVBoxLayout(info_content)
        info_layout.setContentsMargins(8, 0, 8, 8)
        info_layout.setSpacing(10)

        chn_title = QtWidgets.QLabel("中文指令")
        chn_title.setObjectName("sectionTitle")
        info_layout.addWidget(chn_title)
        self.chinese_text = QtWidgets.QPlainTextEdit()
        self.chinese_text.setReadOnly(False)
        self.chinese_text.setPlaceholderText("可直接修改，停止输入后自动保存到原 _chn.txt 文件")
        self.chinese_text.setMinimumHeight(155)
        self.chinese_text.textChanged.connect(self._schedule_prompt_save)
        info_layout.addWidget(self.chinese_text)

        eng_title = QtWidgets.QLabel("英文指令")
        eng_title.setObjectName("sectionTitle")
        info_layout.addWidget(eng_title)
        self.english_text = QtWidgets.QPlainTextEdit()
        self.english_text.setReadOnly(False)
        self.english_text.setPlaceholderText("可直接修改，停止输入后自动保存到原 _eng.txt 文件")
        self.english_text.setMinimumHeight(155)
        self.english_text.textChanged.connect(self._schedule_prompt_save)
        info_layout.addWidget(self.english_text)

        issue_title = QtWidgets.QLabel("质检不通过主要问题")
        issue_title.setObjectName("sectionTitle")
        info_layout.addWidget(issue_title)
        issue_widget = QtWidgets.QWidget()
        issue_grid = QtWidgets.QGridLayout(issue_widget)
        issue_grid.setContentsMargins(0, 0, 0, 0)
        issue_grid.setHorizontalSpacing(8)
        issue_grid.setVerticalSpacing(6)
        self.issue_checks: list[QtWidgets.QCheckBox] = []
        for index, issue in enumerate(ISSUE_OPTIONS):
            checkbox = QtWidgets.QCheckBox(issue)
            self.issue_checks.append(checkbox)
            issue_grid.addWidget(checkbox, index // 2, index % 2)
        info_layout.addWidget(issue_widget)

        remark_title = QtWidgets.QLabel("详细返修备注")
        remark_title.setObjectName("sectionTitle")
        info_layout.addWidget(remark_title)
        self.remark_edit = QtWidgets.QPlainTextEdit()
        self.remark_edit.setPlaceholderText("说明具体位置、缺失细节和返修要求……")
        self.remark_edit.setMinimumHeight(130)
        info_layout.addWidget(self.remark_edit)
        info_layout.addStretch(1)
        info_scroll.setWidget(info_content)
        main_splitter.addWidget(info_scroll)
        main_splitter.setSizes([280, 1000, 390])

        # Bottom action bar
        action_bar = QtWidgets.QHBoxLayout()
        self.previous_button = QtWidgets.QPushButton("上一组")
        self.previous_button.clicked.connect(self.go_previous)
        self.next_button = QtWidgets.QPushButton("下一组")
        self.next_button.clicked.connect(self.go_next)
        self.undo_button = QtWidgets.QPushButton("撤销上一步")
        self.undo_button.clicked.connect(self.undo_last)
        self.undo_button.setEnabled(False)
        self.model_button = QtWidgets.QPushButton("AI辅助模型")
        self.model_button.clicked.connect(self.open_model_dialog)
        self.model_button.setEnabled(self.model_manager is not None)
        self.ai_compare_button = QtWidgets.QPushButton("AI辅助比较")
        self.ai_compare_button.clicked.connect(self.run_ai_compare)
        self.ai_compare_button.setEnabled(False)
        self.delete_button = QtWidgets.QPushButton("删除该组文件夹")
        self.delete_button.setObjectName("deleteButton")
        self.delete_button.clicked.connect(self.delete_current_group)
        self.delete_button.setEnabled(False)
        self.pass_button = QtWidgets.QPushButton("质检通过")
        self.pass_button.setObjectName("passButton")
        self.pass_button.clicked.connect(self.pass_current)
        self.pass_button.setEnabled(False)
        self.fail_button = QtWidgets.QPushButton("质检不通过")
        self.fail_button.setObjectName("failButton")
        self.fail_button.clicked.connect(self.fail_current)
        self.fail_button.setEnabled(False)
        self.finish_button = QtWidgets.QPushButton("结束质检并导出表格")
        self.finish_button.setObjectName("finishButton")
        self.finish_button.clicked.connect(self.export_daily_report)
        self.finish_button.setEnabled(False)

        action_bar.addWidget(self.previous_button)
        action_bar.addWidget(self.next_button)
        action_bar.addStretch(1)
        action_bar.addWidget(self.undo_button)
        action_bar.addWidget(self.model_button)
        action_bar.addWidget(self.ai_compare_button)
        action_bar.addWidget(self.delete_button)
        action_bar.addSpacing(8)
        action_bar.addWidget(self.pass_button)
        action_bar.addWidget(self.fail_button)
        action_bar.addWidget(self.finish_button)
        outer.addLayout(action_bar)

        self.statusBar().showMessage("请选择项目总目录")

    def _create_image_card(
        self, title: str
    ) -> tuple[ZoomableImageView, QtWidgets.QWidget, QtWidgets.QLabel]:
        card = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(title)
        label.setObjectName("sectionTitle")
        pixel_label = QtWidgets.QLabel("未知格式 | -- × -- px")
        pixel_label.setObjectName("pixelLabel")
        pixel_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        zoom_label = QtWidgets.QLabel("100%")
        fit_button = QtWidgets.QPushButton("适应")
        actual_button = QtWidgets.QPushButton("1:1")
        fit_button.setFixedWidth(58)
        actual_button.setFixedWidth(52)
        header.addWidget(label)
        header.addWidget(pixel_label)
        header.addStretch(1)
        header.addWidget(zoom_label)
        header.addWidget(fit_button)
        header.addWidget(actual_button)
        layout.addLayout(header)
        viewer = ZoomableImageView()
        viewer.zoom_changed.connect(
            lambda value, target=zoom_label: target.setText(f"{value * 100:.0f}%")
        )
        viewer.image_info_changed.connect(
            lambda width, height, file_format, target=pixel_label: target.setText(
                f"{file_format or '未知格式'} | {width} × {height} px"
                if width and height
                else "未知格式 | -- × -- px"
            )
        )
        fit_button.clicked.connect(viewer.fit_to_view)
        actual_button.clicked.connect(viewer.actual_size)
        layout.addWidget(viewer, 1)
        return viewer, card, pixel_label

    def _summary_label(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("summaryPill")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        return label

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #F4F6F8; color: #20252B; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            QLineEdit, QPlainTextEdit, QListWidget, QScrollArea { background: white; border: 1px solid #D6DBE1; border-radius: 6px; }
            QLineEdit { padding: 7px 9px; }
            QPlainTextEdit { padding: 6px; selection-background-color: #2E75B6; }
            QListWidget { outline: none; padding: 3px; }
            QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #EEF1F4; }
            QListWidget::item:selected { background: #DCEBFA; color: #133A5C; }
            QPushButton { background: white; border: 1px solid #C8CED6; border-radius: 6px; padding: 7px 14px; min-height: 22px; }
            QPushButton:hover { background: #EEF4F9; }
            QPushButton:disabled { color: #9AA3AD; background: #ECEFF2; }
            QPushButton#passButton { background: #14804A; color: white; border-color: #14804A; font-weight: 600; min-width: 110px; }
            QPushButton#passButton:hover { background: #0E6C3D; }
            QPushButton#failButton { background: #C43B3B; color: white; border-color: #C43B3B; font-weight: 600; min-width: 110px; }
            QPushButton#failButton:hover { background: #A92F2F; }
            QPushButton#deleteButton { background: #6B3A2E; color: white; border-color: #6B3A2E; font-weight: 600; min-width: 130px; }
            QPushButton#deleteButton:hover { background: #552D24; }
            QPushButton#finishButton { background: #245B8F; color: white; border-color: #245B8F; font-weight: 600; min-width: 170px; }
            QLabel#sectionTitle { font-size: 14px; font-weight: 700; color: #25313D; }
            QLabel#groupMeta { background: white; border: 1px solid #D6DBE1; border-radius: 6px; padding: 9px 12px; font-weight: 600; }
            QLabel#summaryPill { background: white; border: 1px solid #D6DBE1; border-radius: 12px; padding: 5px 12px; min-width: 95px; }
            QLabel#hintLabel { color: #6F7882; font-size: 12px; }
            QLabel#pixelLabel { color: #5E6B78; font-size: 12px; padding-left: 8px; }
            QCheckBox { spacing: 6px; }
            QSplitter::handle { background: #DDE2E7; width: 4px; height: 4px; }
            """
        )

    def choose_root(self) -> None:
        initial = str(self.root_path or Path.home())
        selected = QtWidgets.QFileDialog.getExistingDirectory(self, "选择项目总目录", initial)
        if selected:
            self.set_root(Path(selected))

    def set_root(self, root: Path) -> None:
        missing = validate_root(root)
        if missing:
            answer = QtWidgets.QMessageBox.question(
                self,
                "缺少状态文件夹",
                "所选目录缺少以下文件夹：\n\n"
                + "、".join(missing)
                + "\n\n是否自动创建缺失文件夹？",
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.Yes,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            try:
                for status in missing:
                    (root / status).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._show_error("创建状态文件夹失败", exc)
                return

        self.root_path = root
        self.operations = QualityOperations(root)
        self._queue_signature = None
        self.root_edit.setText(str(root))
        self.open_root_button.setEnabled(True)
        self.finish_button.setEnabled(True)
        self.settings.setValue("last_root", str(root))
        try:
            self.watcher.start(root)
        except OSError as exc:
            self.statusBar().showMessage(f"实时监听启动失败，将使用定时刷新：{exc}", 8000)
        self.refresh_queue(preferred_row=0)

    def _restore_last_root(self) -> None:
        value = self.settings.value("last_root", "")
        if value:
            root = Path(str(value))
            if root.is_dir() and not validate_root(root):
                self.set_root(root)

    def refresh_queue(self, preferred_row: int | None = None) -> None:
        if self.root_path is None:
            return
        current_key = self._current_key()
        old_row = self.queue_list.currentRow()
        try:
            groups = scan_queue(self.root_path)
            counts = scan_all_counts(self.root_path)
        except OSError as exc:
            self.statusBar().showMessage(f"读取目录失败：{exc}", 8000)
            return

        signature = self._make_queue_signature(groups)
        self._set_summary_counts(counts, len(groups))
        if preferred_row is None and signature == self._queue_signature:
            self._update_action_states()
            return

        self._queue_signature = signature
        self.groups = groups
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        selected_row = -1
        for index, group in enumerate(groups):
            status_tag = "初检" if group.status == "待质检" else "返修复检"
            missing_text = f"  缺少：{'、'.join(group.missing)}" if group.missing else ""
            item = QtWidgets.QListWidgetItem(
                f"[{status_tag}] {group.person}\n{group.group_name}{missing_text}"
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, self._group_key(group))
            if group.missing:
                item.setForeground(QtGui.QBrush(QtGui.QColor("#B42318")))
                item.setToolTip("文件不完整：" + "、".join(group.missing))
            else:
                item.setToolTip(str(group.folder))
            self.queue_list.addItem(item)
            if current_key and self._group_key(group) == current_key:
                selected_row = index

        if preferred_row is not None:
            selected_row = min(max(preferred_row, 0), len(groups) - 1) if groups else -1
        elif selected_row < 0 and groups:
            selected_row = min(max(old_row, 0), len(groups) - 1)

        self.queue_list.blockSignals(False)
        if selected_row >= 0:
            self.queue_list.setCurrentRow(selected_row)
        else:
            self.queue_list.setCurrentRow(-1)
            self.display_group(-1)

        self._update_action_states()

    def _set_summary_counts(self, counts: dict[str, dict[str, int]], queue_count: int) -> None:
        totals = {
            status: sum(person.get(status, 0) for person in counts.values())
            for status in STATUS_FOLDERS
        }
        self.queue_count_label.setText(f"待检队列 {queue_count}")
        self.completed_count_label.setText(f"质检完成 {totals['质检完成']}")
        self.repair_count_label.setText(f"待返修 {totals['待返修']}")
        self.pending_count_label.setText(f"待质检 {totals['待质检']}")
        self.submitted_count_label.setText(f"返修提交 {totals['返修提交']}")

    def _make_queue_signature(self, groups: list[DataGroup]) -> tuple:
        def stamp(path: Path | None) -> tuple[str, int, int]:
            if path is None:
                return ("", 0, 0)
            try:
                stat = path.stat()
                return (str(path), stat.st_mtime_ns, stat.st_size)
            except OSError:
                return (str(path), 0, 0)

        return tuple(
            (
                self._group_key(group),
                tuple(group.missing),
                stamp(group.original_image),
                stamp(group.result_image),
                stamp(group.chinese_file),
                stamp(group.english_file),
            )
            for group in groups
        )

    def display_group(self, row: int) -> None:
        self._flush_prompt_saves(show_error=True)

        if row < 0 or row >= len(self.groups):
            self._displayed_group = None
            self._current_images_ok = False
            self.group_meta_label.setText("尚未选择数据")
            self.original_view.clear_image()
            self.result_view.clear_image()
            self._loading_prompts = True
            try:
                self.chinese_text.clear()
                self.english_text.clear()
            finally:
                self._loading_prompts = False
            self.chinese_text.setEnabled(False)
            self.english_text.setEnabled(False)
            self._dirty_prompt_fields.clear()
            self.progress_label.setText(f"0 / {len(self.groups)}")
            self._clear_review_inputs()
            self._update_action_states()
            return

        group = self.groups[row]
        self._displayed_group = group
        missing = f"　缺少：{'、'.join(group.missing)}" if group.missing else ""
        original_ok = self.original_view.load_image(group.original_image)
        result_ok = self.result_view.load_image(group.result_image)
        self._current_images_ok = original_ok and result_ok
        decode_warning = "　图片读取失败" if not self._current_images_ok else ""
        self.group_meta_label.setText(
            f"人员：{group.person}　数据组：{group.group_name}　来源：{group.status}"
            f"{missing}{decode_warning}"
        )
        self._loading_prompts = True
        try:
            self.chinese_text.setPlainText(group.chinese_prompt)
            self.english_text.setPlainText(group.english_prompt)
        finally:
            self._loading_prompts = False
        self.chinese_text.setEnabled(True)
        self.english_text.setEnabled(True)
        self._dirty_prompt_fields.clear()
        self.progress_label.setText(f"{row + 1} / {len(self.groups)}")
        self._clear_review_inputs()
        if (
            "原图" in group.missing
            or "结果图" in group.missing
            or not self._current_images_ok
        ):
            for checkbox in self.issue_checks:
                if checkbox.text() == "文件缺失":
                    checkbox.setChecked(True)
                    break
        self._update_action_states()

    def _schedule_prompt_save(self) -> None:
        if self._loading_prompts or self._displayed_group is None:
            return
        sender = self.sender()
        if sender is self.chinese_text:
            self._dirty_prompt_fields.add("chinese")
        elif sender is self.english_text:
            self._dirty_prompt_fields.add("english")
        else:
            self._dirty_prompt_fields.update(("chinese", "english"))
        self.prompt_save_timer.start()
        self.statusBar().showMessage("指令已修改，正在自动保存……", 1500)

    def _flush_prompt_saves(self, show_error: bool = False) -> bool:
        self.prompt_save_timer.stop()
        group = self._displayed_group
        if group is None or not self._dirty_prompt_fields:
            return True

        saved_fields: list[str] = []
        try:
            if "chinese" in self._dirty_prompt_fields:
                path = group.chinese_file or group.folder / f"{group.group_name}_chn.txt"
                text = self.chinese_text.toPlainText()
                write_text_compatible(path, text)
                group.chinese_file = path
                group.chinese_prompt = text
                if "中文指令" in group.missing:
                    group.missing.remove("中文指令")
                saved_fields.append("中文指令")

            if "english" in self._dirty_prompt_fields:
                path = group.english_file or group.folder / f"{group.group_name}_eng.txt"
                text = self.english_text.toPlainText()
                write_text_compatible(path, text)
                group.english_file = path
                group.english_prompt = text
                if "英文指令" in group.missing:
                    group.missing.remove("英文指令")
                saved_fields.append("英文指令")
        except OSError as exc:
            self.statusBar().showMessage(f"指令自动保存失败：{exc}", 8000)
            if show_error:
                self._show_error("指令保存失败", exc)
            return False

        self._dirty_prompt_fields.clear()
        # Prevent the watcher from rebuilding the current editor merely because
        # this program changed the prompt file's timestamp.
        self._queue_signature = self._make_queue_signature(self.groups)
        self.statusBar().showMessage(f"已自动保存：{'、'.join(saved_fields)}", 3500)
        self._update_action_states()
        return True

    def _clear_review_inputs(self) -> None:
        for checkbox in self.issue_checks:
            checkbox.setChecked(False)
        self.remark_edit.clear()

    def current_group(self) -> DataGroup | None:
        row = self.queue_list.currentRow()
        if 0 <= row < len(self.groups):
            return self.groups[row]
        return None

    def pass_current(self) -> None:
        group = self.current_group()
        if group is None or self.operations is None:
            return
        if not self._flush_prompt_saves(show_error=True):
            return
        if not group.is_complete:
            QtWidgets.QMessageBox.warning(
                self, "无法通过", "该数据组文件不完整：" + "、".join(group.missing)
            )
            return
        row = self.queue_list.currentRow()
        try:
            self.operations.pass_group(group)
        except (QualityOperationError, OSError) as exc:
            self._show_error("质检通过操作失败", exc)
            return
        self.statusBar().showMessage(f"已通过：{group.person} / {group.group_name}", 5000)
        self.refresh_queue(preferred_row=row)

    def fail_current(self) -> None:
        group = self.current_group()
        if group is None or self.operations is None:
            return
        if not self._flush_prompt_saves(show_error=True):
            return
        issues = [checkbox.text() for checkbox in self.issue_checks if checkbox.isChecked()]
        remark = self.remark_edit.toPlainText().strip()
        row = self.queue_list.currentRow()
        try:
            self.operations.fail_group(group, issues, remark)
        except (QualityOperationError, OSError) as exc:
            self._show_error("质检不通过操作失败", exc)
            return
        action_text = "已追加返修记录" if group.status == "待返修" else "已退回返修"
        self.statusBar().showMessage(f"{action_text}：{group.person} / {group.group_name}", 5000)
        self.refresh_queue(preferred_row=row)


    def delete_current_group(self) -> None:
        group = self.current_group()
        if group is None or self.operations is None:
            return
        if not self._flush_prompt_saves(show_error=True):
            return

        first = QtWidgets.QMessageBox.warning(
            self,
            "确认删除数据组",
            f"即将删除以下整个数据组文件夹：\n\n"
            f"人员：{group.person}\n数据组：{group.group_name}\n来源：{group.status}\n\n"
            "文件夹会被移动到系统回收站，不会进入质检完成或待返修。\n"
            "是否继续？",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if first != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        typed, accepted = QtWidgets.QInputDialog.getText(
            self,
            "二次确认",
            f"请输入数据组编号 {group.group_name} 以确认删除：",
        )
        if not accepted:
            return
        if typed.strip() != group.group_name:
            QtWidgets.QMessageBox.warning(
                self, "编号不一致", "输入的数据组编号不一致，已取消删除。"
            )
            return

        row = self.queue_list.currentRow()
        try:
            self.operations.delete_group(group)
        except (QualityOperationError, OSError) as exc:
            self._show_error("删除数据组失败", exc)
            return
        self.statusBar().showMessage(
            f"已移动到系统回收站：{group.person} / {group.group_name}", 7000
        )
        self.refresh_queue(preferred_row=row)

    def undo_last(self) -> None:
        if self.operations is None:
            return
        try:
            record = self.operations.undo_last()
        except (QualityOperationError, OSError) as exc:
            self._show_error("撤销失败", exc)
            return
        self.statusBar().showMessage(
            f"已撤销：{record.action} / {record.person} / {record.group_name}", 5000
        )
        self.refresh_queue()

    def go_previous(self) -> None:
        row = self.queue_list.currentRow()
        if self.groups:
            self.queue_list.setCurrentRow(max(0, row - 1))

    def go_next(self) -> None:
        row = self.queue_list.currentRow()
        if self.groups:
            self.queue_list.setCurrentRow(min(len(self.groups) - 1, row + 1))

    def export_daily_report(self) -> None:
        if self.root_path is None:
            return
        now = datetime.now()
        default_dir = self.root_path / "质检报表"
        default_dir.mkdir(parents=True, exist_ok=True)
        default_path = default_dir / f"质检统计_{now:%Y-%m-%d_%H%M%S}.xlsx"
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "导出质检统计表",
            str(default_path),
            "Excel 工作簿 (*.xlsx)",
        )
        if not selected:
            return
        output = Path(selected)
        if output.suffix.lower() != ".xlsx":
            output = output.with_suffix(".xlsx")
        try:
            daily_records = load_effective_records(self.root_path, date.today().isoformat())
            export_report(self.root_path, output, daily_records)
        except (OSError, ValueError) as exc:
            self._show_error("导出报表失败", exc)
            return
        self.statusBar().showMessage(f"报表已导出：{output}", 8000)
        answer = QtWidgets.QMessageBox.question(
            self,
            "导出完成",
            f"质检统计表已保存：\n\n{output}\n\n是否打开所在文件夹？",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            self._open_in_file_manager(output.parent)


    def run_ai_compare(self) -> None:
        group = self.current_group()
        if (
            group is None
            or self.model_manager is None
            or group.original_image is None
            or group.result_image is None
            or self._ai_thread is not None
        ):
            return
        if not self.model_manager.is_installed("onnx-community/dinov2-small"):
            QtWidgets.QMessageBox.information(
                self,
                "AI辅助比较",
                "请先点击“AI辅助模型”下载模型。",
            )
            return

        self.ai_compare_button.setEnabled(False)
        self.statusBar().showMessage("正在进行 AI 辅助比较……")
        self._ai_thread = QtCore.QThread(self)
        self._ai_worker = AiCompareWorker(
            self.model_manager,
            group.original_image,
            group.result_image,
        )
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.finished.connect(self._ai_compare_finished)
        self._ai_worker.failed.connect(self._ai_compare_failed)
        self._ai_worker.finished.connect(self._ai_thread.quit)
        self._ai_worker.failed.connect(self._ai_thread.quit)
        self._ai_thread.finished.connect(self._ai_worker.deleteLater)
        self._ai_thread.finished.connect(self._ai_thread_finished)
        self._ai_thread.start()

    @QtCore.Slot(float)
    def _ai_compare_finished(self, score: float) -> None:
        percent = max(-1.0, min(1.0, score)) * 100
        self.statusBar().showMessage(f"AI视觉相似度：{percent:.1f}%（仅供人工参考）", 10000)
        QtWidgets.QMessageBox.information(
            self,
            "AI辅助比较完成",
            f"原图与结果图的视觉特征相似度：{percent:.1f}%\n\n"
            "该数值仅用于提醒，不会自动决定通过或不通过。",
        )

    @QtCore.Slot(str)
    def _ai_compare_failed(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)
        QtWidgets.QMessageBox.warning(self, "AI辅助比较失败", message)

    @QtCore.Slot()
    def _ai_thread_finished(self) -> None:
        self._ai_thread = None
        self._ai_worker = None
        self._update_action_states()

    def open_model_dialog(self) -> None:
        if self.model_manager is None:
            QtWidgets.QMessageBox.information(
                self,
                "AI辅助模型",
                "当前启动方式没有提供程序缓存目录，无法保存模型。",
            )
            return
        dialog = ModelDownloadDialog(self.model_manager, self)
        dialog.exec()
        self._update_action_states()

    def open_root_folder(self) -> None:
        if self.root_path is not None:
            self._open_in_file_manager(self.root_path)

    def _open_in_file_manager(self, path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            self._show_error("打开文件夹失败", exc)

    def _schedule_refresh(self) -> None:
        self.refresh_debounce.start()

    def _periodic_refresh(self) -> None:
        if self.root_path is not None and not self.refresh_debounce.isActive():
            self.refresh_queue()

    def _update_action_states(self) -> None:
        group = self.current_group()
        self.pass_button.setEnabled(
            group is not None and group.is_complete and self._current_images_ok
        )
        self.fail_button.setEnabled(group is not None)
        self.delete_button.setEnabled(group is not None)
        self.previous_button.setEnabled(group is not None and self.queue_list.currentRow() > 0)
        self.next_button.setEnabled(
            group is not None and self.queue_list.currentRow() < len(self.groups) - 1
        )
        self.undo_button.setEnabled(self.operations is not None and self.operations.can_undo)
        model_ready = (
            self.model_manager is not None
            and self.model_manager.is_installed("onnx-community/dinov2-small")
        )
        self.ai_compare_button.setEnabled(
            group is not None
            and group.original_image is not None
            and group.result_image is not None
            and model_ready
            and self._ai_thread is None
        )

    def _group_key(self, group: DataGroup) -> tuple[str, str, str]:
        return group.status, group.person, group.group_name

    def _current_key(self) -> tuple[str, str, str] | None:
        group = self.current_group()
        return self._group_key(group) if group is not None else None

    def _show_error(self, title: str, error: Exception) -> None:
        detail = str(error)
        if isinstance(error, DestinationExistsError):
            detail += "\n\n请先检查目标状态目录中的同名数据组。"
        QtWidgets.QMessageBox.critical(self, title, detail)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._ai_thread is not None:
            QtWidgets.QMessageBox.information(
                self,
                "AI辅助比较中",
                "AI 辅助比较尚未完成，请等待完成后再关闭工具。",
            )
            event.ignore()
            return
        if not self._flush_prompt_saves(show_error=True):
            event.ignore()
            return
        self.watcher.stop()
        super().closeEvent(event)
