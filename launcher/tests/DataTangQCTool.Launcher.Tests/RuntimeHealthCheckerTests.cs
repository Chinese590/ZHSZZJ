using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class RuntimeHealthCheckerTests
{
    [Fact]
    public async Task Health_check_executes_embedded_python_and_imports_required_packages()
    {
        using var temp = new TempDirectory();
        var layout = CacheLayout.FromRoot(temp.Combine("缓存"));
        layout.EnsureDirectories();
        var state = new InstallState(1, "1.0.0", "2.0.0", "app/main.py");
        var runtimeDirectory = Path.Combine(layout.Runtime, state.RuntimeVersion);
        var appDirectory = Path.Combine(layout.App, state.AppVersion, "app");
        Directory.CreateDirectory(runtimeDirectory);
        Directory.CreateDirectory(appDirectory);
        File.WriteAllText(Path.Combine(runtimeDirectory, "python.exe"), "fixture");
        File.WriteAllText(Path.Combine(runtimeDirectory, "pythonw.exe"), "fixture");
        File.WriteAllText(Path.Combine(appDirectory, "main.py"), "fixture");
        var runner = new FakeProcessRunner
        {
            Result = new ProcessResult(0, "OK\n", string.Empty)
        };
        var checker = new RuntimeHealthChecker(runner);

        var report = await checker.CheckAsync(layout, state, CancellationToken.None);

        Assert.True(report.IsHealthy);
        Assert.Contains("huggingface_hub", runner.LastArguments);
        Assert.Contains("onnxruntime", runner.LastArguments);
        Assert.Contains("numpy", runner.LastArguments);
    }

    [Fact]
    public async Task Health_check_reports_failed_dependency_import()
    {
        using var temp = new TempDirectory();
        var layout = CacheLayout.FromRoot(temp.Combine("缓存"));
        layout.EnsureDirectories();
        var state = new InstallState(1, "1.0.0", "2.0.0", "app/main.py");
        var runtimeDirectory = Path.Combine(layout.Runtime, state.RuntimeVersion);
        var appDirectory = Path.Combine(layout.App, state.AppVersion, "app");
        Directory.CreateDirectory(runtimeDirectory);
        Directory.CreateDirectory(appDirectory);
        File.WriteAllText(Path.Combine(runtimeDirectory, "python.exe"), "fixture");
        File.WriteAllText(Path.Combine(runtimeDirectory, "pythonw.exe"), "fixture");
        File.WriteAllText(Path.Combine(appDirectory, "main.py"), "fixture");
        var runner = new FakeProcessRunner
        {
            Result = new ProcessResult(1, string.Empty, "missing module")
        };
        var checker = new RuntimeHealthChecker(runner);

        var report = await checker.CheckAsync(layout, state, CancellationToken.None);

        Assert.False(report.IsHealthy);
        Assert.Contains("missing module", report.ErrorMessage);
    }
}
