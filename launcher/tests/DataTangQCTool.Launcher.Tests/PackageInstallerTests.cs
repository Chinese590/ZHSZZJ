using System.IO.Compression;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class PackageInstallerTests
{
    [Fact]
    public async Task Install_extracts_to_version_directory_and_checks_expected_files()
    {
        using var temp = new TempDirectory();
        var zip = temp.Combine("runtime.zip");
        using (var archive = ZipFile.Open(zip, ZipArchiveMode.Create))
        {
            var entry = archive.CreateEntry("python.exe");
            await using var stream = entry.Open();
            await stream.WriteAsync(new byte[] { 1, 2, 3 });
        }
        var target = temp.Combine("runtime", "1.0.0");
        var installer = new PackageInstaller();

        await installer.InstallPackageAsync(zip, target, new[] { "python.exe" }, CancellationToken.None);

        Assert.True(File.Exists(Path.Combine(target, "python.exe")));
        Assert.False(Directory.Exists(target + ".staging"));
    }

    [Fact]
    public async Task Install_rejects_zip_path_traversal()
    {
        using var temp = new TempDirectory();
        var zip = temp.Combine("bad.zip");
        using (var archive = ZipFile.Open(zip, ZipArchiveMode.Create))
        {
            archive.CreateEntry("../outside.txt");
        }
        var installer = new PackageInstaller();
        await Assert.ThrowsAsync<InvalidDataException>(() => installer.InstallPackageAsync(zip, temp.Combine("target"), Array.Empty<string>(), CancellationToken.None));
    }
}
