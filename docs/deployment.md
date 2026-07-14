# 部署说明

## 1. 创建 GitHub 仓库

将本项目完整推送到一个能够创建 Releases 的 GitHub 仓库。启动器只允许从该仓库的 `/releases/download/` 路径下载。

## 2. 运行发布工作流

进入 GitHub → Actions → `Release Stable DataTang QC Tool` → `Run workflow`，输入版本，例如 `1.0.0`。

工作流成功后 Release 包含：

- `DataTangQCTool-Launcher.exe`
- `runtime-win-x64.zip`
- `app.zip`
- `stable-manifest.json`
- `SHA256SUMS.txt`

只需要把 `DataTangQCTool-Launcher.exe` 发给使用人员。

## 3. 首次启动

用户首次启动时选择程序缓存根目录。启动器把地址指针保存到：

```text
%LOCALAPPDATA%\DataTangQCToolLauncher\launcher.json
```

运行库、主程序和可选模型都保存在用户选择的缓存根目录。

## 4. 二次启动

缓存地址有效且运行库健康时，启动器直接启动本地程序，不请求 GitHub 或 Hugging Face。
