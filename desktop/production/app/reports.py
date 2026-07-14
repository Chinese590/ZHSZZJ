from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import OperationRecord
from .scanner import STATUS_FOLDERS, scan_all_counts

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SUB_FILL = PatternFill("solid", fgColor="D9EAF7")


def _style_sheet(ws, widths: list[int]) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def export_report(
    root: Path | str,
    output_path: Path | str,
    session_records: list[OperationRecord],
) -> Path:
    root_path = Path(root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    counts = scan_all_counts(root_path)
    failed_records = [record for record in session_records if record.action == "不通过"]
    issues_by_person: dict[str, Counter[str]] = defaultdict(Counter)
    all_issues: Counter[str] = Counter()
    for record in failed_records:
        for issue in record.issues or ["其他问题"]:
            issues_by_person[record.person][issue] += 1
            all_issues[issue] += 1

    wb = Workbook()
    summary = wb.active
    summary.title = "人员汇总"
    summary.append([
        "人员姓名",
        "标注总数量",
        "质检完成数量",
        "待返修数量",
        "待质检数量",
        "返修提交数量",
        "质检不通过的主要问题",
    ])

    all_people = sorted(set(counts) | set(issues_by_person), key=str.lower)
    for person in all_people:
        person_counts = counts.get(person, {status: 0 for status in STATUS_FOLDERS})
        total = sum(person_counts.get(status, 0) for status in STATUS_FOLDERS)
        issue_summary = "；".join(
            f"{name} {number}" for name, number in issues_by_person[person].most_common()
        )
        summary.append([
            person,
            total,
            person_counts.get("质检完成", 0),
            person_counts.get("待返修", 0),
            person_counts.get("待质检", 0),
            person_counts.get("返修提交", 0),
            issue_summary,
        ])
    _style_sheet(summary, [16, 14, 16, 14, 14, 16, 42])

    detail = wb.create_sheet("不通过明细")
    detail.append(["质检时间", "人员姓名", "数据编号", "原始状态", "主要问题", "详细返修备注"])
    for record in failed_records:
        detail.append([
            record.timestamp,
            record.person,
            record.group_name,
            record.source_status,
            "、".join(record.issues) if record.issues else "其他问题",
            record.remark,
        ])
    _style_sheet(detail, [22, 16, 18, 14, 34, 60])

    total_sheet = wb.create_sheet("总体汇总")
    grand = {status: sum(person.get(status, 0) for person in counts.values()) for status in STATUS_FOLDERS}
    total_count = sum(grand.values())
    total_sheet.append(["统计项目", "数量"])
    total_sheet.append(["全部标注数量", total_count])
    for status in STATUS_FOLDERS:
        total_sheet.append([status, grand[status]])
    total_sheet.append(["本次质检不通过操作数", len(failed_records)])
    total_sheet.append([])
    total_sheet.append(["主要问题", "出现次数"])
    for issue, number in all_issues.most_common():
        total_sheet.append([issue, number])
    for cell in total_sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
    if total_sheet.max_row >= 9:
        for cell in total_sheet[9]:
            cell.fill = SUB_FILL
            cell.font = Font(bold=True)
    total_sheet.column_dimensions["A"].width = 30
    total_sheet.column_dimensions["B"].width = 16
    for row in total_sheet.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    wb.save(output)
    return output
