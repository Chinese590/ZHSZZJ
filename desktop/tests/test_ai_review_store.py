from pathlib import Path

from PIL import Image

from app.ai_review_models import AiReviewResult, ReviewFinding
from app.ai_review_store import AiReviewStore, image_pair_signature


def make_image(path: Path, color: str):
    Image.new("RGB", (32, 32), color).save(path)


def result(stage: str, provider: str, score: float):
    return AiReviewResult(
        stage=stage,
        provider=provider,
        score=score,
        risk="medium",
        recommendation="review",
        summary=f"{stage} result",
        findings=[ReviewFinding("颜色错误", "medium", 80, "偏色")],
    )


def test_signature_changes_when_image_content_changes(tmp_path: Path):
    original = tmp_path / "o.png"
    output = tmp_path / "r.png"
    make_image(original, "red")
    make_image(output, "blue")
    first = image_pair_signature(original, output)

    make_image(output, "green")
    second = image_pair_signature(original, output)

    assert first != second


def test_store_loads_latest_online_result_for_same_group_and_signature(tmp_path: Path):
    original = tmp_path / "o.png"
    output = tmp_path / "r.png"
    make_image(original, "red")
    make_image(output, "blue")
    signature = image_pair_signature(original, output)
    store = AiReviewStore(tmp_path)

    store.append("待质检", "张三", "000001", tmp_path / "待质检/张三/000001", signature, result("local", "local", 70))
    store.append("待质检", "张三", "000001", tmp_path / "待质检/张三/000001", signature, result("online", "openai", 55))

    loaded = store.latest_for_group("张三", "000001", signature)

    assert loaded is not None
    assert loaded.stage == "online"
    assert loaded.provider == "openai"
    assert loaded.score == 55


def test_latest_reviews_deduplicates_repeated_runs_and_filters_date(tmp_path: Path):
    store = AiReviewStore(tmp_path)
    signature = "abc"
    store.append("待质检", "李四", "000002", tmp_path, signature, result("local", "local", 80), timestamp="2026-07-15 08:00:00")
    store.append("待质检", "李四", "000002", tmp_path, signature, result("local", "local", 75), timestamp="2026-07-15 09:00:00")
    store.append("待质检", "王五", "000003", tmp_path, "def", result("online", "gemini", 45), timestamp="2026-07-14 09:00:00")

    records = store.latest_reviews("2026-07-15")

    assert len(records) == 1
    assert records[0].person == "李四"
    assert records[0].result.score == 75


def test_store_log_never_contains_api_key_field(tmp_path: Path):
    store = AiReviewStore(tmp_path)
    review = result("online", "custom", 60)
    review.metrics["api_key"] = "SHOULD-NOT-BE-WRITTEN"

    store.append("待质检", "赵六", "000004", tmp_path, "sig", review)

    text = store.log_path.read_text(encoding="utf-8")
    assert "SHOULD-NOT-BE-WRITTEN" not in text
    assert '"api_key"' not in text
