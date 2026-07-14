namespace DataTangQCTool.Launcher.Services;

public enum StartupStage
{
    SelectingCache,
    CheckingLocal,
    FetchingManifest,
    DownloadingRuntime,
    DownloadingApp,
    Installing,
    Verifying,
    Starting,
    Completed,
    Error
}

public sealed record StartupProgress(StartupStage Stage, string Message, double? Percent = null, double? BytesPerSecond = null);

public interface IStartupProgress
{
    void Report(StartupProgress progress);
}

public sealed class NullStartupProgress : IStartupProgress
{
    public static NullStartupProgress Instance { get; } = new();
    private NullStartupProgress() { }
    public void Report(StartupProgress progress) { }
}


public sealed record UpdateInfo(
    string CurrentRuntimeVersion,
    string CurrentAppVersion,
    string NewRuntimeVersion,
    string NewAppVersion,
    bool RuntimeWillUpdate,
    bool AppWillUpdate);

public interface IUpdatePrompt
{
    Task<bool> ConfirmUpdateAsync(UpdateInfo update, CancellationToken cancellationToken);
}

public sealed class AlwaysAcceptUpdatePrompt : IUpdatePrompt
{
    public static AlwaysAcceptUpdatePrompt Instance { get; } = new();
    private AlwaysAcceptUpdatePrompt() { }
    public Task<bool> ConfirmUpdateAsync(UpdateInfo update, CancellationToken cancellationToken) => Task.FromResult(true);
}
