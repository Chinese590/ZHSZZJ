from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageFile, ImageOps, UnidentifiedImageError
from PySide6 import QtCore, QtGui

# Some production JPEG files are valid enough to display but contain a truncated
# final block. Pillow can safely render the available pixels in that case.
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageLoadError(RuntimeError):
    """Raised when neither Pillow nor Qt can decode an image."""


@dataclass(frozen=True, slots=True)
class LoadedImage:
    image: QtGui.QImage
    width: int
    height: int
    source_mode: str
    color_managed: bool
    file_format: str


def _normalize_file_format(value: str | bytes | None, suffix: str = "") -> str:
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="ignore")
    normalized = str(value or "").strip().upper()
    aliases = {"JPG": "JPEG", "JPE": "JPEG", "TIF": "TIFF"}
    normalized = aliases.get(normalized, normalized)
    if normalized:
        return normalized
    fallback = suffix.lstrip(".").upper()
    return aliases.get(fallback, fallback or "未知格式")


def _apply_srgb_color_management(image: Image.Image) -> tuple[Image.Image, bool]:
    """Return an RGB/RGBA Pillow image converted to the sRGB display space."""
    icc_profile = image.info.get("icc_profile")
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    alpha = image.convert("RGBA").getchannel("A") if has_alpha else None
    color_managed = False

    if icc_profile:
        try:
            source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
            target_profile = ImageCms.createProfile("sRGB")
            working = image
            if working.mode in {"RGBA", "LA", "PA", "P"}:
                working = working.convert("RGB")
            converted = ImageCms.profileToProfile(
                working,
                source_profile,
                target_profile,
                outputMode="RGB",
                renderingIntent=ImageCms.Intent.PERCEPTUAL,
            )
            color_managed = True
        except (ImageCms.PyCMSError, OSError, ValueError, TypeError):
            converted = image.convert("RGB")
    else:
        converted = image.convert("RGB")

    if alpha is not None:
        converted = converted.convert("RGBA")
        converted.putalpha(alpha)
    return converted, color_managed


def _pillow_to_qimage(image: Image.Image) -> QtGui.QImage:
    if image.mode == "RGBA":
        data = image.tobytes("raw", "RGBA")
        qimage = QtGui.QImage(
            data,
            image.width,
            image.height,
            image.width * 4,
            QtGui.QImage.Format.Format_RGBA8888,
        )
    else:
        if image.mode != "RGB":
            image = image.convert("RGB")
        data = image.tobytes("raw", "RGB")
        qimage = QtGui.QImage(
            data,
            image.width,
            image.height,
            image.width * 3,
            QtGui.QImage.Format.Format_RGB888,
        )
    return qimage.copy()


def _oriented_dimensions(source: Image.Image) -> tuple[int, int]:
    width, height = source.size
    try:
        orientation = int(source.getexif().get(274, 1))
    except (AttributeError, TypeError, ValueError):
        orientation = 1
    return (height, width) if orientation in {5, 6, 7, 8} else (width, height)


def _load_with_pillow(path: Path, max_size: tuple[int, int] | None = None) -> LoadedImage:
    with Image.open(path) as source:
        source_mode = source.mode
        file_format = _normalize_file_format(source.format, path.suffix)
        actual_width, actual_height = _oriented_dimensions(source)

        # JPEG draft mode avoids decoding every source pixel for a fit-to-window
        # preview. Other formats are reduced immediately after EXIF orientation.
        if max_size and file_format == "JPEG":
            try:
                source.draft("RGB", max_size)
            except (OSError, ValueError):
                pass
        oriented = ImageOps.exif_transpose(source)
        if max_size:
            oriented.thumbnail(max_size, Image.Resampling.LANCZOS, reducing_gap=3.0)
        display_image, color_managed = _apply_srgb_color_management(oriented)
        qimage = _pillow_to_qimage(display_image)
        if qimage.isNull():
            raise ImageLoadError("Pillow 已解码，但转换为显示图像失败")
        return LoadedImage(
            image=qimage,
            width=actual_width,
            height=actual_height,
            source_mode=source_mode,
            color_managed=color_managed,
            file_format=file_format,
        )


def _load_with_qt(path: Path, max_size: tuple[int, int] | None = None) -> LoadedImage:
    reader = QtGui.QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
    source_size = reader.size()
    if max_size and source_size.isValid():
        target = source_size.scaled(
            max_size[0],
            max_size[1],
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        )
        if target.width() < source_size.width() or target.height() < source_size.height():
            reader.setScaledSize(target)
    image = reader.read()
    if image.isNull():
        raise ImageLoadError(reader.errorString() or "Qt 无法识别图片格式")

    color_managed = False
    color_space = image.colorSpace()
    if color_space.isValid():
        try:
            srgb = QtGui.QColorSpace(QtGui.QColorSpace.NamedColorSpace.SRgb)
            if color_space != srgb:
                converted = image.convertedToColorSpace(srgb)
                if not converted.isNull():
                    image = converted
                    color_managed = True
        except (AttributeError, TypeError):
            pass

    actual_width = source_size.width() if source_size.isValid() else image.width()
    actual_height = source_size.height() if source_size.isValid() else image.height()
    return LoadedImage(
        image=image,
        width=actual_width,
        height=actual_height,
        source_mode=str(image.format()),
        color_managed=color_managed,
        file_format=_normalize_file_format(bytes(reader.format()), path.suffix),
    )


def _decode(path: Path, max_size: tuple[int, int] | None) -> LoadedImage:
    pillow_error = ""
    try:
        return _load_with_pillow(path, max_size=max_size)
    except (UnidentifiedImageError, OSError, ValueError, ImageLoadError) as exc:
        pillow_error = str(exc)

    try:
        return _load_with_qt(path, max_size=max_size)
    except ImageLoadError as qt_exc:
        detail = f"Pillow：{pillow_error or '无法读取'}；Qt：{qt_exc}"
        raise ImageLoadError(detail) from qt_exc


@lru_cache(maxsize=24)
def _load_preview_cached(
    path_text: str,
    modified_ns: int,
    file_size: int,
    max_size: tuple[int, int],
) -> LoadedImage:
    del modified_ns, file_size
    return _decode(Path(path_text), max_size)


def load_image_for_display(
    path: Path | str,
    max_size: tuple[int, int] | None = None,
) -> LoadedImage:
    """Decode an image robustly while keeping fit previews lightweight.

    ``max_size`` creates and caches a reduced display image while preserving the
    source pixel dimensions in ``LoadedImage.width`` and ``height``. Passing
    ``None`` performs the explicit full-resolution load used by the 1:1 action.
    """
    image_path = Path(path)
    if not image_path.is_file():
        raise ImageLoadError(f"图片文件不存在：{image_path}")
    if max_size is None:
        return _decode(image_path, None)
    normalized = (max(1, int(max_size[0])), max(1, int(max_size[1])))
    stat = image_path.stat()
    return _load_preview_cached(
        str(image_path.resolve()), stat.st_mtime_ns, stat.st_size, normalized
    )
