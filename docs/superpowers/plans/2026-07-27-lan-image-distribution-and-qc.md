# 局域网图片分发中心与质检可靠性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在管理者电脑上运行无数据库的局域网图片分发中心，并接入现有质检工具、修复运行库安装上限和高 DPI 看图清晰度。

**Architecture:** 分发中心由 Python 标准库 HTTP 服务和文件持久化组成。核心服务将成员、任务和审计写入项目根目录 `.图片分发中心`，图片始终存于管理者电脑；浏览器仅通过已鉴权 API 获取本人任务。质检继续以现有目录队列为主，新增 `distribution-task.json` 和 `qc-result.json` 作为双向状态契约。

**Tech Stack:** Python 3.11 标准库、Pillow、PySide6、pytest、Playwright、C#/.NET 8 xUnit；不添加 SQLite、ORM、Web 框架或前端框架。

## Global Constraints

- 管理者电脑是唯一服务端；服务仅可绑定 `127.0.0.1` 或 RFC1918 私网地址。
- 图片一张一任务，成员不可通过 API 或路径访问他人图片。
- 所有状态在 `<project>/.图片分发中心` 以原子 JSON 写入和追加 JSONL 保存。
- SHA-256 相同图片硬阻断；近似图片仅告警，不能静默作为同一图片。
- 已下载文件不能远程擦除；召回只能撤销服务端后续访问，须审计。
- 质检尺寸与编号规则均为高优先级提醒，不自动替代人工结论。
- GitHub 推送和 Release 必须等待用户最终确认。

---

### Task 1: 创建纯文件持久化任务服务

**Files:**
- Create: `desktop/production/app/distribution.py`
- Test: `desktop/tests/test_distribution.py`

**Interfaces:**
- Produces: `DistributionService(project_root: Path)`, `import_images(source: Path) -> ImportResult`, `distribute(member_ids: list[str], per_member: int) -> list[Assignment]`, `my_tasks(member_id: str) -> list[Task]`, `recall(task_id: str, reason: str) -> Task`, `daily_report(day: date) -> list[dict]`.
- Consumes: `hashlib`, `json`, `os.replace`, `secrets`, `PIL.Image`.

- [ ] **Step 1: Write the failing import and atomic-write tests**

```python
def test_import_rejects_exact_duplicate_and_keeps_first_task(tmp_path):
    service = DistributionService(tmp_path)
    source = make_image_folder(tmp_path, {"a.jpg": (3000, 3000), "b.jpg": (3000, 3000)})
    shutil.copy2(source / "a.jpg", source / "b.jpg")
    result = service.import_images(source)
    assert result.imported == 1
    assert result.exact_duplicates == ["b.jpg"]
    assert len(list((tmp_path / ".图片分发中心" / "tasks").glob("*.json"))) == 1
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution.py -q`

Expected: FAIL because `DistributionService` does not exist.

- [ ] **Step 3: Implement minimum file-backed state**

Implement `DistributionService` with one task JSON per image, SHA-256, image width/height, perceptual hash, a `members.json` reader/writer, atomic `*.tmp` then `os.replace`, and append-only `audit.jsonl`. Reject duplicate SHA-256 against every persisted task and `successful-images.jsonl`; record near perceptual matches as warnings without blocking import.

- [ ] **Step 4: Run import tests**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add desktop/production/app/distribution.py desktop/tests/test_distribution.py
git commit -m "feat: add file-backed image distribution state"
```

### Task 2: 实现成员、随机无重复分发、上传和召回

**Files:**
- Modify: `desktop/production/app/distribution.py`
- Modify: `desktop/tests/test_distribution.py`

**Interfaces:**
- Consumes: `DistributionService` from Task 1.
- Produces: member methods `create_member`, `authenticate`, task state transition methods `assign`, `start`, `upload`, and `recall`.

- [ ] **Step 1: Write failing state-transition tests**

```python
def test_distribution_is_unique_and_recall_restores_only_unused_task(tmp_path):
    service = seeded_service(tmp_path, images=5, members=("a", "b"))
    assignments = service.distribute(["a", "b"], per_member=2)
    assert len({item.task_id for item in assignments}) == 4
    service.start(assignments[0].task_id, "a")
    recalled = service.recall(assignments[0].task_id, "operator", "下班召回")
    assert recalled.state == "AVAILABLE"
    assert service.task(assignments[0].task_id).member_id is None


def test_member_can_upload_before_task_completion(tmp_path):
    service, task_id = assigned_service(tmp_path)
    uploaded = service.upload(task_id, "member-a", make_result_image(tmp_path))
    assert uploaded.state == "UPLOADED_PENDING_QC"
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution.py -q`

Expected: FAIL because transitions are absent.

- [ ] **Step 3: Implement minimum transitions and checks**

Use `secrets.SystemRandom` to select only `AVAILABLE` task files. Before each assignment re-read task state and atomically write `ASSIGNED`; never choose task IDs already allocated in the same operation. Require matching owner and active state for start/upload. On recall, reject uploaded or QC-final tasks, remove member ownership, append recall reason and return task to `AVAILABLE`. Store uploaded results under `.图片分发中心/uploads/<task-id>/` and write a queue directory under `质检项目/待质检/<member>/<task-id>/` with `distribution-task.json`.

- [ ] **Step 4: Run transition tests**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add desktop/production/app/distribution.py desktop/tests/test_distribution.py
git commit -m "feat: distribute and recall one-image tasks"
```

### Task 3: 以最小 Web 界面提供管理员与成员端

**Files:**
- Create: `desktop/production/app/distribution_server.py`
- Create: `desktop/production/app/distribution_ui.html`
- Test: `desktop/tests/test_distribution_server.py`
- Test: `desktop/tests/browser/test_distribution_flow.py`

**Interfaces:**
- Consumes: `DistributionService`.
- Produces: `serve(project_root: Path, host: str, port: int)`, authenticated JSON API under `/api/`, HTML interface under `/`.

- [ ] **Step 1: Write failing authorization and bind tests**

```python
def test_private_host_is_allowed_and_public_host_is_rejected(tmp_path):
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("192.168.1.20") == "192.168.1.20"
    with pytest.raises(ValueError):
        validate_bind_host("8.8.8.8")


def test_member_cannot_read_other_member_task(client, seeded_web_service):
    member_a = client.login("member-a", "password-a")
    response = member_a.get("/api/tasks/member-b-task-id")
    assert response.status_code == 403
```

- [ ] **Step 2: Run server tests and verify they fail**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution_server.py -q`

Expected: FAIL because the server is absent.

- [ ] **Step 3: Implement standard-library HTTP server**

Build a `ThreadingHTTPServer` with explicit routes: `/api/login`, `/api/logout`, `/api/admin/members`, `/api/admin/import`, `/api/admin/distribute`, `/api/admin/recall`, `/api/admin/report`, `/api/my/tasks`, `/api/tasks/<id>/image`, and `/api/tasks/<id>/upload`. Use PBKDF2-HMAC password hashes in `members.json`; use a random HttpOnly session cookie; enforce same-origin POST requests and session role checks. Serve a single HTML file with a manager panel and a member “我的任务” panel. Reject public bind addresses, path traversal, missing uploads, wrong task owner, expired sessions, and unsupported image extension.

- [ ] **Step 4: Write browser flow test**

```python
def test_manager_distributes_then_member_uploads_and_manager_recalls(page, live_server, image_folder):
    manager = page
    manager.goto(live_server.url)
    login(manager, "admin", "admin-password")
    import_images(manager, image_folder)
    distribute(manager, ["member-a"], per_member=1)
    member = manager.context.browser.new_page()
    member.goto(live_server.url)
    login(member, "member-a", "member-password")
    assert member.get_by_text("我的任务").is_visible()
    member.get_by_role("button", name="上传结果").click()
    assert manager.get_by_text("已上传待质检").is_visible()
```

- [ ] **Step 5: Run unit and browser tests**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution_server.py desktop/tests/browser/test_distribution_flow.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add desktop/production/app/distribution_server.py desktop/production/app/distribution_ui.html desktop/tests/test_distribution_server.py desktop/tests/browser/test_distribution_flow.py
git commit -m "feat: add LAN distribution manager and member portal"
```

### Task 4: 接入质检状态、重复、尺寸和编号校验

**Files:**
- Create: `desktop/production/app/distribution_qc.py`
- Modify: `desktop/production/app/scanner.py`
- Modify: `desktop/production/app/ui/main_window.py`
- Modify: `desktop/tests/test_scanner.py`
- Create: `desktop/tests/test_distribution_qc.py`

**Interfaces:**
- Produces: `validate_distribution_task(path: Path, successful_registry: Path) -> list[QcWarning]`, `sync_qc_result(project_root: Path, task_dir: Path) -> Task`.
- Consumes: queued `distribution-task.json`, task file JSON, existing scanner records.

- [ ] **Step 1: Write failing QC warning tests**

```python
def test_distribution_warnings_cover_small_edge_and_number_mismatch(tmp_path):
    task = make_distribution_task(tmp_path, folder="12345678", image_name="87654321_edit.jpg", size=(1800, 3000))
    warnings = validate_distribution_task(task, tmp_path / "successful-images.jsonl")
    assert {warning.code for warning in warnings} >= {"MIN_EDGE_LT_2048", "NUMBER_MISMATCH"}


def test_exact_successful_image_is_reported_as_reused(tmp_path):
    task = make_distribution_task(tmp_path, folder="12345678", image_name="12345678.jpg")
    write_successful_hash(tmp_path / "successful-images.jsonl", sha256_of(task / "12345678.jpg"))
    assert "EXACT_REUSE" in {item.code for item in validate_distribution_task(task, tmp_path / "successful-images.jsonl")}
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution_qc.py -q`

Expected: FAIL because validator is absent.

- [ ] **Step 3: Implement validator and UI presentation**

Read only `distribution-task.json` when present. Check original/result dimensions through Pillow, calculate hashes, compare successful registry and current QC tasks, extract a complete numeric directory name and leading filename digits, and return non-blocking warnings. In the existing QC window show warnings above the decision controls and include them in the QC result JSON. On pass/fail write `qc-result.json`; the distribution service synchronizes status and appends successful hashes only after `QC_PASS`.

- [ ] **Step 4: Run QC tests**

Run: `PYTHONPATH=desktop/production .venv\Scripts\python.exe -m pytest desktop/tests/test_distribution_qc.py desktop/tests/test_scanner.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add desktop/production/app/distribution_qc.py desktop/production/app/scanner.py desktop/production/app/ui/main_window.py desktop/tests/test_distribution_qc.py desktop/tests/test_scanner.py
git commit -m "feat: validate distributed tasks in QC"
```

### Task 5: 修复启动器对正常运行库的错误拦截

**Files:**
- Modify: `launcher/src/DataTangQCTool.Launcher/Services/PackageInstaller.cs`
- Modify: `launcher/tests/DataTangQCTool.Launcher.Tests/PackageInstallerTests.cs`
- Modify: `.github/workflows/release-stable.yml`

**Interfaces:**
- Consumes: `PackageInstaller.InstallPackageAsync`.
- Produces: a 20,000-entry package limit with retained 2 GiB decompressed-size and ZipSlip checks.

- [ ] **Step 1: Write the boundary test**

```csharp
[Fact]
public async Task InstallPackageAsync_rejects_package_above_20k_entries()
{
    var zip = CreateZipWithEntries(20_001);
    var installer = new PackageInstaller();
    await Assert.ThrowsAsync<InvalidDataException>(() => installer.InstallPackageAsync(zip, TargetDirectory, Array.Empty<string>(), CancellationToken.None));
}
```

- [ ] **Step 2: Run the test and verify the current implementation disagrees at 10,001**

Run: `dotnet test launcher/tests/DataTangQCTool.Launcher.Tests/DataTangQCTool.Launcher.Tests.csproj -c Release --filter PackageInstaller`

Expected: existing 10,001-entry test documents the incorrect threshold; new 20,001 test initially fails.

- [ ] **Step 3: Implement calibrated limit and release assertion**

Change only `MaxEntryCount` from `10_000` to `20_000`; retain total uncompressed limit, zip path validation, staging and required-file verification. After runtime packaging, add a PowerShell assertion that the generated archive has `<= 20000` entries. This protects both the legitimate current 13,922-entry runtime and the security bound.

- [ ] **Step 4: Run C# test**

Run: `dotnet test launcher/tests/DataTangQCTool.Launcher.Tests/DataTangQCTool.Launcher.Tests.csproj -c Release --filter PackageInstaller`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add launcher/src/DataTangQCTool.Launcher/Services/PackageInstaller.cs launcher/tests/DataTangQCTool.Launcher.Tests/PackageInstallerTests.cs .github/workflows/release-stable.yml
git commit -m "fix: allow verified runtime package entry count"
```

### Task 6: 修复高 DPI 预览清晰度

**Files:**
- Modify: `desktop/production/app/ui/image_viewer.py`
- Modify: `desktop/tests/test_image_viewer.py`

**Interfaces:**
- Consumes: `ZoomableImageView._preview_size()` and existing `load_image_for_display` cache.
- Produces: a preview bounded at 4096 physical pixels, full-resolution only on existing 1:1 action.

- [ ] **Step 1: Write failing DPI test**

```python
def test_preview_size_uses_physical_pixels_and_not_legacy_2560_cap(qtbot, monkeypatch):
    viewer = ZoomableImageView()
    qtbot.addWidget(viewer)
    viewer.resize(3000, 1800)
    monkeypatch.setattr(viewer, "devicePixelRatioF", lambda: 2.0)
    width, height = viewer._preview_size()
    assert width == 4096
    assert height == 3600
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `$env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONPATH='desktop/production'; .venv\Scripts\python.exe -m pytest desktop/tests/test_image_viewer.py -q`

Expected: FAIL because current hard cap is 2560.

- [ ] **Step 3: Implement minimum preview adjustment**

Compute preview width and height using `ceil(viewport logical size * devicePixelRatioF())`, clamp each edge from 1024 through 4096, retain the existing thumbnail decode, LRU cache and explicit 1:1 full image path. Do not decode every image at full resolution during row changes.

- [ ] **Step 4: Run viewer tests**

Run: `$env:QT_QPA_PLATFORM='offscreen'; $env:PYTHONPATH='desktop/production'; .venv\Scripts\python.exe -m pytest desktop/tests/test_image_loader.py desktop/tests/test_image_viewer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add desktop/production/app/ui/image_viewer.py desktop/tests/test_image_viewer.py
git commit -m "fix: render high DPI QC previews sharply"
```

### Task 7: 完成测试、攻击性验证和本地交付证据

**Files:**
- Create: `docs/verification/2026-07-27-lan-distribution-evidence.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: all completed application and test interfaces.
- Produces: repeatable command list and actual local results, excluding unrun Windows release gates.

- [ ] **Step 1: Run complete Python and browser gates**

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONPATH='desktop/production'
.venv\Scripts\python.exe -m pytest tests/static desktop/tests -q
```

Expected: PASS with test count recorded from this run.

- [ ] **Step 2: Run focused security tests**

```powershell
.venv\Scripts\python.exe -m pytest desktop/tests/test_distribution_server.py desktop/tests/test_distribution_qc.py -q
```

Expected: PASS for other-user access, traversal, public bind, expired session, duplicate upload and recall cases.

- [ ] **Step 3: Run code review**

```powershell
ocr review
```

Expected: capture findings; fix every actionable finding and rerun the relevant gate.

- [ ] **Step 4: Record actual evidence**

Write exact commands, timestamps, pass/fail output, test totals, observed browser assertions, hash/entry evidence, and limitations. Label measurements `actual` only when command output proves them; otherwise label `estimated`.

- [ ] **Step 5: Update usage documentation and commit**

```powershell
git add README.md docs/verification/2026-07-27-lan-distribution-evidence.md
git commit -m "docs: verify LAN distribution release readiness"
```

- [ ] **Step 6: Await explicit publishing approval**

Do not run `git push`, create a tag, dispatch a release workflow, or publish a GitHub Release until the user explicitly approves after reviewing local evidence.
