# 本地只读版 0.1.0：验收记录

日期：2026-10-26（Asia/Shanghai）。范围基于 [CHG-002](LOCAL-EDITION.md) 的用户明确同意，**不是原 Codex/GitHub 全量插件验收**。

## 实际产物

- `start.sh`：本机零安装启动；`install.sh`：创建当前用户桌面入口。
- `local_app/core.py`：有界只读 Git 读取、固定提交图、SemVer/CC、人工复核及外部安全导出。
- `local_app/server.py`：只监听 127.0.0.1、随机会话令牌、Host/Origin 校验；单会话数据在内存内，无遥测或模型调用。
- `local_app/static/`：中文操作界面，标签/提交证据、风险、报告预览；全部静态资源本地提供。
- 许可随包：semver 3.0.4 与 Lucide。无运行时下载。

## 验证（首批）

| 检查 | 实际结果 | 限制 |
| --- | --- | --- |
| `python3 -B -m unittest discover -s tests -v` | 29 项通过（18 本地产品测试＋11 既有回归） | Linux/Git 本机，不宣称全平台 |
| `node tests/ui_local_app.cjs` | PASS；读取、显式基线、1.3.0 候选、XSS文本、复核、预览、JSON导出、陈旧失效、退出 | 合成临时仓库，无真实仓库数据 |
| 浏览器请求 | 外部请求 0；页面错误 0 | Chrome headless 实测会话 |
| 桌面/窄屏 | 1280×1000、390×844；无横向溢出；截图已查看 | `local-evidence/desktop.png`、`mobile.png` |
| 启动入口 | start.sh 启动、页面200、认证退出成功 | 本机实际进程 |
| 桌面入口 | 创建 `/home/gaozikun/桌面/Git-Version-Planner.desktop`；gio 查询 `metadata::trusted: true` | 本机 GNOME；不等于其他桌面自动兼容 |

UI 初次运行发现退出后访问已移除 DOM 的错误，已修复并重跑；没有将初次失败改称通过。

## 本版约束

- 手动选择与刷新，不是 Codex 生命周期插件；不提供 PAT/SSH 远端连接。
- 不创建提交/分支/标签，不 clone/fetch/push，也不修改版本文件；测试夹具中的写操作仅在临时目录。
- 不读取子模块内部工作区，界面明确提示；保守拒绝 include、部分克隆、浅历史、外部对象、replace/graft 和不支持的 Git 元数据布局。
- 单操作30秒/16 MiB、5000提交/标签；超限失败，不将不完整数据变成确定版本。此为保护上限，不是原 NFR 性能指标验收。
- 不覆盖已有导出文件；必须另选文件名。报告可能含提交消息，只在用户选择的本机目标保存。
- 会话30分钟无请求退出；显式退出立即清除内存。关闭窗口不立即停止进程，可用退出按钮。

## 独立审查

子代理 Linnaeus（`01a173d3-4e24-7523-8462-f4dd53a45325`）已完成首轮独立审查，真实复现1项P1、3项P2；首轮结论为不通过。以下修复曾提交复审；用户随后明确要求“以最快的速度弄好。不用再审查了”，已关闭子代理并停止复审。修复有实际回归证据，但不宣称独立复审通过。

| 发现 | 修复位置与方式 | 实际回归 |
| --- | --- | --- |
| R1/P1：等长修改触发 clean filter 外部命令 | core.py：拒绝 clean/process；密封配置经校验后以只读挂载用于 status；Bubblewrap 无网络/只读根，不可用时失败 | 等长 clean/process、配置校验后注入、隔离缺失均通过 |
| R2/P2：目标目录移动至仓库仍报告成功 | core.py：O_TMPFILE 无名文件；创建前后及发布前后核对目录；失败撤销本次 inode，不覆盖其他文件 | 创建时移动、link后移动、fsync后移动、O_TMPFILE缺失均通过 |
| R3/P2：旧窗口导出另一份计划 | server.py/app.js：预览/导出强制指纹；文件选择器返回后重查 | 缺失/旧指纹、对话框期间换计划均拒绝；正确计划通过 |
| R4/P2：Markdown遗漏breaking说明 | core.py：独立BREAKING组、完整多行正文、转义、OID | 2.0.0建议、footer详情、多行迁移说明及标签转义通过 |

### 修复验证批次

- `python3 -B -m unittest discover -s tests -v`：38项通过，无跳过（27项本地产品＋11项既有工具回归）。
- `PLANNER_EVIDENCE_DIR=/home/gaozikun/git/CODEX/docs/implementation/local-evidence/review-fix-1 node tests/ui_local_app.cjs`：PASS；外部请求0、页面错误0。
- 证据保存在 `local-evidence/review-fix-1/`，未覆盖首批证据。`unit-tests.txt`、`ui-run.txt`、`ui-results.json`及桌面/窄屏截图。
- 引入隔离后的第一次回归曾因只读 `/dev/null` 导致15项错误；增加隔离内部 `/dev` 后重跑18项通过，再加入9项回归并执行完整38项测试。未将该失败冒充成功。
- 导出检查不是防御任意同用户恶意进程的原子路径锁；不能禁止其他程序随后移动报告或目录。发现移动会取消并撤销本次目标；用户不应在导出期间移动目标目录。

### 本地需求追踪

| 原规划/批准位置 | 修改位置 | 本地实现与验证状态 |
| --- | --- | --- |
| REQ-001/002/005/013，NFR-002本地子集 | core.py；test_local_app.py | 快照、固定图、只读限制已实现并验证 |
| REQ-006—009 | core.py；test_local_app.py | 基线、SemVer/CC、0.x、歧义规则已实现并验证 |
| REQ-004/010/011/016，NFR-001本地子集 | core.py/server.py/static；单测及UI E2E | 人工复核、指纹、非模型呈现已实现并验证 |
| REQ-012、SPEC §5.6 | core.py/server.py/static；导出及breaking回归 | 本地预览与导出已实现并验证；并发目录迁移限制见上 |
| CHG-002一键运行；REQ-014本地子集 | start.sh/install.sh/install_launcher.py | 桌面入口已安装并可信；启动、页面200、空会话、认证退出复核通过 |
| 用户独立子代理审查要求 | 本文件；Linnaeus实际审查 | 首轮未通过，已修复并补测；复审按用户最新要求停止，不宣称通过 |

启动复核证据：`local-evidence/review-fix-1/startup.json`。重新运行 `./install.sh` 成功，`gio info -a metadata::trusted /home/gaozikun/桌面/Git-Version-Planner.desktop` 返回 `true`；未自动读取真实仓库。

**交付判定：已批准范围的本地版实现完成，已执行验证通过；子代理复审按用户要求停止，未宣称通过。原完整插件未完成。**
