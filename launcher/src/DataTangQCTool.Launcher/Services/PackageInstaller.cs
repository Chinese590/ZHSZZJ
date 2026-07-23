using System.IO.Compression;

namespace DataTangQCTool.Launcher.Services;

public interface IPackageInstaller
{
    Task InstallPackageAsync(string zipPath, string targetDirectory, IReadOnlyCollection<string> expectedRelativeFiles, CancellationToken cancellationToken);
}

public sealed class PackageInstaller : IPackageInstaller
{
    private const int MaxEntryCount = 10_000;
    private const long MaxUncompressedBytes = 2L * 1024 * 1024 * 1024;

    public async Task InstallPackageAsync(string zipPath, string targetDirectory, IReadOnlyCollection<string> expectedRelativeFiles, CancellationToken cancellationToken)
    {
        if (!File.Exists(zipPath))
        {
            throw new FileNotFoundException("安装包不存在。", zipPath);
        }

        var stagingDirectory = targetDirectory + ".staging";
        TryDeleteDirectory(stagingDirectory);
        Directory.CreateDirectory(stagingDirectory);
        var stagingRoot = Path.GetFullPath(stagingDirectory).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;

        try
        {
            using var archive = ZipFile.OpenRead(zipPath);
            if (archive.Entries.Count > MaxEntryCount)
            {
                throw new InvalidDataException("安装包文件数量超过安全上限。");
            }
            long totalUncompressedBytes = 0;
            foreach (var entry in archive.Entries)
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (string.IsNullOrEmpty(entry.FullName))
                {
                    continue;
                }

                var normalizedName = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                var destination = Path.GetFullPath(Path.Combine(stagingDirectory, normalizedName));
                if (!destination.StartsWith(stagingRoot, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException($"安装包包含越界路径：{entry.FullName}");
                }

                if (entry.FullName.EndsWith("/", StringComparison.Ordinal) || entry.FullName.EndsWith("\\", StringComparison.Ordinal))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }

                totalUncompressedBytes = checked(totalUncompressedBytes + entry.Length);
                if (totalUncompressedBytes > MaxUncompressedBytes)
                {
                    throw new InvalidDataException("安装包解压后大小超过安全上限。");
                }

                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                await using var source = entry.Open();
                await using var target = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None, 1024 * 128, useAsync: true);
                await source.CopyToAsync(target, cancellationToken);
            }

            foreach (var relative in expectedRelativeFiles)
            {
                var expected = Path.Combine(stagingDirectory, relative.Replace('/', Path.DirectorySeparatorChar));
                if (!File.Exists(expected))
                {
                    throw new InvalidDataException($"安装包缺少必要文件：{relative}");
                }
            }

            if (Directory.Exists(targetDirectory))
            {
                Directory.Delete(targetDirectory, recursive: true);
            }
            Directory.Move(stagingDirectory, targetDirectory);
        }
        catch
        {
            TryDeleteDirectory(stagingDirectory);
            throw;
        }
    }

    private static void TryDeleteDirectory(string path)
    {
        try { if (Directory.Exists(path)) Directory.Delete(path, recursive: true); } catch { }
    }
}
