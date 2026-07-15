from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class ShortcutDefinition:
    action_id: str
    label: str
    category: str
    defaults: tuple[str, str]
    allow_while_editing: bool = False
    repeatable: bool = False


SHORTCUT_DEFINITIONS: tuple[ShortcutDefinition, ...] = (
    ShortcutDefinition("previous", "上一组数据", "队列导航", ("A", "Num+4"), repeatable=True),
    ShortcutDefinition("next", "下一组数据", "队列导航", ("D", "Num+6"), repeatable=True),
    ShortcutDefinition("pass", "质检通过并进入下一组", "质检操作", ("Space", "Num+5")),
    ShortcutDefinition("prepare_repair", "进入返修备注", "质检操作", ("X", "Num+0")),
    ShortcutDefinition("submit_repair", "提交返修并进入下一组", "质检操作", ("Return", "Num+Enter")),
    ShortcutDefinition("focus_remark", "聚焦返修备注", "质检操作", ("R", "")),
    ShortcutDefinition("local_ai", "本地AI检测", "AI质检", ("Q", "Num+1")),
    ShortcutDefinition("online_ai", "在线深度复核", "AI质检", ("E", "Num+3")),
    ShortcutDefinition("adopt_tags", "采纳AI标签", "AI质检", ("1", "")),
    ShortcutDefinition("adopt_remark", "采纳AI备注", "AI质检", ("2", "")),
    ShortcutDefinition("clear_ai", "清空当前AI结果", "AI质检", ("3", "")),
    ShortcutDefinition("fit_both", "两张图片适应窗口", "图片查看", ("F", "")),
    ShortcutDefinition("actual_size", "当前图片切换到1:1", "图片查看", ("V", "")),
    ShortcutDefinition("toggle_image_focus", "切换原图/结果图焦点", "图片查看", ("Tab", "")),
    ShortcutDefinition("zoom_in", "放大当前图片", "图片查看", ("+", "="), repeatable=True),
    ShortcutDefinition("zoom_out", "缩小当前图片", "图片查看", ("-", ""), repeatable=True),
    ShortcutDefinition("undo", "撤销上一步", "工具操作", ("Z", "")),
    ShortcutDefinition("refresh", "刷新质检队列", "工具操作", ("C", "")),
    ShortcutDefinition("cancel", "退出当前输入状态", "工具操作", ("Esc", ""), allow_while_editing=True),
    ShortcutDefinition("shortcut_help", "查看/设置快捷键", "工具操作", ("F1", ""), allow_while_editing=True),
    ShortcutDefinition("ai_settings", "打开AI设置", "工具操作", ("F2", ""), allow_while_editing=True),
    ShortcutDefinition("delete_group", "删除当前数据组", "危险操作", ("Ctrl+Delete", "")),
)

SHORTCUT_DEFINITION_BY_ID = {item.action_id: item for item in SHORTCUT_DEFINITIONS}
DEFAULT_SHORTCUTS: dict[str, tuple[str, str]] = {
    item.action_id: item.defaults for item in SHORTCUT_DEFINITIONS
}
SETTINGS_KEY = "shortcuts/json"


def _clean_pair(values: Sequence[str] | str | None, fallback: tuple[str, str]) -> tuple[str, str]:
    if values is None:
        return fallback
    if isinstance(values, str):
        raw = [values]
    else:
        raw = list(values)
    cleaned = [str(value).strip() for value in raw[:2]]
    while len(cleaned) < 2:
        cleaned.append("")
    return cleaned[0], cleaned[1]


def normalize_shortcuts(
    mapping: Mapping[str, Sequence[str] | str] | None,
) -> dict[str, tuple[str, str]]:
    mapping = mapping or {}
    return {
        action_id: _clean_pair(mapping.get(action_id), defaults)
        for action_id, defaults in DEFAULT_SHORTCUTS.items()
    }


def load_shortcuts(settings: object) -> dict[str, tuple[str, str]]:
    value = getattr(settings, "value")(SETTINGS_KEY, "")
    if not value:
        return dict(DEFAULT_SHORTCUTS)
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return dict(DEFAULT_SHORTCUTS)
    if not isinstance(payload, dict):
        return dict(DEFAULT_SHORTCUTS)
    return normalize_shortcuts(payload)


def save_shortcuts(
    settings: object,
    mapping: Mapping[str, Sequence[str] | str],
) -> dict[str, tuple[str, str]]:
    normalized = normalize_shortcuts(mapping)
    payload = {action_id: list(values) for action_id, values in normalized.items()}
    getattr(settings, "setValue")(
        SETTINGS_KEY,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )
    return normalized


def find_conflicts(
    mapping: Mapping[str, Sequence[str] | str],
) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for action_id, values in mapping.items():
        if isinstance(values, str):
            sequences: Iterable[str] = (values,)
        else:
            sequences = values
        for value in sequences:
            normalized = str(value).strip().casefold()
            if normalized:
                owners.setdefault(normalized, []).append(action_id)
    return {
        sequence: action_ids
        for sequence, action_ids in owners.items()
        if len(set(action_ids)) > 1
    }


def shortcut_hint(mapping: Mapping[str, Sequence[str] | str], action_id: str) -> str:
    values = mapping.get(action_id, DEFAULT_SHORTCUTS.get(action_id, ("", "")))
    if isinstance(values, str):
        sequences = [values]
    else:
        sequences = list(values)
    return " / ".join(str(value).strip() for value in sequences if str(value).strip())
