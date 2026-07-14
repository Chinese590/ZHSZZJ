using System.Diagnostics;
using System.Windows;
using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher;

public partial class MainWindow : Window, IStartupProgress
{
    private readonly LauncherLogger _logger;
    private readonly CancellationTokenSource _lifetimeCts = new();
    private StartupCoordinator? _coordinator;
    private LauncherConfigStore? _configStore;
    private bool _running;

    public MainWindow(LauncherLogger logger)
    {
        _logger = logger;
        InitializeComponent();
        Loaded += async (_, _) => await StartAsync();
        Closed += (_, _) => _lifetimeCts.Cancel();
    }

    public void AttachCoordinator(StartupCoordinator coordinator, LauncherConfigStore configStore)
    {
        _coordinator = coordinator;
        _configStore = configStore;
    }

    public void Report(StartupProgress progress)
    {
        Dispatcher.Invoke(() =>
        {
            StageText.Text = progress.Message;
            if (progress.Percent is double percent)
            {
                ProgressBar.IsIndeterminate = false;
                ProgressBar.Value = percent;
            }
            else
            {
                ProgressBar.IsIndeterminate = progress.Stage is not StartupStage.Completed and not StartupStage.Error;
            }

            var speed = progress.BytesPerSecond is double bps && bps > 0
                ? $"，速度 {FormatBytes(bps)}/s"
                : string.Empty;
            DetailText.Text = progress.Percent is double p ? $"{p:F1}%{speed}" : progress.Stage.ToString();
            AppendLog(progress.Message + speed);
        });
    }

    private async Task StartAsync()
    {
        if (_running || _coordinator is null || _configStore is null)
        {
            return;
        }

        _running = true;
        RetryButton.Visibility = Visibility.Collapsed;
        ChangeCacheButton.IsEnabled = false;
        var restartRequested = false;
        try
        {
            var config = await _configStore.LoadAsync(_lifetimeCts.Token);
            CacheRootText.Text = config?.CacheRoot ?? "首次启动时选择";
            var result = await _coordinator.RunAsync(_lifetimeCts.Token);
            if (result.CacheRoot is not null)
            {
                CacheRootText.Text = result.CacheRoot;
            }

            switch (result.Outcome)
            {
                case StartupOutcome.Started:
                    AppendLog("质检主程序已启动，启动器即将关闭。" );
                    await Task.Delay(600);
                    Close();
                    break;
                case StartupOutcome.CacheRootUnavailable:
                    restartRequested = await HandleUnavailableCacheAsync(result.Message);
                    break;
                case StartupOutcome.Cancelled:
                    StageText.Text = "已取消";
                    ProgressBar.IsIndeterminate = false;
                    break;
                default:
                    ShowFailure(result.Message);
                    break;
            }
        }
        catch (Exception ex)
        {
            _logger.Error("启动流程失败。", ex);
            ShowFailure(ex.Message);
        }
        finally
        {
            _running = false;
            ChangeCacheButton.IsEnabled = true;
        }

        if (restartRequested && !_lifetimeCts.IsCancellationRequested)
        {
            await StartAsync();
        }
    }

    private async Task<bool> HandleUnavailableCacheAsync(string message)
    {
        ProgressBar.IsIndeterminate = false;
        var choice = MessageBox.Show(
            $"{message}\n\n选择“是”重新选择缓存目录；选择“否”重试原地址；选择“取消”退出。",
            "上次缓存目录不可访问",
            MessageBoxButton.YesNoCancel,
            MessageBoxImage.Warning);
        if (choice == MessageBoxResult.Yes)
        {
            return await SelectNewCacheAsync();
        }
        if (choice == MessageBoxResult.No)
        {
            return true;
        }

        Close();
        return false;
    }

    private async Task<bool> SelectNewCacheAsync()
    {
        if (_coordinator is null)
        {
            return false;
        }
        var result = await _coordinator.SelectAndSaveNewCacheRootAsync(CacheRootText.Text, _lifetimeCts.Token);
        if (result.Action == CacheRootAction.SelectedNew && result.CacheRoot is not null)
        {
            CacheRootText.Text = result.CacheRoot;
            AppendLog($"缓存目录已改为：{result.CacheRoot}");
            return true;
        }
        if (result.Action == CacheRootAction.ReselectRequired)
        {
            MessageBox.Show(result.ErrorMessage ?? "所选缓存目录不可用。", "缓存目录不可用", MessageBoxButton.OK, MessageBoxImage.Warning);
        }
        return false;
    }

    private void ShowFailure(string message)
    {
        StageText.Text = "启动失败";
        DetailText.Text = message;
        ProgressBar.IsIndeterminate = false;
        RetryButton.Visibility = Visibility.Visible;
        AppendLog("错误：" + message);
        _logger.Error(message);
    }

    private void AppendLog(string message)
    {
        _logger.Info(message);
        LogPreview.AppendText($"[{DateTime.Now:HH:mm:ss}] {message}{Environment.NewLine}");
        LogPreview.ScrollToEnd();
    }

    private async void ChangeCacheButton_Click(object sender, RoutedEventArgs e)
    {
        if (await SelectNewCacheAsync())
        {
            await StartAsync();
        }
    }
    private async void RetryButton_Click(object sender, RoutedEventArgs e) => await StartAsync();

    private void CancelButton_Click(object sender, RoutedEventArgs e)
    {
        _lifetimeCts.Cancel();
        Close();
    }

    private void OpenLogButton_Click(object sender, RoutedEventArgs e)
    {
        Process.Start(new ProcessStartInfo { FileName = _logger.LogPath, UseShellExecute = true });
    }

    private static string FormatBytes(double bytes)
    {
        string[] units = { "B", "KB", "MB", "GB" };
        var index = 0;
        while (bytes >= 1024 && index < units.Length - 1)
        {
            bytes /= 1024;
            index++;
        }
        return $"{bytes:F1} {units[index]}";
    }
}
