from __future__ import annotations

import fnmatch
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


class ModelDownloadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model_id: str
    display_name: str
    allow_patterns: tuple[str, ...] = ("*.json", "onnx/*")
    revision: str | None = None


@dataclass(frozen=True, slots=True)
class ModelDownloadProgress:
    phase: str
    current_file: str
    downloaded_bytes: int
    total_bytes: int
    files_done: int
    files_total: int
    speed_bps: float = 0.0

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, max(0.0, self.downloaded_bytes * 100.0 / self.total_bytes))


@dataclass(frozen=True, slots=True)
class _RemoteFile:
    path: str
    size: int


DEFAULT_MODEL = ModelSpec(
    model_id="onnx-community/dinov2-small",
    display_name="DINOv2 Small ONNX",
    allow_patterns=("*.json", "onnx/*"),
)


class ModelManager:
    def __init__(
        self,
        cache_root: Path | str,
        snapshot_download_fn: Callable[..., str] | None = None,
        repo_tree_fn: Callable[..., Iterable[object]] | None = None,
        file_download_fn: Callable[..., str] | None = None,
    ) -> None:
        self.cache_root = Path(cache_root)
        self.models_root = self.cache_root / "models"
        self.models_root.mkdir(parents=True, exist_ok=True)
        self._snapshot_download_fn = snapshot_download_fn
        self._repo_tree_fn = repo_tree_fn
        self._file_download_fn = file_download_fn

    def model_directory(self, model_id: str) -> Path:
        safe = model_id.replace("/", "--").replace("\\", "--")
        return self.models_root / safe

    def is_installed(self, model_id: str) -> bool:
        model_dir = self.model_directory(model_id)
        marker = model_dir / ".installed.json"
        return marker.is_file() and any(model_dir.rglob("*.onnx"))

    def install(
        self,
        spec: ModelSpec = DEFAULT_MODEL,
        *,
        endpoint: str | None = None,
        progress_callback: Callable[[ModelDownloadProgress], None] | None = None,
    ) -> Path:
        target = self.model_directory(spec.model_id)
        target.mkdir(parents=True, exist_ok=True)

        if progress_callback is None:
            self._install_snapshot(spec, target, endpoint)
        else:
            self._install_with_progress(spec, target, endpoint, progress_callback)

        onnx_files = list(target.rglob("*.onnx"))
        if not onnx_files:
            raise ModelDownloadError("模型下载完成，但未找到 ONNX 模型文件。")

        marker = {
            "schema_version": 1,
            "model_id": spec.model_id,
            "display_name": spec.display_name,
            "revision": spec.revision,
            "installed_at_utc": datetime.now(timezone.utc).isoformat(),
            "onnx_files": [str(path.relative_to(target)).replace("\\", "/") for path in onnx_files],
        }
        self._write_json_atomic(target / ".installed.json", marker)
        return target

    def _install_snapshot(self, spec: ModelSpec, target: Path, endpoint: str | None) -> None:
        download = self._snapshot_download_fn
        if download is None:
            try:
                from huggingface_hub import snapshot_download
            except ImportError as exc:
                raise ModelDownloadError("运行库缺少 huggingface-hub，无法下载模型。") from exc
            download = snapshot_download

        kwargs: dict[str, object] = {
            "repo_id": spec.model_id,
            "local_dir": str(target),
            "allow_patterns": list(spec.allow_patterns),
            "max_workers": 4,
        }
        if spec.revision:
            kwargs["revision"] = spec.revision
        if endpoint:
            kwargs["endpoint"] = endpoint.rstrip("/")

        try:
            download(**kwargs)
        except Exception as exc:
            raise ModelDownloadError(f"Hugging Face 模型下载失败：{exc}") from exc

    def _install_with_progress(
        self,
        spec: ModelSpec,
        target: Path,
        endpoint: str | None,
        callback: Callable[[ModelDownloadProgress], None],
    ) -> None:
        repo_tree = self._repo_tree_fn
        file_download = self._file_download_fn
        if repo_tree is None or file_download is None:
            try:
                from huggingface_hub import HfApi, hf_hub_download
            except ImportError as exc:
                raise ModelDownloadError("运行库缺少 huggingface-hub，无法下载模型。") from exc
            clean_endpoint = endpoint.rstrip("/") if endpoint else None
            api = HfApi(endpoint=clean_endpoint) if clean_endpoint else HfApi()
            repo_tree = api.list_repo_tree
            file_download = hf_hub_download

        callback(ModelDownloadProgress("listing", "", 0, 0, 0, 0, 0.0))
        try:
            entries = repo_tree(
                repo_id=spec.model_id,
                revision=spec.revision,
                repo_type="model",
                recursive=True,
                expand=False,
            )
            files = self._filter_remote_files(entries, spec.allow_patterns)
        except Exception as exc:
            raise ModelDownloadError(f"读取 Hugging Face 模型文件清单失败：{exc}") from exc

        if not files:
            raise ModelDownloadError("模型仓库中没有找到匹配的配置或 ONNX 文件。")

        total_bytes = sum(item.size for item in files)
        files_total = len(files)
        completed_bytes = 0
        files_done = 0
        started_at = time.monotonic()
        callback(
            ModelDownloadProgress(
                "downloading",
                files[0].path,
                0,
                total_bytes,
                0,
                files_total,
                0.0,
            )
        )

        for item in files:
            progress_class = self._make_tqdm_class(
                callback=callback,
                current_file=item.path,
                base_downloaded=completed_bytes,
                file_size=item.size,
                total_bytes=total_bytes,
                files_done=files_done,
                files_total=files_total,
                started_at=started_at,
            )
            kwargs: dict[str, object] = {
                "repo_id": spec.model_id,
                "filename": item.path,
                "repo_type": "model",
                "local_dir": str(target),
                "tqdm_class": progress_class,
            }
            if spec.revision:
                kwargs["revision"] = spec.revision
            if endpoint:
                kwargs["endpoint"] = endpoint.rstrip("/")
            try:
                file_download(**kwargs)
            except Exception as exc:
                raise ModelDownloadError(
                    f"Hugging Face 模型文件下载失败（{item.path}）：{exc}"
                ) from exc

            completed_bytes += item.size
            files_done += 1
            elapsed = max(time.monotonic() - started_at, 0.001)
            callback(
                ModelDownloadProgress(
                    "downloading",
                    item.path,
                    completed_bytes,
                    total_bytes,
                    files_done,
                    files_total,
                    completed_bytes / elapsed,
                )
            )

        elapsed = max(time.monotonic() - started_at, 0.001)
        callback(
            ModelDownloadProgress(
                "complete",
                files[-1].path,
                total_bytes,
                total_bytes,
                files_total,
                files_total,
                total_bytes / elapsed,
            )
        )

    @staticmethod
    def _filter_remote_files(
        entries: Iterable[object],
        allow_patterns: tuple[str, ...],
    ) -> list[_RemoteFile]:
        files: list[_RemoteFile] = []
        for entry in entries:
            path = str(getattr(entry, "path", ""))
            size_value = getattr(entry, "size", None)
            if not path or size_value is None:
                continue
            if not any(fnmatch.fnmatch(path, pattern) for pattern in allow_patterns):
                continue
            try:
                size = max(0, int(size_value))
            except (TypeError, ValueError):
                size = 0
            files.append(_RemoteFile(path=path, size=size))
        return sorted(files, key=lambda item: item.path.casefold())

    @staticmethod
    def _make_tqdm_class(
        *,
        callback: Callable[[ModelDownloadProgress], None],
        current_file: str,
        base_downloaded: int,
        file_size: int,
        total_bytes: int,
        files_done: int,
        files_total: int,
        started_at: float,
    ):
        try:
            from tqdm.auto import tqdm
        except ImportError as exc:
            raise ModelDownloadError("运行库缺少 tqdm，无法显示模型下载进度。") from exc

        class _SilentProgressStream:
            def write(self, value) -> int:  # noqa: ANN001
                return len(str(value))

            def flush(self) -> None:
                return

            def isatty(self) -> bool:
                return False

        class CallbackTqdm(tqdm):
            def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
                if kwargs.get("file") is None:
                    kwargs["file"] = _SilentProgressStream()
                super().__init__(*args, **kwargs)

            def display(self, msg=None, pos=None) -> None:  # noqa: ANN001
                return

            def _emit_progress(self) -> None:
                current = min(file_size, max(0, int(self.n)))
                downloaded = min(total_bytes, base_downloaded + current)
                elapsed = max(time.monotonic() - started_at, 0.001)
                callback(
                    ModelDownloadProgress(
                        "downloading",
                        current_file,
                        downloaded,
                        total_bytes,
                        files_done,
                        files_total,
                        downloaded / elapsed,
                    )
                )

            def update(self, n=1):  # noqa: ANN001
                result = super().update(n)
                self._emit_progress()
                return result

            def close(self) -> None:
                if not self.disable:
                    self._emit_progress()
                super().close()

        return CallbackTqdm

    def delete(self, model_id: str) -> None:
        target = self.model_directory(model_id)
        if target.exists():
            shutil.rmtree(target)

    def find_onnx_model(self, model_id: str) -> Path:
        target = self.model_directory(model_id)
        preferred = target / "onnx" / "model.onnx"
        if preferred.is_file():
            return preferred
        candidates = sorted(
            (path for path in target.rglob("*.onnx") if "quantized" not in path.name.lower()),
            key=lambda path: (len(path.parts), path.name.lower()),
        )
        if not candidates:
            candidates = sorted(target.rglob("*.onnx"))
        if not candidates:
            raise ModelDownloadError("未找到已安装的 ONNX 模型。")
        return candidates[0]

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
            Path(temp_name).replace(path)
        finally:
            Path(temp_name).unlink(missing_ok=True)
