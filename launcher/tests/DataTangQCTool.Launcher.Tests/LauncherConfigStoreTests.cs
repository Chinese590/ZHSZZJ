using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class LauncherConfigStoreTests
{
    [Fact]
    public async Task Load_returns_null_when_pointer_file_does_not_exist()
    {
        using var temp = new TempDirectory();
        var store = new LauncherConfigStore(temp.Path);
        Assert.Null(await store.LoadAsync());
    }

    [Fact]
    public async Task Save_then_load_restores_selected_cache_root()
    {
        using var temp = new TempDirectory();
        var store = new LauncherConfigStore(temp.Path);
        var expected = new LauncherConfig(1, temp.Combine("用户指定缓存"), "stable");
        await store.SaveAsync(expected);

        var actual = await store.LoadAsync();

        Assert.NotNull(actual);
        Assert.Equal(expected.CacheRoot, actual!.CacheRoot);
        Assert.Equal(expected.Channel, actual.Channel);
    }
}
