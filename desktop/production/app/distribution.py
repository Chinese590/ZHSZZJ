from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
from typing import Any

from PIL import Image


_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{22}")
_BUSINESS_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


class DistributionIntegrityError(RuntimeError):
    """Raised when persisted distribution state cannot safely be trusted."""


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
        self.library_dir = self.project_root / "图片库"
        self.members_path = self.root / "members.json"
        self.audit_path = self.root / "audit.jsonl"
        self.successful_images_path = self.root / "successful-images.jsonl"
        self.uploads_dir = self.root / "uploads"
        self._lock = threading.RLock()
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        if not self.members_path.exists():
            self._write_json_atomic(self.members_path, [])

    def import_images(self, source: Path) -> ImportResult:
        source = Path(source).resolve()
        if not source.is_dir():
            raise ValueError(f"图片目录不存在: {source}")
        with self._lock:
            existing = self._known_hashes()
            perceptual_hashes = [(task.task_id, task.perceptual_hash) for task in self._tasks()]
            imported: list[Task] = []
            duplicates: list[str] = []
            warnings: dict[str, list[str]] = {}

            for image_path in sorted(source.rglob("*"), key=lambda path: str(path.relative_to(source))):
                if not image_path.is_file() or image_path.is_symlink() or image_path.suffix.lower() not in _IMAGE_EXTENSIONS:
                    continue
                sha256 = self._sha256(image_path)
                if sha256 in existing:
                    duplicates.append(str(image_path.relative_to(source)))
                    self._append_audit("IMPORT_DUPLICATE", image_name=image_path.name, sha256=sha256)
                    continue

                width, height, perceptual_hash = self._image_metadata(image_path)
                near_matches = [task_id for task_id, candidate in perceptual_hashes if self._hamming_distance(perceptual_hash, candidate) <= 5]
                task_id = secrets.token_urlsafe(16)
                stored_name = f"{task_id}{image_path.suffix.lower()}"
                stored_path = self.library_dir / stored_name
                self._copy_file_atomic(image_path, stored_path)
                task = Task(
                    task_id=task_id,
                    image_name=image_path.name,
                    source_path=str(Path("图片库") / stored_name),
                    sha256=sha256,
                    perceptual_hash=perceptual_hash,
                    width=width,
                    height=height,
                    warnings=tuple(f"NEAR_DUPLICATE:{task_id}" for task_id in near_matches),
                    created_at=self._now(),
                )
                task_path = self._task_path(task.task_id)
                try:
                    self._write_json_atomic(task_path, task.to_dict())
                    self._append_audit("IMPORT", task_id=task.task_id, image_name=task.image_name, sha256=sha256)
                except Exception:
                    task_path.unlink(missing_ok=True)
                    stored_path.unlink(missing_ok=True)
                    raise
                imported.append(task)
                existing.add(sha256)
                perceptual_hashes.append((task.task_id, perceptual_hash))
                if near_matches:
                    warnings[image_path.name] = list(task.warnings)

            return ImportResult(len(imported), duplicates, warnings, imported)

    def my_tasks(self, member_id: str) -> list[Task]:
        return [task for task in self._tasks() if task.member_id == member_id]

    def create_member(self, member_id: str, display_name: str, password: str = "") -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", member_id):
            raise ValueError("成员 ID 只能包含字母、数字、下划线和连字符")
        with self._lock:
            members = self._read_json(self.members_path)
            if not isinstance(members, list):
                raise DistributionIntegrityError("成员文件损坏")
            if any(item.get("member_id") == member_id for item in members if isinstance(item, dict)):
                raise ValueError("成员已存在")
            password_salt = secrets.token_hex(16)
            members.append({"member_id": member_id, "display_name": display_name, "active": True, "password_salt": password_salt, "password_hash": self._password_hash(password, password_salt)})
            self._write_json_atomic(self.members_path, members)
            self._append_audit("MEMBER_CREATE", member_id=member_id)

    def authenticate(self, member_id: str, password: str) -> bool:
        members = self._read_json(self.members_path)
        if not isinstance(members, list):
            raise DistributionIntegrityError("成员文件损坏")
        for item in members:
            if isinstance(item, dict) and item.get("member_id") == member_id and item.get("active"):
                return secrets.compare_digest(str(item.get("password_hash", "")), self._password_hash(password, str(item.get("password_salt", ""))))
        return False

    def distribute(self, member_ids: list[str], per_member: int) -> list[Assignment]:
        if per_member < 1 or not member_ids or len(set(member_ids)) != len(member_ids):
            raise ValueError("分发人数或数量无效")
        with self._lock:
            available = [task for task in self._tasks() if task.state == "AVAILABLE"]
            needed = len(member_ids) * per_member
            if len(available) < needed:
                raise ValueError(f"可分发图片不足：需要 {needed}，当前 {len(available)}")
            selected = secrets.SystemRandom().sample(available, needed)
            assignments: list[Assignment] = []
            for index, task in enumerate(selected):
                member_id = member_ids[index % len(member_ids)]
                assigned = replace(task, state="ASSIGNED", member_id=member_id)
                self._write_json_atomic(self._task_path(task.task_id), assigned.to_dict())
                self._append_audit("DISTRIBUTE", task_id=task.task_id, member_id=member_id)
                assignments.append(Assignment(task.task_id, member_id))
            return assignments

    def start(self, task_id: str, member_id: str) -> Task:
        return self._transition(task_id, member_id, ("ASSIGNED",), "IN_PROGRESS", "START")

    def upload(self, task_id: str, member_id: str, result_image: Path) -> Task:
        result_image = Path(result_image)
        if not result_image.is_file() or result_image.suffix.lower() not in _IMAGE_EXTENSIONS:
            raise ValueError("上传文件不是支持的图片")
        with self._lock:
            task = self.task(task_id)
            if task.member_id != member_id or task.state not in {"ASSIGNED", "IN_PROGRESS"}:
                raise PermissionError("任务不可上传")
            upload_dir = self.uploads_dir / task.task_id
            stored = upload_dir / f"result{result_image.suffix.lower()}"
            self._copy_file_atomic(result_image, stored)
            updated = replace(task, state="UPLOADED_PENDING_QC")
            self._write_json_atomic(self._task_path(task.task_id), updated.to_dict())
            self._append_audit("UPLOAD", task_id=task.task_id, member_id=member_id, sha256=self._sha256(stored))
            return updated

    def recall(self, task_id: str, actor: str, reason: str) -> Task:
        if not reason.strip():
            raise ValueError("召回必须填写原因")
        with self._lock:
            task = self.task(task_id)
            if task.state not in {"ASSIGNED", "IN_PROGRESS"}:
                raise ValueError("仅未上传任务可以召回")
            updated = replace(task, state="AVAILABLE", member_id=None)
            self._write_json_atomic(self._task_path(task.task_id), updated.to_dict())
            self._append_audit("RECALL", task_id=task.task_id, actor=actor, reason=reason)
            return updated

    def _transition(self, task_id: str, member_id: str, allowed: tuple[str, ...], target: str, action: str) -> Task:
        with self._lock:
            task = self.task(task_id)
            if task.member_id != member_id or task.state not in allowed:
                raise PermissionError("任务状态或归属不匹配")
            updated = replace(task, state=target)
            self._write_json_atomic(self._task_path(task.task_id), updated.to_dict())
            self._append_audit(action, task_id=task.task_id, member_id=member_id)
            return updated

    def task(self, task_id: str) -> Task:
        payload = self._read_json(self._task_path(task_id))
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
                    raise DistributionIntegrityError(f"任务状态文件损坏: {path}")
            else:
                raise DistributionIntegrityError(f"任务状态文件损坏: {path}")
        return tasks

    def _known_hashes(self) -> set[str]:
        hashes = {task.sha256 for task in self._tasks()}
        if not self.successful_images_path.exists():
            return hashes
        for raw_line in self.successful_images_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                raise DistributionIntegrityError("成功使用图片登记册损坏")
            if not isinstance(record, dict) or not record.get("sha256"):
                raise DistributionIntegrityError("成功使用图片登记册缺少 SHA-256")
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
    def _password_hash(password: str, salt: str = "") -> str:
        raw_salt = bytes.fromhex(salt) if salt else b"DataTangDistribution-v1"
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, 310_000).hex()

    @staticmethod
    def _read_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _task_path(self, task_id: str) -> Path:
        if not _TASK_ID_PATTERN.fullmatch(task_id):
            raise KeyError(task_id)
        path = (self.tasks_dir / f"{task_id}.json").resolve()
        if path.parent != self.tasks_dir.resolve():
            raise KeyError(task_id)
        return path

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _copy_file_atomic(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        os.close(descriptor)
        try:
            shutil.copyfile(source, temporary_name)
            os.replace(temporary_name, destination)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    def _append_audit(self, action: str, **details: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": self._now(), "action": action, **details}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _now() -> str:
        return datetime.now(_BUSINESS_TIMEZONE).isoformat()

