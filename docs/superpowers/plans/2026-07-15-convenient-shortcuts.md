# Convenient Shortcuts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, customizable left-hand and numeric-keypad shortcuts to the existing DataTang QC desktop application.

**Architecture:** Store shortcut definitions independently from Qt UI, bind them through a focused controller that disables typing-conflicting actions while editing, and dispatch all actions into existing MainWindow safety-checked methods. Add a settings dialog and minimal image viewer helpers.

**Tech Stack:** Python 3.11, PySide6 6.8.3, QSettings, pytest, QtTest.

## Global Constraints

- Do not bypass existing pass, fail, delete, undo, AI busy, or file-completeness validation.
- Single-key shortcuts must not consume normal typing in editable text controls.
- Enter submits only from the repair workflow; Shift+Enter inserts a newline.
- Deleting a group must retain both existing confirmation steps.
- Shortcut changes persist through QSettings and apply immediately.

---

### Task 1: Shortcut configuration model

**Files:**
- Create: `desktop/production/app/shortcut_settings.py`
- Test: `desktop/tests/test_shortcut_settings.py`

- [x] Write failing tests for defaults, merge, persistence, and duplicate detection.
- [x] Run the tests and confirm the missing-module failure.
- [x] Implement definitions and persistence helpers.
- [x] Run the tests and confirm they pass.

### Task 2: Shortcut binding and editing UI

**Files:**
- Create: `desktop/production/app/ui/shortcut_controller.py`
- Create: `desktop/production/app/ui/shortcut_settings_dialog.py`
- Test: `tests/static/test_shortcut_sources.py`

- [x] Write failing source-contract tests.
- [x] Implement QShortcut binding, focus-based enabling, ambiguity reporting, and settings UI.
- [x] Validate conflicts before saving.

### Task 3: Existing-window integration

**Files:**
- Modify: `desktop/production/app/ui/main_window.py`
- Modify: `desktop/production/app/ui/image_viewer.py`
- Test: `desktop/tests/test_ui_shortcuts.py`

- [x] Map shortcuts to existing guarded business methods.
- [x] Add repair-entry, image focus, fit, zoom, cancel-input, and settings actions.
- [x] Add keyboard integration tests for typing protection, Space, X/Enter, Shift+Enter, and numeric keypad.

### Task 4: Documentation and regression verification

**Files:**
- Create: `docs/SHORTCUTS.md`
- Modify: `README.md`
- Modify: `docs/PHASE_STATUS.md`
- Modify: `docs/VERIFICATION.md`

- [x] Document defaults and safety rules.
- [x] Run the full desktop and static test suite.
- [x] Compile all Python sources.
- [x] Package only changed source and test files.
