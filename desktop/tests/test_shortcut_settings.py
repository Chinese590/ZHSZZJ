from app.shortcut_settings import (
    DEFAULT_SHORTCUTS,
    find_conflicts,
    load_shortcuts,
    save_shortcuts,
)


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value



def test_defaults_cover_left_hand_and_numeric_keypad_modes():
    assert DEFAULT_SHORTCUTS["previous"] == ("A", "Num+4")
    assert DEFAULT_SHORTCUTS["next"] == ("D", "Num+6")
    assert DEFAULT_SHORTCUTS["pass"] == ("Space", "Num+5")
    assert DEFAULT_SHORTCUTS["prepare_repair"] == ("X", "Num+0")
    assert DEFAULT_SHORTCUTS["submit_repair"] == ("Return", "Num+Enter")
    assert DEFAULT_SHORTCUTS["local_ai"] == ("Q", "Num+1")
    assert DEFAULT_SHORTCUTS["online_ai"] == ("E", "Num+3")



def test_load_shortcuts_merges_saved_values_with_new_defaults():
    settings = MemorySettings()
    settings.setValue("shortcuts/json", '{"previous":["Left", ""], "pass":["P"]}')

    loaded = load_shortcuts(settings)

    assert loaded["previous"] == ("Left", "")
    assert loaded["pass"] == ("P", "")
    assert loaded["next"] == DEFAULT_SHORTCUTS["next"]



def test_save_shortcuts_round_trips_and_strips_whitespace():
    settings = MemorySettings()

    save_shortcuts(settings, {"previous": ["  Left  ", "Num+4"]})
    loaded = load_shortcuts(settings)

    assert loaded["previous"] == ("Left", "Num+4")



def test_find_conflicts_reports_same_sequence_across_actions_case_insensitively():
    conflicts = find_conflicts(
        {
            "previous": ("A", "Num+4"),
            "next": ("a", "Num+6"),
            "pass": ("Space", ""),
        }
    )

    assert conflicts == {"a": ["previous", "next"]}
