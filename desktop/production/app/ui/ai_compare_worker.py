from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from ..ai_assist import DinoOnnxSimilarity, OptionalAiUnavailable
from ..model_manager import DEFAULT_MODEL, ModelDownloadError, ModelManager


class AiCompareWorker(QtCore.QObject):
    finished = QtCore.Signal(float)
    failed = QtCore.Signal(str)

    def __init__(self, manager: ModelManager, original: Path, result: Path):
        super().__init__()
        self.manager = manager
        self.original = original
        self.result = result

    @QtCore.Slot()
    def run(self) -> None:
        try:
            model_path = self.manager.find_onnx_model(DEFAULT_MODEL.model_id)
            helper = DinoOnnxSimilarity(model_path)
            score = helper.compare(self.original, self.result)
        except (ModelDownloadError, OptionalAiUnavailable, OSError, ValueError) as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:
            self.failed.emit(f"AI辅助比较失败：{exc}")
            return
        self.finished.emit(score)
