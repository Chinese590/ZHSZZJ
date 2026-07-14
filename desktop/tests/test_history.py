import json
from pathlib import Path

from app.history import load_effective_records


def test_load_effective_records_excludes_undone_and_filters_date(tmp_path: Path):
    log_dir = tmp_path / ".质检工具"
    log_dir.mkdir()
    rows = [
        {
            "operation_id": "a",
            "timestamp": "2026-07-14 09:00:00",
            "action": "不通过",
            "person": "张三",
            "group_name": "000001",
            "source_status": "待质检",
            "source_path": "x",
            "destination_path": "y",
            "issues": ["细节丢失"],
            "remark": "标签缺失",
        },
        {
            "timestamp": "2026-07-14 09:05:00",
            "action": "撤销",
            "undone_operation_id": "a",
        },
        {
            "operation_id": "b",
            "timestamp": "2026-07-14 10:00:00",
            "action": "不通过",
            "person": "李四",
            "group_name": "000002",
            "source_status": "返修提交",
            "source_path": "m",
            "destination_path": "n",
            "issues": ["颜色错误"],
            "remark": "偏色",
        },
        {
            "operation_id": "c",
            "timestamp": "2026-07-13 10:00:00",
            "action": "通过",
            "person": "王五",
            "group_name": "000003",
            "source_status": "待质检",
            "source_path": "p",
            "destination_path": "q",
            "issues": [],
            "remark": "",
        },
    ]
    with (log_dir / "operation_log.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    records = load_effective_records(tmp_path, "2026-07-14")

    assert len(records) == 1
    assert records[0].operation_id == "b"
    assert records[0].person == "李四"
