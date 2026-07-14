using DataTangQCTool.Launcher.Models;
using Microsoft.Win32;

namespace DataTangQCTool.Launcher.Services;

public interface IFolderPicker
{
    Task<string?> PickFolderAsync(string? initialDirectory, CancellationToken cancellationToken);
}

public interface ICacheRootValidator
{
    Task<CacheRootValidation> ValidateAsync(string path, CancellationToken cancellationToken);
}

public sealed class CacheRootSelector
{
    private readonly IFolderPicker _folderPicker;
    private readonly ICacheRootValidator _validator;

    public CacheRootSelector(IFolderPicker folderPicker, ICacheRootValidator validator)
    {
        _folderPicker = folderPicker;
        _validator = validator;
    }

    public async Task<CacheRootResult> ResolveAsync(LauncherConfig? saved, CancellationToken cancellationToken)
    {
        if (saved is null)
        {
            return await SelectNewAsync(null, cancellationToken);
        }

        var validation = await _validator.ValidateAsync(saved.CacheRoot, cancellationToken);
        return validation.IsValid
            ? new CacheRootResult(CacheRootAction.UseSaved, Path.GetFullPath(saved.CacheRoot))
            : new CacheRootResult(CacheRootAction.ReselectRequired, saved.CacheRoot, validation.ErrorMessage);
    }

    public async Task<CacheRootResult> SelectNewAsync(string? initialDirectory, CancellationToken cancellationToken)
    {
        var selected = await _folderPicker.PickFolderAsync(initialDirectory, cancellationToken);
        if (string.IsNullOrWhiteSpace(selected))
        {
            return new CacheRootResult(CacheRootAction.Cancelled, null);
        }

        var validation = await _validator.ValidateAsync(selected, cancellationToken);
        return validation.IsValid
            ? new CacheRootResult(CacheRootAction.SelectedNew, Path.GetFullPath(selected))
            : new CacheRootResult(CacheRootAction.ReselectRequired, selected, validation.ErrorMessage);
    }
}

public sealed class WpfFolderPicker : IFolderPicker
{
    public Task<string?> PickFolderAsync(string? initialDirectory, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var dialog = new OpenFolderDialog
        {
            Title = "选择数据堂质检工具缓存目录",
            Multiselect = false
        };
        if (!string.IsNullOrWhiteSpace(initialDirectory) && Directory.Exists(initialDirectory))
        {
            dialog.InitialDirectory = initialDirectory;
        }

        return Task.FromResult(dialog.ShowDialog() == true ? dialog.FolderName : null);
    }
}

public sealed class CacheRootValidator : ICacheRootValidator
{
    private static readonly HashSet<string> StatusFolderNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "质检完成", "待返修", "待质检", "返修提交"
    };

    private readonly long _minimumFreeBytes;

    public CacheRootValidator(long minimumFreeBytes = 2L * 1024 * 1024 * 1024)
    {
        _minimumFreeBytes = minimumFreeBytes;
    }

    public Task<CacheRootValidation> ValidateAsync(string path, CancellationToken cancellationToken)
    {
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path))
            {
                return Task.FromResult(CacheRootValidation.Invalid("缓存目录必须是完整绝对路径。"));
            }

            var full = Path.GetFullPath(path);
            var directoryName = new DirectoryInfo(full).Name;
            if (StatusFolderNames.Contains(directoryName))
            {
                return Task.FromResult(CacheRootValidation.Invalid("不能把业务状态目录作为程序缓存目录。"));
            }

            Directory.CreateDirectory(full);
            if (StatusFolderNames.All(name => Directory.Exists(Path.Combine(full, name))))
            {
                return Task.FromResult(CacheRootValidation.Invalid("所选目录看起来是质检项目目录，请另选程序缓存目录。"));
            }

            var probe = Path.Combine(full, $".datatang-write-test-{Guid.NewGuid():N}.tmp");
            File.WriteAllText(probe, "ok");
            File.Delete(probe);

            var root = Path.GetPathRoot(full);
            if (string.IsNullOrWhiteSpace(root))
            {
                return Task.FromResult(CacheRootValidation.Invalid("无法识别缓存目录所在磁盘。"));
            }

            var freeBytes = new DriveInfo(root).AvailableFreeSpace;
            if (freeBytes < _minimumFreeBytes)
            {
                return Task.FromResult(CacheRootValidation.Invalid($"缓存磁盘剩余空间不足，需要至少 {_minimumFreeBytes / 1024 / 1024 / 1024} GiB。"));
            }

            return Task.FromResult(CacheRootValidation.Valid(freeBytes));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return Task.FromResult(CacheRootValidation.Invalid($"缓存目录不可用：{ex.Message}"));
        }
    }
}
