# 开发与复验

Python标准库HTTP加HTML/CSS/JavaScript，semver/Lucide随包。仅127.0.0.1，不是公网服务器；运行无需Node，Node/Playwright仅测试。

| 文件 | 职责 |
| --- | --- |
| local_app/core.py | 有界Git、配置隔离、快照、规则、复核、报告、导出 |
| local_app/server.py | 会话HTTP、安全校验、对话框、失效 |
| local_app/static/ | 中文界面，本地资源 |
| local_app/install_launcher.py | 当前用户桌面入口，拒绝冲突覆盖 |
| tests/test_local_app.py | 合成临时Git功能/失败/安全回归 |
| tests/test_preflight.py | 前置工具回归，不是完整插件验收 |
| tools/ | 前置能力实验和追加证据，不参与日常启动 |

## 单测

```bash
python3 -B -m unittest discover -s tests -v
```

38项基线：27产品＋11前置工具，无跳过。测试需要本机Git、Bubblewrap、strace和Linux /proc。Git写操作仅临时合成夹具，不动真实项目。

产品子集：`python3 -B -m unittest discover -s tests -p test_local_app.py -v`。

## 浏览器E2E

需Node.js、Playwright和Chrome/Chromium；这些不是产品启动依赖。

```bash
npm install --no-save --package-lock=false playwright
node tests/ui_local_app.cjs
```

已有其他位置依赖时：

```bash
PLAYWRIGHT_MODULE=/absolute/path/to/playwright PLANNER_BROWSER=/usr/bin/google-chrome PLANNER_EVIDENCE_DIR=/tmp/git-planner-ui-evidence node tests/ui_local_app.cjs
```

创建临时仓库、启动服务、操作无头浏览器后清理。测试浏览器带 `--no-sandbox`，仅用于受控合成环境；产品入口不带该参数。页面外部请求0不是浏览器后台全部网络行为审计。

## 原前置探针

`python3 tools/capability_probe.py`：8项临时夹具实验，不等于完整插件。

原ZIP与规格结构复验另需原附件及外部检查器：

```bash
python3 tools/verify_preflight.py   --spec-checker /absolute/path/to/check_spec.py   --baseline-archive /absolute/path/to/codex.zip   --revisions-archive /absolute/path/to/revisions.zip
```

仓库保留原文和历史证据，不保证这些外部文件在其他机器可用；每次新增证据批次，不覆盖失败。

## 发布

维护者在工具外发布本项目，不为应用新增Git写权限。不要发布用户项目数据或凭据；保留远端历史，只快进、不force。文档不新增远端功能，不将原规划改为全过。后续子代理复审按用户要求停止。

主项目许可证待维护者明确，不擅自选许可证；第三方许可保留。
