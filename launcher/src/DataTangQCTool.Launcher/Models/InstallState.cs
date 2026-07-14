using System.Text.Json.Serialization;

namespace DataTangQCTool.Launcher.Models;

public sealed record InstallState(
    [property: JsonPropertyName("schema_version")] int SchemaVersion,
    [property: JsonPropertyName("runtime_version")] string RuntimeVersion,
    [property: JsonPropertyName("app_version")] string AppVersion,
    [property: JsonPropertyName("app_entrypoint")] string AppEntrypoint);

public sealed record HealthReport(bool RuntimeOk, bool AppOk, string ErrorMessage)
{
    public bool IsHealthy => RuntimeOk && AppOk;
    public static HealthReport Healthy() => new(true, true, string.Empty);
    public static HealthReport Unhealthy(string message, bool runtimeOk = false, bool appOk = false) => new(runtimeOk, appOk, message);
}

public enum StartupOutcome
{
    Started,
    CacheRootUnavailable,
    Cancelled,
    Failed
}

public sealed record StartupResult(StartupOutcome Outcome, string Message, string? CacheRoot = null)
{
    public static StartupResult Started(string cacheRoot) => new(StartupOutcome.Started, "已启动。", cacheRoot);
    public static StartupResult CacheUnavailable(string message) => new(StartupOutcome.CacheRootUnavailable, message);
    public static StartupResult Cancelled() => new(StartupOutcome.Cancelled, "用户取消。" );
    public static StartupResult Failed(string message) => new(StartupOutcome.Failed, message);
}
