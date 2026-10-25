# 功能与原规划对照

更新：2026-10-26。依据：[原0.8-draft规格](specs/feat-001-git-version-planner/01-SPEC.md)、[CHG-002本地版批准](implementation/LOCAL-EDITION.md)、实际代码及[验收记录](implementation/LOCAL-ACCEPTANCE.md)。

原文“本轮只修订文档”是历史语境；用户后来授权本地版实施及本项目发布。发布不为运行中的工具添加远端或Git写能力。

**口径：**已实现仅指批准的本地行为；部分实现不等于原AC全过；未实现没有入口；原完整AC-001至AC-024无整体通过结论。

## 19条功能需求

| 条目 | 状态 | 当前行为/缺口 | 依据 |
| --- | --- | --- | --- |
| REQ-001 仓库识别 | 部分实现 | 手选、Git身份、普通/linked worktree；无宿主候选发现与完整嵌套/子模块验收 | repository；worktree/非仓库测试 |
| REQ-002 状态 | 已实现本地行为 | 分支/HEAD/dirty/冲突/upstream本地计数；子模块内部不读 | repository；状态与UI E2E |
| REQ-003 自动触发 | 未实现原自动化 | 只有手动读取/刷新/退出；无Codex启停/暂停恢复 | server.App；Q-004 |
| REQ-004 隔离与失效 | 部分实现 | 单会话、快照/计划指纹、输入失效；无宿主多来源事件协调 | fresh/require_plan；陈旧测试 |
| REQ-005 失败分类 | 已实现本地保守子集 | 非仓库/bare/无HEAD/超限/不完整/不支持拒绝；无全平台/远端覆盖 | PlannerError；失败路径测试 |
| REQ-006 基线 | 已实现本地行为 | 稳定SemVer/裸或v/可达/确认/首次/歧义；远端无 | make_plan；标签/首次测试 |
| REQ-007 固定图 | 已实现本地行为 | 固定OID、父链、可达差集/去重、排除未提交；远端无 | repository/make_plan；集合测试 |
| REQ-008 提交信号 | 已实现本地行为 | fix/feat/breaking、未知/merge/revert复核、完整证据 | classify；信号测试 |
| REQ-009 版本 | 已实现本地行为 | 稳定/0.x/首次/空集/特殊标签/占用；不递增预发布渠道 | make_plan；版本测试 |
| REQ-010 说明/投影 | 部分实现 | 本地非模型说明、完整breaking；没有Codex模型白名单投影 | report/static；Markdown/XSS |
| REQ-011 复核 | 已实现本地行为 | 理由/版本/指纹/冲突保留；非发布授权 | review_plan；人工/陈旧测试 |
| REQ-012 导出 | 已实现批准的本地替代 | 预览MD/JSON、仓库外、拒绝链接/覆盖；原覆盖确认本版改为始终拒绝 | safe_export；导出/移动测试 |
| REQ-013 只读 | 本地保护已实现，远端无 | 白名单/不写Git/status配置隔离；非任意同用户攻击全证明 | run/status_with_config；过滤器/文件不变测试 |
| REQ-014 宿主界面 | 部分实现 | 中文独立窗口、选择器、桌面入口；非Codex插件 | server/static/launcher；UI/启动证据 |
| REQ-015 策略配置 | 未实现 | 规则和上限固定，无配置/最后有效值/持久化 | core.RULE，无配置入口 |
| REQ-016 风险 | 已实现本地行为 | dirty、签名/CI/测试/发行未知、兼容性限制 | make_plan；界面/报告 |
| REQ-017 GitHub选择 | 未实现 | 无PAT/SSH、目标连接/断开入口 | 本地无需凭据 |
| REQ-018 凭据 | 未实现该功能 | 不接受凭据；无会话/系统库/删除管理 | 发布临时认证不是应用功能 |
| REQ-019 直接远端图 | 未实现 | 无分页/限流/PAT与SSH完整图等价性 | 不以手动clone替代 |

## 5条非功能需求

| 条目 | 状态 | 证据与未覆盖 |
| --- | --- | --- |
| NFR-001 数据/模型 | 本地无模型/无外部页面请求；全量未验收 | 资源本地、内存会话、E2E外部0；无远端与宿主间接模型审计 |
| NFR-002 Git/UI安全 | 本地针对性回归通过，非形式化证明 | 白名单/封存配置/隔离/拒绝过滤器/DOM文本/导出防护；目录竞态边界见SECURITY |
| NFR-003 有界协调 | 部分实现 | 串行会话、上限/失败作废/指纹；无宿主乱序队列/停止取消专项 |
| NFR-004 支持/可访问性 | 部分验证 | 当前Linux/GNOME/Chrome、桌面窄屏/启动；无完整键盘/读屏/跨平台 |
| NFR-005 性能 | 未完整验证 | 30秒/16MiB/5000项为保护上限；无批准基准/冷暖缓存统计 |

## 非目标和后续候选

| 项目 | 状态 |
| --- | --- |
| 自动commit/tag/push/pull/reset/rebase/clean/stash | 原非目标，不提供 |
| 版本文件/changelog写回、GitHub Release/包发布 | 非目标/后续候选，不提供 |
| 自动clone/fetch被分析项目 | 不提供；获取本工具的手动clone不改变边界 |
| 多包独立版本、跨仓库依赖求解、自动回退 | 未实现，无日期承诺 |
| 预发布自动递增、CI集成、API差异分析 | 后续候选，未实现 |
| AI摘要、未来路线图、发行日规划 | 未实现，不按项目名猜测 |
| Windows/macOS包、后台服务、自动更新器 | 未实现，不承诺跨平台 |

当前功能用法见[使用指南](USER-GUIDE.md)，开发复验见[DEVELOPMENT.md](DEVELOPMENT.md)。未实现项没有可用配置或受支持用法，不需提供密钥。原完整Q-004和历史证据保留在[STATUS](implementation/STATUS.md)。
