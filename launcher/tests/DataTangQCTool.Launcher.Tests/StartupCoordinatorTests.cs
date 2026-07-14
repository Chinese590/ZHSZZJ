using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class StartupCoordinatorTests
{
    [Fact]
    public async Task Healthy_local_install_checks_manifest_and_starts_when_current()
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
        Assert.Equal(1, manifest.FetchCount);
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

    [Fact]
    public async Task Healthy_local_install_updates_when_manifest_is_newer()
    {
        using var temp = new TempDirectory();
        var configStore = new LauncherConfigStore(temp.Combine("localapp"));
        var cacheRoot = temp.Combine("cache");
        await configStore.SaveAsync(new LauncherConfig(1, cacheRoot, "stable"));
        var layout = CacheLayout.FromRoot(cacheRoot);
        var stateStore = new InstallStateStore(layout.State);
        await stateStore.SaveAsync(new InstallState(1, "1.0.5", "1.0.5", "app/main.py"));
        var health = new FakeHealthChecker { Report = HealthReport.Healthy() };
        var manifest = new FakeManifestClient { Manifest = ManifestFor("1.0.6") };
        var download = new FakeDownloadService();
        var installer = new FakePackageInstaller();
        var launcher = new FakeApplicationLauncher();
        var coordinator = new StartupCoordinator(
            configStore,
            new CacheRootSelector(new FakeFolderPicker(), new FakeCacheRootValidator()),
            manifest,
            download,
            installer,
            health,
            launcher,
            NullStartupProgress.Instance);

        var result = await coordinator.RunAsync(CancellationToken.None);
        var active = await stateStore.LoadAsync();

        Assert.Equal(StartupOutcome.Started, result.Outcome);
        Assert.Equal(1, manifest.FetchCount);
        Assert.Equal(2, download.DownloadCount);
        Assert.Equal(2, installer.InstallCount);
        Assert.Equal("1.0.6", active!.RuntimeVersion);
        Assert.Equal("1.0.6", active.AppVersion);
        Assert.Equal(1, launcher.StartCount);
    }

    [Fact]
    public async Task Healthy_local_install_starts_offline_when_manifest_fetch_fails()
    {
        using var temp = new TempDirectory();
        var configStore = new LauncherConfigStore(temp.Combine("localapp"));
        var cacheRoot = temp.Combine("cache");
        await configStore.SaveAsync(new LauncherConfig(1, cacheRoot, "stable"));
        var stateStore = new InstallStateStore(CacheLayout.FromRoot(cacheRoot).State);
        await stateStore.SaveAsync(new InstallState(1, "1.0.5", "1.0.5", "app/main.py"));
        var launcher = new FakeApplicationLauncher();
        var coordinator = new StartupCoordinator(
            configStore,
            new CacheRootSelector(new FakeFolderPicker(), new FakeCacheRootValidator()),
            new FailingManifestClient(),
            new FakeDownloadService(),
            new FakePackageInstaller(),
            new FakeHealthChecker { Report = HealthReport.Healthy() },
            launcher,
            NullStartupProgress.Instance);

        var result = await coordinator.RunAsync(CancellationToken.None);

        Assert.Equal(StartupOutcome.Started, result.Outcome);
        Assert.Equal(1, launcher.StartCount);
    }

    private static ReleaseManifest ManifestFor(string version) => ReleaseManifest.Parse(
        $$"""
        {
          "schema_version": 1,
          "channel": "stable",
          "runtime": {
            "version": "{{version}}",
            "url": "https://github.com/example/repo/releases/download/v{{version}}/runtime.zip",
            "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "size": 1
          },
          "app": {
            "version": "{{version}}",
            "url": "https://github.com/example/repo/releases/download/v{{version}}/app.zip",
            "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "size": 1,
            "entrypoint": "app/main.py"
          }
        }
        """);

    private sealed class FailingManifestClient : IReleaseManifestClient
    {
        public Task<ReleaseManifest> FetchAsync(CancellationToken cancellationToken) =>
            throw new InvalidOperationException("offline");
    }

}
