from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .ai_review_models import AiReviewResult


@dataclass(slots=True)
class AiReviewAuditRecord:
    timestamp: str
    status: str
    person: str
    group_name: str
    folder: str
    signature: str
    result: AiReviewResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "status": self.status,
            "person": self.person,
            "group_name": self.group_name,
            "folder": self.folder,
            "signature": self.signature,
            "result": _sanitize_result_dict(self.result.to_dict()),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AiReviewAuditRecord":
        return cls(
            timestamp=str(payload.get("timestamp") or ""),
            status=str(payload.get("status") or ""),
            person=str(payload.get("person") or ""),
            group_name=str(payload.get("group_name") or ""),
            folder=str(payload.get("folder") or ""),
            signature=str(payload.get("signature") or ""),
            result=AiReviewResult.from_dict(payload.get("result") if isinstance(payload.get("result"), dict) else {}),
        )


class AiReviewStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.log_dir = self.root / ".质检工具"
        self.log_path = self.log_dir / "ai_review_log.jsonl"

    def append(
        self,
        status: str,
        person: str,
        group_name: str,
        folder: Path | str,
        signature: str,
        result: AiReviewResult,
        *,
        timestamp: str | None = None,
    ) -> AiReviewAuditRecord:
        record = AiReviewAuditRecord(
            timestamp=timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status=status,
            person=person,
            group_name=group_name,
            folder=str(folder),
            signature=signature,
            result=result,
        )
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        return record

    def iter_records(self) -> list[AiReviewAuditRecord]:
        if not self.log_path.is_file():
            return []
        records: list[AiReviewAuditRecord] = []
        with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                try:
                    records.append(AiReviewAuditRecord.from_dict(payload))
                except (TypeError, ValueError):
                    continue
        return records

    def latest_for_group(self, person: str, group_name: str, signature: str) -> AiReviewResult | None:
        matches = [
            item
            for item in self.iter_records()
            if item.person == person and item.group_name == group_name and item.signature == signature
        ]
        if not matches:
            return None
        online = [item for item in matches if item.result.stage == "online"]
        selected = (online or matches)[-1]
        return selected.result

    def latest_reviews(self, date_prefix: str | None = None) -> list[AiReviewAuditRecord]:
        selected: dict[tuple[str, str, str], AiReviewAuditRecord] = {}
        for record in self.iter_records():
            if date_prefix and not record.timestamp.startswith(date_prefix):
                continue
            key = (record.person, record.group_name, record.signature)
            previous = selected.get(key)
            if previous is None:
                selected[key] = record
                continue
            if record.result.stage == "online" or previous.result.stage != "online":
                selected[key] = record
        return list(selected.values())


def image_pair_signature(original: Path | str, result: Path | str) -> str:
    digest = hashlib.sha256()
    for path in (Path(original), Path(result)):
        stat = path.stat()
        digest.update(str(path.name).encode("utf-8", errors="replace"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        with path.open("rb") as handle:
            first = handle.read(65536)
            digest.update(first)
            if stat.st_size > 65536:
                handle.seek(max(0, stat.st_size - 65536))
                digest.update(handle.read(65536))
    return digest.hexdigest()


def _sanitize_result_dict(payload: dict[str, Any]) -> dict[str, Any]:
    clean = dict(payload)
    metrics = clean.get("metrics")
    if isinstance(metrics, dict):
        clean["metrics"] = {
            str(key): value
            for key, value in metrics.items()
            if "key" not in str(key).lower() and "token" not in str(key).lower() and "secret" not in str(key).lower()
        }
    return clean
