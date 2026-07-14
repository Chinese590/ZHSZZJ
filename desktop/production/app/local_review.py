from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageOps

from .ai_review_models import AiReviewResult, ReviewCheck, ReviewFinding, build_remark

SemanticCompare = Callable[[Path | str, Path | str], float]


@dataclass(slots=True)
class _Features:
    rgb: np.ndarray
    gray: np.ndarray
    edge: np.ndarray
    mask: np.ndarray
    palette_hist: np.ndarray
    edge_density: float
    sharpness: float
    occupancy: float
    centroid_x: float
    centroid_y: float


class LocalConsistencyReviewer:
    """Fast advisory comparison that works without network access.

    Text/logo correctness and semantic background compliance are deliberately
    marked as not checked locally because pixel heuristics cannot validate them
    reliably. An optional DINO comparator improves subject identity scoring.
    """

    def review(
        self,
        original: Path | str,
        result: Path | str,
        *,
        semantic_compare: SemanticCompare | None = None,
    ) -> AiReviewResult:
        original_path = Path(original)
        result_path = Path(result)
        left = self._features(original_path)
        right = self._features(result_path)

        semantic_similarity: float | None = None
        if semantic_compare is not None:
            semantic_similarity = float(np.clip(semantic_compare(original_path, result_path), -1.0, 1.0))
            semantic_similarity = (semantic_similarity + 1.0) / 2.0 if semantic_similarity < 0 else semantic_similarity
            semantic_similarity = float(np.clip(semantic_similarity, 0.0, 1.0))

        structure_similarity = self._cosine_similarity(left.edge, right.edge)
        palette_similarity = float(np.sum(np.sqrt(left.palette_hist * right.palette_hist)))
        palette_similarity = float(np.clip(palette_similarity, 0.0, 1.0))
        edge_ratio = self._ratio_score(left.edge_density, right.edge_density)
        sharpness_ratio = self._ratio_score(left.sharpness, right.sharpness)
        detail_score = float(np.clip(0.58 * edge_ratio + 0.42 * sharpness_ratio, 0.0, 1.0))
        layout_score = self._layout_score(right)
        artifact_score = float(np.clip(0.65 * sharpness_ratio + 0.35 * edge_ratio, 0.0, 1.0))

        if semantic_similarity is None:
            subject_score = float(np.clip(0.58 * structure_similarity + 0.24 * palette_similarity + 0.18 * layout_score, 0.0, 1.0))
        else:
            subject_score = float(np.clip(0.72 * semantic_similarity + 0.18 * structure_similarity + 0.10 * palette_similarity, 0.0, 1.0))

        score_components = [
            (subject_score, 0.28),
            (structure_similarity, 0.18),
            (detail_score, 0.16),
            (palette_similarity, 0.14),
            (artifact_score, 0.12),
            (layout_score, 0.12),
        ]
        total_score = round(sum(value * weight for value, weight in score_components) * 100, 1)

        findings: list[ReviewFinding] = []
        checks: dict[str, ReviewCheck] = {}
        checks["主体一致性"] = self._check(
            "主体一致性",
            subject_score,
            "主体视觉特征与原图接近。",
            "主体视觉特征与原图存在差异，建议重点核对类别、数量、轮廓和关键部件。",
            "主体不一致",
            findings,
            critical=True,
            confidence_boost=10 if semantic_similarity is not None else -8,
        )
        checks["结构完整性"] = self._check(
            "结构完整性",
            structure_similarity,
            "主要结构和边缘关系接近原图。",
            "局部边缘或结构关系差异较大，疑似存在变形、错位或透视异常。",
            "结构变形",
            findings,
            critical=True,
        )
        checks["细节保留"] = self._check(
            "细节保留",
            detail_score,
            "清晰度与细节密度基本保持。",
            "结果图细节密度或清晰度下降，疑似纹理、配件、边缘细节丢失。",
            "细节丢失",
            findings,
        )
        checks["颜色一致性"] = self._check(
            "颜色一致性",
            palette_similarity,
            "主体主要颜色分布接近原图。",
            "主要颜色分布差异明显，疑似偏色、改色或材质颜色错误。",
            "颜色错误",
            findings,
        )
        checks["文字与Logo"] = ReviewCheck(
            name="文字与Logo",
            status="not_checked",
            score=None,
            detail="本地像素规则不能可靠判断文字拼写与 Logo 内容，需在线深度复核或人工放大检查。",
        )
        checks["背景符合性"] = ReviewCheck(
            name="背景符合性",
            status="not_checked",
            score=None,
            detail="本地规则不理解指令语义，背景是否符合要求需在线深度复核或人工判断。",
        )
        checks["画面质量"] = self._check(
            "画面质量",
            artifact_score,
            "未发现明显模糊或细节质量下降。",
            "结果图清晰度或边缘质量异常，疑似存在模糊、重影、破图或生成瑕疵。",
            "画面瑕疵",
            findings,
        )
        checks["版面协调性"] = self._check(
            "版面协调性",
            layout_score,
            "主体占比和视觉重心处于合理范围。",
            "主体占比过小、过大或明显偏离视觉中心，疑似版面不协调。",
            "版面不协调",
            findings,
        )

        failed_critical = any(
            checks[name].status == "fail" for name in ("主体一致性", "结构完整性")
        )
        fail_count = sum(check.status == "fail" for check in checks.values())
        suspect_count = sum(check.status == "suspect" for check in checks.values())
        if failed_critical or total_score < 55 or fail_count >= 2:
            risk = "high"
            recommendation = "repair"
        elif total_score < 80 or fail_count or suspect_count:
            risk = "medium"
            recommendation = "review"
        else:
            risk = "low"
            recommendation = "pass"

        model_note = "" if semantic_similarity is not None else "；语义模型未安装，主体判断仅使用本地结构与颜色规则"
        summary = f"本地一致性评分 {total_score:.1f} 分，风险等级：{self._risk_text(risk)}{model_note}。"
        remark = build_remark(findings, "AI 本地初筛发现以下疑似问题：") if findings else ""
        return AiReviewResult(
            stage="local",
            provider="local",
            score=total_score,
            risk=risk,
            recommendation=recommendation,
            summary=summary,
            checks=checks,
            findings=findings,
            remark=remark,
            metrics={
                "semantic_similarity": None if semantic_similarity is None else round(semantic_similarity, 4),
                "structure_similarity": round(structure_similarity, 4),
                "palette_similarity": round(palette_similarity, 4),
                "detail_score": round(detail_score, 4),
                "sharpness_ratio": round(sharpness_ratio, 4),
                "layout_score": round(layout_score, 4),
                "result_occupancy": round(right.occupancy, 4),
                "result_centroid_x": round(right.centroid_x, 4),
                "result_centroid_y": round(right.centroid_y, 4),
            },
        )

    def _features(self, path: Path) -> _Features:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            normalized, mask = self._normalize_subject(image)
        rgb = np.asarray(normalized, dtype=np.float32) / 255.0
        gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        gx = np.zeros_like(gray)
        gy = np.zeros_like(gray)
        gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
        gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
        edge = np.sqrt(gx * gx + gy * gy)
        edge = edge / max(float(edge.max()), 1e-6)
        subject_edge = edge[mask] if np.any(mask) else edge.reshape(-1)
        edge_density = float(np.mean(subject_edge))
        lap = np.zeros_like(gray)
        lap[1:-1, 1:-1] = (
            -4 * gray[1:-1, 1:-1]
            + gray[:-2, 1:-1]
            + gray[2:, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
        )
        sharpness = float(np.var(lap[mask] if np.any(mask) else lap))
        pixels = rgb[mask] if np.any(mask) else rgb.reshape(-1, 3)
        bins = np.clip((pixels * 8).astype(np.int16), 0, 7)
        indices = bins[:, 0] * 64 + bins[:, 1] * 8 + bins[:, 2]
        hist = np.bincount(indices, minlength=512).astype(np.float64)
        hist /= max(float(hist.sum()), 1.0)
        ys, xs = np.where(mask)
        if len(xs):
            occupancy = float(mask.mean())
            centroid_x = float(xs.mean() / max(mask.shape[1] - 1, 1))
            centroid_y = float(ys.mean() / max(mask.shape[0] - 1, 1))
        else:
            occupancy, centroid_x, centroid_y = 1.0, 0.5, 0.5
        return _Features(
            rgb=rgb,
            gray=gray,
            edge=edge,
            mask=mask,
            palette_hist=hist,
            edge_density=edge_density,
            sharpness=sharpness,
            occupancy=occupancy,
            centroid_x=centroid_x,
            centroid_y=centroid_y,
        )

    def _normalize_subject(self, image: Image.Image) -> tuple[Image.Image, np.ndarray]:
        preview = image.copy()
        preview.thumbnail((512, 512), Image.Resampling.LANCZOS)
        array = np.asarray(preview, dtype=np.float32)
        border = np.concatenate(
            [array[0], array[-1], array[:, 0], array[:, -1]], axis=0
        )
        background = np.median(border, axis=0)
        distance = np.linalg.norm(array - background, axis=2)
        threshold = max(24.0, float(np.percentile(distance, 62)))
        mask = distance > threshold
        coverage = float(mask.mean())
        if 0.015 <= coverage <= 0.88:
            ys, xs = np.where(mask)
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            pad_x = max(4, int((x1 - x0) * 0.08))
            pad_y = max(4, int((y1 - y0) * 0.08))
            x0, y0 = max(0, x0 - pad_x), max(0, y0 - pad_y)
            x1, y1 = min(preview.width, x1 + pad_x), min(preview.height, y1 + pad_y)
            crop = preview.crop((x0, y0, x1, y1))
            crop_mask = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8), mode="L")
        else:
            crop = preview
            crop_mask = Image.new("L", crop.size, 255)
        canvas = Image.new("RGB", (256, 256), "white")
        mask_canvas = Image.new("L", (256, 256), 0)
        scale = min(236 / max(crop.width, 1), 236 / max(crop.height, 1))
        size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        resized = crop.resize(size, Image.Resampling.LANCZOS)
        resized_mask = crop_mask.resize(size, Image.Resampling.NEAREST)
        offset = ((256 - size[0]) // 2, (256 - size[1]) // 2)
        canvas.paste(resized, offset)
        mask_canvas.paste(resized_mask, offset)
        return canvas, np.asarray(mask_canvas) > 0

    def _check(
        self,
        name: str,
        score: float,
        pass_detail: str,
        issue_detail: str,
        category: str,
        findings: list[ReviewFinding],
        *,
        critical: bool = False,
        confidence_boost: int = 0,
    ) -> ReviewCheck:
        value = float(np.clip(score, 0.0, 1.0))
        if value >= 0.80:
            return ReviewCheck(name=name, status="pass", score=round(value * 100, 1), detail=pass_detail)
        status = "fail" if value < (0.50 if critical else 0.48) else "suspect"
        severity = "high" if status == "fail" else "medium"
        confidence = float(np.clip((1.0 - value) * 100 + 30 + confidence_boost, 35, 98))
        findings.append(
            ReviewFinding(
                category=category,
                severity=severity,
                confidence=round(confidence, 1),
                description=issue_detail,
                repair_instruction="请对照原图放大核对该项，修复后保持主体关键特征与原图一致。",
            )
        )
        return ReviewCheck(name=name, status=status, score=round(value * 100, 1), detail=issue_detail)

    @staticmethod
    def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
        a = left.reshape(-1).astype(np.float64)
        b = right.reshape(-1).astype(np.float64)
        norm = float(np.linalg.norm(a) * np.linalg.norm(b))
        if norm <= 1e-12:
            return 1.0 if np.allclose(a, b) else 0.0
        return float(np.clip(np.dot(a, b) / norm, 0.0, 1.0))

    @staticmethod
    def _ratio_score(left: float, right: float) -> float:
        maximum = max(abs(left), abs(right), 1e-8)
        return float(np.clip(min(abs(left), abs(right)) / maximum, 0.0, 1.0))

    @staticmethod
    def _layout_score(features: _Features) -> float:
        occupancy = features.occupancy
        if occupancy < 0.12:
            occupancy_score = max(0.0, occupancy / 0.12)
        elif occupancy > 0.92:
            occupancy_score = max(0.0, (1.0 - occupancy) / 0.08)
        elif 0.22 <= occupancy <= 0.82:
            occupancy_score = 1.0
        else:
            occupancy_score = 0.78
        distance = float(np.hypot(features.centroid_x - 0.5, features.centroid_y - 0.5))
        center_score = float(np.clip(1.0 - distance / 0.55, 0.0, 1.0))
        return float(np.clip(0.58 * occupancy_score + 0.42 * center_score, 0.0, 1.0))

    @staticmethod
    def _risk_text(risk: str) -> str:
        return {"low": "低", "medium": "中", "high": "高"}.get(risk, risk)
