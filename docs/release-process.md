# 正式发布流程

1. 所有变更提交到功能分支。
2. 确认本地静态测试与非 UI 业务测试通过。
3. 推送到 GitHub。
4. 运行 `Release Stable DataTang QC Tool`。
5. Windows runner 必须通过：
   - `dotnet test`
   - `pytest tests/static desktop/tests -v`
   - runtime/app/launcher 构建
6. 下载 Actions artifact，先在一台无 Python 的 Windows 电脑测试首次安装。
7. 断网后第二次启动，确认不会重新下载。
8. 再将 Release 中的启动器分发给团队。

禁止直接分发源码目录、`.venv` 或任意电脑已经生成的缓存目录。
