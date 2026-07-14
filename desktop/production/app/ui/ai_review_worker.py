from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from ..ai_assist import DinoOnnxSimilarity, OptionalAiUnavailable
from ..ai_review_models import AiReviewResult
from ..local_review import LocalConsistencyReviewer
from ..model_manager import DEFAULT_MODEL, ModelDownloadError, ModelManager
from ..online_review import OnlineReviewClient, OnlineReviewSettings


class AiReviewWorker(QtCore.QObject):
    finished = QtCore.Signal(object, str)
    failed = QtCore.Signal(str, str)

    def __init__(
        self,
        *,
        mode: str,
        signature: str,
        original: Path,
        result: Path,
        model_manager: ModelManager | None = None,
        online_settings: OnlineReviewSettings | None = None,
        chinese_prompt: str = "",
        english_prompt: str = "",
        local_result: AiReviewResult | None = None,
    ) -> None:
        super().__init__()
        self.mode = mode
        self.signature = signature
        self.original = original
        self.result = result
        self.model_manager = model_manager
        self.online_settings = online_settings
        self.chinese_prompt = chinese_prompt
        self.english_prompt = english_prompt
        self.local_result = local_result

    @QtCore.Slot()
    def run(self) -> None:
        try:
            if self.mode == "local":
                semantic_compare = self._semantic_compare()
                result = LocalConsistencyReviewer().review(
                    self.original,
                    self.result,
                    semantic_compare=semantic_compare,
                )
            elif self.mode == "online":
                if self.online_settings is None:
                    raise ValueError("在线复核设置不存在。")
                result = OnlineReviewClient(self.online_settings).review(
                    self.original,
                    self.result,
                    self.chinese_prompt,
                    self.english_prompt,
                    self.local_result,
                )
            else:
                raise ValueError(f"未知 AI 检测模式：{self.mode}")
        except Exception as exc:
            self.failed.emit(f"AI一致性质检失败：{exc}", self.signature)
            return
        self.finished.emit(result, self.signature)

    def _semantic_compare(self):
        if self.model_manager is None:
            return None
        if not self.model_manager.is_installed(DEFAULT_MODEL.model_id):
            return None
        try:
            model_path = self.model_manager.find_onnx_model(DEFAULT_MODEL.model_id)
            helper = DinoOnnxSimilarity(model_path)
        except (ModelDownloadError, OptionalAiUnavailable, OSError, ValueError):
            return None
        return helper.compare
