using DataTangQCTool.Launcher.Models;

namespace DataTangQCTool.Launcher.Services;

public interface IRuntimeHealthChecker
{
    Task<HealthReport> CheckAsync(CacheLayout layout, InstallState? state, CancellationToken cancellationToken);
}

public sealed class RuntimeHealthChecker : IRuntimeHealthChecker
{
    private readonly IProcessRunner _processRunner;

    public RuntimeHealthChecker(IProcessRunner processRunner)
    {
        _processRunner = processRunner;
    }

    public async Task<HealthReport> CheckAsync(CacheLayout layout, InstallState? state, CancellationToken cancellationToken)
    {
        if (state is null)
        {
            return HealthReport.Unhealthy("尚未安装运行库。" );
        }

        var runtimeDirectory = Path.Combine(layout.Runtime, state.RuntimeVersion);
        var python = Path.Combine(runtimeDirectory, "python.exe");
        var pythonw = Path.Combine(runtimeDirectory, "pythonw.exe");
        if (!File.Exists(python) || !File.Exists(pythonw))
        {
            return HealthReport.Unhealthy("运行库文件不完整。" );
        }

        var appDirectory = Path.Combine(layout.App, state.AppVersion);
        var entrypoint = Path.Combine(appDirectory, state.AppEntrypoint.Replace('/', Path.DirectorySeparatorChar));
        var appOk = File.Exists(entrypoint);
        if (!appOk)
        {
            return HealthReport.Unhealthy("主程序文件不完整。", runtimeOk: true, appOk: false);
        }

        try
        {
            var result = await _processRunner.RunAsync(
                python,
                "-c \"import PySide6, PIL, openpyxl, watchdog, send2trash, huggingface_hub, onnxruntime, numpy; print('OK')\"",
                runtimeDirectory,
                cancellationToken);
            if (result.ExitCode != 0 || !result.StandardOutput.Contains("OK", StringComparison.Ordinal))
            {
                var error = string.IsNullOrWhiteSpace(result.StandardError) ? "依赖导入失败。" : result.StandardError.Trim();
                return HealthReport.Unhealthy(error, runtimeOk: false, appOk: true);
            }
            return HealthReport.Healthy();
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException)
        {
            return HealthReport.Unhealthy($"运行库检查失败：{ex.Message}", runtimeOk: false, appOk: true);
        }
    }
}
