from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from pygments import lex
from pygments.lexers.dotnet import CSharpLexer
from pygments.token import Comment, String

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "launcher" / "src" / "DataTangQCTool.Launcher"
TESTS = ROOT / "launcher" / "tests" / "DataTangQCTool.Launcher.Tests"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_required_phase1_files_exist():
    required = [
        LAUNCHER / "DataTangQCTool.Launcher.csproj",
        LAUNCHER / "App.xaml",
        LAUNCHER / "App.xaml.cs",
        LAUNCHER / "MainWindow.xaml",
        LAUNCHER / "MainWindow.xaml.cs",
        LAUNCHER / "Models" / "LauncherConfig.cs",
        LAUNCHER / "Models" / "ReleaseManifest.cs",
        LAUNCHER / "Services" / "LauncherConfigStore.cs",
        LAUNCHER / "Services" / "CacheRootSelector.cs",
        LAUNCHER / "Services" / "ResumableDownloadService.cs",
        LAUNCHER / "Services" / "PackageInstaller.cs",
        LAUNCHER / "Services" / "StartupCoordinator.cs",
        ROOT / ".github" / "workflows" / "release-stable.yml",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, missing


def test_project_is_self_contained_single_file_wpf_and_embeds_settings():
    project = ET.parse(LAUNCHER / "DataTangQCTool.Launcher.csproj").getroot()
    values = {node.tag: (node.text or "").strip() for node in project.iter()}
    assert values["TargetFramework"] == "net8.0-windows"
    assert values["UseWPF"] == "true"
    assert values["SelfContained"] == "true"
    assert values["PublishSingleFile"] == "true"
    assert any(node.tag == "EmbeddedResource" and node.attrib.get("Include") == "launcher.settings.json" for node in project.iter())


def test_xaml_files_are_well_formed_xml():
    ET.parse(LAUNCHER / "App.xaml")
    ET.parse(LAUNCHER / "MainWindow.xaml")


def test_launcher_config_pointer_is_outside_selected_cache_and_is_atomic():
    source = read(LAUNCHER / "Services" / "LauncherConfigStore.cs")
    assert '"DataTangQCToolLauncher"' in source
    assert '"launcher.json"' in source
    assert 'ConfigPath + ".tmp"' in source
    assert "Flush(flushToDisk: true)" in source
    assert "File.Replace" in source


def test_cache_selector_uses_saved_root_and_never_silently_changes_drive():
    source = read(LAUNCHER / "Services" / "CacheRootSelector.cs")
    assert "CacheRootAction.UseSaved" in source
    assert "CacheRootAction.ReselectRequired" in source
    resolve_body = source.split("ResolveAsync", 1)[1].split("SelectNewAsync", 1)[0]
    assert "PickFolderAsync" not in resolve_body


def test_download_service_has_range_resume_sha_and_part_file():
    source = read(LAUNCHER / "Services" / "ResumableDownloadService.cs")
    assert 'request.FinalPath + ".part"' in source
    assert "RangeHeaderValue" in source
    assert "SHA256.HashDataAsync" in source
    assert "File.Move(partPath, request.FinalPath, overwrite: true)" in source
    assert "ReleaseUrlPolicy" in source


def test_startup_checks_updates_and_falls_back_to_healthy_local_install_offline():
    source = read(LAUNCHER / "Services" / "StartupCoordinator.cs")
    assert '"检查 GitHub 更新……"' in source
    assert "manifest = await _manifestClient.FetchAsync" in source
    assert "if (manifest is null)" in source
    assert "if (localIsHealthy)" in source
    assert '"已离线启动本地版本。"' in source
    assert "if (localIsHealthy && !IsUpdateRequired(state!, manifest))" in source
    assert "IsRemoteNewer" in source


def test_workflow_builds_on_windows_tests_and_releases_all_assets():
    path = ROOT / ".github" / "workflows" / "release-stable.yml"
    data = yaml.safe_load(read(path))
    assert data["jobs"]["build-release"]["runs-on"] == "windows-latest"
    text = read(path)
    assert "actions/setup-dotnet@v4" in text
    assert "dotnet test" in text
    for asset in [
        "runtime-win-x64.zip",
        "app.zip",
        "stable-manifest.json",
        "SHA256SUMS.txt",
        "DataTangQCTool-Launcher.exe",
    ]:
        assert asset in text


def test_manifest_schema_and_template_are_valid_json():
    schema = json.loads(read(ROOT / "release" / "manifests" / "runtime-manifest.schema.json"))
    settings = json.loads(read(LAUNCHER / "launcher.settings.json"))
    assert schema["properties"]["schema_version"]["const"] == 1
    assert settings["manifest_url"].startswith("https://github.com/")
    assert settings["allowed_release_prefix"].endswith("/releases/download/")


def test_csharp_delimiters_are_balanced_outside_strings_and_comments():
    failures: list[str] = []
    for path in sorted((ROOT / "launcher").rglob("*.cs")):
        code = read(path)
        visible = []
        for token_type, value in lex(code, CSharpLexer()):
            if token_type in Comment or token_type in String:
                visible.append(" " * len(value))
            else:
                visible.append(value)
        cleaned = "".join(visible)
        for opening, closing in [("{", "}"), ("[", "]")]:
            balance = 0
            for char in cleaned:
                if char == opening:
                    balance += 1
                elif char == closing:
                    balance -= 1
                if balance < 0:
                    failures.append(f"{path.relative_to(ROOT)} closes {closing} before {opening}")
                    break
            if balance != 0:
                failures.append(f"{path.relative_to(ROOT)} has unbalanced {opening}{closing}: {balance}")
    assert not failures, failures


def test_xunit_tests_cover_phase1_contracts():
    combined = "\n".join(read(path) for path in TESTS.glob("*Tests.cs"))
    expected = [
        "Save_then_load_restores_selected_cache_root",
        "Resolve_uses_saved_root_without_opening_picker_when_valid",
        "Resolve_requests_reselection_when_saved_drive_is_unavailable",
        "Download_sends_range_header_when_part_file_exists",
        "Download_deletes_part_file_when_sha256_mismatches",
        "Install_rejects_zip_path_traversal",
        "Healthy_local_install_checks_manifest_and_starts_when_current",
        "Healthy_local_install_updates_when_manifest_is_newer",
        "Healthy_local_install_starts_offline_when_manifest_fetch_fails",
        "Health_check_executes_embedded_python_and_imports_required_packages",
        "Start_rejects_non_python_entrypoint_before_spawning_process",
    ]
    for name in expected:
        assert name in combined


def test_production_app_package_is_used_and_queue_matches_latest_requirement():
    build_script = read(ROOT / "scripts" / "build_app_package.ps1")
    scanner = read(ROOT / "desktop" / "production" / "app" / "scanner.py")
    window = read(ROOT / "desktop" / "production" / "app" / "ui" / "main_window.py")
    assert '"desktop\\production"' in build_script
    assert 'QUEUE_FOLDERS = ("待质检", "待返修")' in scanner
    assert "队列来源：待质检 + 待返修" in window


def test_release_workflow_runs_full_desktop_test_suite_with_packaged_runtime():
    workflow = read(ROOT / ".github" / "workflows" / "release-stable.yml")
    assert "PYTHONPATH" not in workflow
    assert "sys.path.insert(0, " in workflow
    assert 'pytest.main([\"tests/static\", \"desktop/tests\", \"-v\"])' in workflow
    assert "QT_QPA_PLATFORM = 'offscreen'" in workflow


def test_optional_huggingface_model_is_cached_under_selected_root_and_never_required_for_startup():
    manager = read(ROOT / "desktop" / "production" / "app" / "model_manager.py")
    app_main = read(ROOT / "desktop" / "production" / "app" / "main.py")
    requirements = read(ROOT / "release" / "requirements" / "runtime-requirements.lock")
    assert 'self.models_root = self.cache_root / "models"' in manager
    assert 'model_id="onnx-community/dinov2-small"' in manager
    assert "snapshot_download" in manager
    assert "--cache-root" in app_main
    assert "huggingface-hub==" in requirements
    assert "onnxruntime==" in requirements


def test_main_window_exposes_model_download_and_advisory_compare_only():
    source = read(ROOT / "desktop" / "production" / "app" / "ui" / "main_window.py")
    assert 'QPushButton("AI辅助模型")' in source
    assert 'QPushButton("AI辅助比较")' in source
    assert "仅供人工参考" in source
    assert "pass_group" not in source[source.index("def run_ai_compare"):source.index("def open_model_dialog")]


def test_application_launcher_executes_absolute_script_after_validating_entrypoint():
    source = read(LAUNCHER / "Services" / "ProcessServices.cs")
    assert 'var normalizedEntrypoint = state.AppEntrypoint.Replace' in source
    assert 'EndsWith(".py", StringComparison.OrdinalIgnoreCase)' in source
    assert 'startInfo.ArgumentList.Add(entrypoint)' in source
    assert 'startInfo.ArgumentList.Add("--cache-root")' in source
    assert 'startInfo.ArgumentList.Add(layout.Root)' in source
    assert 'Arguments = $"-m ' not in source


def test_app_entrypoint_bootstraps_package_root_for_embedded_python():
    source = read(ROOT / "desktop" / "production" / "app" / "main.py")
    assert "APP_ROOT = Path(__file__).resolve().parents[1]" in source
    assert "sys.path.insert(0, str(APP_ROOT))" in source
    assert source.index("sys.path.insert(0, str(APP_ROOT))") < source.index("from app.startup")


def test_runtime_health_check_covers_core_and_optional_model_dependencies():
    source = read(LAUNCHER / "Services" / "RuntimeHealthChecker.cs")
    for module in [
        "PySide6",
        "PIL",
        "openpyxl",
        "watchdog",
        "send2trash",
        "huggingface_hub",
        "onnxruntime",
        "numpy",
    ]:
        assert module in source


def test_optional_ai_uses_onnx_stack_without_torch_or_transformers():
    requirements = read(ROOT / "desktop" / "requirements-ai.txt")
    assert "huggingface-hub" in requirements
    assert "onnxruntime" in requirements
    assert "numpy" in requirements
    assert "torch" not in requirements.lower()
    assert "transformers" not in requirements.lower()


def test_main_window_prevents_close_while_ai_worker_is_running():
    source = read(ROOT / "desktop" / "production" / "app" / "ui" / "main_window.py")
    close_body = source[source.index("def closeEvent"):]
    assert "self._ai_thread is not None" in close_body
    assert "event.ignore()" in close_body


def test_qapplication_does_not_receive_launcher_only_cache_argument():
    source = read(ROOT / "desktop" / "production" / "app" / "main.py")
    assert "QApplication([sys.argv[0]])" in source


def test_readme_describes_full_product_instead_of_phase_one_only():
    readme = read(ROOT / "README.md")
    assert "第一阶段启动器实现" not in readme
    assert "待质检" in readme and "待返修" in readme
    assert "Hugging Face" in readme


def test_active_install_pointer_is_saved_only_after_new_version_health_check():
    source = read(LAUNCHER / "Services" / "StartupCoordinator.cs")
    check_index = source.index("_healthChecker.CheckAsync(layout, nextState")
    healthy_index = source.index("if (!health.IsHealthy)", check_index)
    save_index = source.index("stateStore.SaveAsync(nextState", healthy_index)
    start_index = source.index("_applicationLauncher.StartAsync(layout, nextState", save_index)
    assert check_index < healthy_index < save_index < start_index


def test_model_download_dialog_uses_determinate_progress_and_detail_text():
    source = (ROOT / "desktop/production/app/ui/model_download_dialog.py").read_text(encoding="utf-8")
    assert "progress_changed = QtCore.Signal(object)" in source
    assert "progress_callback=self.progress_changed.emit" in source
    assert "self.progress.setRange(0, 1000)" in source
    assert "self.progress_detail_label" in source
    assert "self.progress.setRange(0, 0)" not in source


def test_model_manager_reports_byte_progress():
    source = (ROOT / "desktop/production/app/model_manager.py").read_text(encoding="utf-8")
    assert "class ModelDownloadProgress" in source
    assert "progress_callback" in source
    assert "list_repo_tree" in source
    assert "hf_hub_download" in source
    assert '"tqdm_class": progress_class' in source
