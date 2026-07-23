using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Services;

public sealed class StartupCoordinator
{
    private readonly LauncherConfigStore _configStore;
    private readonly CacheRootSelector _cacheRootSelector;
    private readonly IReleaseManifestClient _manifestClient;
    private readonly IResumableDownloadService _downloadService;
    private readonly IPackageInstaller _packageInstaller;
    private readonly IRuntimeHealthChecker _healthChecker;
    private readonly IApplicationLauncher _applicationLauncher;
    private readonly IStartupProgress _progress;
    private readonly IUpdatePrompt _updatePrompt;

    public StartupCoordinator(
        LauncherConfigStore configStore,
        CacheRootSelector cacheRootSelector,
        IReleaseManifestClient manifestClient,
        IResumableDownloadService downloadService,
        IPackageInstaller packageInstaller,
        IRuntimeHealthChecker healthChecker,
        IApplicationLauncher applicationLauncher,
        IStartupProgress progress,
        IUpdatePrompt? updatePrompt = null)
    {
        _configStore = configStore;
        _cacheRootSelector = cacheRootSelector;
        _manifestClient = manifestClient;
        _downloadService = downloadService;
        _packageInstaller = packageInstaller;
        _healthChecker = healthChecker;
        _applicationLauncher = applicationLauncher;
        _progress = progress;
        _updatePrompt = updatePrompt ?? AlwaysAcceptUpdatePrompt.Instance;
    }

    public async Task<StartupResult> RunAsync(CancellationToken cancellationToken)
    {
        try
        {
            _progress.Report(new StartupProgress(StartupStage.SelectingCache, "读取缓存位置……"));
            var saved = await _configStore.LoadAsync(cancellationToken);
            var resolved = await _cacheRootSelector.ResolveAsync(saved, cancellationToken);
            if (resolved.Action == CacheRootAction.Cancelled)
            {
                return StartupResult.Cancelled();
            }
            if (resolved.Action == CacheRootAction.ReselectRequired)
            {
                return StartupResult.CacheUnavailable(resolved.ErrorMessage ?? "上次缓存目录不可访问。" );
            }

            var cacheRoot = resolved.CacheRoot ?? throw new InvalidDataException("未获得缓存目录。" );
            if (saved is null || resolved.Action == CacheRootAction.SelectedNew)
            {
                await _configStore.SaveAsync(new LauncherConfig(1, cacheRoot, saved?.Channel ?? "stable"), cancellationToken);
            }

            var layout = CacheLayout.FromRoot(cacheRoot);
            layout.EnsureDirectories();
            var stateStore = new InstallStateStore(layout.State);
            var state = await stateStore.LoadAsync(cancellationToken);

            _progress.Report(new StartupProgress(StartupStage.CheckingLocal, "检查本地运行库……"));
            var health = await _healthChecker.CheckAsync(layout, state, cancellationToken);
            var localIsHealthy = health.IsHealthy && state is not null;

            _progress.Report(new StartupProgress(StartupStage.FetchingManifest, "检查 GitHub 更新……"));
            ReleaseManifest? manifest = null;
            Exception? manifestFailure = null;
            try
            {
                manifest = await _manifestClient.FetchAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                manifestFailure = ex;
            }

            if (manifest is null)
            {
                if (localIsHealthy)
                {
                    _progress.Report(new StartupProgress(
                        StartupStage.Starting,
                        $"无法检查更新，使用本地版本：{manifestFailure?.Message}"));
                    await _applicationLauncher.StartAsync(layout, state!, cancellationToken);
                    _progress.Report(new StartupProgress(StartupStage.Completed, "已离线启动本地版本。", 100));
                    return StartupResult.Started(cacheRoot);
                }

                throw new InvalidOperationException(
                    $"无法获取 GitHub 版本清单：{manifestFailure?.Message ?? "未知错误"}",
                    manifestFailure);
            }

            var runtimeNeedsUpdate = !localIsHealthy || state is null
                || IsRemoteNewer(state.RuntimeVersion, manifest.Runtime.Version);
            var appNeedsUpdate = !localIsHealthy || state is null
                || IsRemoteNewer(state.AppVersion, manifest.App.Version);

            if (localIsHealthy && !runtimeNeedsUpdate && !appNeedsUpdate)
            {
                _progress.Report(new StartupProgress(StartupStage.Starting, "当前已是最新版本，正在启动……"));
                await _applicationLauncher.StartAsync(layout, state!, cancellationToken);
                _progress.Report(new StartupProgress(StartupStage.Completed, "启动完成。", 100));
                return StartupResult.Started(cacheRoot);
            }

            if (localIsHealthy)
            {
                var shouldUpdate = await _updatePrompt.ConfirmUpdateAsync(
                    new UpdateInfo(
                        state!.RuntimeVersion,
                        state.AppVersion,
                        manifest.Runtime.Version,
                        manifest.App.Version,
                        runtimeNeedsUpdate,
                        appNeedsUpdate),
                    cancellationToken);
                if (!shouldUpdate)
                {
                    _progress.Report(new StartupProgress(StartupStage.Starting, "已暂缓更新，正在启动当前版本……"));
                    await _applicationLauncher.StartAsync(layout, state, cancellationToken);
                    _progress.Report(new StartupProgress(StartupStage.Completed, "当前版本已启动。", 100));
                    return StartupResult.Started(cacheRoot);
                }
            }

            string? runtimeZip = null;
            string? appZip = null;
            if (runtimeNeedsUpdate)
            {
                runtimeZip = Path.Combine(layout.Downloads, $"runtime-{manifest.Runtime.Version}.zip");
                var runtimeProgress = new Progress<DownloadProgress>(p =>
                    _progress.Report(new StartupProgress(StartupStage.DownloadingRuntime, "下载运行库（支持断点续传，请勿关闭）……", p.Percent, p.BytesPerSecond)));
                await _downloadService.DownloadAsync(
                    new DownloadRequest(manifest.Runtime.Uri, runtimeZip, manifest.Runtime.Sha256, manifest.Runtime.Size),
                    runtimeProgress,
                    cancellationToken);
            }

            if (appNeedsUpdate)
            {
                appZip = Path.Combine(layout.Downloads, $"app-{manifest.App.Version}.zip");
                var appProgress = new Progress<DownloadProgress>(p =>
                    _progress.Report(new StartupProgress(StartupStage.DownloadingApp, "下载主程序……", p.Percent, p.BytesPerSecond)));
                await _downloadService.DownloadAsync(
                    new DownloadRequest(manifest.App.Uri, appZip, manifest.App.Sha256, manifest.App.Size),
                    appProgress,
                    cancellationToken);
            }

            _progress.Report(new StartupProgress(StartupStage.Installing, "安装更新……"));
            if (runtimeNeedsUpdate)
            {
                var runtimeTarget = Path.Combine(layout.Runtime, manifest.Runtime.Version);
                await _packageInstaller.InstallPackageAsync(
                    runtimeZip!, runtimeTarget, new[] { "python.exe", "pythonw.exe" }, cancellationToken);
            }
            if (appNeedsUpdate)
            {
                var appTarget = Path.Combine(layout.App, manifest.App.Version);
                await _packageInstaller.InstallPackageAsync(
                    appZip!, appTarget, new[] { manifest.App.Entrypoint! }, cancellationToken);
            }

            var nextState = new InstallState(
                1,
                runtimeNeedsUpdate ? manifest.Runtime.Version : state!.RuntimeVersion,
                appNeedsUpdate ? manifest.App.Version : state!.AppVersion,
                appNeedsUpdate ? manifest.App.Entrypoint! : state!.AppEntrypoint);

            _progress.Report(new StartupProgress(StartupStage.Verifying, "验证新安装环境……"));
            health = await _healthChecker.CheckAsync(layout, nextState, cancellationToken);
            if (!health.IsHealthy)
            {
                return StartupResult.Failed($"安装后验证失败：{health.ErrorMessage}");
            }

            // Only switch the active pointer after the complete runtime and app pass health checks.
            await stateStore.SaveAsync(nextState, cancellationToken);

            _progress.Report(new StartupProgress(StartupStage.Starting, "正在启动质检工具……"));
            await _applicationLauncher.StartAsync(layout, nextState, cancellationToken);
            _progress.Report(new StartupProgress(StartupStage.Completed, "启动完成。", 100));
            return StartupResult.Started(cacheRoot);
        }
        catch (OperationCanceledException)
        {
            return StartupResult.Cancelled();
        }
        catch (Exception ex)
        {
            _progress.Report(new StartupProgress(StartupStage.Error, ex.Message));
            return StartupResult.Failed(ex.Message);
        }
    }


    private static bool IsUpdateRequired(InstallState state, ReleaseManifest manifest)
    {
        return IsRemoteNewer(state.RuntimeVersion, manifest.Runtime.Version)
            || IsRemoteNewer(state.AppVersion, manifest.App.Version);
    }

    private static bool IsRemoteNewer(string localVersion, string remoteVersion)
    {
        var localText = localVersion.Trim().TrimStart('v', 'V');
        var remoteText = remoteVersion.Trim().TrimStart('v', 'V');
        if (Version.TryParse(localText, out var local) && Version.TryParse(remoteText, out var remote))
        {
            return remote > local;
        }

        return !string.Equals(localText, remoteText, StringComparison.OrdinalIgnoreCase);
    }

    public async Task<CacheRootResult> SelectAndSaveNewCacheRootAsync(string? initialDirectory, CancellationToken cancellationToken)
    {
        var result = await _cacheRootSelector.SelectNewAsync(initialDirectory, cancellationToken);
        if (result.Action == CacheRootAction.SelectedNew && result.CacheRoot is not null)
        {
            await _configStore.SaveAsync(new LauncherConfig(1, result.CacheRoot, "stable"), cancellationToken);
        }
        return result;
    }
}
