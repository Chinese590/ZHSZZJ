using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class ApplicationLauncherTests
{
    [Fact]
    public async Task Start_rejects_non_python_entrypoint_before_spawning_process()
    {
        using var temp = new TempDirectory();
        var layout = CacheLayout.FromRoot(temp.Combine("缓存"));
        layout.EnsureDirectories();
        var state = new InstallState(1, "1.0.0", "2.0.0", "app/main.txt");
        var runtimeDirectory = Path.Combine(layout.Runtime, state.RuntimeVersion);
        var appDirectory = Path.Combine(layout.App, state.AppVersion, "app");
        Directory.CreateDirectory(runtimeDirectory);
        Directory.CreateDirectory(appDirectory);
        File.WriteAllText(Path.Combine(runtimeDirectory, "pythonw.exe"), "fixture");
        File.WriteAllText(Path.Combine(appDirectory, "main.txt"), "fixture");

        await Assert.ThrowsAsync<InvalidDataException>(
            () => new ApplicationLauncher().StartAsync(layout, state, CancellationToken.None));
    }
}
