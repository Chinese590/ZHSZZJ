from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DataGroup:
    status: str
    person: str
    group_name: str
    folder: Path
    original_image: Path | None = None
    result_image: Path | None = None
    chinese_file: Path | None = None
    english_file: Path | None = None
    chinese_prompt: str = ""
    english_prompt: str = ""
    missing: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.missing


@dataclass(slots=True)
class OperationRecord:
    timestamp: str
    action: str
    person: str
    group_name: str
    source_status: str
    source_path: str
    destination_path: str
    operation_id: str = ""
    issues: list[str] = field(default_factory=list)
    remark: str = ""
    ai_detected: bool = False
    ai_stage: str = ""
    ai_provider: str = ""
    ai_score: float | None = None
    ai_risk: str = ""
    ai_recommendation: str = ""
    ai_issues: list[str] = field(default_factory=list)
    ai_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
