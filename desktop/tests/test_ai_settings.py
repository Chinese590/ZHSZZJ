from app.ai_settings import load_online_settings, save_online_settings
from app.online_review import OnlineReviewSettings


class FakeSettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, type=None):
        value = self.values.get(key, default)
        if type is bool:
            return bool(value)
        if type is int:
            return int(value)
        return value

    def setValue(self, key, value):
        self.values[key] = value


def test_settings_round_trip_all_providers_and_flags():
    storage = FakeSettings()
    expected = OnlineReviewSettings(
        provider="custom",
        api_key="secret",
        model="vision-x",
        base_url="https://api.test/v1",
        timeout_seconds=120,
        max_image_edge=1400,
        auto_local=False,
        smart_trigger=True,
    )

    save_online_settings(storage, expected)
    actual = load_online_settings(storage)

    assert actual == expected


def test_default_settings_enable_local_and_smart_trigger():
    actual = load_online_settings(FakeSettings())

    assert actual.auto_local is True
    assert actual.smart_trigger is True
    assert actual.provider == "openai"


def test_redacted_dict_does_not_expose_key():
    settings = OnlineReviewSettings(provider="openai", api_key="abc", model="m")

    assert settings.redacted_dict()["api_key"] == "***"
    assert "abc" not in str(settings.redacted_dict())
