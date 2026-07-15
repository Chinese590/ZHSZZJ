from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "desktop" / "production" / "app"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shortcut_settings_dialog_and_manager_are_packaged():
    required = [
        APP / "shortcut_settings.py",
        APP / "ui" / "shortcut_settings_dialog.py",
        APP / "ui" / "shortcut_controller.py",
    ]
    assert all(path.is_file() for path in required)


def test_main_window_wires_convenient_shortcuts_without_bypassing_safety_checks():
    source = read(APP / "ui" / "main_window.py")
    assert "ShortcutController" in source
    assert "open_shortcut_settings" in source
    assert "prepare_repair" in source
    assert "submit_repair" in source
    assert "fit_both_images" in source
    assert "toggle_image_focus" in source
    assert "delete_current_group" in source
    assert "self.pass_current" in source
    assert "self.fail_current" in source
    assert 'QPushButton("快捷键设置")' in source


def test_text_editing_guard_and_numeric_keypad_defaults_exist():
    settings = read(APP / "shortcut_settings.py")
    controller = read(APP / "ui" / "shortcut_controller.py")
    assert '("A", "Num+4")' in settings
    assert '("D", "Num+6")' in settings
    assert '("Space", "Num+5")' in settings
    assert '("X", "Num+0")' in settings
    assert '("Q", "Num+1")' in settings
    assert '("E", "Num+3")' in settings
    assert "_is_text_editor" in controller
    assert "allow_while_editing" in controller
    assert "setAutoRepeat" in controller


def test_image_viewer_has_keyboard_zoom_helpers():
    source = read(APP / "ui" / "image_viewer.py")
    assert "def zoom_in" in source
    assert "def zoom_out" in source
    assert "def zoom_by" in source
