import json
from pathlib import Path

from PIL import Image

from app.distribution_qc import sync_qc_result
from app.models import DataGroup
from app.operations import QualityOperations


def test_qc_pass_syncs_back_to_distribution_state(tmp_path: Path):
    task_id = "A" * 22
    task_path = tmp_path / ".图片分发中心" / "tasks" / f"{task_id}.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(json.dumps({"task_id": task_id, "sha256": "abc", "state": "UPLOADED_PENDING_QC"}), encoding="utf-8")
    folder = tmp_path / "质检项目" / "待质检" / "成员A" / task_id
    folder.mkdir(parents=True)
    Image.new("RGB", (2048, 2048)).save(folder / f"{task_id}.jpg")
    Image.new("RGB", (2048, 2048)).save(folder / f"{task_id}_edit.jpg")
    (folder / f"{task_id}_chn.txt").touch(); (folder / f"{task_id}_eng.txt").touch()
    (folder / "distribution-task.json").write_text(json.dumps({"task_id": task_id}), encoding="utf-8")

    group = DataGroup("待质检", "成员A", task_id, folder, folder / f"{task_id}.jpg", folder / f"{task_id}_edit.jpg", folder / f"{task_id}_chn.txt", folder / f"{task_id}_eng.txt")
    QualityOperations(tmp_path / "质检项目").pass_group(group)
    assert json.loads(task_path.read_text(encoding="utf-8"))["state"] == "QC_PASS"
    assert (tmp_path / ".图片分发中心" / "successful-images.jsonl").is_file()
