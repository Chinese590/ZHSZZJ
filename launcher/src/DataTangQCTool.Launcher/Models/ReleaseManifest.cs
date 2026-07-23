using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace DataTangQCTool.Launcher.Models;

public sealed class ReleaseManifest
{
    private static readonly Regex Sha256Pattern = new("^[a-f0-9]{64}$", RegexOptions.Compiled | RegexOptions.CultureInvariant);
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true
    };

    [JsonPropertyName("schema_version")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("channel")]
    public string Channel { get; init; } = string.Empty;

    [JsonPropertyName("runtime")]
    public ReleaseAsset Runtime { get; init; } = new();

    [JsonPropertyName("app")]
    public ReleaseAsset App { get; init; } = new();

    public static ReleaseManifest Parse(string json)
    {
        ReleaseManifest? manifest;
        try
        {
            manifest = JsonSerializer.Deserialize<ReleaseManifest>(json, JsonOptions);
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("版本清单不是有效的 JSON。", ex);
        }

        if (manifest is null)
        {
            throw new InvalidDataException("版本清单为空。");
        }

        manifest.Validate();
        return manifest;
    }

    public string ToJson() => JsonSerializer.Serialize(this, JsonOptions);

    public void ValidateReleasePrefix(Uri allowedPrefix)
    {
        ArgumentNullException.ThrowIfNull(allowedPrefix);
        var prefix = allowedPrefix.AbsoluteUri.TrimEnd('/') + "/";
        foreach (var asset in new[] { Runtime, App })
        {
            if (!asset.Uri.AbsoluteUri.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"下载地址不属于允许的 GitHub Releases 仓库：{asset.Url}");
            }
        }
    }

    private void Validate()
    {
        if (SchemaVersion != 1)
        {
            throw new InvalidDataException($"不支持的清单版本：{SchemaVersion}");
        }

        if (string.IsNullOrWhiteSpace(Channel))
        {
            throw new InvalidDataException("清单缺少 channel。");
        }

        ValidateAsset(Runtime, "runtime", requiresEntrypoint: false);
        ValidateAsset(App, "app", requiresEntrypoint: true);
    }

    private static void ValidateAsset(ReleaseAsset asset, string name, bool requiresEntrypoint)
    {
        if (!IsSafeVersionSegment(asset.Version))
        {
            throw new InvalidDataException($"{name} version 必须是单个安全目录名。");
        }

        if (!Uri.TryCreate(asset.Url, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps)
        {
            throw new InvalidDataException($"{name} 下载地址必须使用 HTTPS。");
        }

        if (!uri.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"{name} 下载地址必须来自 github.com。");
        }

        if (!uri.AbsolutePath.Contains("/releases/download/", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"{name} 下载地址必须是 GitHub Release 资源。");
        }

        if (!Sha256Pattern.IsMatch(asset.Sha256 ?? string.Empty))
        {
            throw new InvalidDataException($"{name} 缺少有效的 SHA256。");
        }

        if (asset.Size <= 0)
        {
            throw new InvalidDataException($"{name} 文件大小必须大于 0。");
        }

        if (requiresEntrypoint && !IsSafeRelativePath(asset.Entrypoint))
        {
            throw new InvalidDataException("app entrypoint 必须是安全的相对路径。");
        }
    }

    private static bool IsSafeVersionSegment(string? value)
    {
        return !string.IsNullOrWhiteSpace(value)
            && value.IndexOfAny(Path.GetInvalidFileNameChars()) < 0
            && value.IndexOfAny([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar]) < 0
            && value is not "." and not "..";
    }

    private static bool IsSafeRelativePath(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || Path.IsPathRooted(value)) return false;
        var segments = value.Replace('\\', '/').Split('/', StringSplitOptions.RemoveEmptyEntries);
        return segments.Length > 0 && segments.All(segment => segment is not "." and not "..");
    }
}

public sealed class ReleaseAsset
{
    [JsonPropertyName("version")]
    public string Version { get; init; } = string.Empty;

    [JsonPropertyName("url")]
    public string Url { get; init; } = string.Empty;

    [JsonPropertyName("sha256")]
    public string Sha256 { get; init; } = string.Empty;

    [JsonPropertyName("size")]
    public long Size { get; init; }

    [JsonPropertyName("entrypoint")]
    public string? Entrypoint { get; init; }

    [JsonIgnore]
    public Uri Uri => new(Url, UriKind.Absolute);
}
