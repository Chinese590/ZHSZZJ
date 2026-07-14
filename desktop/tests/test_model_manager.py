from __future__ import annotations

import json
from pathlib import Path

from app.model_manager import ModelManager, ModelSpec


def test_model_root_uses_user_selected_cache_root(tmp_path: Path):
    manager = ModelManager(tmp_path / "用户指定缓存")
    assert manager.models_root == tmp_path / "用户指定缓存" / "models"


def test_install_uses_local_dir_and_writes_marker(tmp_path: Path):
    calls: list[dict] = []

    def fake_snapshot_download(**kwargs):
        calls.append(kwargs)
        local_dir = Path(kwargs["local_dir"])
        (local_dir / "onnx").mkdir(parents=True, exist_ok=True)
        (local_dir / "onnx" / "model.onnx").write_bytes(b"model")
        (local_dir / "config.json").write_text("{}", encoding="utf-8")
        return str(local_dir)

    spec = ModelSpec(
        model_id="onnx-community/dinov2-small",
        display_name="DINOv2 Small ONNX",
        allow_patterns=("*.json", "onnx/*"),
    )
    manager = ModelManager(tmp_path / "cache", snapshot_download_fn=fake_snapshot_download)

    result = manager.install(spec, endpoint="https://hf-mirror.example")

    assert result == manager.model_directory(spec.model_id)
    assert calls[0]["repo_id"] == spec.model_id
    assert calls[0]["local_dir"] == str(result)
    assert calls[0]["endpoint"] == "https://hf-mirror.example"
    marker = json.loads((result / ".installed.json").read_text(encoding="utf-8"))
    assert marker["model_id"] == spec.model_id
    assert manager.is_installed(spec.model_id)


def test_delete_removes_only_selected_model_directory(tmp_path: Path):
    manager = ModelManager(tmp_path / "cache", snapshot_download_fn=lambda **_: "")
    first = manager.model_directory("org/first")
    second = manager.model_directory("org/second")
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (first / ".installed.json").write_text("{}", encoding="utf-8")
    (second / ".installed.json").write_text("{}", encoding="utf-8")

    manager.delete("org/first")

    assert not first.exists()
    assert second.exists()


def test_progress_tqdm_works_when_pythonw_has_no_stderr(monkeypatch):
    import sys
    import time

    events = []
    monkeypatch.setattr(sys, "stderr", None)
    progress_class = ModelManager._make_tqdm_class(
        callback=events.append,
        current_file="config.json",
        base_downloaded=0,
        file_size=10,
        total_bytes=10,
        files_done=0,
        files_total=1,
        started_at=time.monotonic(),
    )

    with progress_class(total=10) as progress:
        progress.update(5)

    assert events
    assert events[-1].current_file == "config.json"
    assert events[-1].downloaded_bytes == 5
