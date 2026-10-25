# Git Version Planner 0.1.0 · DEB 安装版

首个Linux本地只读版DEB：安装后直接从应用菜单打开 **Git 版本规划（本地版）**，或运行 `git-version-planner`。无需保留源码目录，无需pip/npm。

## 下载和安装

下载 `git-version-planner_0.1.0-1_all.deb` 与 `SHA256SUMS` 到同一目录：

```bash
sha256sum -c SHA256SUMS
sudo apt install ./git-version-planner_0.1.0-1_all.deb
git-version-planner
```

需要Linux图形桌面、Python>=3.10、Git>=2.48、Bubblewrap>=0.8、Zenity、xdg-utils和浏览器。依赖须可从系统软件源获得；较旧发行版不一定满足。all表示纯Python/前端包，不代表所有CPU或发行版已验证。卸载：`sudo apt remove git-version-planner`。

## 可用功能

- 本地Git工作树选择、状态/标签证据、手动刷新。
- 显式稳定基线/首次版本，SemVer与Conventional Commits建议、稳定/0.x映射。
- breaking说明、未知/merge/revert等复核、人工理由和版本调整。
- Markdown/JSON预览与仓库外导出、陈旧计划失效。
- 中文本地界面、系统菜单/图标；数据不传模型。

## 未实现及限制

不是Codex插件；无自动工作开始/结束触发、PAT/SSH/远端规划、凭据库、多包版本或自动更新。不commit/tag/push、不改版本文件、不执行发布。LFS clean/process、浅历史/include/部分克隆等保守拒绝。标签签名、CI/测试/实际发行及API兼容未知。

每次读取限30秒/16MiB、5000提交和标签。导出要求支持O_TMPFILE的文件系统，不覆盖；不要在导出期间移动目录。Ubuntu/Debian软件源须提供所列依赖，未验证所有系统。

## 验证

38项回归通过；桌面入口校验、临时dpkg根安装/配置/卸载、安装路径启动/HTTP200/认证退出、包内合成Git规划与JSON导出通过。无免密sudo，未进行特权宿主安装；本机嵌套命名空间受限，安装路径启动与包内Git功能分别验证。既有浏览器端到端结果保留。

独立复审按用户要求停止，不宣称复审通过。主项目许可证尚未指定，第三方许可证随包保留。

详见仓库 `docs/DEB.md`、`docs/USER-GUIDE.md`、`docs/FEATURES.md` 和 `SECURITY.md`。
