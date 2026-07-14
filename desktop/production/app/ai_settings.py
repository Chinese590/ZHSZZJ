from __future__ import annotations

from typing import Any, Protocol

from .online_review import OnlineReviewSettings


class SettingsLike(Protocol):
    def value(self, key: str, default: Any = None, type: Any = None) -> Any: ...
    def setValue(self, key: str, value: Any) -> None: ...


_PREFIX = "ai_review/"


def load_online_settings(settings: SettingsLike) -> OnlineReviewSettings:
    return OnlineReviewSettings(
        provider=str(settings.value(_PREFIX + "provider", "openai") or "openai"),
        api_key=str(settings.value(_PREFIX + "api_key", "") or ""),
        model=str(settings.value(_PREFIX + "model", "") or ""),
        base_url=str(settings.value(_PREFIX + "base_url", "") or ""),
        timeout_seconds=int(settings.value(_PREFIX + "timeout_seconds", 90, type=int)),
        max_image_edge=int(settings.value(_PREFIX + "max_image_edge", 1600, type=int)),
        auto_local=bool(settings.value(_PREFIX + "auto_local", True, type=bool)),
        smart_trigger=bool(settings.value(_PREFIX + "smart_trigger", True, type=bool)),
    )


def save_online_settings(settings: SettingsLike, config: OnlineReviewSettings) -> None:
    settings.setValue(_PREFIX + "provider", config.provider)
    settings.setValue(_PREFIX + "api_key", config.api_key)
    settings.setValue(_PREFIX + "model", config.model)
    settings.setValue(_PREFIX + "base_url", config.base_url)
    settings.setValue(_PREFIX + "timeout_seconds", config.timeout_seconds)
    settings.setValue(_PREFIX + "max_image_edge", config.max_image_edge)
    settings.setValue(_PREFIX + "auto_local", config.auto_local)
    settings.setValue(_PREFIX + "smart_trigger", config.smart_trigger)
