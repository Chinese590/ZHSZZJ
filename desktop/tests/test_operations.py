from pathlib import Path

import pytest

from app.operations import DestinationExistsError, QualityOperations
from app.scanner import scan_status


def make_group(root: Path, status: str, person: str, group: str) -> Path:
    folder = root / status / person / group
    folder.mkdir(parents=True)
    (folder / f"{group}.jpg").write_bytes(b"jpg")
    (folder / f"{group}_edit.jpg").write_bytes(b"edit")
    (folder / f"{group}_chn.txt").write_text("中文", encoding="utf-8")
    (folder / f"{group}_eng.txt").write_text("English", encoding="utf-8")
    return folder


def test_pass_group_moves_to_completed_and_undo_restores(tmp_path: Path):
    original = make_group(tmp_path, "待质检", "张三", "000001")
    group = scan_status(tmp_path, "待质检")[0]
    service = QualityOperations(tmp_path)

    record = service.pass_group(group)

    target = tmp_path / "质检完成" / "张三" / "000001"
    assert record.action == "通过"
    assert target.exists()
    assert not original.exists()

    service.undo_last()
    assert original.exists()
    assert not target.exists()


def test_fail_group_writes_note_moves_and_undo_removes_new_note(tmp_path: Path):
    original = make_group(tmp_path, "待质检", "李四", "000002")
    group = scan_status(tmp_path, "待质检")[0]
    service = QualityOperations(tmp_path)

    service.fail_group(group, ["主体不一致", "细节丢失"], "左侧结构变形")

    target = tmp_path / "待返修" / "李四" / "000002"
    note = target / "质检返修备注.txt"
    text = note.read_text(encoding="utf-8")
    assert "主体不一致" in text
    assert "左侧结构变形" in text
    assert target.exists()
    assert not original.exists()

    service.undo_last()
    assert original.exists()
    assert not target.exists()
    assert not (original / "质检返修备注.txt").exists()


def test_fail_group_appends_to_existing_note_and_undo_restores_original(tmp_path: Path):
    original = make_group(tmp_path, "待质检", "王五", "000003")
    note = original / "质检返修备注.txt"
    note.write_text("旧备注\n", encoding="utf-8")
    group = scan_status(tmp_path, "待质检")[0]
    service = QualityOperations(tmp_path)

    service.fail_group(group, ["颜色错误"], "颜色偏差")
    moved_note = tmp_path / "待返修" / "王五" / "000003" / "质检返修备注.txt"
    assert moved_note.read_text(encoding="utf-8").startswith("旧备注")

    service.undo_last()
    assert note.read_text(encoding="utf-8") == "旧备注\n"


def test_move_refuses_to_overwrite_existing_target(tmp_path: Path):
    make_group(tmp_path, "待质检", "赵六", "000004")
    make_group(tmp_path, "质检完成", "赵六", "000004")
    group = scan_status(tmp_path, "待质检")[0]
    service = QualityOperations(tmp_path)

    with pytest.raises(DestinationExistsError):
        service.pass_group(group)


def test_delete_group_sends_folder_to_trash_and_logs(tmp_path: Path, monkeypatch):
    original = make_group(tmp_path, "待质检", "孙七", "000005")
    group = scan_status(tmp_path, "待质检")[0]
    service = QualityOperations(tmp_path)
    trashed: list[str] = []

    def fake_send2trash(path: str) -> None:
        trashed.append(path)
        import shutil
        shutil.rmtree(path)

    monkeypatch.setattr("app.operations.send2trash", fake_send2trash)
    record = service.delete_group(group)

    assert record.action == "删除"
    assert trashed == [str(original)]
    assert not original.exists()
    log_text = service.log_path.read_text(encoding="utf-8")
    assert '"action": "删除"' in log_text
    assert '"group_name": "000005"' in log_text


def test_delete_group_refuses_missing_source(tmp_path: Path):
    original = make_group(tmp_path, "待质检", "孙七", "000006")
    group = scan_status(tmp_path, "待质检")[0]
    import shutil
    shutil.rmtree(original)
    service = QualityOperations(tmp_path)

    with pytest.raises(Exception, match="不存在"):
        service.delete_group(group)


def test_fail_group_already_in_rework_appends_in_place_and_undo_restores(tmp_path: Path):
    folder = make_group(tmp_path, "待返修", "钱八", "000007")
    note = folder / "质检返修备注.txt"
    note.write_text("原返修记录\n", encoding="utf-8")
    group = scan_status(tmp_path, "待返修")[0]
    service = QualityOperations(tmp_path)

    record = service.fail_group(group, ["细节丢失"], "仍缺少标签")

    assert record.source_path == record.destination_path == str(folder)
    assert folder.exists()
    assert "仍缺少标签" in note.read_text(encoding="utf-8")

    service.undo_last()
    assert folder.exists()
    assert note.read_text(encoding="utf-8") == "原返修记录\n"


def test_pass_and_fail_records_capture_advisory_ai_context(tmp_path: Path):
    from app.ai_review_models import AiReviewResult, ReviewFinding

    make_group(tmp_path, "待质检", "AI人员", "000008")
    group = scan_status(tmp_path, "待质检")[0]
    service = QualityOperations(tmp_path)
    ai_review = AiReviewResult(
        stage="online",
        provider="gemini",
        score=44.5,
        risk="high",
        recommendation="repair",
        summary="主体结构异常",
        findings=[ReviewFinding("结构变形", "high", 95, "结构畸形")],
    )

    record = service.pass_group(group, ai_review=ai_review)

    assert record.ai_detected is True
    assert record.ai_score == 44.5
    assert record.ai_provider == "gemini"
    assert record.ai_issues == ["结构变形"]
    assert '"api_key"' not in service.log_path.read_text(encoding="utf-8")
