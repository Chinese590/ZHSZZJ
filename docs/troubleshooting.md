# 故障排查

## 上次缓存目录不可访问

选择“重试原地址”“重新选择”或“退出”。程序不会自动把缓存切换到 C 盘。

## GitHub 下载失败

检查代理、防火墙和公司网络。保留 `downloads/*.part` 可在下次启动断点续传。启动器日志位于：

```text
%LOCALAPPDATA%\DataTangQCToolLauncher\logs
```

## SHA256 或大小校验失败

启动器会拒绝安装并删除损坏的临时包。重新启动后重新下载。

## 主程序无法启动

检查用户指定缓存目录下的 `logs/startup_error.log`，以及启动器日志。

## Hugging Face 模型下载失败

不影响基础质检。可在 AI 辅助模型窗口设置自定义 Endpoint 后重试，或删除模型目录后重新下载。
