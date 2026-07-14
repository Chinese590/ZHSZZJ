from pathlib import Path

from app.startup import write_startup_error


def test_write_startup_error_creates_readable_log(tmp_path: Path):
    try:
        raise RuntimeError("启动测试异常")
    except RuntimeError as exc:
        path = write_startup_error(exc, root=tmp_path)

    text = path.read_text(encoding="utf-8")
    assert path.name == "startup_error.log"
    assert "RuntimeError" in text
    assert "启动测试异常" in text
