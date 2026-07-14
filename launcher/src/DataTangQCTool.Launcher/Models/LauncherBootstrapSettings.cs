using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace DataTangQCTool.Launcher.Models;

public sealed class LauncherBootstrapSettings
{
    [JsonPropertyName("manifest_url")]
    public string ManifestUrl { get; init; } = string.Empty;

    [JsonPropertyName("allowed_release_prefix")]
    public string AllowedReleasePrefix { get; init; } = string.Empty;

    public Uri ManifestUri => RequireHttps(ManifestUrl, "manifest_url");
    public Uri AllowedReleasePrefixUri => RequireHttps(AllowedReleasePrefix, "allowed_release_prefix");

    public static LauncherBootstrapSettings Load(string path)
    {
        if (!File.Exists(path))
        {
            throw new FileNotFoundException("缺少启动器配置 launcher.settings.json。", path);
        }

        var value = JsonSerializer.Deserialize<LauncherBootstrapSettings>(File.ReadAllText(path))
                    ?? throw new InvalidDataException("启动器配置为空。");
        _ = value.ManifestUri;
        _ = value.AllowedReleasePrefixUri;
        return value;
    }


    public static LauncherBootstrapSettings LoadEmbedded(Assembly assembly)
    {
        var resourceName = assembly.GetManifestResourceNames()
            .SingleOrDefault(name => name.EndsWith("launcher.settings.json", StringComparison.OrdinalIgnoreCase))
            ?? throw new FileNotFoundException("启动器内嵌配置不存在。");
        using var stream = assembly.GetManifestResourceStream(resourceName)
                           ?? throw new FileNotFoundException("无法读取启动器内嵌配置。");
        var value = JsonSerializer.Deserialize<LauncherBootstrapSettings>(stream)
                    ?? throw new InvalidDataException("启动器内嵌配置为空。");
        _ = value.ManifestUri;
        _ = value.AllowedReleasePrefixUri;
        return value;
    }

    private static Uri RequireHttps(string value, string field)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps)
        {
            throw new InvalidDataException($"{field} 必须是 HTTPS 地址。");
        }
        return uri;
    }
}
