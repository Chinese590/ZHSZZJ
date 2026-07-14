using System.Diagnostics;
using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Services;

public sealed record ProcessResult(int ExitCode, string StandardOutput, string StandardError);

public interface IProcessRunner
{
    Task<ProcessResult> RunAsync(string fileName, string arguments, string? workingDirectory, CancellationToken cancellationToken);
}

public sealed class ProcessRunner : IProcessRunner
{
    public async Task<ProcessResult> RunAsync(string fileName, string arguments, string? workingDirectory, CancellationToken cancellationToken)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            Arguments = arguments,
            WorkingDirectory = workingDirectory ?? string.Empty,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true
        };
        using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!process.Start())
        {
            throw new InvalidOperationException($"无法启动进程：{fileName}");
        }

        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        return new ProcessResult(process.ExitCode, await stdoutTask, await stderrTask);
    }
}

public interface IApplicationLauncher
{
    Task StartAsync(CacheLayout layout, InstallState state, CancellationToken cancellationToken);
}

public sealed class ApplicationLauncher : IApplicationLauncher
{
    public Task StartAsync(CacheLayout layout, InstallState state, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var runtimeDirectory = Path.Combine(layout.Runtime, state.RuntimeVersion);
        var appDirectory = Path.Combine(layout.App, state.AppVersion);
        var pythonw = Path.Combine(runtimeDirectory, "pythonw.exe");
        var entrypoint = Path.Combine(appDirectory, state.AppEntrypoint.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(pythonw))
        {
            throw new FileNotFoundException("运行库缺少 pythonw.exe。", pythonw);
        }
        if (!File.Exists(entrypoint))
        {
            throw new FileNotFoundException("主程序入口不存在。", entrypoint);
        }

        var normalizedEntrypoint = state.AppEntrypoint.Replace('\\', '/');
        if (!normalizedEntrypoint.EndsWith(".py", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("主程序 entrypoint 必须是 .py 文件。");
        }
        var moduleName = normalizedEntrypoint[..^3].Replace('/', '.');
        var process = Process.Start(new ProcessStartInfo
        {
            FileName = pythonw,
            Arguments = $"-m {moduleName} --cache-root \"{layout.Root}\"",
            WorkingDirectory = appDirectory,
            UseShellExecute = false,
            CreateNoWindow = true
        });
        if (process is null)
        {
            throw new InvalidOperationException("主程序启动失败。" );
        }
        return Task.CompletedTask;
    }
}
