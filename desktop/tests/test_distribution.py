from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
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


def test_distribution_upload_and_recall_follow_owner_and_state(tmp_path):
    service = DistributionService(tmp_path)
    service.create_member("a", "成员A", "password-a")
    service.create_member("b", "成员B", "password-b")
    source = make_image_folder(tmp_path, {"1.jpg": (3000, 3000), "2.jpg": (3000, 3000)})
    Image.new("RGB", (3000, 3000), "#993333").save(source / "2.jpg")
    service.import_images(source)
    assignments = service.distribute(["a", "b"], 1)
    owned = next(item for item in assignments if item.member_id == "a")
    with pytest.raises(PermissionError):
        service.start(owned.task_id, "b")
    assert service.start(owned.task_id, "a").state == "IN_PROGRESS"
    assert service.recall(owned.task_id, "admin", "下班召回").state == "AVAILABLE"
    replacement = service.distribute(["a"], 1)[0]
    assert service.upload(replacement.task_id, "a", source / "1.jpg").state == "UPLOADED_PENDING_QC"
    with pytest.raises(ValueError):
        service.recall(replacement.task_id, "admin", "不能召回已上传")


def test_member_password_is_hashed_and_can_authenticate(tmp_path):
    service = DistributionService(tmp_path)
    service.create_member("member", "成员", "correct-password")
    raw = (tmp_path / ".图片分发中心" / "members.json").read_text(encoding="utf-8")
    assert "correct-password" not in raw
    assert service.authenticate("member", "correct-password")
    assert not service.authenticate("member", "wrong-password")


def test_initialize_admin_and_bulk_members_are_hashed_and_audited(tmp_path):
    service = DistributionService(tmp_path)

    service.initialize_admin("admin", "管理员", "admin-password")
    service.create_members([
        {"member_id": "a", "display_name": "成员 A", "password": "password-a", "role": "member"},
        {"member_id": "b", "display_name": "成员 B", "password": "password-b", "role": "member"},
    ])

    raw = (tmp_path / ".图片分发中心" / "members.json").read_text(encoding="utf-8")
    assert "admin-password" not in raw and "password-a" not in raw
    assert service.is_admin("admin") and service.authenticate("b", "password-b")
    with pytest.raises(ValueError, match="已初始化"):
        service.initialize_admin("other", "其他", "other-password")
    records = service.daily_report(date.today())
    assert [record["action"] for record in records] == ["MEMBER_CREATE"] * 3
    assert {record["role"] for record in records} == {"admin", "member"}


def test_daily_summary_counts_member_workflow_events(tmp_path):
    service = DistributionService(tmp_path)
    service.create_member("a", "成员A", "password-a")
    source = make_image_folder(tmp_path, {"1.jpg": (3000, 3000)})
    task = service.import_images(source).tasks[0]
    service.distribute(["a"], 1)
    service.start(task.task_id, "a")

    summary = service.daily_summary(date.today())

    assert summary["actions"]["DISTRIBUTE"] == 1
    assert summary["members"]["a"] == {"distributed": 1, "started": 1, "uploaded": 0}
    assert summary["task_states"] == {"IN_PROGRESS": 1}
