from pathlib import Path

from app.main import parse_args


def test_main_requires_and_accepts_cache_root(tmp_path: Path):
    args = parse_args(["--cache-root", str(tmp_path / "程序缓存")])
    assert args.cache_root.endswith("程序缓存")
