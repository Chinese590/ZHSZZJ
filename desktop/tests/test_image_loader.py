from pathlib import Path

from PIL import Image

from app.image_loader import load_image_for_display


def test_load_cmyk_jpeg_converts_to_display_rgb_and_keeps_dimensions(tmp_path: Path):
    path = tmp_path / "cmyk.jpg"
    Image.new("CMYK", (7, 5), (0, 255, 255, 0)).save(path, format="JPEG", quality=95)

    loaded = load_image_for_display(path)

    assert loaded.width == 7
    assert loaded.height == 5
    pixel = loaded.image.pixelColor(3, 2)
    assert pixel.red() > 220
    assert pixel.green() < 40
    assert pixel.blue() < 40


def test_load_jpeg_applies_exif_orientation(tmp_path: Path):
    path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (8, 3), (30, 80, 140))
    exif = image.getexif()
    exif[274] = 6  # 90 degrees clockwise
    image.save(path, format="JPEG", exif=exif)

    loaded = load_image_for_display(path)

    assert (loaded.width, loaded.height) == (3, 8)


def test_loaded_image_reports_actual_file_format(tmp_path: Path):
    path = tmp_path / "misnamed.jpg"
    Image.new("RGB", (9, 6), (1, 2, 3)).save(path, format="PNG")

    loaded = load_image_for_display(path)

    assert loaded.file_format == "PNG"
