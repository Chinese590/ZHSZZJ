from __future__ import annotations

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from PIL import Image

from app.distribution import DistributionService


def make_image_folder(root: Path, images: dict[str, tuple[int, int]]) -> Path:
    folder = root / "source"
    folder.mkdir()
    for name, size in images.items():
        Image.new("RGB", size, "#336699").save(folder / name)
    return folder


def test_import_rejects_exact_duplicate_and_keeps_first_task(tmp_path):
    service = DistributionService(tmp_path)
    source = make_image_folder(tmp_path, {"a.jpg": (3000, 3000), "b.jpg": (3000, 3000)})
    shutil.copy2(source / "a.jpg", source / "b.jpg")

    result = service.import_images(source)

    assert result.imported == 1
    assert result.exact_duplicates == ["b.jpg"]
    assert len(list((tmp_path / ".图片分发中心" / "tasks").glob("*.json"))) == 1


def test_import_persists_image_metadata_and_uses_atomic_task_write(tmp_path):
    service = DistributionService(tmp_path)
    source = make_image_folder(tmp_path, {"photo.png": (3000, 2000)})

    result = service.import_images(source)

    task_path = tmp_path / ".图片分发中心" / "tasks" / f"{result.tasks[0].task_id}.json"
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    assert payload["state"] == "AVAILABLE"
    assert payload["width"] == 3000
    assert payload["height"] == 2000
    assert len(payload["sha256"]) == 64
    assert len(payload["perceptual_hash"]) == 16
    assert not list(task_path.parent.glob("*.tmp"))


def test_import_rejects_hashes_already_recorded_as_successful(tmp_path):
    source = make_image_folder(tmp_path, {"done.jpg": (3000, 3000)})
    sha256 = hashlib.sha256((source / "done.jpg").read_bytes()).hexdigest()
    registry = tmp_path / ".图片分发中心" / "successful-images.jsonl"
    registry.parent.mkdir()
    registry.write_text(json.dumps({"sha256": sha256}) + "\n", encoding="utf-8")

    result = DistributionService(tmp_path).import_images(source)

    assert result.imported == 0
    assert result.exact_duplicates == ["done.jpg"]
    assert result.tasks == []


def test_concurrent_import_keeps_one_task_for_the_same_source(tmp_path):
    source = make_image_folder(tmp_path, {"only.jpg": (3000, 3000)})
    service = DistributionService(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.import_images, [source, source]))

    assert sorted(result.imported for result in results) == [0, 1]
    assert len(list((tmp_path / ".图片分发中心" / "tasks").glob("*.json"))) == 1


def test_task_id_and_corrupt_state_fail_closed(tmp_path):
    service = DistributionService(tmp_path)
    with pytest.raises(KeyError):
        service.task("../members")
    corrupt = tmp_path / ".图片分发中心" / "tasks" / "broken.json"
    corrupt.write_text("{not-json", encoding="utf-8")
    source = make_image_folder(tmp_path, {"valid.jpg": (3000, 3000)})
    with pytest.raises(RuntimeError, match="损坏"):
        service.import_images(source)
