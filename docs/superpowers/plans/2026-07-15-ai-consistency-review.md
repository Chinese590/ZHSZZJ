# AI Consistency Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add local and online original-versus-result consistency review to the existing DataTang Windows QC application without allowing AI to move files automatically.

**Architecture:** Introduce focused domain modules for review models, local metrics, online providers, settings and append-only audit storage. Add a reusable PySide6 result panel and worker, integrate it into the current main window, then attach the selected AI result to operation logs and Excel reports.

**Tech Stack:** Python 3.11, PySide6 6.8, Pillow 11, NumPy 2.2, ONNX Runtime 1.22, urllib, openpyxl, pytest.

## Global Constraints

- Keep all existing QC workflows and folder movement rules unchanged.
- AI output is advisory and must never automatically pass, fail, delete or move a data group.
- Support OpenAI, Gemini and OpenAI-compatible custom APIs.
- Default flow is local review first and smart online review only for medium/high risk when configuration is complete.
- Do not log API keys.
- Add no new runtime dependency.
- Preserve backward compatibility with existing operation JSONL records and reports.

---

### Task 1: Review domain models and deterministic local metrics

**Files:**
- Create: `desktop/production/app/ai_review_models.py`
- Create: `desktop/production/app/local_review.py`
- Test: `desktop/tests/test_local_review.py`

**Interfaces:**
- Produces: `ReviewFinding`, `ReviewCheck`, `AiReviewResult`, `LocalConsistencyReviewer.review(original, result, semantic_compare=None)`.

- [x] Write failing tests for identical images, color-shifted images, blurred images, layout imbalance and missing DINO fallback.
- [x] Run `pytest desktop/tests/test_local_review.py -q` and confirm failures are caused by missing modules.
- [x] Implement image loading, normalized metrics, issue/risk mapping and editable remark generation.
- [x] Re-run the focused tests and confirm all pass.

### Task 2: Online provider clients and strict JSON parsing

**Files:**
- Create: `desktop/production/app/online_review.py`
- Test: `desktop/tests/test_online_review.py`

**Interfaces:**
- Consumes: `AiReviewResult` local summary.
- Produces: `OnlineReviewSettings`, `OnlineReviewClient.review(...)`, `parse_review_response(text, provider)`.

- [x] Write failing tests for OpenAI Responses payload, Gemini inline-data payload, custom chat-completions payload, fenced JSON parsing and invalid response errors.
- [x] Run focused tests and confirm expected failures.
- [x] Implement injected JSON HTTP transport, image downscaling/base64 encoding, provider payloads, response extraction and normalization.
- [x] Re-run focused tests and confirm all pass.

### Task 3: Persistent settings and append-only AI audit store

**Files:**
- Create: `desktop/production/app/ai_review_store.py`
- Create: `desktop/production/app/ui/ai_settings_dialog.py`
- Test: `desktop/tests/test_ai_review_store.py`
- Test: `desktop/tests/test_ai_settings.py`

**Interfaces:**
- Produces: `AiReviewStore.append`, `AiReviewStore.latest_for_group`, `AiReviewStore.latest_reviews`; `load_online_settings`, `save_online_settings`.

- [x] Write failing tests for signatures, append/load, online-over-local precedence, date filtering and redacted settings representation.
- [x] Implement JSONL storage and QSettings mapping without logging API keys.
- [x] Re-run focused tests.

### Task 4: AI review panel and background worker

**Files:**
- Create: `desktop/production/app/ui/ai_review_panel.py`
- Create: `desktop/production/app/ui/ai_review_worker.py`
- Test: `desktop/tests/test_ai_review_panel.py`

**Interfaces:**
- Produces: panel signals `local_requested`, `online_requested`, `settings_requested`, `adopt_tags_requested`, `adopt_remark_requested`, `clear_requested`; worker signals `finished(result, signature)`, `failed(message, signature)`.

- [x] Write failing headless widget tests for result rendering, button signals and busy state.
- [x] Implement the compact result table, score/risk/recommendation display and action buttons.
- [x] Re-run focused tests with `QT_QPA_PLATFORM=offscreen`.

### Task 5: Main-window integration and smart trigger

**Files:**
- Modify: `desktop/production/app/ui/main_window.py`
- Test: `desktop/tests/test_ui_ai_review.py`

**Interfaces:**
- Consumes all prior tasks.
- Produces: current selected `AiReviewResult` and automatic/manual review flow.

- [x] Write failing tests for local review on selection, medium-risk smart online trigger, stale-result rejection, adopt tags, adopt remark and no automatic file operation.
- [x] Replace the old one-number comparison UX with the new panel while keeping the model download button.
- [x] Add cache loading, task lifecycle, signature checks and provider configuration validation.
- [x] Re-run focused UI tests.

### Task 6: Attach AI context to operations and reports

**Files:**
- Modify: `desktop/production/app/models.py`
- Modify: `desktop/production/app/operations.py`
- Modify: `desktop/production/app/history.py`
- Modify: `desktop/production/app/reports.py`
- Modify: `desktop/production/app/ui/main_window.py`
- Test: `desktop/tests/test_operations.py`
- Test: `desktop/tests/test_history.py`
- Test: `desktop/tests/test_reports.py`

**Interfaces:**
- `QualityOperations.pass_group(group, ai_review=None)` and `fail_group(group, issues, remark, ai_review=None)`.
- `export_report(root, output, session_records, ai_reviews=None)`.

- [x] Add failing backward-compatibility and AI-statistics tests.
- [x] Add optional AI fields to operation records and JSONL parsing.
- [x] Add AI columns and an `AI辅助统计` worksheet.
- [x] Re-run focused tests.

### Task 7: Release contracts, documentation and regression suite

**Files:**
- Modify: `README.md`
- Modify: `docs/PHASE_STATUS.md`
- Modify: `docs/VERIFICATION.md`
- Modify: `tests/static/test_phase1_sources.py`
- Add: `修复说明_AI一致性质检_v1.1.0.txt`

- [x] Add static tests proving all providers, smart trigger, no-auto-move statement and report sheet exist.
- [x] Run `pytest tests/static desktop/tests -q`.
- [x] Run `python -m compileall -q desktop/production/app`.
- [x] Parse workflow YAML and release JSON contracts.
- [x] Package only changed source files and documentation as `数据堂质检工具_AI一致性质检助手_v1.1.0.zip` with SHA256.
