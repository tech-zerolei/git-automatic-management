# DEB 安装包

版本：应用0.1.0；Debian包0.1.0-1。文件：`git-version-planner_0.1.0-1_all.deb`。

## 下载与安装

从本仓库GitHub Releases下载DEB和SHA256SUMS，放在同一目录：

```bash
sha256sum -c SHA256SUMS
sudo apt install ./git-version-planner_0.1.0-1_all.deb
```

也可用系统软件安装器打开DEB。`apt install` 会按包声明处理依赖，所用系统软件源须提供Python>=3.10、Git>=2.48、Bubblewrap>=0.8、Zenity、xdg-utils；另需桌面浏览器。较旧发行版如软件源Git版本不足，不在本包支持范围，不能强行忽略依赖。

这是独立下载包，不是已纳入Debian/Ubuntu官方仓库的包；未承诺所有发行版兼容。当前仅在开发机Linux/GNOME环境验证应用及隔离安装流程。`Architecture: all` 表示包内没有本机编译二进制，不等于所有CPU/系统已实测。

## 打开

在应用菜单查找 **Git 版本规划（本地版）**，或运行：

```bash
git-version-planner
```

命令也支持 `git-version-planner --no-browser`。DEB自动提供系统菜单项和图标，无需再运行源码的install.sh，也无需保留下载的源码目录。选择仓库、基线、生成/复核/导出等行为与源码版相同，参见USER-GUIDE。

程序不应以root运行。安装需要管理员权限，日常使用不需要。

## 路径和卸载

| 路径 | 用途 |
| --- | --- |
| /usr/bin/git-version-planner | 命令入口 |
| /usr/share/git-version-planner/ | 应用和本地资源 |
| /usr/share/applications/git-version-planner.desktop | 菜单项 |
| /usr/share/icons/hicolor/scalable/apps/git-version-planner.svg | 图标 |
| /usr/share/doc/git-version-planner/ | 使用说明和第三方许可 |

卸载前通过窗口右上角退出，随后：

```bash
sudo apt remove git-version-planner
```

不安装系统服务、钩子或定时任务，不在安装后自动启动，不修改用户项目。源码版先前手动安装的桌面图标不受包管理器控制，若不再使用请自行移除；报告也不会随卸载删除。

## 重建

无需sudo，使用系统Python和dpkg-deb：

```bash
python3 packaging/build_deb.py --output dist
```

输出包及SHA256SUMS；拒绝覆盖已有同名包，可改用新输出目录。默认使用最近Git提交时间，可通过SOURCE_DATE_EPOCH固定时间复现。包不含凭据、仓库元数据、测试夹具或开发机路径；不附维护脚本，不在安装时联网下载应用依赖。

## 本次实际验证

- 38项既有回归通过；桌面入口通过desktop-file-validate。
- 临时dpkg根中安装/配置/卸载成功；核对真实已安装依赖版本，宿主dpkg数据库未变化。
- 安装路径命令启动、HTTP200、认证退出通过；解出的包内程序以普通用户运行，临时Git仓库生成1.0.1并导出JSON通过。
- 本机无免密sudo，没有执行管理员权限的宿主安装。系统拒绝嵌套用户命名空间，因此安装路径启动与包内Git功能分别测试，不将该限制描述为已完成特权主机安装。
- 原始尝试的只读临时挂载路径/嵌套仓库读取曾失败，已修正测试布置并记录限制；未改变应用隔离策略。

开发复验：`python3 -B packaging/test_deb.py dist/git-version-planner_0.1.0-1_all.deb`。依赖本机dpkg、desktop-file-validate与可用Bubblewrap；仅操作自动创建的临时安装根和合成仓库。
