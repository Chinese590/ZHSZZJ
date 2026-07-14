using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Services;

public interface IReleaseManifestClient
{
    Task<ReleaseManifest> FetchAsync(CancellationToken cancellationToken);
}

public sealed class ReleaseManifestClient : IReleaseManifestClient
{
    private readonly HttpClient _httpClient;
    private readonly Uri _manifestUri;
    private readonly Uri _allowedReleasePrefix;

    public ReleaseManifestClient(HttpClient httpClient, Uri manifestUri, Uri allowedReleasePrefix)
    {
        _httpClient = httpClient;
        _manifestUri = manifestUri;
        _allowedReleasePrefix = allowedReleasePrefix;
    }

    public async Task<ReleaseManifest> FetchAsync(CancellationToken cancellationToken)
    {
        using var response = await _httpClient.GetAsync(_manifestUri, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadAsStringAsync(cancellationToken);
        var manifest = ReleaseManifest.Parse(json);
        manifest.ValidateReleasePrefix(_allowedReleasePrefix);
        return manifest;
    }
}
