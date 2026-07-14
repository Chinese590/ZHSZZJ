import base64
import json
from pathlib import Path

import pytest
from PIL import Image

from app.ai_review_models import AiReviewResult, ReviewCheck
from app.online_review import (
    OnlineReviewClient,
    OnlineReviewError,
    OnlineReviewSettings,
    parse_review_response,
)


def make_image(path: Path, color: str):
    Image.new("RGB", (80, 60), color).save(path)


def local_result():
    return AiReviewResult(
        stage="local",
        provider="local",
        score=72,
        risk="medium",
        recommendation="review",
        summary="本地发现颜色差异。",
        checks={
            "颜色一致性": ReviewCheck("颜色一致性", "suspect", 61, "疑似偏色")
        },
    )


def valid_response():
    return {
        "score": 58,
        "risk": "high",
        "recommendation": "repair",
        "summary": "主体右侧结构异常。",
        "checks": {
            "主体一致性": {"status": "suspect", "score": 62, "detail": "主体相近"},
            "结构完整性": {"status": "fail", "score": 35, "detail": "右侧结构畸形"},
        },
        "issues": [
            {
                "category": "结构变形",
                "severity": "high",
                "confidence": 93,
                "location": "主体右侧",
                "description": "右侧边缘和连接结构发生畸形。",
                "repair_instruction": "恢复原图结构比例。",
            }
        ],
    }


def test_openai_responses_payload_contains_two_data_images(tmp_path: Path):
    original = tmp_path / "o.png"
    result = tmp_path / "r.png"
    make_image(original, "red")
    make_image(result, "blue")
    captured = {}

    def transport(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {"output": [{"content": [{"type": "output_text", "text": json.dumps(valid_response(), ensure_ascii=False)}]}]}

    settings = OnlineReviewSettings(provider="openai", api_key="secret", model="gpt-5.6", timeout_seconds=45)
    review = OnlineReviewClient(settings, transport=transport).review(
        original, result, "中文指令", "English prompt", local_result()
    )

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    content = captured["payload"]["input"][0]["content"]
    images = [item for item in content if item["type"] == "input_image"]
    assert len(images) == 2
    assert all(item["image_url"].startswith("data:image/jpeg;base64,") for item in images)
    assert review.provider == "openai"
    assert review.issue_categories == ["结构变形"]


def test_gemini_payload_uses_inline_data_for_both_images(tmp_path: Path):
    original = tmp_path / "o.png"
    result = tmp_path / "r.png"
    make_image(original, "red")
    make_image(result, "blue")
    captured = {}

    def transport(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(valid_response(), ensure_ascii=False)}]}}]}

    settings = OnlineReviewSettings(provider="gemini", api_key="g-key", model="gemini-3.5-flash")
    review = OnlineReviewClient(settings, transport=transport).review(
        original, result, "", "", local_result()
    )

    assert captured["url"].endswith("/v1beta/models/gemini-3.5-flash:generateContent")
    assert captured["headers"]["x-goog-api-key"] == "g-key"
    parts = captured["payload"]["contents"][0]["parts"]
    inline = [part["inline_data"] for part in parts if "inline_data" in part]
    assert len(inline) == 2
    assert all(base64.b64decode(item["data"]) for item in inline)
    assert review.provider == "gemini"


def test_custom_openai_compatible_uses_chat_completions(tmp_path: Path):
    original = tmp_path / "o.png"
    result = tmp_path / "r.png"
    make_image(original, "red")
    make_image(result, "blue")
    captured = {}

    def transport(url, headers, payload, timeout):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": json.dumps(valid_response(), ensure_ascii=False)}}]}

    settings = OnlineReviewSettings(
        provider="custom",
        api_key="token",
        model="vision-model",
        base_url="https://example.test/v1",
    )
    OnlineReviewClient(settings, transport=transport).review(original, result, "", "", None)

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["payload"]["model"] == "vision-model"
    image_items = [item for item in captured["payload"]["messages"][0]["content"] if item["type"] == "image_url"]
    assert len(image_items) == 2


def test_parse_review_response_accepts_fenced_json_and_normalizes_categories():
    payload = valid_response()
    payload["issues"][0]["category"] = "Logo错误"
    text = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    result = parse_review_response(text, "custom")

    assert result.score == 58
    assert result.risk == "high"
    assert result.issue_categories == ["文字或Logo错误"]
    assert "主体右侧" in result.remark


def test_invalid_online_response_raises_clear_error():
    with pytest.raises(OnlineReviewError, match="JSON"):
        parse_review_response("not-json", "openai")


def test_settings_require_provider_key_and_model():
    assert not OnlineReviewSettings(provider="openai").is_configured
    assert OnlineReviewSettings(provider="openai", api_key="x", model="gpt-5.6").is_configured
    assert not OnlineReviewSettings(provider="custom", api_key="x", model="m").is_configured
