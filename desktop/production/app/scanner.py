from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .models import DataGroup

STATUS_FOLDERS = ("质检完成", "待返修", "待质检", "返修提交")
QUEUE_FOLDERS = ("待质检", "返修提交")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".jfif", ".png", ".bmp", ".webp", ".tif", ".tiff", ".gif"}


def detect_text_encoding(raw: bytes) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in ("utf-8", "gb18030"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def read_text_compatible(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    raw = path.read_bytes()
    encoding = detect_text_encoding(raw)
    return raw.decode(encoding, errors="replace")


def write_text_compatible(path: Path, text: str) -> None:
    """Atomically replace a prompt file while preserving its current encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoding = "utf-8"
    if path.exists():
        encoding = detect_text_encoding(path.read_bytes())
    data = text.encode(encoding)

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _choose_preferred(paths: list[Path], preferred_stem: str) -> Path | None:
    for path in paths:
        if path.stem.lower() == preferred_stem.lower():
            return path
    return sorted(paths, key=lambda item: item.name.lower())[0] if paths else None


def inspect_group(folder: Path, status: str, person: str) -> DataGroup:
    files = [item for item in folder.iterdir() if item.is_file()]
    images = [item for item in files if item.suffix.lower() in IMAGE_SUFFIXES]
    def is_result_image(path: Path) -> bool:
        stem = path.stem.lower()
        return stem.endswith(("_edit", "_edit_clean", "_edited"))

    result_images = [item for item in images if is_result_image(item)]
    originals = [item for item in images if not is_result_image(item)]
    chinese_files = [item for item in files if item.name.lower().endswith("_chn.txt")]
    english_files = [item for item in files if item.name.lower().endswith("_eng.txt")]

    group_name = folder.name
    original = _choose_preferred(originals, group_name)
    result = _choose_preferred(result_images, f"{group_name}_edit")
    if result is None and result_images:
        result = sorted(
            result_images,
            key=lambda item: (
                0 if item.stem.lower().endswith("_edit") else 1,
                item.name.lower(),
            ),
        )[0]
    chinese = _choose_preferred(chinese_files, f"{group_name}_chn")
    english = _choose_preferred(english_files, f"{group_name}_eng")

    missing: list[str] = []
    if original is None:
        missing.append("原图")
    if result is None:
        missing.append("结果图")
    if chinese is None:
        missing.append("中文指令")
    if english is None:
        missing.append("英文指令")

    return DataGroup(
        status=status,
        person=person,
        group_name=group_name,
        folder=folder,
        original_image=original,
        result_image=result,
        chinese_file=chinese,
        english_file=english,
        chinese_prompt=read_text_compatible(chinese),
        english_prompt=read_text_compatible(english),
        missing=missing,
    )


def scan_status(root: Path | str, status: str) -> list[DataGroup]:
    root_path = Path(root)
    status_path = root_path / status
    if not status_path.is_dir():
        return []

    groups: list[DataGroup] = []
    for person_dir in sorted((item for item in status_path.iterdir() if item.is_dir()), key=lambda p: p.name.lower()):
        for group_dir in sorted((item for item in person_dir.iterdir() if item.is_dir()), key=lambda p: p.name.lower()):
            groups.append(inspect_group(group_dir, status, person_dir.name))
    return groups


def scan_queue(root: Path | str) -> list[DataGroup]:
    groups: list[DataGroup] = []
    for status in QUEUE_FOLDERS:
        groups.extend(scan_status(root, status))
    status_order = {name: index for index, name in enumerate(QUEUE_FOLDERS)}
    return sorted(groups, key=lambda g: (status_order.get(g.status, 99), g.person.lower(), g.group_name.lower()))


def scan_all_counts(root: Path | str) -> dict[str, dict[str, int]]:
    root_path = Path(root)
    persons: set[str] = set()
    raw: dict[str, dict[str, int]] = {}

    for status in STATUS_FOLDERS:
        status_path = root_path / status
        if not status_path.is_dir():
            continue
        for person_dir in (item for item in status_path.iterdir() if item.is_dir()):
            persons.add(person_dir.name)
            group_count = sum(1 for item in person_dir.iterdir() if item.is_dir())
            raw.setdefault(person_dir.name, {})[status] = group_count

    return {
        person: {status: raw.get(person, {}).get(status, 0) for status in STATUS_FOLDERS}
        for person in sorted(persons, key=str.lower)
    }


def validate_root(root: Path | str) -> list[str]:
    root_path = Path(root)
    return [status for status in STATUS_FOLDERS if not (root_path / status).is_dir()]
