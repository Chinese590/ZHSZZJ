from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

CHECK_NAMES = (
    "主体一致性",
    "结构完整性",
    "细节保留",
    "颜色一致性",
    "文字与Logo",
    "背景符合性",
    "画面质量",
    "版面协调性",
)

ISSUE_CATEGORIES = (
    "主体不一致",
    "结构变形",
    "细节丢失",
    "颜色错误",
    "文字或Logo错误",
    "背景不符合要求",
    "画面瑕疵",
    "版面不协调",
    "文件缺失",
    "其他问题",
)

RISK_VALUES = {"low", "medium", "high"}
RECOMMENDATION_VALUES = {"pass", "review", "repair"}
CHECK_STATUS_VALUES = {"pass", "suspect", "fail", "not_checked", "not_applicable"}


@dataclass(slots=True)
class ReviewFinding:
    category: str
    severity: str
    confidence: float
    description: str
    location: str = ""
    repair_instruction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReviewFinding":
        return cls(
            category=str(payload.get("category") or "其他问题"),
            severity=str(payload.get("severity") or "medium"),
            confidence=_clamp_float(payload.get("confidence"), 0.0, 100.0),
            description=str(payload.get("description") or "检测到疑似问题。"),
            location=str(payload.get("location") or ""),
            repair_instruction=str(payload.get("repair_instruction") or ""),
        )


@dataclass(slots=True)
class ReviewCheck:
    name: str
    status: str
    score: float | None
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, name: str, payload: dict[str, Any]) -> "ReviewCheck":
        status = str(payload.get("status") or "not_checked")
        if status not in CHECK_STATUS_VALUES:
            status = "not_checked"
        raw_score = payload.get("score")
        score = None if raw_score is None else _clamp_float(raw_score, 0.0, 100.0)
        return cls(name=name, status=status, score=score, detail=str(payload.get("detail") or ""))


@dataclass(slots=True)
class AiReviewResult:
    stage: str
    provider: str
    score: float
    risk: str
    recommendation: str
    summary: str
    checks: dict[str, ReviewCheck] = field(default_factory=dict)
    findings: list[ReviewFinding] = field(default_factory=list)
    remark: str = ""
    metrics: dict[str, float | int | str | None] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def issue_categories(self) -> list[str]:
        result: list[str] = []
        for finding in self.findings:
            if finding.category not in result:
                result.append(finding.category)
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "provider": self.provider,
            "score": self.score,
            "risk": self.risk,
            "recommendation": self.recommendation,
            "summary": self.summary,
            "checks": {name: check.to_dict() for name, check in self.checks.items()},
            "findings": [item.to_dict() for item in self.findings],
            "remark": self.remark,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AiReviewResult":
        checks_payload = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        checks = {
            name: ReviewCheck.from_dict(name, checks_payload.get(name, {}))
            for name in CHECK_NAMES
        }
        findings_payload = payload.get("findings") if isinstance(payload.get("findings"), list) else []
        risk = str(payload.get("risk") or "medium")
        if risk not in RISK_VALUES:
            risk = "medium"
        recommendation = str(payload.get("recommendation") or "review")
        if recommendation not in RECOMMENDATION_VALUES:
            recommendation = "review"
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        return cls(
            stage=str(payload.get("stage") or "online"),
            provider=str(payload.get("provider") or "unknown"),
            score=_clamp_float(payload.get("score"), 0.0, 100.0),
            risk=risk,
            recommendation=recommendation,
            summary=str(payload.get("summary") or ""),
            checks=checks,
            findings=[ReviewFinding.from_dict(item) for item in findings_payload if isinstance(item, dict)],
            remark=str(payload.get("remark") or ""),
            metrics={str(key): value for key, value in metrics.items()},
            timestamp=str(payload.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )


def build_remark(findings: list[ReviewFinding], summary: str = "") -> str:
    lines: list[str] = []
    if summary.strip():
        lines.append(summary.strip())
    for index, finding in enumerate(findings, start=1):
        location = f"（位置：{finding.location}）" if finding.location else ""
        line = f"{index}. 【{finding.category}】{finding.description.strip()}{location}"
        if finding.repair_instruction.strip():
            line += f"；返修要求：{finding.repair_instruction.strip()}"
        lines.append(line)
    return "\n".join(lines)


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))
