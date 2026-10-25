# 本次需求—产物—验收追踪

> 下表保留原完整插件前置阶段的历史口径。2026-10-26用户另行批准的本地版已实现并测试；当前逐项状态见 [功能对照](../FEATURES.md) 和 [本地验收](LOCAL-ACCEPTANCE.md)。不将本地子集标为原完整AC通过。

基线：[SPEC 0.8-draft](../specs/feat-001-git-version-planner/01-SPEC.md) 第 4、7、8 节；任务映射原文：[TASKS 第 3 节](../specs/feat-001-git-version-planner/03-TASKS.md#3-全量需求覆盖)。不变更原定范围。

`P01` 至 `P08` 指 `tools/capability_probe.py` 的隔离能力实验，仅提供 TASK-002 的局部证据。所有下列产品项仍为**未实施，产品验收未执行**；“无”不是删除需求。拟新增模块来自 PLAN，不冒充现有实现。

| 原条目 | 原任务 / AC | 对应产品模块（尚未实现） | 本次可复核证据 | 仍需执行的验收要点 |
| --- | --- | --- | --- | --- |
| REQ-001 | TASK-004 / AC-001 | HostAdapter、GitReadAdapter | P04 仅验证 worktree 身份基础 | 批准边界、候选发现、嵌套/子模块/符号链接 |
| REQ-002 | TASK-005 / AC-002 | GitReadAdapter | P01 仅验证 NUL 状态原始格式 | 状态解析、冲突、detached、upstream 未知与本地计数 |
| REQ-003 | TASK-006 / AC-003 | DetectionCoordinator、HostAdapter | 本机静态协议结构，不是事件运行证据 | 真实开始/结束、暂停恢复、失败可见、无持续监控 |
| REQ-004 | TASK-006 / AC-004 | DetectionCoordinator | 无 | 乱序、取消、身份隔离、陈旧确认失效 |
| REQ-005 | TASK-007 / AC-005 | GitReadAdapter | P05、P07 仅验证底层错误可观察 | 产品错误分类、浅历史、缺对象、权限和中途变化 |
| REQ-006 | TASK-008 / AC-006 | ReleaseAnalyzer | 无 | SemVer 可达基线、显式确认、歧义、initialVersion |
| REQ-007 | TASK-009 / AC-007 | ReleaseAnalyzer | P06 仅验证两提交固定差集 | 多父 DAG、去重、完整性和两通道远端等价 |
| REQ-008 | TASK-010 / AC-008 | ReleaseAnalyzer | 无 | CC 信号、未知/merge/revert 保留与复核 |
| REQ-009 | TASK-011 / AC-009 | ReleaseAnalyzer | 无 | major≥1 与 0.x 映射、预发布/首次版本/空集 |
| REQ-010 | TASK-012 / AC-010 | PlanReview、ModelSummaryProjector | 无 | 确定性非模型说明、来源/证据、白名单投影 |
| REQ-011 | TASK-012 / AC-011 | PlanReview | 无 | 当前指纹确认、调整理由、版本冲突与失效 |
| REQ-012 | TASK-014 / AC-012 | ExportWriter、HostAdapter | 无 | 外部目标、预览、覆盖确认、链接/竞态/写失败 |
| REQ-013 | TASK-003 / AC-013 | GitReadAdapter、GitHubReadAdapter | P02、P03、P07、P08 局部只读实验 | 全路径本地副作用及远端只读审计；不得 clone/fetch |
| REQ-014 | TASK-015 / AC-014 | HostAdapter、NonModelReportView | 无 | 真实宿主完整交互、非模型详情/安全输入/导出 |
| REQ-015 | TASK-013 / AC-015 | PolicyAndConfig | 无 | 非法配置保留最后有效项、持久化、策略失效 |
| REQ-016 | TASK-012 / AC-016 | PlanReview | 无 | 仓库风险与未知 CI/测试/发布状态分离 |
| REQ-017 | TASK-019 / AC-022 | HostAdapter、GitHubReadAdapter | 无 | 本地可跳过、PAT/SSH、逐次明确选择、禁止跨通道 |
| REQ-018 | TASK-020 / AC-023 | CredentialBroker | 无 | 非模型输入、会话/安全库、断开/删除、既有身份保护 |
| REQ-019 | TASK-021 / AC-024 | GitHubReadAdapter | 无 | 两通道无克隆完整图、固定对象、分页/限流/取消 |
| NFR-001 | TASK-016 / AC-017 | ModelSummaryProjector、专项审计 | 无 | 假秘密及直接/间接模型通道、日志/通知/widget 隔离 |
| NFR-002 | TASK-003、016 / AC-018 | GitReadAdapter、界面与专项审计 | P01、P03、P07 局部进程边界 | 产品白名单、恶意元数据/UI、全部助手与副作用 |
| NFR-003 | TASK-016 / AC-019 | DetectionCoordinator | 无 | 队列/并发有界、取消、确定性与故障恢复 |
| NFR-004 | TASK-017 / AC-020 | HostAdapter、交付验证 | 仅记录当前 Linux/Git/CLI 版本 | 经批准矩阵、安装卸载、键盘/焦点/可访问性 |
| NFR-005 | TASK-017 / AC-021 | 性能验证 | 无；探针超时不是产品预算 | 批准样本/设备/阈值、冷暖缓存、超预算语义 |

## 前置工作与文件

| 条目 | 实际修改位置 | 状态 | 验证 |
| --- | --- | --- | --- |
| TASK-001 材料与追踪 | 原始五份文档、revisions/、本文件 | 材料齐备，产品技术评审未完成 | 两个 ZIP 与提取文件逐字节比对；check_spec.py |
| TASK-002 隔离能力实验 | tools/capability_probe.py | 实验已实现，非 GitReadAdapter | P01—P08；临时仓库内准备/销毁 |
| TASK-002 证据留存 | tools/verify_preflight.py、evidence/ | 运行日志、源码哈希与命令记录 | 每次新建证据目录，不覆盖旧批次 |
| Q-004 能力缺口 | CAPABILITIES.md、STATUS.md | 未关闭 | 区分静态结构、局部实验与端到端能力 |

不得因本次实验通过将 TASK-003、TASK-016、TASK-018 或任一完整 AC 标为通过。
