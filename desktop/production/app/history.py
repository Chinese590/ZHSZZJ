from __future__ import annotations

import json
from pathlib import Path

from .models import OperationRecord


def load_effective_records(root: Path | str, date_prefix: str | None = None) -> list[OperationRecord]:
    """Load non-undone pass/fail records from the JSONL operation log.

    Undo events remove the referenced operation ID. Invalid or partial lines are
    skipped so a truncated final write does not make report export fail.
    """

    log_path = Path(root) / ".质检工具" / "operation_log.jsonl"
    if not log_path.is_file():
        return []

    active: dict[str, OperationRecord] = {}
    order: list[str] = []

    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            action = payload.get("action")
            if action in {"通过", "不通过"}:
                operation_id = str(payload.get("operation_id") or "")
                if not operation_id:
                    # Backward compatibility for logs produced before IDs existed.
                    operation_id = "|".join(
                        str(payload.get(key, ""))
                        for key in ("timestamp", "action", "person", "group_name")
                    )
                try:
                    record = OperationRecord(
                        timestamp=str(payload.get("timestamp", "")),
                        action=str(action),
                        person=str(payload.get("person", "")),
                        group_name=str(payload.get("group_name", "")),
                        source_status=str(payload.get("source_status", "")),
                        source_path=str(payload.get("source_path", "")),
                        destination_path=str(payload.get("destination_path", "")),
                        operation_id=operation_id,
                        issues=[str(item) for item in payload.get("issues", [])],
                        remark=str(payload.get("remark", "")),
                        ai_detected=bool(payload.get("ai_detected", False)),
                        ai_stage=str(payload.get("ai_stage", "")),
                        ai_provider=str(payload.get("ai_provider", "")),
                        ai_score=(
                            None
                            if payload.get("ai_score") is None
                            else float(payload.get("ai_score"))
                        ),
                        ai_risk=str(payload.get("ai_risk", "")),
                        ai_recommendation=str(payload.get("ai_recommendation", "")),
                        ai_issues=[str(item) for item in payload.get("ai_issues", [])],
                        ai_summary=str(payload.get("ai_summary", "")),
                    )
                except (TypeError, ValueError):
                    continue
                active[operation_id] = record
                if operation_id not in order:
                    order.append(operation_id)
            elif action == "撤销":
                undone_id = str(payload.get("undone_operation_id") or "")
                if undone_id:
                    active.pop(undone_id, None)

    records = [active[operation_id] for operation_id in order if operation_id in active]
    if date_prefix:
        records = [record for record in records if record.timestamp.startswith(date_prefix)]
    return records
