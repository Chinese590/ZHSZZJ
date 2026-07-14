using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Tests;

public sealed class ReleaseManifestTests
{
    [Fact]
    public void Parse_rejects_manifest_without_sha256()
    {
        var json = """{"schema_version":1,"channel":"stable","runtime":{"version":"1.0.0","url":"https://github.com/example/repo/releases/download/x/runtime.zip","size":1},"app":{"version":"1.0.0","url":"https://github.com/example/repo/releases/download/x/app.zip","sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","size":1,"entrypoint":"app/main.py"}}""";
        Assert.Throws<InvalidDataException>(() => ReleaseManifest.Parse(json));
    }

    [Fact]
    public void Parse_rejects_non_https_asset()
    {
        var manifest = TestManifests.Valid();
        var json = manifest.ToJson().Replace("https://", "http://", StringComparison.Ordinal);
        Assert.Throws<InvalidDataException>(() => ReleaseManifest.Parse(json));
    }

    [Fact]
    public void ValidateReleasePrefix_rejects_other_repository()
    {
        var manifest = TestManifests.Valid();
        Assert.Throws<InvalidDataException>(() => manifest.ValidateReleasePrefix(new Uri("https://github.com/owner/other/releases/download/")));
    }
}
