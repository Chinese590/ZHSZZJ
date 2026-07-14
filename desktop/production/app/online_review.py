from __future__ import annotations

import base64
import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageOps

from .ai_review_models import (
    AiReviewResult,
    CHECK_NAMES,
    ISSUE_CATEGORIES,
    ReviewCheck,
    ReviewFinding,
    build_remark,
)

JsonTransport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class OnlineReviewError(RuntimeError):
    pass


@dataclass(slots=True)
class OnlineReviewSettings:
    provider: str = "openai"
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    timeout_seconds: int = 90
    max_image_edge: int = 1600
    auto_local: bool = True
    smart_trigger: bool = True

    @property
    def is_configured(self) -> bool:
        if not self.api_key.strip() or not self.model.strip():
            return False
        if self.provider == "custom" and not self.base_url.strip():
            return False
        return self.provider in {"openai", "gemini", "custom"}

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "max_image_edge": self.max_image_edge,
            "auto_local": self.auto_local,
            "smart_trigger": self.smart_trigger,
            "api_key": "***" if self.api_key else "",
        }


class OnlineReviewClient:
    def __init__(self, settings: OnlineReviewSettings, *, transport: JsonTransport | None = None):
        self.settings = settings
        self.transport = transport or _post_json

    def review(
        self,
        original: Path | str,
        result: Path | str,
        chinese_prompt: str,
        english_prompt: str,
        local_result: AiReviewResult | None,
    ) -> AiReviewResult:
        if not self.settings.is_configured:
            raise OnlineReviewError("在线复核配置不完整，请先填写提供商、模型和 API Key。")

        original_data = _encode_image(Path(original), self.settings.max_image_edge)
        result_data = _encode_image(Path(result), self.settings.max_image_edge)
        prompt = _build_prompt(chinese_prompt, english_prompt, local_result)

        provider = self.settings.provider
        if provider == "openai":
            url = (self.settings.base_url.strip() or "https://api.openai.com/v1").rstrip("/") + "/responses"
            headers = {
                "Authorization": f"Bearer {self.settings.api_key.strip()}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.settings.model.strip(),
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt + "\n\n图片1：原图"},
                            {"type": "input_image", "image_url": original_data},
                            {"type": "input_text", "text": "图片2：结果图"},
                            {"type": "input_image", "image_url": result_data},
                        ],
                    }
                ],
            }
            raw = self.transport(url, headers, payload, float(self.settings.timeout_seconds))
            text = _extract_openai_responses_text(raw)
        elif provider == "gemini":
            base = (self.settings.base_url.strip() or "https://generativelanguage.googleapis.com").rstrip("/")
            url = f"{base}/v1beta/models/{self.settings.model.strip()}:generateContent"
            headers = {
                "x-goog-api-key": self.settings.api_key.strip(),
                "Content-Type": "application/json",
            }
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt + "\n\n图片1：原图"},
                            _gemini_inline_part(original_data),
                            {"text": "图片2：结果图"},
                            _gemini_inline_part(result_data),
                        ]
                    }
                ],
                "generationConfig": {"response_mime_type": "application/json"},
            }
            raw = self.transport(url, headers, payload, float(self.settings.timeout_seconds))
            text = _extract_gemini_text(raw)
        else:
            base = self.settings.base_url.strip().rstrip("/")
            url = base if base.endswith("/chat/completions") else base + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.settings.api_key.strip()}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.settings.model.strip(),
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt + "\n\n图片1：原图"},
                            {"type": "image_url", "image_url": {"url": original_data}},
                            {"type": "text", "text": "图片2：结果图"},
                            {"type": "image_url", "image_url": {"url": result_data}},
                        ],
                    }
                ],
            }
            raw = self.transport(url, headers, payload, float(self.settings.timeout_seconds))
            text = _extract_chat_text(raw)

        parsed = parse_review_response(text, provider)
        parsed.metrics["online_model"] = self.settings.model.strip()
        return parsed


def parse_review_response(text: str, provider: str) -> AiReviewResult:
    payload = _extract_json_object(text)
    checks_payload = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    checks: dict[str, ReviewCheck] = {}
    for name in CHECK_NAMES:
        raw = checks_payload.get(name)
        checks[name] = ReviewCheck.from_dict(name, raw if isinstance(raw, dict) else {})

    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    findings: list[ReviewFinding] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized["category"] = _normalize_category(str(item.get("category") or "其他问题"))
        findings.append(ReviewFinding.from_dict(normalized))

    risk = str(payload.get("risk") or "medium").lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    recommendation = str(payload.get("recommendation") or "review").lower()
    recommendation_aliases = {
        "通过": "pass",
        "建议通过": "pass",
        "复核": "review",
        "建议复核": "review",
        "返修": "repair",
        "建议返修": "repair",
    }
    recommendation = recommendation_aliases.get(recommendation, recommendation)
    if recommendation not in {"pass", "review", "repair"}:
        recommendation = "review"
    summary = str(payload.get("summary") or "在线深度复核已完成。")
    remark = str(payload.get("remark") or "").strip() or build_remark(findings, summary)
    try:
        score = float(payload.get("score", 0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))
    return AiReviewResult(
        stage="online",
        provider=provider,
        score=round(score, 1),
        risk=risk,
        recommendation=recommendation,
        summary=summary,
        checks=checks,
        findings=findings,
        remark=remark,
        metrics={},
    )


def _build_prompt(
    chinese_prompt: str,
    english_prompt: str,
    local_result: AiReviewResult | None,
) -> str:
    local_summary = "无本地检测结果。"
    if local_result is not None:
        local_summary = json.dumps(local_result.to_dict(), ensure_ascii=False)
    return (
        "你是专业图片一致性质检员。请严格比较图片1原图与图片2结果图，只判断可见证据，"
        "不要臆测。重点检查：主体类别和数量、轮廓与结构比例、局部畸形、关键细节丢失、"
        "颜色和材质错误、文字或Logo拼写/形态/位置错误、背景是否符合指令、画面瑕疵、"
        "版面遮挡与协调性。生成场景和背景允许按指令改变，但原图中要求保留的主体特征必须一致。\n"
        "必须只返回一个 JSON 对象，不要添加 Markdown。字段格式：\n"
        '{"score":0-100,"risk":"low|medium|high","recommendation":"pass|review|repair",'
        '"summary":"中文总结","checks":{"主体一致性":{"status":"pass|suspect|fail|not_applicable",'
        '"score":0-100,"detail":"说明"},"结构完整性":{},"细节保留":{},"颜色一致性":{},'
        '"文字与Logo":{},"背景符合性":{},"画面质量":{},"版面协调性":{}},'
        '"issues":[{"category":"主体不一致|结构变形|细节丢失|颜色错误|文字或Logo错误|'
        '背景不符合要求|画面瑕疵|版面不协调|其他问题","severity":"low|medium|high",'
        '"confidence":0-100,"location":"具体位置","description":"问题证据",'
        '"repair_instruction":"明确返修要求"}]}\n\n'
        f"中文指令：{chinese_prompt.strip() or '无'}\n"
        f"英文指令：{english_prompt.strip() or '无'}\n"
        f"本地检测结果：{local_summary}"
    )


def _encode_image(path: Path, max_edge: int) -> str:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        edge = max(image.size)
        if edge > max_edge > 0:
            scale = max_edge / edge
            image = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _gemini_inline_part(data_url: str) -> dict[str, Any]:
    encoded = data_url.split(",", 1)[1]
    return {"inline_data": {"mime_type": "image/jpeg", "data": encoded}}


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise OnlineReviewError(f"在线复核请求失败：HTTP {exc.code}，{detail}") from exc
    except urllib.error.URLError as exc:
        raise OnlineReviewError(f"在线复核网络连接失败：{exc.reason}") from exc
    except TimeoutError as exc:
        raise OnlineReviewError("在线复核请求超时，请检查网络或提高超时时间。") from exc
    try:
        payload_out = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OnlineReviewError("在线接口返回的内容不是有效 JSON。") from exc
    if not isinstance(payload_out, dict):
        raise OnlineReviewError("在线接口返回格式不正确。")
    return payload_out


def _extract_openai_responses_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    output = payload.get("output")
    if isinstance(output, list):
        texts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if texts:
            return "\n".join(texts)
    error = payload.get("error")
    if error:
        raise OnlineReviewError(f"OpenAI 返回错误：{error}")
    raise OnlineReviewError("OpenAI 响应中没有可读取的文本结果。")


def _extract_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [str(item.get("text")) for item in content if isinstance(item, dict) and item.get("text")]
            if texts:
                return "\n".join(texts)
    error = payload.get("error")
    if error:
        raise OnlineReviewError(f"兼容接口返回错误：{error}")
    raise OnlineReviewError("兼容接口响应中没有可读取的文本结果。")


def _extract_gemini_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        if isinstance(parts, list):
            texts = [str(part.get("text")) for part in parts if isinstance(part, dict) and part.get("text")]
            if texts:
                return "\n".join(texts)
    if payload.get("error"):
        raise OnlineReviewError(f"Gemini 返回错误：{payload['error']}")
    raise OnlineReviewError("Gemini 响应中没有可读取的文本结果。")


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise OnlineReviewError("在线复核返回内容中没有有效 JSON 对象。")
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise OnlineReviewError(f"在线复核返回 JSON 解析失败：{exc}") from exc
    if not isinstance(payload, dict):
        raise OnlineReviewError("在线复核 JSON 顶层必须是对象。")
    return payload


def _normalize_category(value: str) -> str:
    compact = value.replace(" ", "").lower()
    aliases = {
        "主体不一致": "主体不一致",
        "主体错误": "主体不一致",
        "结构变形": "结构变形",
        "畸形": "结构变形",
        "细节丢失": "细节丢失",
        "颜色错误": "颜色错误",
        "色差": "颜色错误",
        "文字错误": "文字或Logo错误",
        "logo错误": "文字或Logo错误",
        "文字或logo错误": "文字或Logo错误",
        "背景不符合要求": "背景不符合要求",
        "画面瑕疵": "画面瑕疵",
        "版面不协调": "版面不协调",
    }
    if compact in aliases:
        return aliases[compact]
    for category in ISSUE_CATEGORIES:
        if compact == category.replace(" ", "").lower():
            return category
    if "logo" in compact or "文字" in compact:
        return "文字或Logo错误"
    if "结构" in compact or "畸形" in compact or "变形" in compact:
        return "结构变形"
    return "其他问题"
