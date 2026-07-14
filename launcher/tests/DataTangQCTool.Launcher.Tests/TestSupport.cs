using System.Net;
using System.Text;
using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

internal sealed class TempDirectory : IDisposable
{
    public TempDirectory()
    {
        Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "DataTangQCTool.Tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path);
    }

    public string Path { get; }

    public string Combine(params string[] parts)
    {
        var all = new[] { Path }.Concat(parts).ToArray();
        return System.IO.Path.Combine(all);
    }

    public void Dispose()
    {
        try { Directory.Delete(Path, recursive: true); } catch { }
    }
}

internal sealed class FakeFolderPicker : IFolderPicker
{
    public string? Result { get; set; }
    public int OpenCount { get; private set; }

    public Task<string?> PickFolderAsync(string? initialDirectory, CancellationToken cancellationToken)
    {
        OpenCount++;
        return Task.FromResult(Result);
    }
}

internal sealed class FakeCacheRootValidator : ICacheRootValidator
{
    public CacheRootValidation Result { get; set; } = CacheRootValidation.Valid(10L * 1024 * 1024 * 1024);
    public Task<CacheRootValidation> ValidateAsync(string path, CancellationToken cancellationToken) => Task.FromResult(Result);
}

internal sealed class RecordingHttpHandler : HttpMessageHandler
{
    private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

    public RecordingHttpHandler(Func<HttpRequestMessage, HttpResponseMessage> handler) => _handler = handler;

    public string? LastRangeHeader { get; private set; }
    public int RequestCount { get; private set; }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        RequestCount++;
        LastRangeHeader = request.Headers.Range?.ToString();
        return Task.FromResult(_handler(request));
    }

    public static HttpResponseMessage Bytes(byte[] bytes, HttpStatusCode status = HttpStatusCode.OK)
    {
        var response = new HttpResponseMessage(status)
        {
            Content = new ByteArrayContent(bytes)
        };
        response.Content.Headers.ContentLength = bytes.LongLength;
        return response;
    }
}

internal sealed class FakeManifestClient : IReleaseManifestClient
{
    public int FetchCount { get; private set; }
    public ReleaseManifest Manifest { get; set; } = TestManifests.Valid();

    public Task<ReleaseManifest> FetchAsync(CancellationToken cancellationToken)
    {
        FetchCount++;
        return Task.FromResult(Manifest);
    }
}

internal sealed class FakeHealthChecker : IRuntimeHealthChecker
{
    public HealthReport Report { get; set; } = HealthReport.Unhealthy("missing");
    public int CheckCount { get; private set; }

    public Task<HealthReport> CheckAsync(CacheLayout layout, InstallState? state, CancellationToken cancellationToken)
    {
        CheckCount++;
        return Task.FromResult(Report);
    }
}


internal sealed class FakeProcessRunner : IProcessRunner
{
    public ProcessResult Result { get; set; } = new(0, "OK", string.Empty);
    public string LastFileName { get; private set; } = string.Empty;
    public string LastArguments { get; private set; } = string.Empty;

    public Task<ProcessResult> RunAsync(string fileName, string arguments, string? workingDirectory, CancellationToken cancellationToken)
    {
        LastFileName = fileName;
        LastArguments = arguments;
        return Task.FromResult(Result);
    }
}


internal sealed class FakeUpdatePrompt : IUpdatePrompt
{
    public bool Result { get; set; } = true;
    public int PromptCount { get; private set; }
    public UpdateInfo? LastUpdate { get; private set; }

    public Task<bool> ConfirmUpdateAsync(UpdateInfo update, CancellationToken cancellationToken)
    {
        PromptCount++;
        LastUpdate = update;
        return Task.FromResult(Result);
    }
}

internal sealed class FakeApplicationLauncher : IApplicationLauncher
{
    public int StartCount { get; private set; }
    public Task StartAsync(CacheLayout layout, InstallState state, CancellationToken cancellationToken)
    {
        StartCount++;
        return Task.CompletedTask;
    }
}

internal sealed class FakeDownloadService : IResumableDownloadService
{
    public int DownloadCount { get; private set; }
    public Task<string> DownloadAsync(DownloadRequest request, IProgress<DownloadProgress>? progress, CancellationToken cancellationToken)
    {
        DownloadCount++;
        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(request.FinalPath)!);
        File.WriteAllBytes(request.FinalPath, Array.Empty<byte>());
        return Task.FromResult(request.FinalPath);
    }
}

internal sealed class FakePackageInstaller : IPackageInstaller
{
    public int InstallCount { get; private set; }
    public Task InstallPackageAsync(string zipPath, string targetDirectory, IReadOnlyCollection<string> expectedRelativeFiles, CancellationToken cancellationToken)
    {
        InstallCount++;
        Directory.CreateDirectory(targetDirectory);
        foreach (var file in expectedRelativeFiles)
        {
            var full = System.IO.Path.Combine(targetDirectory, file.Replace('/', System.IO.Path.DirectorySeparatorChar));
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(full)!);
            File.WriteAllText(full, "fixture");
        }
        return Task.CompletedTask;
    }
}

internal static class TestManifests
{
    public static ReleaseManifest Valid() => ReleaseManifest.Parse(
        """
        {
          "schema_version": 1,
          "channel": "stable",
          "runtime": {
            "version": "1.0.0",
            "url": "https://github.com/example/repo/releases/download/runtime-v1.0.0/runtime.zip",
            "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "size": 1
          },
          "app": {
            "version": "1.0.0",
            "url": "https://github.com/example/repo/releases/download/app-v1.0.0/app.zip",
            "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "size": 1,
            "entrypoint": "app/main.py"
          }
        }
        """);
}
