from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from send2trash import send2trash

from .ai_review_models import AiReviewResult
from .models import DataGroup, OperationRecord


class QualityOperationError(RuntimeError):
    pass


class DestinationExistsError(QualityOperationError):
    pass


@dataclass(slots=True)
class _UndoEntry:
    record: OperationRecord
    note_existed: bool = False
    previous_note_content: str = ""
    moved: bool = True


class QualityOperations:
    NOTE_NAME = "质检返修备注.txt"

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self._undo_stack: list[_UndoEntry] = []
        self._records: list[OperationRecord] = []
        self.log_dir = self.root / ".质检工具"
        self.log_path = self.log_dir / "operation_log.jsonl"

    @property
    def session_records(self) -> list[OperationRecord]:
        return list(self._records)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def _timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _target(self, group: DataGroup, status: str) -> Path:
        return self.root / status / group.person / group.group_name

    def _check_move(self, source: Path, target: Path) -> None:
        if not source.is_dir():
            raise QualityOperationError(f"源数据文件夹不存在：{source}")
        if target.exists():
            raise DestinationExistsError(f"目标文件夹已存在，为防止覆盖已停止操作：{target}")

    def _append_log(self, payload: dict) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _move(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))

    def pass_group(self, group: DataGroup, ai_review: AiReviewResult | None = None) -> OperationRecord:
        source = group.folder
        target = self._target(group, "质检完成")
        self._check_move(source, target)
        self._move(source, target)
        record = OperationRecord(
            timestamp=self._timestamp(),
            action="通过",
            person=group.person,
            group_name=group.group_name,
            source_status=group.status,
            source_path=str(source),
            destination_path=str(target),
            operation_id=uuid.uuid4().hex,
            **self._ai_record_fields(ai_review),
        )
        self._records.append(record)
        self._undo_stack.append(_UndoEntry(record=record))
        self._append_log(record.to_dict())
        return record

    def fail_group(
        self,
        group: DataGroup,
        issues: list[str],
        remark: str,
        ai_review: AiReviewResult | None = None,
    ) -> OperationRecord:
        clean_issues = [item.strip() for item in issues if item.strip()]
        clean_remark = remark.strip()
        if not clean_issues and not clean_remark:
            raise QualityOperationError("请至少选择一个主要问题，或填写详细返修备注。")

        source = group.folder
        if not source.is_dir():
            raise QualityOperationError(f"源数据文件夹不存在：{source}")

        # Items already in 待返修 stay in place. A second rejection appends a new
        # audit block instead of trying to move the directory onto itself.
        moved = group.status != "待返修"
        target = self._target(group, "待返修") if moved else source
        if moved:
            self._check_move(source, target)

        note_path = source / self.NOTE_NAME
        note_existed = note_path.exists()
        previous_content = note_path.read_text(encoding="utf-8") if note_existed else ""
        timestamp = self._timestamp()
        issue_text = "、".join(clean_issues) if clean_issues else "其他问题"
        block = (
            f"===== 质检返修记录 {timestamp} =====\n"
            f"人员姓名：{group.person}\n"
            f"数据编号：{group.group_name}\n"
            f"原始状态：{group.status}\n"
            f"主要问题：{issue_text}\n"
            f"详细返修备注：{clean_remark or '无'}\n"
            "========================================\n"
        )
        separator = "" if not previous_content or previous_content.endswith("\n") else "\n"
        note_path.write_text(previous_content + separator + block, encoding="utf-8")

        if moved:
            try:
                self._move(source, target)
            except Exception:
                if note_existed:
                    note_path.write_text(previous_content, encoding="utf-8")
                elif note_path.exists():
                    note_path.unlink()
                raise

        record = OperationRecord(
            timestamp=timestamp,
            action="不通过",
            person=group.person,
            group_name=group.group_name,
            source_status=group.status,
            source_path=str(source),
            destination_path=str(target),
            operation_id=uuid.uuid4().hex,
            issues=clean_issues,
            remark=clean_remark,
            **self._ai_record_fields(ai_review),
        )
        self._records.append(record)
        self._undo_stack.append(
            _UndoEntry(
                record=record,
                note_existed=note_existed,
                previous_note_content=previous_content,
                moved=moved,
            )
        )
        self._append_log(record.to_dict())
        return record



    @staticmethod
    def _ai_record_fields(ai_review: AiReviewResult | None) -> dict[str, object]:
        if ai_review is None:
            return {}
        return {
            "ai_detected": True,
            "ai_stage": ai_review.stage,
            "ai_provider": ai_review.provider,
            "ai_score": ai_review.score,
            "ai_risk": ai_review.risk,
            "ai_recommendation": ai_review.recommendation,
            "ai_issues": ai_review.issue_categories,
            "ai_summary": ai_review.summary,
        }

    def delete_group(self, group: DataGroup) -> OperationRecord:
        """Move one complete data-group folder to the operating system recycle bin.

        Deletion is intentionally not added to the undo stack because recovery is
        handled by the system recycle bin. Every deletion is still written to the
        operation log for auditability.
        """
        source = group.folder
        if not source.is_dir():
            raise QualityOperationError(f"数据组文件夹不存在：{source}")

        try:
            resolved_source = source.resolve(strict=True)
            resolved_root = self.root.resolve(strict=True)
            resolved_source.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise QualityOperationError(f"拒绝删除项目目录之外的路径：{source}") from exc

        if resolved_source == resolved_root:
            raise QualityOperationError("拒绝删除项目总目录。")

        timestamp = self._timestamp()
        try:
            send2trash(str(source))
        except OSError as exc:
            raise QualityOperationError(f"移动到系统回收站失败：{source}") from exc

        record = OperationRecord(
            timestamp=timestamp,
            action="删除",
            person=group.person,
            group_name=group.group_name,
            source_status=group.status,
            source_path=str(source),
            destination_path="系统回收站",
            operation_id=uuid.uuid4().hex,
        )
        self._append_log(record.to_dict())
        return record

    def undo_last(self) -> OperationRecord:
        if not self._undo_stack:
            raise QualityOperationError("当前会话没有可撤销的质检操作。")

        entry = self._undo_stack[-1]
        record = entry.record
        source = Path(record.destination_path)
        target = Path(record.source_path)
        if entry.moved:
            self._check_move(source, target)
            self._move(source, target)
        elif not target.is_dir():
            raise QualityOperationError(f"数据组文件夹不存在：{target}")

        if record.action == "不通过":
            note_path = target / self.NOTE_NAME
            if entry.note_existed:
                note_path.write_text(entry.previous_note_content, encoding="utf-8")
            elif note_path.exists():
                note_path.unlink()

        self._undo_stack.pop()
        if self._records and self._records[-1] is record:
            self._records.pop()
        else:
            self._records = [item for item in self._records if item is not record]
        self._append_log(
            {
                "timestamp": self._timestamp(),
                "action": "撤销",
                "person": record.person,
                "group_name": record.group_name,
                "source_action": record.action,
                "undone_operation_id": record.operation_id,
                "restored_path": str(target),
            }
        )
        return record
