# 验证记录

验证日期：2026-07-15

## 当前环境已实际执行

```text
PYTHONPATH=desktop/production QT_QPA_PLATFORM=offscreen \
  pytest desktop/tests tests/static -q
结果：107 passed

python -m compileall -q desktop/production/app
结果：通过
```

覆盖范围包括：

- 原有目录扫描、图片读取、指令保存、通过/返修、撤销、历史和 Excel。
- Hugging Face 模型下载与 `pythonw.exe` 无 stderr 场景。
- 本地一致性评分、主体语义可选路径、风险和建议映射。
- OpenAI、Gemini、自定义兼容 API 的双图请求结构和 JSON 解析。
- AI 设置保存、API Key 脱敏、审计日志和结果恢复。
- AI 面板、本地/在线线程、智能触发、采纳标签、采纳备注和清空显示。
- AI 运行期间文件操作隔离与窗口线程生命周期。
- 人工操作记录携带 AI 辅助上下文及“AI辅助统计”工作表。
- 发布工作流、启动器更新契约和必要源码文件静态检查。
- 左手单键、数字键盘、快捷键自定义和冲突检测。
- 文本编辑防误触、Space 通过、X/Enter 返修、Shift+Enter 换行。
- 图片焦点切换、适应窗口、1:1 和键盘缩放。

## 必须由 GitHub Windows runner 执行

- .NET 8 WPF 启动器真实编译。
- xUnit 启动器测试。
- Windows PySide6 界面和 ICC/CMYK/EXIF 显示验证。
- Windows 运行库构建。
- GitHub Release 下载、组件更新、首次安装和离线二次启动。

上述项目已写入 `.github/workflows/release-stable.yml`；任一发布门禁失败都不会创建正式 Release。
