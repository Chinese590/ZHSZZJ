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
        match = re.match(r"^(\d+)(?:$|[_-])", image.stem)
        if not match:
            warnings.append(QcWarning("NUMBER_MISSING", "图片文件名缺少数字编号"))
        elif folder_number and match.group(1) != folder_number:
            warnings.append(QcWarning("NUMBER_MISMATCH", "文件夹编号与图片编号不一致"))
        if hashlib.sha256(image.read_bytes()).hexdigest() in known:
            warnings.append(QcWarning("EXACT_REUSE", "图片已成功使用，禁止重复"))
    return warnings


def sync_qc_result(project_root: Path, task_id: str, result: dict) -> str:
    """Apply one structured QC result and register successful output hashes."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}", task_id) or result.get("task_id") != task_id or result.get("verdict") not in {"PASS", "FAIL", "REPAIR_REQUIRED"}:
        raise ValueError("质检结果契约无效")
    state_dir = Path(project_root) / ".图片分发中心" / "tasks"
    task_path = next(state_dir.glob(f"{task_id}.json"), None)
    if task_path is None:
        raise FileNotFoundError(task_id)
    task = json.loads(task_path.read_text(encoding="utf-8"))
    verdict = str(result["verdict"])
    task["state"] = "QC_PASS" if verdict == "PASS" else "QC_REPAIR"
    task["qc_status"] = verdict
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    if verdict == "PASS":
        registry = Path(project_root) / ".图片分发中心" / "successful-images.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        with registry.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"task_id": task_id, "sha256": task["sha256"], "checked_at": result.get("checked_at", "")}, ensure_ascii=False) + "\n")
    return task["state"]
