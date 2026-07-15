from pathlib import Path

from app.scanner import scan_all_counts, scan_queue, scan_status


def make_group(root: Path, status: str, person: str, group: str, complete: bool = True) -> Path:
    folder = root / status / person / group
    folder.mkdir(parents=True)
    (folder / f"{group}.jpg").write_bytes(b"jpg")
    (folder / f"{group}_chn.txt").write_text("中文指令", encoding="utf-8")
    if complete:
        (folder / f"{group}_edit.jpg").write_bytes(b"edit")
        (folder / f"{group}_eng.txt").write_text("English prompt", encoding="utf-8")
    return folder


def test_scan_status_recognizes_files_and_missing_items(tmp_path: Path):
    complete = make_group(tmp_path, "待质检", "张三", "000001", True)
    incomplete = make_group(tmp_path, "待质检", "李四", "000002", False)

    groups = scan_status(tmp_path, "待质检")

    by_name = {group.group_name: group for group in groups}
    assert by_name["000001"].folder == complete
    assert by_name["000001"].is_complete is True
    assert by_name["000001"].chinese_prompt == "中文指令"
    assert by_name["000002"].folder == incomplete
    assert by_name["000002"].is_complete is False
    assert set(by_name["000002"].missing) == {"结果图", "英文指令"}


def test_scan_queue_reads_pending_and_repair_submissions_only(tmp_path: Path):
    for status in ("质检完成", "待返修", "待质检", "返修提交"):
        make_group(tmp_path, status, "王五", status, True)

    groups = scan_queue(tmp_path)

    assert [(g.status, g.group_name) for g in groups] == [
        ("待质检", "待质检"),
        ("返修提交", "返修提交"),
    ]
    assert all(group.status in {"待质检", "返修提交"} for group in groups)


def test_scan_all_counts_counts_groups_per_person_and_status(tmp_path: Path):
    make_group(tmp_path, "待质检", "张三", "000001")
    make_group(tmp_path, "待返修", "张三", "000002")
    make_group(tmp_path, "质检完成", "李四", "000003")

    counts = scan_all_counts(tmp_path)

    assert counts["张三"] == {
        "质检完成": 0,
        "待返修": 1,
        "待质检": 1,
        "返修提交": 0,
    }
    assert counts["李四"]["质检完成"] == 1


def test_scan_recognizes_jfif_original_and_does_not_treat_edit_clean_as_original(tmp_path: Path):
    folder = tmp_path / "待质检" / "周六" / "000010"
    folder.mkdir(parents=True)
    (folder / "000010_F.jfif").write_bytes(b"original")
    (folder / "000010_edit_clean.jpg").write_bytes(b"result")
    (folder / "000010_chn.txt").write_text("中文", encoding="utf-8")
    (folder / "000010_eng.txt").write_text("English", encoding="utf-8")

    group = scan_status(tmp_path, "待质检")[0]

    assert group.original_image.name == "000010_F.jfif"
    assert group.result_image.name == "000010_edit_clean.jpg"
