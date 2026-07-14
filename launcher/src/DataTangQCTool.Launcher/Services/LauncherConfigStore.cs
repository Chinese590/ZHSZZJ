using System.Text.Json;
using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Services;

public sealed class LauncherConfigStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };

    public LauncherConfigStore(string? localAppDataRoot = null)
    {
        var baseDirectory = localAppDataRoot ?? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        DirectoryPath = Path.Combine(baseDirectory, "DataTangQCToolLauncher");
        ConfigPath = Path.Combine(DirectoryPath, "launcher.json");
    }

    public string DirectoryPath { get; }
    public string ConfigPath { get; }

    public async Task<LauncherConfig?> LoadAsync(CancellationToken cancellationToken = default)
    {
        if (!File.Exists(ConfigPath))
        {
            return null;
        }

        try
        {
            await using var stream = new FileStream(ConfigPath, FileMode.Open, FileAccess.Read, FileShare.Read);
            var config = await JsonSerializer.DeserializeAsync<LauncherConfig>(stream, JsonOptions, cancellationToken);
            if (config is null || config.SchemaVersion != 1 || string.IsNullOrWhiteSpace(config.CacheRoot))
            {
                throw new InvalidDataException("启动器缓存位置配置无效。");
            }
            return config;
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("启动器缓存位置配置损坏。", ex);
        }
    }

    public async Task SaveAsync(LauncherConfig config, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(config);
        Directory.CreateDirectory(DirectoryPath);
        var temporaryPath = ConfigPath + ".tmp";
        var backupPath = ConfigPath + ".bak";

        await using (var stream = new FileStream(
                         temporaryPath,
                         FileMode.Create,
                         FileAccess.Write,
                         FileShare.None,
                         4096,
                         FileOptions.WriteThrough))
        {
            await JsonSerializer.SerializeAsync(stream, config, JsonOptions, cancellationToken);
            await stream.FlushAsync(cancellationToken);
            stream.Flush(flushToDisk: true);
        }

        if (File.Exists(ConfigPath))
        {
            try
            {
                File.Replace(temporaryPath, ConfigPath, backupPath, ignoreMetadataErrors: true);
                TryDelete(backupPath);
            }
            catch (PlatformNotSupportedException)
            {
                File.Move(temporaryPath, ConfigPath, overwrite: true);
            }
            catch (IOException)
            {
                File.Move(temporaryPath, ConfigPath, overwrite: true);
            }
        }
        else
        {
            File.Move(temporaryPath, ConfigPath);
        }
    }

    private static void TryDelete(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); } catch { }
    }
}
