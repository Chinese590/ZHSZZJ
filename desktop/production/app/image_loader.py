from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageFile, ImageOps, UnidentifiedImageError
from PySide6 import QtGui

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
    # QImage initially points at Pillow-owned bytes. copy() gives Qt independent
    # storage so the image remains valid after this function returns.
    return qimage.copy()


def _load_with_pillow(path: Path) -> LoadedImage:
    with Image.open(path) as source:
        source.load()
        source_mode = source.mode
        file_format = _normalize_file_format(source.format, path.suffix)
        oriented = ImageOps.exif_transpose(source)
        display_image, color_managed = _apply_srgb_color_management(oriented)
        qimage = _pillow_to_qimage(display_image)
        if qimage.isNull():
            raise ImageLoadError("Pillow 已解码，但转换为显示图像失败")
        return LoadedImage(
            image=qimage,
            width=qimage.width(),
            height=qimage.height(),
            source_mode=source_mode,
            color_managed=color_managed,
            file_format=file_format,
        )


def _load_with_qt(path: Path) -> LoadedImage:
    reader = QtGui.QImageReader(str(path))
    reader.setAutoTransform(True)
    reader.setDecideFormatFromContent(True)
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

    return LoadedImage(
        image=image,
        width=image.width(),
        height=image.height(),
        source_mode=str(image.format()),
        color_managed=color_managed,
        file_format=_normalize_file_format(bytes(reader.format()), path.suffix),
    )


def load_image_for_display(path: Path | str) -> LoadedImage:
    """Decode an image robustly, apply EXIF orientation and normalize to sRGB."""
    image_path = Path(path)
    if not image_path.is_file():
        raise ImageLoadError(f"图片文件不存在：{image_path}")

    pillow_error = ""
    try:
        return _load_with_pillow(image_path)
    except (UnidentifiedImageError, OSError, ValueError, ImageLoadError) as exc:
        pillow_error = str(exc)

    try:
        return _load_with_qt(image_path)
    except ImageLoadError as qt_exc:
        detail = f"Pillow：{pillow_error or '无法读取'}；Qt：{qt_exc}"
        raise ImageLoadError(detail) from qt_exc
