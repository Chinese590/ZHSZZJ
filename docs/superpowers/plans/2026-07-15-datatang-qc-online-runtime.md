# 数据堂质检工具：在线下载运行库版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Windows 10/11 x64 桌面质检工具：首次启动由用户指定程序缓存目录，启动器从 GitHub Releases 下载并校验运行库与主程序；以后自动读取已保存缓存地址并可离线运行；Hugging Face 模型作为可选辅助按需下载。

**Architecture:** 使用 .NET 8 WPF 单文件启动器负责缓存目录选择、路径持久化、GitHub 下载、断点续传、SHA256 校验、原子安装、修复和启动。质检主程序使用 Python 3.11 + PySide6，运行在 GitHub 发布的独立运行库中；基础功能完全不依赖 Hugging Face，模型管理器只在用户主动启用 AI 辅助时下载模型。

**Tech Stack:** C# 12、.NET 8 WPF、Python 3.11、PySide6、Pillow/ImageCms、Watchdog、OpenPyXL、Send2Trash、Transformers（可选）、Hugging Face Hub（可选）、pytest、xUnit、GitHub Actions。

## Global Constraints

- 目标系统：Windows 10/11 x64。
- 目标电脑不需要预装 Python、pip、Git 或管理员权限。
- 首次运行需要联网；运行库和主程序安装完成后，基础质检功能必须可以断网启动。
- 程序缓存根目录必须由用户首次启动时自行选择，不固定写入 `%LOCALAPPDATA%`。
- 已选择的缓存地址指针保存到 `%LOCALAPPDATA%\DataTangQCToolLauncher\launcher.json`，启动器移动位置后仍能自动读取。
- 第二次及后续启动必须优先加载上次保存的缓存地址；目录不可访问时不得静默改用其他位置。
- 用户指定缓存根目录下统一建立 `runtime/`、`app/`、`models/`、`downloads/`、`logs/`、`config/`、`state/`。
- 运行库和主程序只从固定 GitHub 仓库的 Releases 下载；下载使用 HTTPS、`.part` 临时文件、断点续传和 SHA256 校验。
- Hugging Face 模型默认不下载、不加载，模型下载失败不得阻塞基础质检功能。
- 所有安装和更新必须使用版本目录与原子切换，不得覆盖正在使用的版本。
- 质检项目目录与程序缓存目录完全分离，程序不得把业务图片复制进缓存。
- 质检队列按用户最终要求同时读取 `待质检` 和 `待返修`。
- 数据组必须支持通过、不通过、删除至回收站、撤销移动、指令自动回写和 Excel 日报。
- 图片显示必须支持 EXIF 方向、ICC/CMYK 转 sRGB、真实格式、像素、自适应、缩放和拖动。
- 所有错误必须写入日志并显示明确中文错误，不得出现无响应或一闪而过。

---

## Repository Structure

```text
DataTangQCTool/
├─ launcher/
│  ├─ src/DataTangQCTool.Launcher/
│  │  ├─ App.xaml
│  │  ├─ App.xaml.cs
│  │  ├─ MainWindow.xaml
│  │  ├─ MainWindow.xaml.cs
│  │  ├─ Models/
│  │  │  ├─ LauncherConfig.cs
│  │  │  ├─ ReleaseManifest.cs
│  │  │  └─ InstallState.cs
│  │  └─ Services/
│  │     ├─ LauncherConfigStore.cs
│  │     ├─ CacheRootSelector.cs
│  │     ├─ ReleaseManifestClient.cs
│  │     ├─ ResumableDownloadService.cs
│  │     ├─ PackageInstaller.cs
│  │     ├─ RuntimeHealthChecker.cs
│  │     ├─ StartupCoordinator.cs
│  │     └─ LauncherLogger.cs
│  └─ tests/DataTangQCTool.Launcher.Tests/
├─ desktop/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ domain.py
│  │  ├─ config.py
│  │  ├─ services/
│  │  │  ├─ project_scanner.py
│  │  │  ├─ image_service.py
│  │  │  ├─ instruction_service.py
│  │  │  ├─ qc_service.py
│  │  │  ├─ recycle_service.py
│  │  │  ├─ report_service.py
│  │  │  ├─ operation_log.py
│  │  │  ├─ watcher_service.py
│  │  │  └─ model_manager.py
│  │  └─ ui/
│  │     ├─ main_window.py
│  │     ├─ zoom_image_view.py
│  │     ├─ cache_settings_dialog.py
│  │     └─ model_download_dialog.py
│  └─ tests/
├─ release/
│  ├─ manifests/runtime-manifest.schema.json
│  └─ requirements/runtime-requirements.lock
├─ scripts/
│  ├─ build_runtime.ps1
│  ├─ build_app_package.ps1
│  ├─ build_launcher.ps1
│  └─ publish_release.ps1
├─ .github/workflows/
│  ├─ build-runtime.yml
│  ├─ build-app.yml
│  └─ release-stable.yml
└─ docs/
   ├─ deployment.md
   ├─ release-process.md
   └─ troubleshooting.md
```

---

### Task 1: 建立仓库骨架与版本清单协议

**Files:**
- Create: `release/manifests/runtime-manifest.schema.json`
- Create: `launcher/src/DataTangQCTool.Launcher/Models/ReleaseManifest.cs`
- Create: `launcher/tests/DataTangQCTool.Launcher.Tests/ReleaseManifestTests.cs`
- Create: `desktop/app/config.py`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/ReleaseManifestTests.cs`

**Interfaces:**
- Produces: `ReleaseManifest.Parse(string json) -> ReleaseManifest`
- Produces: `get_cache_layout(cache_root: Path) -> CacheLayout`

- [ ] **Step 1: 写清单解析失败测试**

```csharp
[Fact]
public void Parse_rejects_manifest_without_sha256()
{
    var json = """{"runtime":{"version":"1.0.0","url":"https://example/runtime.zip"}}""";
    Assert.Throws<InvalidDataException>(() => ReleaseManifest.Parse(json));
}
```

- [ ] **Step 2: 运行测试并确认失败**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests --filter Parse_rejects_manifest_without_sha256
```

Expected: FAIL，提示 `ReleaseManifest` 尚不存在。

- [ ] **Step 3: 实现固定清单结构**

```json
{
  "schema_version": 1,
  "channel": "stable",
  "runtime": {
    "version": "1.0.0",
    "url": "https://github.com/OWNER/REPO/releases/download/runtime-v1.0.0/runtime-win-x64.zip",
    "sha256": "64位小写十六进制",
    "size": 123456789
  },
  "app": {
    "version": "1.0.0",
    "url": "https://github.com/OWNER/REPO/releases/download/app-v1.0.0/app.zip",
    "sha256": "64位小写十六进制",
    "size": 1234567,
    "entrypoint": "app/main.py"
  }
}
```

`ReleaseManifest.Parse` 必须验证 HTTPS、GitHub 固定仓库前缀、版本、文件大小和 64 位 SHA256。

- [ ] **Step 4: 增加缓存目录布局测试**

```python
def test_cache_layout_uses_selected_root(tmp_path):
    layout = get_cache_layout(tmp_path / "用户指定目录")
    assert layout.runtime == tmp_path / "用户指定目录" / "runtime"
    assert layout.models == tmp_path / "用户指定目录" / "models"
    assert layout.state == tmp_path / "用户指定目录" / "state"
```

- [ ] **Step 5: 运行两端测试**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests
python -m pytest desktop/tests/test_config.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add release launcher desktop
git commit -m "chore: define release manifest and cache layout"
```

---

### Task 2: 用户指定缓存根目录与二次自动加载

**Files:**
- Create: `launcher/src/DataTangQCTool.Launcher/Models/LauncherConfig.cs`
- Create: `launcher/src/DataTangQCTool.Launcher/Services/LauncherConfigStore.cs`
- Create: `launcher/src/DataTangQCTool.Launcher/Services/CacheRootSelector.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/LauncherConfigStoreTests.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/CacheRootSelectorTests.cs`

**Interfaces:**
- Produces: `LauncherConfigStore.LoadAsync() -> LauncherConfig?`
- Produces: `LauncherConfigStore.SaveAsync(LauncherConfig config) -> Task`
- Produces: `CacheRootSelector.ResolveAsync(LauncherConfig? saved) -> CacheRootResult`
- Config path: `%LOCALAPPDATA%\DataTangQCToolLauncher\launcher.json`

- [ ] **Step 1: 写首次无配置测试**

```csharp
[Fact]
public async Task Load_returns_null_when_pointer_file_does_not_exist()
{
    var store = new LauncherConfigStore(_temp.LocalAppData);
    Assert.Null(await store.LoadAsync());
}
```

- [ ] **Step 2: 写保存并重新加载测试**

```csharp
[Fact]
public async Task Save_then_load_restores_selected_cache_root()
{
    var store = new LauncherConfigStore(_temp.LocalAppData);
    var expected = new LauncherConfig(1, @"D:\DataTangCache", "stable");
    await store.SaveAsync(expected);

    var actual = await store.LoadAsync();

    Assert.Equal(expected.CacheRoot, actual!.CacheRoot);
}
```

- [ ] **Step 3: 验证测试失败**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests --filter LauncherConfigStore
```

Expected: FAIL，类型尚不存在。

- [ ] **Step 4: 实现原子配置写入**

配置格式：

```json
{
  "schema_version": 1,
  "cache_root": "D:\\DataTangQCToolCache",
  "channel": "stable"
}
```

写入流程必须是：

```text
launcher.json.tmp → Flush → File.Replace/Move → launcher.json
```

不得将缓存地址只写在启动器同目录，因为启动器可能被移动或重新下载。

- [ ] **Step 5: 实现目录选择与验证**

首次启动显示 Windows 文件夹选择器，选择后验证：

```csharp
public sealed record CacheRootValidation(
    bool IsValid,
    string ErrorMessage,
    long FreeBytes
);
```

验证规则：

- 必须是绝对路径。
- 必须可创建和删除测试文件。
- 可用空间不少于 2 GiB。
- 不允许选择项目业务数据四状态目录本身。
- 不允许选择启动器 ZIP 内部虚拟路径。
- 允许中文、空格和非系统盘路径。

- [ ] **Step 6: 写二次自动加载测试**

```csharp
[Fact]
public async Task Resolve_uses_saved_root_without_opening_picker_when_valid()
{
    var saved = new LauncherConfig(1, _temp.ValidCacheRoot, "stable");
    var picker = new FakeFolderPicker();
    var result = await _selector.ResolveAsync(saved);

    Assert.Equal(_temp.ValidCacheRoot, result.CacheRoot);
    Assert.Equal(0, picker.OpenCount);
}
```

- [ ] **Step 7: 写保存路径失效测试**

```csharp
[Fact]
public async Task Resolve_requests_reselection_when_saved_drive_is_unavailable()
{
    var saved = new LauncherConfig(1, @"Z:\Missing\DataTangCache", "stable");
    var result = await _selector.ResolveAsync(saved);

    Assert.Equal(CacheRootAction.ReselectRequired, result.Action);
}
```

界面必须提供“重试原地址”“重新选择”“退出”，不得自动切到 C 盘。

- [ ] **Step 8: 运行测试**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests --filter "LauncherConfigStore|CacheRootSelector"
```

Expected: 全部 PASS。

- [ ] **Step 9: Commit**

```bash
git add launcher
git commit -m "feat: persist user-selected cache root"
```

---

### Task 3: GitHub Release 清单获取与断点续传

**Files:**
- Create: `launcher/src/DataTangQCTool.Launcher/Services/ReleaseManifestClient.cs`
- Create: `launcher/src/DataTangQCTool.Launcher/Services/ResumableDownloadService.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/ReleaseManifestClientTests.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/ResumableDownloadServiceTests.cs`

**Interfaces:**
- Produces: `FetchAsync(Uri manifestUri, CancellationToken) -> ReleaseManifest`
- Produces: `DownloadAsync(DownloadRequest, IProgress<DownloadProgress>, CancellationToken) -> Path`

- [ ] **Step 1: 写断点请求测试**

```csharp
[Fact]
public async Task Download_sends_range_header_when_part_file_exists()
{
    await File.WriteAllBytesAsync(_partPath, new byte[1024]);
    await _service.DownloadAsync(_request, null, default);

    Assert.Equal("bytes=1024-", _server.LastRangeHeader);
}
```

- [ ] **Step 2: 写 SHA256 不匹配测试**

```csharp
[Fact]
public async Task Download_deletes_completed_file_when_sha256_mismatches()
{
    var request = _request with { Sha256 = new string('0', 64) };
    await Assert.ThrowsAsync<InvalidDataException>(
        () => _service.DownloadAsync(request, null, default)
    );
    Assert.False(File.Exists(request.FinalPath));
}
```

- [ ] **Step 3: 运行并确认失败**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests --filter ResumableDownload
```

- [ ] **Step 4: 实现下载协议**

- 仅允许固定 GitHub 仓库 Releases HTTPS 地址。
- 临时文件使用 `downloads/<asset>.part`。
- 已存在 `.part` 时发送 `Range`。
- 服务端不支持 Range 时清空后重下。
- 最多自动重试 3 次，退避 1、3、8 秒。
- 显示总大小、已下载、百分比和速度。
- 完成后先校验 SHA256，再原子改名。
- 清单获取失败但本地安装健康时允许离线启动。

- [ ] **Step 5: 运行测试**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests --filter "ReleaseManifestClient|ResumableDownload"
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add launcher
git commit -m "feat: add verified resumable GitHub downloads"
```

---

### Task 4: 运行库与主程序的原子安装、健康检查和修复

**Files:**
- Create: `launcher/src/DataTangQCTool.Launcher/Models/InstallState.cs`
- Create: `launcher/src/DataTangQCTool.Launcher/Services/PackageInstaller.cs`
- Create: `launcher/src/DataTangQCTool.Launcher/Services/RuntimeHealthChecker.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/PackageInstallerTests.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/RuntimeHealthCheckerTests.cs`

**Interfaces:**
- Produces: `InstallPackageAsync(zip, targetVersionDir, expectedFiles) -> Task`
- Produces: `CheckAsync(cacheRoot, InstallState) -> HealthReport`
- State file: `<cache_root>/state/active.json`

- [ ] **Step 1: 写禁止半安装版本生效测试**

```csharp
[Fact]
public async Task Failed_extract_does_not_change_active_version()
{
    await Assert.ThrowsAsync<InvalidDataException>(() =>
        _installer.InstallPackageAsync(_brokenZip, _target, _expectedFiles)
    );

    Assert.Equal("1.0.0", _stateStore.Load().RuntimeVersion);
}
```

- [ ] **Step 2: 写健康检查测试**

```csharp
[Fact]
public async Task Health_check_executes_embedded_python_and_imports_required_packages()
{
    var report = await _checker.CheckAsync(_cacheRoot, _state);
    Assert.True(report.RuntimeOk);
    Assert.True(report.AppOk);
}
```

实际命令：

```powershell
<cache>\runtime\<version>\python.exe -c "import PySide6, PIL, openpyxl, watchdog, send2trash; print('OK')"
```

- [ ] **Step 3: 实现版本目录和原子切换**

```text
runtime/
  1.0.0/
  1.1.0/
app/
  1.2.0/
state/
  active.json
```

先解压到 `<version>.staging`，验证完成后改名为正式版本，再更新 `active.json`。

- [ ] **Step 4: 实现损坏修复**

1. 保留日志。
2. 删除对应损坏版本，不删除其他可用版本。
3. 从 GitHub 重新下载相同版本。
4. 验证成功后重新启动。
5. 网络不可用且有上一健康版本时回滚。

- [ ] **Step 5: 运行测试**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests --filter "PackageInstaller|RuntimeHealthChecker"
```

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
git add launcher
git commit -m "feat: install and repair versioned runtime packages"
```

---

### Task 5: 启动协调器、启动器界面和单文件 EXE

**Files:**
- Create: `launcher/src/DataTangQCTool.Launcher/Services/StartupCoordinator.cs`
- Modify: `launcher/src/DataTangQCTool.Launcher/MainWindow.xaml`
- Modify: `launcher/src/DataTangQCTool.Launcher/MainWindow.xaml.cs`
- Test: `launcher/tests/DataTangQCTool.Launcher.Tests/StartupCoordinatorTests.cs`

**Interfaces:**
- Produces: `StartupCoordinator.RunAsync() -> StartupResult`
- Starts: `<runtime>\pythonw.exe <app>\app\main.py --cache-root "<selected>"`

- [ ] **Step 1: 写“本地健康时不联网”测试**

```csharp
[Fact]
public async Task Healthy_local_install_starts_without_fetching_manifest()
{
    _health.Report = HealthReport.Healthy;
    await _coordinator.RunAsync();

    Assert.Equal(0, _manifestClient.FetchCount);
    Assert.Equal(1, _processRunner.StartCount);
}
```

- [ ] **Step 2: 写“首次安装”顺序测试**

```csharp
[Fact]
public async Task First_run_selects_root_then_downloads_runtime_and_app()
{
    await _coordinator.RunAsync();

    Assert.Equal(
        new[] {"select-root", "save-root", "fetch-manifest", "runtime", "app", "start"},
        _events
    );
}
```

- [ ] **Step 3: 实现启动状态 UI**

```text
选择缓存位置
检查本地环境
获取版本信息
下载运行库
下载主程序
校验文件
安装
启动
```

必须显示进度、当前文件、速度、日志入口、“取消”和“重试”。

- [ ] **Step 4: 增加缓存位置管理**

启动器设置中显示：

- 当前缓存目录。
- 打开缓存目录。
- 更改缓存目录。

更改后将新地址写入 `launcher.json`；新目录没有运行库时在新目录重新下载，旧缓存不自动删除。

- [ ] **Step 5: 生成单文件 EXE**

```powershell
dotnet publish launcher/src/DataTangQCTool.Launcher `
  -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true `
  -p:IncludeNativeLibrariesForSelfExtract=true
```

- [ ] **Step 6: 运行测试**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests
```

Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add launcher
git commit -m "feat: add first-run installer launcher"
```

---

### Task 6: 项目目录扫描与数据组识别

**Files:**
- Create: `desktop/app/domain.py`
- Create: `desktop/app/services/project_scanner.py`
- Test: `desktop/tests/test_project_scanner.py`

**Interfaces:**
- Produces: `scan_project(root: Path, queue_statuses=("待质检", "待返修")) -> list[DataGroup]`
- `DataGroup` fields: status, person, group_id, directory, original_image, result_image, chn_txt, eng_txt, completeness

- [ ] **Step 1: 写目录扫描测试**

```python
def test_scans_pending_and_rework_queues(sample_project):
    groups = scan_project(sample_project)
    assert {(g.status, g.person, g.group_id) for g in groups} == {
        ("待质检", "张三", "000001"),
        ("待返修", "李四", "000002"),
    }
```

- [ ] **Step 2: 写文件匹配测试**

```python
def test_prefers_edit_clean_over_edit(group_dir):
    (group_dir / "000001_edit.jpg").touch()
    (group_dir / "000001_edit_clean.jpg").touch()
    group = parse_group(group_dir, "待质检", "张三")
    assert group.result_image.name == "000001_edit_clean.jpg"
```

- [ ] **Step 3: 实现格式兼容和完整性状态**

原图不得误选 `_edit`、`_edit_clean`；支持 `.jpg/.jpeg/.jfif/.png/.webp/.bmp/.tif/.tiff`。

- [ ] **Step 4: 运行测试**

```powershell
python -m pytest desktop/tests/test_project_scanner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add desktop
git commit -m "feat: scan personnel and data group folders"
```

---

### Task 7: 图片解码、颜色管理与缩放查看器

**Files:**
- Create: `desktop/app/services/image_service.py`
- Create: `desktop/app/ui/zoom_image_view.py`
- Test: `desktop/tests/test_image_service.py`
- Test: `desktop/tests/test_zoom_image_view.py`

**Interfaces:**
- Produces: `load_display_image(path: Path) -> DisplayImage`
- `DisplayImage`: qimage, width, height, detected_format, error
- Produces: `ZoomImageView.fit_to_view()`, `set_100_percent()`

- [ ] **Step 1: 写 CMYK/ICC 转换测试**

```python
def test_cmyk_jpeg_is_converted_to_srgb(cmyk_jpeg_with_icc):
    image = load_display_image(cmyk_jpeg_with_icc)
    assert image.error is None
    assert image.qimage.format() in {
        QImage.Format_RGB888,
        QImage.Format_RGBA8888,
    }
```

- [ ] **Step 2: 写 EXIF 方向测试**

```python
def test_applies_exif_orientation(rotated_jpeg):
    image = load_display_image(rotated_jpeg)
    assert (image.width, image.height) == (360, 640)
```

- [ ] **Step 3: 实现 Pillow 优先、Qt 兜底**

处理顺序：

1. `Image.open`
2. `ImageOps.exif_transpose`
3. `ImageCms.profileToProfile(..., sRGB)`
4. 转 RGB/RGBA
5. 转 QImage
6. Pillow 失败时尝试 QImageReader
7. 失败时返回明确错误

- [ ] **Step 4: 实现查看器行为**

- 首次加载自动适应。
- 窗口尺寸变化且仍处于 fit 模式时重新适应。
- 滚轮以鼠标位置为中心缩放。
- 左键拖动。
- 双击恢复自适应。
- `1:1` 设置真实像素。
- 顶部显示 `JPEG | 2048 × 2048 px`。

- [ ] **Step 5: 运行测试**

```powershell
python -m pytest desktop/tests/test_image_service.py desktop/tests/test_zoom_image_view.py -v
```

- [ ] **Step 6: Commit**

```bash
git add desktop
git commit -m "feat: add color-managed zoomable image viewer"
```

---

### Task 8: 中英文指令编辑与自动回写

**Files:**
- Create: `desktop/app/services/instruction_service.py`
- Test: `desktop/tests/test_instruction_service.py`

**Interfaces:**
- Produces: `read_text_preserving_encoding(path) -> TextDocument`
- Produces: `save_text_atomic(document, new_text) -> None`

- [ ] **Step 1: 写 GB18030 回写测试**

```python
def test_gb18030_file_is_saved_using_original_encoding(tmp_path):
    path = tmp_path / "000001_chn.txt"
    path.write_bytes("原指令".encode("gb18030"))
    doc = read_text_preserving_encoding(path)

    save_text_atomic(doc, "修改后的指令")

    assert path.read_bytes().decode("gb18030") == "修改后的指令"
```

- [ ] **Step 2: 写自动创建缺失文件测试**

```python
def test_missing_instruction_file_is_created_as_utf8(tmp_path):
    path = tmp_path / "000001_eng.txt"
    save_new_text(path, "new prompt")
    assert path.read_text(encoding="utf-8") == "new prompt"
```

- [ ] **Step 3: 实现 650ms 防抖保存**

切换数据、点击通过、不通过、删除和关闭窗口前调用 `flush_pending_saves()`。

- [ ] **Step 4: 运行测试**

```powershell
python -m pytest desktop/tests/test_instruction_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add desktop
git commit -m "feat: edit and autosave instruction files"
```

---

### Task 9: 质检通过、不通过、备注、删除与撤销

**Files:**
- Create: `desktop/app/services/qc_service.py`
- Create: `desktop/app/services/recycle_service.py`
- Create: `desktop/app/services/operation_log.py`
- Test: `desktop/tests/test_qc_service.py`
- Test: `desktop/tests/test_recycle_service.py`

**Interfaces:**
- Produces: `approve(group) -> OperationRecord`
- Produces: `reject(group, issues, note) -> OperationRecord`
- Produces: `delete_to_recycle_bin(group) -> OperationRecord`
- Produces: `undo(record) -> None`

- [ ] **Step 1: 写通过移动测试**

```python
def test_approve_moves_group_to_completed_person_folder(sample_group, project_root):
    record = approve(sample_group)
    expected = project_root / "质检完成" / sample_group.person / sample_group.group_id
    assert expected.exists()
    assert record.destination == expected
```

- [ ] **Step 2: 写不通过备注测试**

```python
def test_reject_appends_note_before_moving(sample_group):
    reject(sample_group, ["主体不一致"], "产品左侧结构变形")
    note = sample_group.target_rework_dir / "质检返修备注.txt"
    text = note.read_text(encoding="utf-8")
    assert "主体不一致" in text
    assert "产品左侧结构变形" in text
```

- [ ] **Step 3: 写冲突禁止覆盖测试**

```python
def test_approve_refuses_to_overwrite_existing_target(sample_group):
    sample_group.completed_target.mkdir(parents=True)
    with pytest.raises(TargetConflictError):
        approve(sample_group)
```

- [ ] **Step 4: 写回收站删除测试**

使用 `send2trash`，删除前 UI 必须二次确认并要求输入组编号。

- [ ] **Step 5: 写撤销移动测试**

```python
def test_undo_restores_moved_group(operation_record):
    undo(operation_record)
    assert operation_record.source.exists()
    assert not operation_record.destination.exists()
```

- [ ] **Step 6: 运行测试**

```powershell
python -m pytest desktop/tests/test_qc_service.py desktop/tests/test_recycle_service.py -v
```

- [ ] **Step 7: Commit**

```bash
git add desktop
git commit -m "feat: implement qc actions and safe deletion"
```

---

### Task 10: 实时目录监控与稳定队列刷新

**Files:**
- Create: `desktop/app/services/watcher_service.py`
- Test: `desktop/tests/test_watcher_service.py`

**Interfaces:**
- Produces: `ProjectWatcher.start(root, callback)`
- Produces: `ProjectWatcher.stop()`

- [ ] **Step 1: 写新增组刷新测试**

```python
def test_new_group_emits_single_refresh_event(project_watcher, pending_dir):
    create_complete_group(pending_dir / "张三" / "000003")
    events = project_watcher.wait_for_events()
    assert events.count("refresh") == 1
```

- [ ] **Step 2: 实现 Watchdog + 3 秒兜底扫描**

- Watchdog 事件合并防抖 500ms。
- 每 3 秒计算目录签名兜底。
- 目录签名未变化时不重建当前 UI。
- 当前组文件改变时只重新加载该组。
- 正在复制且文件大小持续变化的数据标记为“复制中”，暂不允许通过。

- [ ] **Step 3: 运行测试**

```powershell
python -m pytest desktop/tests/test_watcher_service.py -v
```

- [ ] **Step 4: Commit**

```bash
git add desktop
git commit -m "feat: add stable realtime project monitoring"
```

---

### Task 11: Excel 日报与当日操作恢复

**Files:**
- Create: `desktop/app/services/report_service.py`
- Test: `desktop/tests/test_report_service.py`

**Interfaces:**
- Produces: `build_daily_report(project_root, operation_log, output_path) -> Path`

- [ ] **Step 1: 写人员汇总测试**

```python
def test_total_equals_four_status_counts(sample_project):
    report = collect_summary(sample_project)
    row = report.people["张三"]
    assert row.total == (
        row.completed + row.rework + row.pending + row.rework_submitted
    )
```

- [ ] **Step 2: 写问题统计测试**

```python
def test_rejected_issue_counts_ignore_undone_records(operation_log):
    operation_log.append(reject_record("细节丢失"))
    operation_log.append(undo_record_for_last())
    summary = collect_issue_summary(operation_log)
    assert "细节丢失" not in summary
```

- [ ] **Step 3: 实现三个工作表**

- `人员汇总`
- `不通过明细`
- `总体汇总`

输出文件名：

```text
质检统计_YYYY-MM-DD_HHMMSS.xlsx
```

- [ ] **Step 4: 运行测试**

```powershell
python -m pytest desktop/tests/test_report_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add desktop
git commit -m "feat: export daily qc workbook"
```

---

### Task 12: Hugging Face 可选模型管理器

**Files:**
- Create: `desktop/app/services/model_manager.py`
- Create: `desktop/app/ui/model_download_dialog.py`
- Test: `desktop/tests/test_model_manager.py`

**Interfaces:**
- Produces: `ModelManager(cache_root).install(model_spec, progress)`
- Produces: `ModelManager.is_installed(model_id) -> bool`
- Model root: `<selected_cache_root>/models`

- [ ] **Step 1: 写基础功能不触发模型下载测试**

```python
def test_app_start_does_not_contact_huggingface(http_spy):
    start_core_services(ai_enabled=False)
    assert http_spy.requests_to("huggingface.co") == 0
```

- [ ] **Step 2: 写模型缓存位置测试**

```python
def test_model_download_uses_selected_cache_root(tmp_path):
    manager = ModelManager(tmp_path / "用户缓存")
    assert manager.model_root == tmp_path / "用户缓存" / "models"
```

- [ ] **Step 3: 实现显式下载流程**

设置页提供：

- 模型名称和用途。
- 预计大小。
- 下载进度。
- 暂停/取消。
- 删除模型。
- 自定义 Hugging Face Endpoint。
- 下载失败不修改基础配置。

初始模型只配置 `facebook/dinov2-small` 作为可选视觉相似度提示，不自动判定通过或不通过。

- [ ] **Step 4: 运行测试**

```powershell
python -m pytest desktop/tests/test_model_manager.py -v
```

- [ ] **Step 5: Commit**

```bash
git add desktop
git commit -m "feat: add optional Hugging Face model downloads"
```

---

### Task 13: 桌面主界面整合

**Files:**
- Create: `desktop/app/ui/main_window.py`
- Create: `desktop/app/main.py`
- Test: `desktop/tests/test_main_window.py`

**Interfaces:**
- Consumes: Tasks 6–12 services
- Produces: complete PySide6 desktop workflow

- [ ] **Step 1: 写队列选择测试**

```python
def test_selecting_group_loads_images_and_instructions(qtbot, window, group):
    window.select_group(group)
    assert window.current_group == group
    assert "×" in window.original_meta.text()
    assert window.chn_editor.toPlainText() == group.chn_text
```

- [ ] **Step 2: 实现三栏布局**

- 左栏：状态筛选、人员、组编号、完整性、刷新状态。
- 中栏：原图和结果图双视图。
- 右栏：中文指令、英文指令、主要问题、返修备注。
- 底栏：上一组、下一组、通过、不通过、删除、撤销、结束质检、设置。

- [ ] **Step 3: 增加缓存设置入口**

从主程序打开“缓存设置”时展示启动器保存的实际缓存根目录；点击更改调用启动器：

```text
DataTangQCTool.Launcher.exe --change-cache-root
```

变更后提示重启主程序。

- [ ] **Step 4: 运行 UI 测试**

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest desktop/tests/test_main_window.py -v
```

- [ ] **Step 5: Commit**

```bash
git add desktop
git commit -m "feat: integrate complete qc desktop interface"
```

---

### Task 14: Windows 运行库、主程序包与 GitHub Actions 发布

**Files:**
- Create: `scripts/build_runtime.ps1`
- Create: `scripts/build_app_package.ps1`
- Create: `scripts/build_launcher.ps1`
- Create: `.github/workflows/build-runtime.yml`
- Create: `.github/workflows/build-app.yml`
- Create: `.github/workflows/release-stable.yml`
- Create: `docs/release-process.md`

**Interfaces:**
- Produces release assets:
  - `DataTangQCTool-Launcher.exe`
  - `runtime-win-x64-<version>.zip`
  - `app-<version>.zip`
  - `stable-manifest.json`
  - `SHA256SUMS.txt`

- [ ] **Step 1: 固定运行库依赖**

`runtime-requirements.lock` 必须固定精确版本，不允许 `>=`：

```text
PySide6==<已验证版本>
Pillow==<已验证版本>
openpyxl==<已验证版本>
watchdog==<已验证版本>
send2trash==<已验证版本>
huggingface-hub==<已验证版本>
```

Transformers 放在可选模型扩展包中，避免增加首次运行库下载体积。

- [ ] **Step 2: 构建 runtime ZIP**

运行库中必须包含：

```text
python.exe
pythonw.exe
python311.dll
Lib/
site-packages/
licenses/
runtime-version.json
```

- [ ] **Step 3: 构建 app ZIP**

主程序包只包含 `desktop/app`、资源和版本信息，不包含用户数据。

- [ ] **Step 4: GitHub Actions 生成 SHA256 和清单**

Windows runner 执行：

1. 构建。
2. 运行 launcher tests。
3. 运行 desktop tests。
4. 创建 ZIP。
5. 计算 SHA256。
6. 生成 manifest。
7. 上传 Release assets。

- [ ] **Step 5: Commit**

```bash
git add scripts .github release docs
git commit -m "ci: build verified Windows runtime releases"
```

---

### Task 15: 端到端 Windows 验收与发布门禁

**Files:**
- Create: `tests/e2e/first_run.ps1`
- Create: `tests/e2e/offline_second_run.ps1`
- Create: `tests/e2e/cache_reselection.ps1`
- Create: `docs/troubleshooting.md`

**Interfaces:**
- Verifies complete launcher → runtime → desktop flow

- [ ] **Step 1: 首次运行测试**

在全新 Windows 11 沙箱中：

- 删除 `%LOCALAPPDATA%\DataTangQCToolLauncher`。
- 启动 EXE。
- 选择含中文和空格的 `D:\测试 缓存\DataTang`。
- 完成下载和安装。
- 验证程序启动。
- 验证 `launcher.json` 保存了该路径。

- [ ] **Step 2: 二次离线启动测试**

断开网络，再次启动：

- 不显示文件夹选择器。
- 自动读取之前保存的缓存地址。
- 不请求 GitHub 或 Hugging Face。
- 5 秒内进入主界面。

- [ ] **Step 3: 缓存盘不可用测试**

把保存地址改为不存在的盘符，验证显示：

```text
上次缓存目录不可访问
[重试原地址] [重新选择] [退出]
```

- [ ] **Step 4: 业务完整链路测试**

创建样例项目并验证：

1. 同时读取待质检和待返修。
2. 显示图片、格式、像素和颜色。
3. 修改中英文指令并写回。
4. 通过移动。
5. 不通过写备注并移动。
6. 删除到回收站。
7. 撤销移动。
8. 导出 Excel。
9. 重启后继续读取目录和当日日志。

- [ ] **Step 5: AI 可选模型测试**

- 未下载模型时基础功能正常。
- 模型下载失败时基础功能正常。
- 模型安装后缓存到用户指定根目录下的 `models/`。

- [ ] **Step 6: 发布门禁**

```powershell
dotnet test launcher/tests/DataTangQCTool.Launcher.Tests
python -m pytest desktop/tests -v
powershell -ExecutionPolicy Bypass -File tests/e2e/first_run.ps1
powershell -ExecutionPolicy Bypass -File tests/e2e/offline_second_run.ps1
powershell -ExecutionPolicy Bypass -File tests/e2e/cache_reselection.ps1
```

Expected: 零失败后才允许生成正式 Release。

- [ ] **Step 7: Commit**

```bash
git add tests docs
git commit -m "test: add Windows first-run and offline acceptance gates"
```

---

## Requirement Coverage Review

| 用户需求 | 对应任务 |
|---|---|
| GitHub 下载运行库 | Task 3、4、14 |
| 首次联网、以后本地运行 | Task 5、15 |
| 缓存目录由用户指定 | Task 2 |
| 二次自动加载保存地址 | Task 2、5、15 |
| Hugging Face 可选模型 | Task 12 |
| 同时读取待质检和待返修 | Task 6、10 |
| 图片完整显示、色彩、像素、格式、缩放 | Task 7 |
| 指令编辑自动回写 | Task 8 |
| 通过、不通过、备注、删除、撤销 | Task 9 |
| 实时更新 | Task 10 |
| Excel 日报 | Task 11 |
| 完整桌面界面 | Task 13 |
| Windows 正式发布 | Task 14、15 |

## Implementation Order

```text
Task 1 → Task 2 → Task 3 → Task 4 → Task 5
      → Task 6 → Task 7 → Task 8 → Task 9
      → Task 10 → Task 11 → Task 12 → Task 13
      → Task 14 → Task 15
```

第一阶段交付物是可选择并记住缓存目录、可下载并启动空白主程序的启动器。  
第二阶段交付物是完整本地质检业务。  
第三阶段交付物是可选模型和 GitHub 自动发布。  
最终发布必须经过全新 Windows 首次联网安装与断网二次启动验收。
