import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6 import QtWidgets

from app.ui.image_viewer import ZoomableImageView


def test_viewer_reports_pixels_and_refits_when_resized(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    path = tmp_path / "wide.jpg"
    Image.new("RGB", (1200, 400), (120, 80, 40)).save(path)
    view = ZoomableImageView()
    view.resize(400, 300)
    view.show()
    app.processEvents()
    assert view.load_image(path) is True
    app.processEvents()
    first_scale = view.transform().m11()
    assert view.image_dimensions == (1200, 400)
    assert view.fit_mode is True
    view.resize(800, 300)
    app.processEvents()
    assert view.transform().m11() > first_scale
    view.close()


def test_viewer_uses_preview_until_actual_size_requested(tmp_path: Path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    path = tmp_path / "large.png"
    Image.new("RGB", (5000, 3000), (20, 40, 60)).save(path)
    view = ZoomableImageView()
    view.resize(500, 400)
    view.show()
    app.processEvents()
    assert view.load_image(path) is True
    assert view.full_resolution_loaded is False
    assert view._pixmap_item.pixmap().width() < 5000
    view.actual_size()
    assert view.full_resolution_loaded is True
    assert view._pixmap_item.pixmap().width() == 5000
    view.close()
