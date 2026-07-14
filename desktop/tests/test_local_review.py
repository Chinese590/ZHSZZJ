from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.local_review import LocalConsistencyReviewer


def make_subject(path: Path, *, color=(220, 30, 30), box=(60, 45, 196, 210), blur=False):
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=18, fill=color, outline="black", width=5)
    draw.line((75, 80, 180, 175), fill="white", width=8)
    draw.ellipse((105, 105, 145, 145), fill="black")
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(5))
    image.save(path)


def check(result, name):
    return result.checks[name]


def test_identical_images_are_low_risk_and_high_score(tmp_path: Path):
    original = tmp_path / "original.png"
    result_path = tmp_path / "result.png"
    make_subject(original)
    make_subject(result_path)

    result = LocalConsistencyReviewer().review(
        original,
        result_path,
        semantic_compare=lambda _a, _b: 0.99,
    )

    assert result.stage == "local"
    assert result.score >= 90
    assert result.risk == "low"
    assert result.recommendation == "pass"
    assert check(result, "主体一致性").status == "pass"
    assert not result.issue_categories


def test_color_shift_is_reported_as_color_error(tmp_path: Path):
    original = tmp_path / "original.png"
    result_path = tmp_path / "result.png"
    make_subject(original, color=(220, 30, 30))
    make_subject(result_path, color=(25, 60, 225))

    result = LocalConsistencyReviewer().review(
        original,
        result_path,
        semantic_compare=lambda _a, _b: 0.96,
    )

    assert check(result, "颜色一致性").status in {"suspect", "fail"}
    assert "颜色错误" in result.issue_categories
    assert result.risk in {"medium", "high"}


def test_blurred_result_is_reported_as_detail_or_artifact_problem(tmp_path: Path):
    original = tmp_path / "original.png"
    result_path = tmp_path / "result.png"
    make_subject(original)
    make_subject(result_path, blur=True)

    result = LocalConsistencyReviewer().review(
        original,
        result_path,
        semantic_compare=lambda _a, _b: 0.93,
    )

    assert {"细节丢失", "画面瑕疵"} & set(result.issue_categories)
    assert check(result, "细节保留").score < 80


def test_off_center_small_subject_is_layout_risk(tmp_path: Path):
    original = tmp_path / "original.png"
    result_path = tmp_path / "result.png"
    make_subject(original)
    make_subject(result_path, box=(8, 8, 70, 82))

    result = LocalConsistencyReviewer().review(
        original,
        result_path,
        semantic_compare=lambda _a, _b: 0.90,
    )

    assert "版面不协调" in result.issue_categories
    assert check(result, "版面协调性").status in {"suspect", "fail"}


def test_missing_semantic_model_degrades_without_claiming_subject_pass(tmp_path: Path):
    original = tmp_path / "original.png"
    result_path = tmp_path / "result.png"
    make_subject(original)
    make_subject(result_path)

    result = LocalConsistencyReviewer().review(original, result_path)

    assert result.metrics["semantic_similarity"] is None
    assert "语义模型未安装" in result.summary
    assert check(result, "文字与Logo").status == "not_checked"
    assert check(result, "背景符合性").status == "not_checked"
