from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ..image_loader import ImageLoadError, LoadedImage, load_image_for_display


class ZoomableImageView(QtWidgets.QGraphicsView):
    """Image viewer with cached fit preview and explicit full-resolution 1:1."""

    zoom_changed = QtCore.Signal(float)
    image_info_changed = QtCore.Signal(int, int, str)

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self._pixmap_item = QtWidgets.QGraphicsPixmapItem()
        self._placeholder = QtWidgets.QGraphicsSimpleTextItem("未加载图片")
        self._placeholder.setBrush(QtGui.QBrush(QtGui.QColor("#7A8490")))
        placeholder_font = self._placeholder.font()
        placeholder_font.setPointSize(12)
        self._placeholder.setFont(placeholder_font)
        self._scene.addItem(self._pixmap_item)
        self._scene.addItem(self._placeholder)
        self.setScene(self._scene)

        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#171B21")))
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing
            | QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setMinimumSize(320, 300)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._has_image = False
        self._scale_value = 1.0
        self._fit_mode = True
        self._image_dimensions = (0, 0)
        self._image_format = ""
        self._refit_pending = False
        self._source_path: Path | None = None
        self._full_resolution_loaded = False
        self._center_placeholder()

    @property
    def has_image(self) -> bool:
        return self._has_image

    @property
    def fit_mode(self) -> bool:
        return self._fit_mode

    @property
    def image_dimensions(self) -> tuple[int, int]:
        return self._image_dimensions

    @property
    def image_format(self) -> str:
        return self._image_format

    @property
    def full_resolution_loaded(self) -> bool:
        return self._full_resolution_loaded

    def clear_image(self, message: str = "未加载图片") -> None:
        self._pixmap_item.setPixmap(QtGui.QPixmap())
        self._placeholder.setText(message)
        self._placeholder.show()
        self._has_image = False
        self._fit_mode = True
        self._image_dimensions = (0, 0)
        self._image_format = ""
        self._source_path = None
        self._full_resolution_loaded = False
        self.resetTransform()
        self._scale_value = 1.0
        self._scene.setSceneRect(QtCore.QRectF())
        self._center_placeholder()
        self.zoom_changed.emit(self._scale_value)
        self.image_info_changed.emit(0, 0, "")

    def _preview_size(self) -> tuple[int, int]:
        viewport = self.viewport().size()
        return (
            min(2560, max(1024, viewport.width() * 2)),
            min(2560, max(1024, viewport.height() * 2)),
        )

    def _apply_loaded(self, loaded: LoadedImage, *, full_resolution: bool) -> bool:
        pixmap = QtGui.QPixmap.fromImage(loaded.image)
        if pixmap.isNull():
            self.clear_image("图片已解码，但无法创建显示画面")
            return False
        self._pixmap_item.setPixmap(pixmap)
        self._placeholder.hide()
        self._scene.setSceneRect(QtCore.QRectF(pixmap.rect()))
        self._has_image = True
        self._full_resolution_loaded = full_resolution
        self._image_dimensions = (loaded.width, loaded.height)
        self._image_format = loaded.file_format
        self.image_info_changed.emit(loaded.width, loaded.height, loaded.file_format)
        return True

    def load_image(self, path: Path | str | None) -> bool:
        if path is None:
            self.clear_image("缺少图片")
            return False
        image_path = Path(path)
        if not image_path.is_file():
            self.clear_image("图片文件不存在")
            return False
        try:
            loaded = load_image_for_display(image_path, max_size=self._preview_size())
        except ImageLoadError as exc:
            self.clear_image(f"无法读取图片\n{exc}")
            return False

        self._source_path = image_path
        if not self._apply_loaded(loaded, full_resolution=False):
            return False
        self._fit_mode = True
        self.fit_to_view()
        self._schedule_refit()
        return True

    def _ensure_full_resolution(self) -> bool:
        if self._full_resolution_loaded:
            return True
        if self._source_path is None:
            return False
        try:
            loaded = load_image_for_display(self._source_path)
        except ImageLoadError as exc:
            self.clear_image(f"无法读取完整图片\n{exc}")
            return False
        return self._apply_loaded(loaded, full_resolution=True)

    def fit_to_view(self) -> None:
        if not self._has_image:
            return
        self._fit_mode = True
        self.resetTransform()
        self.fitInView(self._pixmap_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self._pixmap_item)
        self._scale_value = self.transform().m11()
        self.zoom_changed.emit(self._scale_value)

    def actual_size(self) -> None:
        if not self._has_image or not self._ensure_full_resolution():
            return
        self._fit_mode = False
        self.resetTransform()
        self.centerOn(self._pixmap_item)
        self._scale_value = 1.0
        self.zoom_changed.emit(self._scale_value)

    def zoom_by(self, factor: float) -> bool:
        if not self._has_image or factor <= 0:
            return False
        current = self.transform().m11()
        next_value = current * factor
        if not 0.03 <= next_value <= 30:
            return False
        self._fit_mode = False
        self.scale(factor, factor)
        self._scale_value = next_value
        self.zoom_changed.emit(next_value)
        return True

    def zoom_in(self) -> bool:
        return self.zoom_by(1.25)

    def zoom_out(self) -> bool:
        return self.zoom_by(0.8)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._has_image:
            super().wheelEvent(event)
            return
        self.zoom_by(1.25 if event.angleDelta().y() > 0 else 0.8)
        event.accept()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._has_image:
            self.fit_to_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._has_image and self._fit_mode:
            self._schedule_refit()
        elif not self._has_image:
            self._center_placeholder()

    def _schedule_refit(self) -> None:
        if self._refit_pending:
            return
        self._refit_pending = True
        QtCore.QTimer.singleShot(0, self._run_scheduled_refit)

    def _run_scheduled_refit(self) -> None:
        self._refit_pending = False
        if self._has_image and self._fit_mode:
            self.fit_to_view()

    def _center_placeholder(self) -> None:
        rect = self.viewport().rect()
        text_rect = self._placeholder.boundingRect()
        self._placeholder.setPos(
            max(0, (rect.width() - text_rect.width()) / 2),
            max(0, (rect.height() - text_rect.height()) / 2),
        )
