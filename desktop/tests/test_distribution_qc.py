from __future__ import annotations

import hashlib
import json

from PIL import Image

from app.distribution_qc import sync_qc_result, validate_distribution_task


def test_qc_warns_for_small_edge_number_mismatch_and_successful_reuse(tmp_path):
    task = tmp_path / "12345678"; task.mkdir()
    image = task / "87654321_edit.jpg"
    Image.new("RGB", (1800, 3000), "#336699").save(image)
    registry = tmp_path / "successful-images.jsonl"
    registry.write_text(json.dumps({"sha256": hashlib.sha256(image.read_bytes()).hexdigest()}) + "\n", encoding="utf-8")
    assert {item.code for item in validate_distribution_task(task, registry)} == {"MIN_EDGE_LT_2048", "NUMBER_MISMATCH", "EXACT_REUSE"}


def test_qc_pass_sync_registers_successful_image(tmp_path):
    task_dir = tmp_path / ".图片分发中心" / "tasks"; task_dir.mkdir(parents=True)
    task_id = "A" * 22
    (task_dir / f"{task_id}.json").write_text(json.dumps({"task_id": task_id, "sha256": "abc"}), encoding="utf-8")
    assert sync_qc_result(tmp_path, task_id, {"task_id": task_id, "verdict": "PASS"}) == "QC_PASS"
    assert '"sha256": "abc"' in (tmp_path / ".图片分发中心" / "successful-images.jsonl").read_text(encoding="utf-8")
