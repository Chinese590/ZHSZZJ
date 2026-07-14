using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class StartupCoordinatorTests
{
    [Fact]
    public async Task Healthy_local_install_starts_without_fetching_manifest()
    {
        using var temp = new TempDirectory();
        var configStore = new LauncherConfigStore(temp.Combine("localapp"));
        var cacheRoot = temp.Combine("cache");
        await configStore.SaveAsync(new LauncherConfig(1, cacheRoot, "stable"));
        var stateStore = new InstallStateStore(CacheLayout.FromRoot(cacheRoot).State);
        await stateStore.SaveAsync(new InstallState(1, "1.0.0", "1.0.0", "app/main.py"));
        var health = new FakeHealthChecker { Report = HealthReport.Healthy() };
        var manifest = new FakeManifestClient();
        var launcher = new FakeApplicationLauncher();
        var coordinator = new StartupCoordinator(
            configStore,
            new CacheRootSelector(new FakeFolderPicker(), new FakeCacheRootValidator()),
            manifest,
            new FakeDownloadService(),
            new FakePackageInstaller(),
            health,
            launcher,
            NullStartupProgress.Instance);

        var result = await coordinator.RunAsync(CancellationToken.None);

        Assert.Equal(StartupOutcome.Started, result.Outcome);
        Assert.Equal(0, manifest.FetchCount);
        Assert.Equal(1, launcher.StartCount);
    }

    [Fact]
    public async Task Missing_saved_cache_returns_reselection_required_without_silent_fallback()
    {
        using var temp = new TempDirectory();
        var configStore = new LauncherConfigStore(temp.Combine("localapp"));
        await configStore.SaveAsync(new LauncherConfig(1, @"Z:\Missing", "stable"));
        var validator = new FakeCacheRootValidator { Result = CacheRootValidation.Invalid("不可访问") };
        var coordinator = new StartupCoordinator(
            configStore,
            new CacheRootSelector(new FakeFolderPicker(), validator),
            new FakeManifestClient(),
            new FakeDownloadService(),
            new FakePackageInstaller(),
            new FakeHealthChecker(),
            new FakeApplicationLauncher(),
            NullStartupProgress.Instance);

        var result = await coordinator.RunAsync(CancellationToken.None);

        Assert.Equal(StartupOutcome.CacheRootUnavailable, result.Outcome);
    }
}
