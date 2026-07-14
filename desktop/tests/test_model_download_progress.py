from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.model_manager import ModelDownloadProgress, ModelManager, ModelSpec


@dataclass
class _RemoteFile:
    path: str
    size: int


def test_install_reports_real_byte_progress(tmp_path: Path):
    remote_files = [
        _RemoteFile("config.json", 100),
        _RemoteFile("onnx/model.onnx", 900),
    ]
    progress: list[ModelDownloadProgress] = []

    def fake_list_repo_tree(**kwargs):
        assert kwargs["repo_id"] == "org/model"
        assert kwargs["recursive"] is True
        return remote_files

    def fake_hf_hub_download(**kwargs):
        filename = kwargs["filename"]
        remote = next(item for item in remote_files if item.path == filename)
        tqdm_class = kwargs["tqdm_class"]
        with tqdm_class(total=remote.size, initial=0, unit="B", desc=filename) as bar:
            first = remote.size // 2
            bar.update(first)
            bar.update(remote.size - first)
        destination = Path(kwargs["local_dir"]) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"x" * remote.size)
        return str(destination)

    manager = ModelManager(
        tmp_path / "cache",
        repo_tree_fn=fake_list_repo_tree,
        file_download_fn=fake_hf_hub_download,
    )
    spec = ModelSpec("org/model", "Demo", ("*.json", "onnx/*"))

    result = manager.install(spec, progress_callback=progress.append)

    assert result == manager.model_directory("org/model")
    assert progress
    assert progress[-1].phase == "complete"
    assert progress[-1].downloaded_bytes == 1000
    assert progress[-1].total_bytes == 1000
    assert progress[-1].files_done == 2
    assert progress[-1].files_total == 2
    assert progress[-1].percent == 100.0
    assert any(0 < item.percent < 100 for item in progress)
    assert any(item.current_file == "onnx/model.onnx" for item in progress)


def test_install_filters_remote_tree_using_allow_patterns(tmp_path: Path):
    requested: list[str] = []

    def fake_list_repo_tree(**_kwargs):
        return [
            _RemoteFile("README.md", 10),
            _RemoteFile("config.json", 20),
            _RemoteFile("onnx/model.onnx", 30),
        ]

    def fake_hf_hub_download(**kwargs):
        requested.append(kwargs["filename"])
        destination = Path(kwargs["local_dir"]) / kwargs["filename"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"x" * (30 if destination.suffix == ".onnx" else 20))
        return str(destination)

    manager = ModelManager(
        tmp_path / "cache",
        repo_tree_fn=fake_list_repo_tree,
        file_download_fn=fake_hf_hub_download,
    )

    manager.install(
        ModelSpec("org/model", "Demo", ("*.json", "onnx/*")),
        progress_callback=lambda _item: None,
    )

    assert requested == ["config.json", "onnx/model.onnx"]
