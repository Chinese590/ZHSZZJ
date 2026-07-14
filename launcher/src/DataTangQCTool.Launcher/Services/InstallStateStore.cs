using System.Text.Json;
using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Services;

public sealed class InstallStateStore
{
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };

    public InstallStateStore(string stateDirectory)
    {
        DirectoryPath = stateDirectory;
        StatePath = Path.Combine(stateDirectory, "active.json");
    }

    public string DirectoryPath { get; }
    public string StatePath { get; }

    public async Task<InstallState?> LoadAsync(CancellationToken cancellationToken = default)
    {
        if (!File.Exists(StatePath))
        {
            return null;
        }
        await using var stream = File.OpenRead(StatePath);
        try
        {
            return await JsonSerializer.DeserializeAsync<InstallState>(stream, Options, cancellationToken);
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("本地安装状态文件损坏。", ex);
        }
    }

    public async Task SaveAsync(InstallState state, CancellationToken cancellationToken = default)
    {
        Directory.CreateDirectory(DirectoryPath);
        var temp = StatePath + ".tmp";
        await using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
        {
            await JsonSerializer.SerializeAsync(stream, state, Options, cancellationToken);
            await stream.FlushAsync(cancellationToken);
            stream.Flush(true);
        }
        File.Move(temp, StatePath, overwrite: true);
    }
}
