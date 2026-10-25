"""Offline, bounded local repository planning. No Git writes or remote calls."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from semver import Version


GIT = "/usr/bin/git"
MAX_ITEMS = 5000
MAX_BYTES = 16 * 1024 * 1024
TIMEOUT = 30
RULE = "local-0.1/semver-cc-conservative"
FLAGS = ["--no-pager", "--no-optional-locks", "--no-lazy-fetch",
         "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
         "-c", "core.untrackedCache=false", "-c", "core.preloadIndex=false",
         "-c", "protocol.allow=never", "-c", "maintenance.auto=false",
         "-c", "gc.auto=0", "-c", "diff.external=", "-c", "core.pager=cat"]
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "XDG_CONFIG_HOME": "/nonexistent",
       "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
       "GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat"}
ALLOWED = {"rev-parse", "config", "status", "for-each-ref", "log", "rev-list", "worktree"}


class PlannerError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def fail(code, message):
    raise PlannerError(code, message)


def version(text):
    if not isinstance(text, str) or not text or len(text) > 128:
        fail("version", "请输入合法 SemVer 版本，例如 1.2.3。")
    try:
        return Version.parse(text)
    except ValueError:
        fail("version", "版本必须符合 SemVer，且不能带 v 前缀或前导零。")


def run(args, cwd, deadline=None, optional=False, *, pass_fds=(), config_view=None):
    if args[0] not in ALLOWED or (args[0] == "worktree" and args[1:] != ["list", "--porcelain", "-z"]):
        fail("operation", "不允许的 Git 操作。")
    end = min(deadline or time.monotonic() + TIMEOUT, time.monotonic() + TIMEOUT)
    if time.monotonic() >= end:
        fail("timeout", "读取超过 30 秒，未生成完整结果。")
    command = [GIT, *FLAGS, *args]
    env = ENV.copy()
    if config_view:
        config_fd, root, gitdir, common = config_view
        # Pin the validated configuration, including during concurrent config edits.
        # The explicit common directory prevents a changed commondir redirect.
        env["GIT_COMMON_DIR"] = str(common)
        command = ["/usr/bin/bwrap", "--ro-bind", "/", "/", "--unshare-net",
                   "--unshare-pid", "--proc", "/proc", "--dev", "/dev", "--die-with-parent",
                   "--ro-bind-data", str(config_fd), str(common / "config"),
                   "--", GIT, *FLAGS, "--git-dir=" + str(gitdir),
                   "--work-tree=" + str(root), *args]
        pass_fds = (config_fd,)
    try:
        p = subprocess.Popen(command, cwd=cwd, env=env, pass_fds=pass_fds,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        fail("git_unavailable", "Git 不可用，或所选目录无法访问。")
    chunks = {"out": bytearray(), "err": bytearray()}
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(p.stdout, selectors.EVENT_READ, "out")
            selector.register(p.stderr, selectors.EVENT_READ, "err")
            while selector.get_map():
                left = end - time.monotonic()
                if left <= 0:
                    fail("timeout", "读取超过 30 秒，未生成完整结果。")
                for key, _ in selector.select(min(left, 0.1)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                    else:
                        chunks[key.data].extend(data)
                        if len(chunks["out"]) + len(chunks["err"]) > MAX_BYTES:
                            fail("limit", "元数据超过 16 MiB，无法保证完整性。")
            code = p.wait(timeout=max(0.01, end - time.monotonic()))
        if code and not optional:
            fail("git_read", "Git 读取失败：可能存在缺失对象、权限问题或不支持的仓库格式。")
        return bytes(chunks["out"]) if code == 0 else None
    except subprocess.TimeoutExpired:
        fail("timeout", "Git 读取超时，结果未采用。")
    finally:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        p.stdout.close()
        p.stderr.close()


def text(raw):
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        fail("encoding", "元数据不是有效 UTF-8；本版不能无损展示，已停止规划。")


def tag_version(ref):
    label = ref.removeprefix("refs/tags/")
    label = label[1:] if label.startswith("v") else label
    try:
        return Version.parse(label) if len(label) <= 128 else None
    except ValueError:
        return None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def status_with_config(root, gitdir, common, deadline):
    """Validate immutable bytes and use those exact bytes for content conversion."""
    fd = os.memfd_create("planner-config", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        source = os.open(common / "config", os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(source, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                fail("unsafe_layout", "Git 配置不是普通文件。")
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: fail("limit", "Git 配置超过读取上限。")
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(raw)
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW |
                    fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        config = run(["config", "--file", f"/proc/self/fd/{fd}", "--no-includes", "--null", "--list"],
                     root, deadline, pass_fds=(fd,))
        validate_config(config)
        result = run(["status", "--porcelain=v2", "--branch", "-z", "--untracked-files=normal", "--ignore-submodules=all"],
                     root, deadline, config_view=(fd, root, gitdir, common))
        return result, config
    except OSError:
        fail("unsafe_layout", "无法隔离 Git 配置或状态读取；本版不会降级为不隔离执行。")
    finally:
        os.close(fd)


def validate_config(config):
    for item in config.split(b"\0"):
        key = item.split(b"\n", 1)[0].lower()
        if key.startswith(b"filter.") and key.endswith((b".clean", b".process")):
            fail("unsupported_config", "仓库配置了 clean/process 过滤器；为避免执行外部命令，本版拒绝读取。")
        if (key.startswith((b"include.", b"includeif.", b"extensions."))
                or key.endswith((b".promisor", b".partialclonefilter")) or key == b"core.worktree"):
            if key == b"extensions.objectformat" and item.endswith(b"\nsha256"):
                continue
            fail("unsupported_config", "仓库含 include、扩展、替代工作树或部分克隆配置；本版不自动降级读取。")


def repository(path):
    if not isinstance(path, str) or not path or len(path) > 4096 or any(ord(c) < 32 for c in path):
        fail("path", "请选择一个本地 Git 工作树。")
    selected = Path(path).expanduser()
    if not selected.is_absolute() or not selected.is_dir():
        fail("path", "请选择可访问的绝对目录路径。")
    end = time.monotonic() + TIMEOUT
    cwd = selected.resolve()
    bare = run(["rev-parse", "--is-bare-repository"], cwd, end, True)
    if bare is None:
        fail("not_repository", "所选目录不是可访问或可信的 Git 工作树。")
    if bare.strip() == b"true":
        fail("bare", "裸仓库没有工作树，本版本不支持。")
    root = Path(text(run(["rev-parse", "--show-toplevel"], cwd, end)).strip()).resolve()
    gitdir = Path(text(run(["rev-parse", "--absolute-git-dir"], root, end)).strip()).resolve()
    common = Path(text(run(["rev-parse", "--path-format=absolute", "--git-common-dir"], root, end)).strip()).resolve()
    for base in {gitdir, common}:
        for name in ["config", "config.worktree", "index", "HEAD", "objects", "refs", "packed-refs"]:
            if (base / name).is_symlink():
                fail("unsafe_layout", "关键 Git 元数据为符号链接，本版安全拒绝。")
        for name in ["info/grafts", "objects/info/alternates", "objects/info/http-alternates", "shallow"]:
            if (base / name).exists():
                fail("incomplete", "存在浅历史、graft 或外部对象依赖，不能证明原始完整提交图。")
    config = run(["config", "--local", "--no-includes", "--null", "--list"], root, end)
    validate_config(config)
    if run(["for-each-ref", "--format=%(refname)", "refs/replace/"], root, end).strip():
        fail("replaced_history", "存在 replace refs，不能将改写图当作原始历史。")
    before = run(["rev-parse", "--verify", "HEAD"], root, end, True)
    head = text(before).strip() if before else None
    status_raw, status_config = status_with_config(root, gitdir, common, end)
    if config != status_config: fail("stale", "读取期间 Git 配置变化，请重新刷新。")
    status = {"branch": None, "upstream": None, "ahead": None, "behind": None,
              "staged": 0, "unstaged": 0, "untracked": 0, "conflicts": 0}
    entries = status_raw.split(b"\0")
    i = 0
    while i < len(entries):
        line = entries[i]; i += 1
        if line.startswith(b"# branch.head "):
            status["branch"] = text(line[14:])
        elif line.startswith(b"# branch.upstream "):
            status["upstream"] = text(line[18:])
        elif line.startswith(b"# branch.ab "):
            a, b = line[12:].split()
            status["ahead"], status["behind"] = int(a), -int(b)
        elif line.startswith((b"1 ", b"2 ")):
            xy = line.split(b" ", 2)[1]
            status["staged"] += xy[0:1] != b"."
            status["unstaged"] += xy[1:2] != b"."
            if line.startswith(b"2 "):
                i += 1
        elif line.startswith(b"? "):
            status["untracked"] += 1
        elif line.startswith(b"u "):
            status["conflicts"] += 1
    fmt = "%(refname)%00%(objectname)%00%(*objectname)%00%(objecttype)%00%(*objecttype)"
    refs_raw = run(["for-each-ref", "--format=" + fmt, "refs/tags/"], root, end)
    ref_rows = [row.split(b"\0") for row in refs_raw.splitlines()]
    if len(ref_rows) > MAX_ITEMS:
        fail("limit", "标签超过 5000 个，未生成完整结果。")
    commits = []
    if head:
        raw = run(["log", "--no-show-signature", "--no-decorate", "--max-count=5001", "-z", "--format=%H%x00%P%x00%B", head, "--"], root, end)
        parts = raw.split(b"\0")
        if parts and parts[-1] == b"": parts.pop()
        if len(parts) % 3:
            fail("encoding", "提交元数据格式异常，已停止规划。")
        for n in range(0, len(parts), 3):
            commits.append({"oid": text(parts[n]), "parents": text(parts[n+1]).split(), "message": text(parts[n+2])})
        if len(commits) > MAX_ITEMS:
            fail("limit", "提交超过 5000 个，无法证明本版范围完整。")
    graph = {c["oid"] for c in commits}
    if any(p not in graph for c in commits for p in c["parents"]):
        fail("incomplete", "提交父链缺失，不生成确定版本。")
    tags = []
    for fields in ref_rows:
        ref, oid, peeled, kind, peeled_kind = map(text, fields)
        commit = oid if kind == "commit" else peeled if peeled_kind == "commit" else None
        v = tag_version(ref)
        tags.append({"ref": ref, "object": oid, "commit": commit, "annotated": kind == "tag",
                     "version": str(v) if v else None, "reachable": commit in graph,
                     "stable": bool(v and not v.prerelease and not v.build), "signature": "未验证"})
    worktrees = run(["worktree", "list", "--porcelain", "-z"], root, end)
    protected = {str(root), str(gitdir), str(common)}
    for field in worktrees.split(b"\0"):
        if field.startswith(b"worktree "):
            protected.add(str(Path(text(field[9:])).resolve()))
    after = run(["rev-parse", "--verify", "HEAD"], root, end, True)
    final_status, final_config = status_with_config(root, gitdir, common, end)
    if before != after or config != final_config or refs_raw != run(["for-each-ref", "--format=" + fmt, "refs/tags/"], root, end) or status_raw != final_status:
        fail("stale", "读取期间仓库变化，请刷新后重新确认。")
    snap = {"root": str(root), "gitdir": str(gitdir), "common": str(common), "head": head,
            "status": status, "tags": sorted(tags, key=lambda t:t["ref"]), "commits": commits,
            "protected": sorted(protected), "rule": RULE}
    snap["fingerprint"] = fingerprint({**snap, "raw_status": status_raw.hex(), "config": config.hex()})
    snap["capturedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    return snap


def classify(commit):
    lines = commit["message"].splitlines()
    title = lines[0] if lines else ""
    match = re.fullmatch(r"([a-zA-Z][a-zA-Z0-9_-]*)(?:\(([^()\r\n]+)\))?(!)?: (\S.*)", title)
    kind = match.group(1) if match else "unknown"
    breaking = bool(match and match.group(3)) or bool(re.search(r"\n\n(?:[\s\S]*\n)?BREAKING(?: CHANGE|-CHANGE): \S", commit["message"]))
    reviews = []
    if not match: reviews.append("非规范提交")
    if kind not in {"fix", "feat"}: reviews.append("未映射类型" if kind != "revert" else "revert 需要复核")
    if len(commit["parents"]) > 1: reviews.append("merge 需要复核")
    if title.startswith("Revert "): reviews.append("revert 需要复核")
    return {**commit, "title": title, "type": kind, "breaking": breaking,
            "signal": "breaking" if breaking else kind if kind in {"fix", "feat"} else "none", "reviews": reviews}


def make_plan(snap, baseline, initial):
    if not snap["head"]:
        fail("unborn", "仓库尚无提交，无法生成版本计划。")
    candidates = [t for t in snap["tags"] if t["reachable"] and t["stable"]]
    reasons = []
    baseline_tag = None
    initial_v = None
    if candidates:
        baseline_tag = next((t for t in candidates if t["ref"] == baseline), None)
        if not baseline_tag:
            fail("baseline", "请显式选择并确认一个可达稳定标签。")
        base_version = version(baseline_tag["version"])
        excluded = set()
        graph = {c["oid"]: c for c in snap["commits"]}
        queue = [baseline_tag["commit"]]
        while queue:
            oid = queue.pop()
            if oid in excluded: continue
            excluded.add(oid)
            queue.extend(graph[oid]["parents"])
        selected = [c for c in snap["commits"] if c["oid"] not in excluded]
    else:
        initial_v = version(initial)
        base_version = None
        selected = snap["commits"]
        if len([c for c in selected if not c["parents"]]) != 1:
            reasons.append("首次版本历史不是单一完整根")
        if initial_v.prerelease or initial_v.build:
            reasons.append("首次版本含预发布或构建元数据")
    normalized = Counter(t["version"] for t in snap["tags"] if t["version"])
    if any(n > 1 for n in normalized.values()): reasons.append("标签存在重复归一版本，需要复核")
    if any(t["reachable"] and t["version"] and not t["stable"] for t in snap["tags"]):
        reasons.append("可达标签涉及预发布或构建元数据")
    evidence = sorted((classify(c) for c in selected), key=lambda c:c["oid"])
    if any(c["reviews"] for c in evidence): reasons.append("存在非规范、未映射、merge 或 revert 提交")
    signals = {c["signal"] for c in evidence}
    bump = "none"
    proposed = None
    if evidence:
        if initial_v is not None:
            proposed = str(initial_v)
            bump = "initial"
        elif "breaking" in signals:
            bump = "major" if base_version.major else "minor"
        elif "feat" in signals: bump = "minor"
        elif "fix" in signals: bump = "patch"
        if base_version and bump != "none": proposed = str(getattr(base_version, "bump_" + bump)())
    occupied = {t["version"] for t in snap["tags"] if t["version"]}
    if proposed in occupied: reasons.append("候选版本已被本地标签占用")
    if snap["status"]["conflicts"]: reasons.append("工作树存在冲突")
    risks = ["标签签名未验证；标签不证明已发布", "CI、测试、发布状态未知", "提交描述不证明 API 兼容性", "子模块工作区内部状态不读取；仅分析所选项目提交"]
    if any(snap["status"][k] for k in ["staged", "unstaged", "untracked", "conflicts"]):
        risks.append("未提交内容未纳入版本计算")
    if any(t["version"] and not t["commit"] for t in snap["tags"]):
        reasons.append("存在无法直接解析到提交的版本标签")
    state = "needs_review" if reasons else "suggested" if proposed else "no_release"
    plan = {"schemaVersion": 1, "ruleVersion": RULE, "source": "local", "repositoryAlias": "所选本地仓库",
            "head": snap["head"], "snapshotFingerprint": snap["fingerprint"], "capturedAt": snap["capturedAt"],
            "baseline": baseline_tag, "initialVersion": str(initial_v) if initial_v else None,
            "status": state, "bump": bump, "candidateVersion": proposed if state == "suggested" else None,
            "provisionalCandidate": proposed, "reviewReasons": sorted(set(reasons)), "risks": risks,
            "commits": evidence, "manualReview": None, "releaseAuthorized": False}
    plan["planFingerprint"] = fingerprint(plan)
    return plan


def review_plan(plan, snap, override, reason):
    if plan["snapshotFingerprint"] != snap["fingerprint"]:
        fail("stale", "仓库已变化，旧计划和确认已失效。请刷新后重新生成。")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        fail("reason", "请填写复核理由，最多 2000 字。")
    updated = json.loads(json.dumps(plan))
    if override:
        v = version(override)
        if plan["baseline"] and v <= version(plan["baseline"]["version"]):
            fail("version", "人工版本必须高于基线版本。")
        if any(t["version"] == str(v) for t in snap["tags"]):
            fail("occupied", "人工版本已被本地标签占用。")
        updated["reviewReasons"] = sorted(set(updated["reviewReasons"] + ["人工版本调整，保留规则建议供复核"]))
        updated["status"] = "needs_review"
        updated["candidateVersion"] = None
    updated["manualReview"] = {"reason": reason.strip(), "overrideVersion": override or None,
                               "snapshotFingerprint": snap["fingerprint"], "reviewedAt": datetime.now().astimezone().isoformat(timespec="seconds")}
    updated["planFingerprint"] = fingerprint({k:v for k,v in updated.items() if k != "planFingerprint"})
    return updated


def report(plan, kind):
    if kind == "json": return json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if kind != "md": fail("format", "仅支持 Markdown 或 JSON。")
    def escape(s):
        return re.sub(r"([\\`*_{}\[\]()#+.!<>|~-])", r"\\\1", str(s)).replace("\r", "")
    lines = ["# 本地版本规划报告", "", "仅为提案，不构成发布授权。", "", "- 状态：" + plan["status"],
             "- 规则：" + plan["ruleVersion"], "- HEAD：" + plan["head"],
             "- 快照：" + plan["snapshotFingerprint"], "- 基线：" + escape(plan["baseline"]["ref"] if plan["baseline"] else "首次版本"),
             "- 候选：" + str(plan["candidateVersion"] or "无确定候选"),
             "- 暂定候选：" + str(plan["provisionalCandidate"] or "无"), "", "## 风险与复核"]
    lines += ["- " + escape(r) for r in plan["risks"] + plan["reviewReasons"]]
    if plan["manualReview"]:
        lines += ["", "## 人工复核", escape(plan["manualReview"]["reason"]),
                  "人工版本：" + str(plan["manualReview"]["overrideVersion"] or "未调整")]
    lines += ["", "## 变更说明"]
    breaking = [c for c in plan["commits"] if c["breaking"]]
    if breaking:
        lines += ["", "### 破坏性变更（BREAKING CHANGE）"]
        for commit in breaking:
            lines += ["", "- BREAKING: " + escape(commit["title"]) + " (`" + commit["oid"] + "`)"]
            # Keep the full body: footers may contain multiline migration details.
            lines += ["> " + escape(line) for line in commit["message"].splitlines()[1:]]
    for group in ["feat", "fix", "other"]:
        items = [c for c in plan["commits"] if (c["type"] if c["type"] in {"feat","fix"} else "other") == group]
        if items:
            lines += ["", "### " + {"feat":"新增", "fix":"修复", "other":"待复核变更"}[group]]
            lines += ["- " + escape(c["title"]) + " (`" + c["oid"] + "`)" for c in items]
    return "\n".join(lines) + "\n"


def safe_export(path, content, protected):
    # No overwrite in the local edition: choosing another name is explicit and race-safe.
    target = Path(path)
    if not target.is_absolute() or target.name in {"", ".", ".."}:
        fail("export_path", "请选择绝对文件路径。")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    output = None
    published = False
    completed = False
    identity = None
    try:
        for part in target.parent.parts[1:]:
            if part in {".", ".."}: fail("export_path", "导出路径不能包含相对跳转。")
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = nxt
        def check_parent():
            actual_parent = Path(os.readlink(f"/proc/self/fd/{fd}"))
            if actual_parent != target.parent:
                fail("export_moved", "导出目录在操作期间移动，已取消导出。请重新选择目录。")
            actual = actual_parent / target.name
            if any(actual.is_relative_to(Path(base)) for base in protected):
                fail("export_protected", "不能导出到工作树、关联工作树或 Git 元数据目录。")
            if any((parent / ".git").exists() for parent in [actual_parent, *actual_parent.parents]):
                fail("export_protected", "不能导出到其他 Git 工作树中。")
        check_parent()
        # An unnamed inode avoids leaving report contents under a moved directory.
        # Filesystems without O_TMPFILE fail closed; there is no named fallback.
        output = os.open(".", os.O_RDWR | os.O_TMPFILE, 0o600, dir_fd=fd)
        with os.fdopen(os.dup(output), "wb") as stream:
            info = os.fstat(stream.fileno()); identity = (info.st_dev, info.st_ino)
            check_parent()
            stream.write(content.encode("utf-8")); stream.flush(); os.fsync(stream.fileno())
        check_parent()
        # Hard-link publication is atomic and never replaces an existing target.
        os.link(f"/proc/self/fd/{output}", target.name, dst_dir_fd=fd, follow_symlinks=True)
        published = True
        os.fsync(fd)
        check_parent()
        completed = True
    except FileExistsError:
        fail("exists", "目标已存在。为保护原文件，请选择新的文件名。")
    except OSError:
        fail("export_io", "导出失败：权限不足、目录不存在或路径包含符号链接。")
    finally:
        if published and not completed:
            try:
                info = os.stat(target.name, dir_fd=fd, follow_symlinks=False)
                if (info.st_dev, info.st_ino) == identity:
                    os.unlink(target.name, dir_fd=fd)
            except FileNotFoundError:
                pass
        if output is not None:
            os.close(output)
        os.close(fd)
