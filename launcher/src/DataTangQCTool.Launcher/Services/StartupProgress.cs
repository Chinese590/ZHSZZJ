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
