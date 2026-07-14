using System.Text.Json.Serialization;

namespace DataTangQCTool.Launcher.Models;

public sealed record LauncherConfig(
    [property: JsonPropertyName("schema_version")] int SchemaVersion,
    [property: JsonPropertyName("cache_root")] string CacheRoot,
    [property: JsonPropertyName("channel")] string Channel);

public sealed record CacheLayout(
    string Root,
    string Runtime,
    string App,
    string Models,
    string Downloads,
    string Logs,
    string Config,
    string State)
{
    public static CacheLayout FromRoot(string root)
    {
        var full = Path.GetFullPath(root);
        return new CacheLayout(
            full,
            Path.Combine(full, "runtime"),
            Path.Combine(full, "app"),
            Path.Combine(full, "models"),
            Path.Combine(full, "downloads"),
            Path.Combine(full, "logs"),
            Path.Combine(full, "config"),
            Path.Combine(full, "state"));
    }

    public void EnsureDirectories()
    {
        foreach (var path in new[] { Root, Runtime, App, Models, Downloads, Logs, Config, State })
        {
            Directory.CreateDirectory(path);
        }
    }
}

public enum CacheRootAction
{
    UseSaved,
    SelectedNew,
    ReselectRequired,
    Cancelled
}

public sealed record CacheRootResult(CacheRootAction Action, string? CacheRoot, string? ErrorMessage = null);

public sealed record CacheRootValidation(bool IsValid, string ErrorMessage, long FreeBytes)
{
    public static CacheRootValidation Valid(long freeBytes) => new(true, string.Empty, freeBytes);
    public static CacheRootValidation Invalid(string errorMessage) => new(false, errorMessage, 0);
}
