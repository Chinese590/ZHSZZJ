using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;

namespace DataTangQCTool.Launcher.Services;

public sealed record DownloadRequest(Uri Uri, string FinalPath, string Sha256, long ExpectedSize);
public sealed record DownloadProgress(long DownloadedBytes, long TotalBytes, double BytesPerSecond)
{
    public double Percent => TotalBytes <= 0 ? 0 : Math.Min(100, DownloadedBytes * 100d / TotalBytes);
}

public interface IResumableDownloadService
{
    Task<string> DownloadAsync(DownloadRequest request, IProgress<DownloadProgress>? progress, CancellationToken cancellationToken);
}

public sealed class ReleaseUrlPolicy
{
    private readonly string _allowedPrefix;

    public ReleaseUrlPolicy(string allowedPrefix)
    {
        var uri = new Uri(allowedPrefix, UriKind.Absolute);
        if (uri.Scheme != Uri.UriSchemeHttps || !uri.Host.Equals("github.com", StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException("允许的下载前缀必须是 github.com HTTPS 地址。", nameof(allowedPrefix));
        }
        _allowedPrefix = uri.AbsoluteUri.TrimEnd('/') + "/";
    }

    public void EnsureAllowed(Uri uri)
    {
        if (!uri.AbsoluteUri.StartsWith(_allowedPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"拒绝非指定 GitHub Release 下载地址：{uri}");
        }
    }
}

public sealed class ResumableDownloadService : IResumableDownloadService
{
    private readonly HttpClient _httpClient;
    private readonly ReleaseUrlPolicy _urlPolicy;
    private readonly int _maxRetries;
    private readonly TimeSpan[] _retryDelays = { TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(3), TimeSpan.FromSeconds(8) };
    private static readonly TimeSpan ReadIdleTimeout = TimeSpan.FromSeconds(90);

    public ResumableDownloadService(HttpClient httpClient, ReleaseUrlPolicy urlPolicy, int maxRetries = 3)
    {
        _httpClient = httpClient;
        _urlPolicy = urlPolicy;
        _maxRetries = Math.Max(1, maxRetries);
    }

    public async Task<string> DownloadAsync(DownloadRequest request, IProgress<DownloadProgress>? progress, CancellationToken cancellationToken)
    {
        _urlPolicy.EnsureAllowed(request.Uri);
        Directory.CreateDirectory(Path.GetDirectoryName(request.FinalPath) ?? throw new InvalidDataException("下载目标路径无效。"));
        var partPath = request.FinalPath + ".part";

        Exception? lastError = null;
        for (var attempt = 0; attempt < _maxRetries; attempt++)
        {
            try
            {
                await DownloadAttemptAsync(request, partPath, progress, cancellationToken);
                await VerifyAsync(partPath, request, cancellationToken);
                File.Move(partPath, request.FinalPath, overwrite: true);
                return request.FinalPath;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (InvalidDataException)
            {
                TryDelete(partPath);
                TryDelete(request.FinalPath);
                throw;
            }
            catch (Exception ex) when (ex is HttpRequestException or IOException or TimeoutException)
            {
                lastError = ex;
                if (attempt + 1 >= _maxRetries)
                {
                    break;
                }
                await Task.Delay(_retryDelays[Math.Min(attempt, _retryDelays.Length - 1)], cancellationToken);
            }
        }

        throw new IOException("GitHub 运行库下载失败，已达到重试次数。", lastError);
    }

    private async Task DownloadAttemptAsync(DownloadRequest request, string partPath, IProgress<DownloadProgress>? progress, CancellationToken cancellationToken)
    {
        var existingBytes = File.Exists(partPath) ? new FileInfo(partPath).Length : 0;
        HttpResponseMessage? response = null;
        while (response is null)
        {
            using var message = new HttpRequestMessage(HttpMethod.Get, request.Uri);
            if (existingBytes > 0)
            {
                message.Headers.Range = new RangeHeaderValue(existingBytes, null);
            }

            response = await _httpClient.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if (existingBytes > 0 && response.StatusCode != HttpStatusCode.PartialContent)
            {
                response.Dispose();
                response = null;
                File.Delete(partPath);
                existingBytes = 0;
            }
        }

        using (response)
        {
            response.EnsureSuccessStatusCode();
            var responseLength = response.Content.Headers.ContentLength ?? Math.Max(0, request.ExpectedSize - existingBytes);
            var totalBytes = existingBytes + responseLength;
            await using var input = await response.Content.ReadAsStreamAsync(cancellationToken);
            await using var output = new FileStream(partPath, existingBytes > 0 ? FileMode.Append : FileMode.Create, FileAccess.Write, FileShare.None, 1024 * 128, useAsync: true);
            var buffer = new byte[1024 * 128];
            var downloaded = existingBytes;
            var started = System.Diagnostics.Stopwatch.StartNew();
            var lastProgressReport = TimeSpan.Zero;

            while (true)
            {
                var read = await input.ReadAsync(buffer, cancellationToken).AsTask().WaitAsync(ReadIdleTimeout, cancellationToken);
                if (read == 0)
                {
                    break;
                }
                await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
                downloaded += read;
                if (started.Elapsed - lastProgressReport >= TimeSpan.FromMilliseconds(250))
                {
                    lastProgressReport = started.Elapsed;
                    var seconds = Math.Max(0.001, started.Elapsed.TotalSeconds);
                    progress?.Report(new DownloadProgress(downloaded, totalBytes, (downloaded - existingBytes) / seconds));
                }
            }
            // Always emit the final byte count, even for a small or very fast download.
            var seconds = Math.Max(0.001, started.Elapsed.TotalSeconds);
            progress?.Report(new DownloadProgress(downloaded, totalBytes, (downloaded - existingBytes) / seconds));

            await output.FlushAsync(cancellationToken);
            output.Flush(flushToDisk: true);
        }
    }

    private static async Task VerifyAsync(string partPath, DownloadRequest request, CancellationToken cancellationToken)
    {
        var size = new FileInfo(partPath).Length;
        if (request.ExpectedSize > 0 && size != request.ExpectedSize)
        {
            throw new InvalidDataException($"下载文件大小不正确：期望 {request.ExpectedSize}，实际 {size}。" );
        }

        await using var stream = new FileStream(partPath, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 128, useAsync: true);
        var hash = await SHA256.HashDataAsync(stream, cancellationToken);
        var actual = Convert.ToHexString(hash).ToLowerInvariant();
        if (!actual.Equals(request.Sha256, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("下载文件 SHA256 校验失败。" );
        }
    }

    private static void TryDelete(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); } catch { }
    }
}
