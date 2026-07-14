using System.Net.Http.Headers;
using System.Windows;
using DataTangQCTool.Launcher.Models;
using DataTangQCTool.Launcher.Services;

namespace DataTangQCTool.Launcher;

public partial class App : Application
{
    private LauncherLogger? _logger;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        _logger = new LauncherLogger();
        DispatcherUnhandledException += (_, args) =>
        {
            _logger.Error("未处理的界面异常。", args.Exception);
            MessageBox.Show($"启动器发生异常：{args.Exception.Message}\n\n日志：{_logger.LogPath}", "数据堂质检工具", MessageBoxButton.OK, MessageBoxImage.Error);
            args.Handled = true;
        };

        try
        {
            var settings = LauncherBootstrapSettings.LoadEmbedded(typeof(App).Assembly);
            var httpClient = new HttpClient { Timeout = TimeSpan.FromMinutes(30) };
            httpClient.DefaultRequestHeaders.UserAgent.Add(new ProductInfoHeaderValue("DataTangQCTool-Launcher", "1.0.0"));

            var configStore = new LauncherConfigStore();
            var selector = new CacheRootSelector(new WpfFolderPicker(), new CacheRootValidator());
            var manifestClient = new ReleaseManifestClient(httpClient, settings.ManifestUri, settings.AllowedReleasePrefixUri);
            var downloader = new ResumableDownloadService(httpClient, new ReleaseUrlPolicy(settings.AllowedReleasePrefix));
            var processRunner = new ProcessRunner();
            var healthChecker = new RuntimeHealthChecker(processRunner);
            var window = new MainWindow(_logger);
            var coordinator = new StartupCoordinator(
                configStore,
                selector,
                manifestClient,
                downloader,
                new PackageInstaller(),
                healthChecker,
                new ApplicationLauncher(),
                window);
            window.AttachCoordinator(coordinator, configStore);
            MainWindow = window;
            window.Show();
        }
        catch (Exception ex)
        {
            _logger.Error("启动器初始化失败。", ex);
            MessageBox.Show($"启动器初始化失败：{ex.Message}\n\n日志：{_logger.LogPath}", "数据堂质检工具", MessageBoxButton.OK, MessageBoxImage.Error);
            Shutdown(1);
        }
    }
}
