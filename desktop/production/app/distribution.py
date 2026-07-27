from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
from typing import Any

from PIL import Image


_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True, slots=True)
class Task:
    task_id: str
    image_name: str
    source_path: str
    sha256: str
    perceptual_hash: str
    width: int
    height: int
    state: str = "AVAILABLE"
    member_id: str | None = None
    warnings: tuple[str, ...] = ()
    created_at: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Task":
        return cls(
            task_id=str(payload["task_id"]),
            image_name=str(payload["image_name"]),
            source_path=str(payload["source_path"]),
            sha256=str(payload["sha256"]),
            perceptual_hash=str(payload["perceptual_hash"]),
            width=int(payload["width"]),
            height=int(payload["height"]),
            state=str(payload.get("state", "AVAILABLE")),
            member_id=(None if payload.get("member_id") is None else str(payload["member_id"])),
            warnings=tuple(str(item) for item in payload.get("warnings", [])),
            created_at=str(payload.get("created_at", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "image_name": self.image_name,
            "source_path": self.source_path,
            "sha256": self.sha256,
            "perceptual_hash": self.perceptual_hash,
            "width": self.width,
            "height": self.height,
            "state": self.state,
            "member_id": self.member_id,
            "warnings": list(self.warnings),
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class Assignment:
    task_id: str
    member_id: str


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int
    exact_duplicates: list[str] = field(default_factory=list)
    warnings: dict[str, list[str]] = field(default_factory=dict)
    tasks: list[Task] = field(default_factory=list)


class DistributionService:
    """File-backed task state rooted at ``<project>/.图片分发中心``."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.root = self.project_root / ".图片分发中心"
        self.tasks_dir = self.root / "tasks"
        self.members_path = self.root / "members.json"
        self.audit_path = self.root / "audit.jsonl"
        self.successful_images_path = self.root / "successful-images.jsonl"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        if not self.members_path.exists():
            self._write_json_atomic(self.members_path, [])

    def import_images(self, source: Path) -> ImportResult:
        source = Path(source)
        if not source.is_dir():
            raise ValueError(f"图片目录不存在: {source}")

        existing = self._known_hashes()
        perceptual_hashes = [(task.task_id, task.perceptual_hash) for task in self._tasks()]
        imported: list[Task] = []
        duplicates: list[str] = []
        warnings: dict[str, list[str]] = {}

        for image_path in sorted((path for path in source.iterdir() if path.is_file()), key=lambda path: path.name):
            if image_path.suffix.lower() not in _IMAGE_EXTENSIONS:
                continue
            sha256 = self._sha256(image_path)
            if sha256 in existing:
                duplicates.append(image_path.name)
                self._append_audit("IMPORT_DUPLICATE", image_name=image_path.name, sha256=sha256)
                continue

            width, height, perceptual_hash = self._image_metadata(image_path)
            near_matches = [task_id for task_id, candidate in perceptual_hashes if self._hamming_distance(perceptual_hash, candidate) <= 5]
            task = Task(
                task_id=secrets.token_urlsafe(16),
                image_name=image_path.name,
                source_path=str(image_path.resolve()),
                sha256=sha256,
                perceptual_hash=perceptual_hash,
                width=width,
                height=height,
                warnings=tuple(f"NEAR_DUPLICATE:{task_id}" for task_id in near_matches),
                created_at=self._now(),
            )
            self._write_json_atomic(self.tasks_dir / f"{task.task_id}.json", task.to_dict())
            self._append_audit("IMPORT", task_id=task.task_id, image_name=task.image_name, sha256=sha256)
            imported.append(task)
            existing.add(sha256)
            perceptual_hashes.append((task.task_id, perceptual_hash))
            if near_matches:
                warnings[image_path.name] = list(task.warnings)

        return ImportResult(len(imported), duplicates, warnings, imported)

    def my_tasks(self, member_id: str) -> list[Task]:
        return [task for task in self._tasks() if task.member_id == member_id]

    def task(self, task_id: str) -> Task:
        payload = self._read_json(self.tasks_dir / f"{task_id}.json")
        if not isinstance(payload, dict):
            raise KeyError(task_id)
        return Task.from_dict(payload)

    def daily_report(self, day: date) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        prefix = day.isoformat()
        report: list[dict[str, Any]] = []
        for raw_line in self.audit_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and str(record.get("timestamp", "")).startswith(prefix):
                report.append(record)
        return report

    def _tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for path in sorted(self.tasks_dir.glob("*.json")):
            payload = self._read_json(path)
            if isinstance(payload, dict):
                try:
                    tasks.append(Task.from_dict(payload))
                except (KeyError, TypeError, ValueError):
                    continue
        return tasks

    def _known_hashes(self) -> set[str]:
        hashes = {task.sha256 for task in self._tasks()}
        if not self.successful_images_path.exists():
            return hashes
        for raw_line in self.successful_images_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and record.get("sha256"):
                hashes.add(str(record["sha256"]))
        return hashes

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _image_metadata(path: Path) -> tuple[int, int, str]:
        with Image.open(path) as image:
            width, height = image.size
            grayscale = image.convert("L").resize((8, 8))
            values = list(grayscale.tobytes())
        average = sum(values) / len(values)
        bits = "".join("1" if value >= average else "0" for value in values)
        return width, height, f"{int(bits, 2):016x}"

    @staticmethod
    def _hamming_distance(left: str, right: str) -> int:
        return (int(left, 16) ^ int(right, 16)).bit_count()

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)

    def _append_audit(self, action: str, **details: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": self._now(), "action": action, **details}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

