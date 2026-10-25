# 实际验证与证据

## 批次与边界

日期按 Asia/Shanghai。产品尚无构建版本；产品验收 AC-001 至 AC-024 均未执行。以下为 TASK-001/002 的准备核验，不使用“全部验收通过”描述。

本次首个持久批次：[20261025T232846+0800-1a5l3h3w](evidence/20261025T232846+0800-1a5l3h3w/manifest.json)。包含命令参数、工作目录、返回码、stdout/stderr、源码与基线文档 SHA-256、输入 ZIP SHA-256，以及静态宿主 schema。

| 实际检查 / 命令 | 实际结果 | 证据及限制 |
| --- | --- | --- |
| 前轮 `check_spec.py`（补充材料前） | 退出 1：18 处缺失历史 SPEC 引用 | 原始工具输出在聊天记录；STATUS 保留失败事实，没有事后改称初次通过 |
| `revisions.zip` 条目安全检查与文件恢复 | 31 文件；七版 SPEC；与 ZIP 全部逐字节匹配 | ZIP 哈希 `71764814a6e58b6393b77bd56b337080fce59035eea950044916f57746322852`；检查路径穿越/符号链接/冲突覆盖的过程仅有当时聊天工具记录，首批持久证据不独立证明该过程 |
| `python3 /home/gaozikun/.codex/skills/spec-driven/scripts/check_spec.py docs/specs/feat-001-git-version-planner` | 退出 0：当前 5 文档、24 条需求、24 项 AC、0 错误 | spec-check.stdout.txt；不是七版历史全量语义审查 |
| `python3 tools/capability_probe.py` | 退出 0：8 项通过，无跳过 | git-probes.stderr.txt；本机隔离实验，不是产品验收 |
| `git --version` | 退出 0：2.53.0 | git-version.stdout.txt；未声称最低版本兼容 |
| `codex --version` / `codex --help` | 退出 0：0.164.0-alpha.11.1；帮助含插件管理入口 | 对应 stdout；不据此推定桌面扩展能力完整 |
| `codex app-server generate-json-schema --out <临时目录>` | 退出 0；静态事件/动态工具返回结构可导出 | schema-*.json；不是生命周期运行和非模型隔离测试 |
| 需求矩阵与 TASKS 原 AC 映射对比 | 24 行无重复、无遗漏；AC 对应一致 | 主代理实际断言检查；不是行为验证 |
| 工作区 `.git` 存在性检查 | 未创建 | 未在真实工作区执行 init/commit/tag；只在临时合成夹具内写入 Git |

## 探针明细

| 探针 | 断言 | 未覆盖内容 |
| --- | --- | --- |
| P01 | Git 禁用选项可用，NUL 输出保留换行/命令样式文件名 | 产品状态解析、HTML 渲染、全部特殊路径 |
| P02 | 四种读取前后文件内容、mode/size/mtime/ctime 一致 | atime、全部 Git 配置和系统调用副作用 |
| P03 | 带 fsmonitor 配置时此 status 未执行合成助手 | 所有潜在外部助手与生产命令白名单 |
| P04 | linked worktree 的 Git 目录不同、common-dir 相同 | 越界授权、子模块、扫描、产品身份缓存 |
| P05 | unborn HEAD 读取失败，bare 属性为 true | 产品明确错误分类与界面展示 |
| P06 | 固定两提交差集忽略工作树未提交内容 | 复杂 merge DAG、shallow、远端完整图 |
| P07 | 原批次验证缺对象失败、transport 未执行；修复批次增加 strace 断言无额外进程，并用仍禁联网的弱化参数对照检测 fetch 尝试 | 全部传输/凭据助手、PAT/SSH 实现 |
| P08 | strace 对一次 status 的进程树未记录网络 syscall | 非 status 路径、真实远端、模型外发与宿主通道 |

## 尚未执行

真实宿主端到端、双认证远端图、会话/系统安全库、模型隔离、产品安全/竞态/可访问性/性能/安装卸载和全部 AC。未接触真实凭据、未连接真实仓库，未启动持续监控。

## 首轮审查后复验

[修复后批次](evidence/20261025T233850+0800-0uz4qdv3/manifest.json) 不覆盖首批，新增超时进程组清理、严格归档成员核验和结构化探针结果；实际 8 探针通过、0 跳过，10 项回归通过，基线结构检查仍通过。必需探针跳过会返回 INCOMPLETE，不再通过。

独立审查发现、修复对应与复审状态见 [REVIEW.md](REVIEW.md)。本记录不替子代理签署通过。

## 嵌套超时补充复验

首次复审发现 R1 还有“外层先超时、内层进程组仍存活”的窗口，另外四项通过。第二次修复增加层级进程组登记与关闭机制；[最新证据](evidence/20261025T234829+0800-yw8h1y9l/manifest.json) 实际记录 **8 探针通过、0 跳过，11 回归通过**。新增测试专门覆盖外层先超时路径。旧两批次与首轮/首次复审未通过结论全部保留。

同一子代理最终复审确认前置产物通过：原 0.15/0.25 秒反例连续三次通过，晚到注册拒绝、兄弟 scope 不误杀、独立/监督模式 11 回归均通过、监督模式 8 探针无跳过、最新批次哈希匹配。具体记录见 REVIEW.md。全部产品 AC 仍未执行。
