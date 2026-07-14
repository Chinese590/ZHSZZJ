# 验证记录

验证日期：2026-07-15

## 当前环境已实际执行

```text
python3 -m compileall -q desktop/production desktop/tests
python3 -m pytest tests/static/test_phase1_sources.py -q
结果：22 passed

PYTHONPATH=desktop/production python3 -m pytest \
  desktop/tests/test_scanner.py \
  desktop/tests/test_operations.py \
  desktop/tests/test_reports.py \
  desktop/tests/test_history.py \
  desktop/tests/test_prompt_storage.py \
  desktop/tests/test_startup.py \
  desktop/tests/test_main_entrypoint.py \
  desktop/tests/test_model_manager.py \
  desktop/tests/test_ai_assist.py -q
结果：21 passed
```

最终 ZIP 重新解压后再次执行相同测试，结果仍为 22 + 21 项通过。

## 必须由 GitHub Windows runner 执行

- .NET 8 WPF 启动器真实编译。
- xUnit 启动器测试。
- PySide6 offscreen UI 测试。
- ICC/CMYK/EXIF Windows 图片显示测试。
- Windows 运行库构建。
- GitHub Release 下载、首次安装与断网二次启动。

上述项目已写入 `.github/workflows/release-stable.yml`，任何一项失败都不会创建正式 Release。

## Hugging Face Jobs

已尝试提交 .NET SDK 云编译任务，但 Hugging Face Jobs 返回 HTTP 402（账户预付费余额不足），因此未获得云端编译结果。这不影响 GitHub Actions 构建链路。
