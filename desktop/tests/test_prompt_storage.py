from pathlib import Path

from app.scanner import read_text_compatible, write_text_compatible


def test_write_text_compatible_preserves_gb18030_file_encoding(tmp_path: Path):
    path = tmp_path / "000001_chn.txt"
    path.write_bytes("原中文指令".encode("gb18030"))

    write_text_compatible(path, "修改后的中文指令")

    assert path.read_bytes().decode("gb18030") == "修改后的中文指令"
    assert read_text_compatible(path) == "修改后的中文指令"


def test_write_text_compatible_preserves_utf8_bom(tmp_path: Path):
    path = tmp_path / "000001_eng.txt"
    path.write_bytes(b"\xef\xbb\xbfOriginal")

    write_text_compatible(path, "Edited")

    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert read_text_compatible(path) == "Edited"
