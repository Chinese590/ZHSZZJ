using System.Net;
using System.Security.Cryptography;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class ResumableDownloadServiceTests
{
    [Fact]
    public async Task Download_sends_range_header_when_part_file_exists()
    {
        using var temp = new TempDirectory();
        var full = Enumerable.Range(0, 2048).Select(i => (byte)(i % 251)).ToArray();
        var part = full[..1024];
        var remainder = full[1024..];
        var finalPath = temp.Combine("runtime.zip");
        await File.WriteAllBytesAsync(finalPath + ".part", part);
        var handler = new RecordingHttpHandler(_ => RecordingHttpHandler.Bytes(remainder, HttpStatusCode.PartialContent));
        var service = new ResumableDownloadService(new HttpClient(handler), new ReleaseUrlPolicy("https://github.com/example/repo/releases/download/"), maxRetries: 1);
        var request = new DownloadRequest(new Uri("https://github.com/example/repo/releases/download/v1/runtime.zip"), finalPath, Convert.ToHexString(SHA256.HashData(full)).ToLowerInvariant(), full.LongLength);

        await service.DownloadAsync(request, null, CancellationToken.None);

        Assert.Equal("bytes=1024-", handler.LastRangeHeader);
        Assert.Equal(full, await File.ReadAllBytesAsync(finalPath));
    }

    [Fact]
    public async Task Download_deletes_part_file_when_sha256_mismatches()
    {
        using var temp = new TempDirectory();
        var bytes = new byte[] { 1, 2, 3, 4 };
        var finalPath = temp.Combine("runtime.zip");
        var handler = new RecordingHttpHandler(_ => RecordingHttpHandler.Bytes(bytes));
        var service = new ResumableDownloadService(new HttpClient(handler), new ReleaseUrlPolicy("https://github.com/example/repo/releases/download/"), maxRetries: 1);
        var request = new DownloadRequest(new Uri("https://github.com/example/repo/releases/download/v1/runtime.zip"), finalPath, new string('0', 64), bytes.LongLength);

        await Assert.ThrowsAsync<InvalidDataException>(() => service.DownloadAsync(request, null, CancellationToken.None));

        Assert.False(File.Exists(finalPath));
        Assert.False(File.Exists(finalPath + ".part"));
    }
}
