from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True, slots=True)
class QcWarning:
    code: str
    message: str


def validate_distribution_task(folder: Path, successful_registry: Path) -> list[QcWarning]:
    folder = Path(folder)
    images = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}]
    warnings: list[QcWarning] = []
    folder_number = folder.name if folder.name.isdigit() else ""
    known = {json.loads(line).get("sha256") for line in successful_registry.read_text(encoding="utf-8").splitlines()} if successful_registry.exists() else set()
    for image in images:
        with Image.open(image) as decoded:
            if min(decoded.size) < 2048:
                warnings.append(QcWarning("MIN_EDGE_LT_2048", "图片最短边小于 2048 像素"))
        match = re.match(r"(\d+)", image.stem)
        if folder_number and match and match.group(1) != folder_number:
            warnings.append(QcWarning("NUMBER_MISMATCH", "文件夹编号与图片编号不一致"))
        if hashlib.sha256(image.read_bytes()).hexdigest() in known:
            warnings.append(QcWarning("EXACT_REUSE", "图片已成功使用，禁止重复"))
    return warnings
