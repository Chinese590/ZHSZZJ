namespace DataTangQCTool.Launcher.Services;

public sealed class LauncherLogger
{
    private readonly object _gate = new();

    public LauncherLogger(string? baseDirectory = null)
    {
        var root = baseDirectory ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "DataTangQCToolLauncher",
            "logs");
        Directory.CreateDirectory(root);
        LogPath = Path.Combine(root, "launcher.log");
    }

    public string LogPath { get; }

    public void Info(string message) => Write("INFO", message);
    public void Error(string message, Exception? exception = null) => Write("ERROR", exception is null ? message : $"{message}{Environment.NewLine}{exception}");

    private void Write(string level, string message)
    {
        lock (_gate)
        {
            File.AppendAllText(LogPath, $"{DateTimeOffset.Now:O} [{level}] {message}{Environment.NewLine}");
        }
    }
}
