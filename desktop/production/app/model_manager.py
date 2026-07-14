from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class ModelDownloadError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model_id: str
    display_name: str
    allow_patterns: tuple[str, ...] = ("*.json", "onnx/*")
    revision: str | None = None


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
    ) -> None:
        self.cache_root = Path(cache_root)
        self.models_root = self.cache_root / "models"
        self.models_root.mkdir(parents=True, exist_ok=True)
        self._snapshot_download_fn = snapshot_download_fn

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
    ) -> Path:
        target = self.model_directory(spec.model_id)
        target.mkdir(parents=True, exist_ok=True)
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
