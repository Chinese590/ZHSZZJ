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
    second_scale = view.transform().m11()

    assert second_scale > first_scale
    view.close()
