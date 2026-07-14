# 数据堂质检工具：GitHub 在线运行库版

这是一个面向 Windows 10/11 x64 的图片质检桌面工具。启动器为 .NET 8 WPF 单文件 EXE；首次运行由用户选择程序缓存目录，并从固定 GitHub Releases 下载经过 SHA256 校验的 Python/PySide6 运行库和主程序。后续启动会检测新版本，用户确认后直接更新发生变化的组件；网络不可用时仍可使用本地健康版本。

## 已实现

- 首次启动选择缓存根目录，地址指针保存到 `%LOCALAPPDATA%\DataTangQCToolLauncher\launcher.json`。
- 缓存地址不可访问时提供“重试、重新选择、退出”，不静默切换磁盘。
- GitHub Release `.part` 断点续传、真实进度、速度、大小和 SHA256 校验。
- 检测到新版时弹窗提示；确认后自动下载、安装并启动，只更新变化的主程序或运行库。
- 队列读取 `待质检` 与 `待返修`，通过后移入 `质检完成`，不通过后写入返修备注并移入 `待返修`。
- 原图/结果图显示，支持 EXIF 方向、ICC/CMYK 转 sRGB、真实格式、像素、自适应、滚轮缩放、拖动和 1:1。
- 中文、英文指令可编辑，并按原编码自动写回原 TXT 文件。
- 删除到回收站、撤销移动、操作日志和 Excel 汇总。

## AI 一致性质检助手

AI 功能直接集成在原质检界面中，用于比较原图与结果图，辅助发现：

- 主体不一致、数量或轮廓错误。
- 畸形、结构变形、部件错位和透视异常。
- 纹理、配件、边缘等关键细节丢失。
- 主体颜色、材质和局部色彩错误。
- 文字或 Logo 拼写、形态、位置及缺失问题。
- 背景不符合指令、模糊、重影、破图和其他生成瑕疵。
- 主体占比、遮挡、留白和版面不协调。

### 本地初筛

可选语义模型从 Hugging Face 下载并缓存在用户选择的 `models/` 目录。

- 默认切换数据组后执行本地检测。
- 使用主体区域、结构边缘、颜色分布、细节密度、清晰度和版面位置进行快速评分。
- 安装可选 `onnx-community/dinov2-small` 后，增加主体语义相似度。
- 文字/Logo 内容和指令语义不会由本地像素规则强行判定，会明确标记为“未检测”。

### 在线深度复核

支持三种提供商：

- OpenAI Responses API。
- Gemini `generateContent` API。
- OpenAI 兼容的自定义 `/chat/completions` API。

在线复核同时读取原图、结果图、中英文指令及本地初筛结果，返回一致性评分、风险等级、八项检测结果、问题标签、返修建议和“建议通过 / 建议复核 / 建议返修”。中高风险可智能触发，也可手动点击“在线深度复核”。在线调用会把两张图片和指令发送给用户选择的服务商。

### 人工最终决定

AI 只提供辅助建议：

- 可以自动推荐或人工采纳问题标签和返修备注。
- 不会自动点击通过或不通过。
- 不会自动删除、移动或修改数据组。
- 人工备注不会被 AI 静默覆盖。

AI 检测记录写入项目目录的 `.质检工具/ai_review_log.jsonl`，不记录 API Key。Excel 增加“AI辅助统计”工作表及人员 AI 检测汇总字段。

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

将源码推送到 GitHub 后，手动运行 `.github/workflows/release-stable.yml` 并填写版本号。Windows runner 会：

1. 编译并运行启动器 xUnit 测试。
2. 构建固定依赖的 Windows 运行库。
3. 使用打包运行库执行完整 Python、PySide6 和静态契约测试。
4. 构建应用包与自包含单文件启动器。
5. 生成 `stable-manifest.json`、SHA256 并发布 GitHub Release。

详细说明见 `docs/deployment.md`、`docs/release-process.md`、`docs/troubleshooting.md` 和 `docs/AI_CONSISTENCY_REVIEW.md`。

## 验证边界

当前开发环境不是 Windows。Python 业务、PySide6 无头界面、静态契约和语法编译可在当前环境验证；WPF 启动器编译、xUnit、Windows 图片色彩显示、发布下载和自动更新由仓库中的 Windows GitHub Actions 作为正式发布门禁。
