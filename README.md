# 数据堂质检工具：GitHub 在线运行库版

这是一个 Windows 10/11 x64 桌面质检工具。启动器为 .NET 8 WPF 单文件 EXE；首次运行由用户选择程序缓存目录，并从固定 GitHub Releases 下载已校验的 Python/PySide6 运行库与主程序。安装完成后，本地环境健康时直接离线启动，不再访问 GitHub。

## 已实现

- 首次启动选择缓存根目录。
- 缓存地址指针保存到 `%LOCALAPPDATA%\DataTangQCToolLauncher\launcher.json`。
- 第二次启动自动读取保存地址；地址不可访问时提供“重试、重新选择、退出”，不静默切换磁盘。
- GitHub Release `.part` 断点续传、进度、速度、大小与 SHA256 校验。
- 运行库与主程序采用版本目录、staging 解压和原子切换。
- 本地健康环境直接启动，基础功能可断网运行。
- 队列同时读取 `待质检` 与 `待返修`。
- 原图/结果图显示、EXIF 方向、ICC/CMYK 转 sRGB、真实格式、像素、自适应、滚轮缩放、拖动与 1:1。
- 中英文指令可编辑，并按原编码自动写回。
- 通过、不通过、返修备注、删除到回收站、撤销移动和操作日志。
- Excel 人员汇总、不通过明细和总体汇总。
- Hugging Face 模型为显式可选下载，保存到用户指定缓存根目录的 `models/`；下载失败不影响基础质检。
- 可选 `onnx-community/dinov2-small` ONNX 相似度提示，仅供人工参考，不自动判定通过/不通过。

## 缓存目录

```text
用户指定缓存目录/
├─ runtime/
├─ app/
├─ models/
├─ downloads/
├─ logs/
├─ config/
└─ state/
```

业务项目目录与程序缓存完全分离。

## 构建与发布

将源码推送到 GitHub 后，手动运行 `.github/workflows/release-stable.yml`，输入版本号。Windows runner 会：

1. 编译并运行启动器 xUnit 测试。
2. 构建固定依赖的 Windows 运行库。
3. 使用该运行库执行完整 Python/PySide6 测试。
4. 构建应用包与自包含单文件启动器。
5. 生成 `stable-manifest.json`、SHA256 并发布 GitHub Release。

详细说明见 `docs/deployment.md`、`docs/release-process.md` 和 `docs/troubleshooting.md`。

## 当前验证边界

当前生成环境不是 Windows，且没有 .NET SDK，因此本地已执行 Python 业务测试和源码静态检查；WPF 编译、xUnit、PySide6 Windows 界面、GitHub 下载及首次/二次启动必须由仓库中的 Windows GitHub Actions 作为正式发布门禁。
