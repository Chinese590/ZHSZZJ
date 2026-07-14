from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


class OptionalAiUnavailable(RuntimeError):
    pass


class DinoOnnxSimilarity:
    """Optional DINOv2 ONNX visual-similarity helper.

    The score is advisory only and is never used for automatic pass/fail.
    """

    def __init__(self, model_path: Path | str | None = None, *, session=None):
        if session is not None:
            self.session = session
            return
        if model_path is None:
            raise OptionalAiUnavailable("未指定 ONNX 模型路径。")
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise OptionalAiUnavailable("运行库缺少 onnxruntime。") from exc
        self.session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )

    @staticmethod
    def _prepare(path: Path | str) -> np.ndarray:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            width, height = image.size
            short = min(width, height)
            scale = 256 / short
            resized = image.resize((round(width * scale), round(height * scale)), Image.Resampling.BICUBIC)
            left = max(0, (resized.width - 224) // 2)
            top = max(0, (resized.height - 224) // 2)
            cropped = resized.crop((left, top, left + 224, top + 224))
            array = np.asarray(cropped, dtype=np.float32) / 255.0
        mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
        array = (array - mean) / std
        return np.transpose(array, (2, 0, 1))

    def compare(self, original: Path | str, result: Path | str) -> float:
        batch = np.stack([self._prepare(original), self._prepare(result)]).astype(np.float32)
        input_name = self.session.get_inputs()[0].name
        output = self.session.run(None, {input_name: batch})[0]
        vectors = output[:, 0, :] if output.ndim == 3 else output
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = vectors / np.clip(norms, 1e-12, None)
        return float(np.dot(vectors[0], vectors[1]))
