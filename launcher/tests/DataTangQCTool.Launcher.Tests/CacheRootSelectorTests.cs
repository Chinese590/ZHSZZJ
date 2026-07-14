using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher.Tests;

public sealed class CacheRootSelectorTests
{
    [Fact]
    public async Task Resolve_uses_saved_root_without_opening_picker_when_valid()
    {
        using var temp = new TempDirectory();
        var picker = new FakeFolderPicker();
        var selector = new CacheRootSelector(picker, new FakeCacheRootValidator());
        var saved = new LauncherConfig(1, temp.Combine("缓存"), "stable");

        var result = await selector.ResolveAsync(saved, CancellationToken.None);

        Assert.Equal(CacheRootAction.UseSaved, result.Action);
        Assert.Equal(saved.CacheRoot, result.CacheRoot);
        Assert.Equal(0, picker.OpenCount);
    }

    [Fact]
    public async Task Resolve_requests_reselection_when_saved_drive_is_unavailable()
    {
        var picker = new FakeFolderPicker();
        var validator = new FakeCacheRootValidator
        {
            Result = CacheRootValidation.Invalid("目录不可访问")
        };
        var selector = new CacheRootSelector(picker, validator);
        var saved = new LauncherConfig(1, @"Z:\Missing\DataTangCache", "stable");

        var result = await selector.ResolveAsync(saved, CancellationToken.None);

        Assert.Equal(CacheRootAction.ReselectRequired, result.Action);
        Assert.Equal(0, picker.OpenCount);
    }

    [Fact]
    public async Task SelectNew_returns_cancelled_when_picker_is_cancelled()
    {
        var selector = new CacheRootSelector(new FakeFolderPicker { Result = null }, new FakeCacheRootValidator());
        var result = await selector.SelectNewAsync(null, CancellationToken.None);
        Assert.Equal(CacheRootAction.Cancelled, result.Action);
    }
}
