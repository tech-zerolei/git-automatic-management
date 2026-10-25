#!/usr/bin/env python3
"""Record repeatable, append-only TASK-002 evidence, never product acceptance."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from zoneinfo import ZoneInfo

from probe_support import run_bounded


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/specs/feat-001-git-version-planner"
FILES = ("01-SPEC.md", "02-PLAN.md", "03-TASKS.md", "04-ACCEPTANCE.md", "05-CHANGE.md")
REVISION_FILES = {
    f"revisions/0.{version}-draft/{name}"
    for version in range(1, 8)
    for name in (FILES[:1] if version == 2 else FILES)
}
EXPECTED_PROBES = [f"P{i:02d}" for i in range(1, 9)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_archive(archive, root, expected):
    item = {"path": str(archive.resolve()), "sha256": None, "files": [], "errors": []}
    try:
        item["sha256"] = digest(archive)
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            names = [entry.filename for entry in entries]
            item["errors"].extend("duplicate:" + name for name, count in Counter(names).items() if count != 1)
            actual = {entry.filename for entry in entries if not entry.is_dir()}
            item["errors"].extend("missing:" + name for name in sorted(expected - actual))
            item["errors"].extend("unexpected:" + name for name in sorted(actual - expected))
            allowed_dirs = {str(parent) + "/" for name in expected for parent in Path(name).parents if str(parent) != "."}
            for info in entries:
                if info.is_dir():
                    if info.filename not in allowed_dirs:
                        item["errors"].append("unexpected-directory:" + info.filename)
                    continue
                target = root / info.filename
                safe = info.filename in expected and not stat.S_ISLNK(info.external_attr >> 16)
                safe = safe and target.resolve().is_relative_to(root.resolve())
                matches = safe and not target.is_symlink() and target.is_file() and target.read_bytes() == zipped.read(info)
                item["files"].append({"name": info.filename, "matches": bool(matches)})
                if not matches:
                    item["errors"].append("mismatch-or-unsafe:" + info.filename)
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        item["errors"].append(type(exc).__name__)
    return item


def assess_probes(summary):
    if not isinstance(summary, dict):
        return "INCOMPLETE"
    counts = summary.get("counts", {})
    if not isinstance(counts, dict):
        return "INCOMPLETE"
    if counts.get("failures", 0) or counts.get("errors", 0):
        return "FAIL"
    if (summary.get("status") != "PASS" or summary.get("expected") != EXPECTED_PROBES
            or sorted(summary.get("executed", [])) != EXPECTED_PROBES
            or counts != {"run": 8, "failures": 0, "errors": 0, "skipped": 0}
            or summary.get("skips") != []):
        return "INCOMPLETE"
    return "PASS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-checker", type=Path, required=True)
    parser.add_argument("--baseline-archive", type=Path, required=True)
    parser.add_argument("--revisions-archive", type=Path, required=True)
    args = parser.parse_args()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    parent = ROOT / "docs/implementation/evidence"
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=now.strftime("%Y%m%dT%H%M%S%z-") , dir=parent))
    result = {
        "time": now.isoformat(), "scope": "TASK-002 preflight only; not product acceptance",
        "platform": platform.platform(), "python": sys.version,
        "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in [
            ROOT / "tools/capability_probe.py", ROOT / "tools/probe_support.py", Path(__file__).resolve(),
            ROOT / "tests/test_preflight.py",
            *(SPEC / name for name in FILES),
        ]},
        "spec_checker_sha256": digest(args.spec_checker), "commands": [], "archives": [],
        "product_acceptance": "AC-001 through AC-024: NOT EXECUTED",
    }
    failures = []

    def command(name, argv, timeout=30, env=None):
        entry = {"name": name, "argv": [str(x) for x in argv], "cwd": str(ROOT), "timeout_seconds": timeout}
        try:
            completed = run_bounded(entry["argv"], cwd=ROOT, env=env, timeout=timeout)
            entry["returncode"] = completed.returncode
            stdout, stderr = completed.stdout, completed.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            entry["returncode"] = None
            entry["error"] = type(exc).__name__
            stdout, stderr = getattr(exc, "stdout", None) or b"", getattr(exc, "stderr", None) or b""
        (output / (name + ".stdout.txt")).write_bytes(stdout)
        (output / (name + ".stderr.txt")).write_bytes(stderr)
        result["commands"].append(entry)
        if entry["returncode"] != 0:
            failures.append(name)
        return entry

    for archive, expected in [(args.baseline_archive, set(FILES)), (args.revisions_archive, REVISION_FILES)]:
        item = check_archive(archive, SPEC, expected)
        if item["errors"]:
            failures.append("archive-integrity")
        result["archives"].append(item)

    command("spec-check", [sys.executable, str(args.spec_checker.resolve()), str(SPEC)])
    command("git-probes", [sys.executable, "-B", str(ROOT / "tools/capability_probe.py"), "--supervised-group"])
    try:
        result["probe_summary"] = json.loads((output / "git-probes.stdout.txt").read_text())
    except (ValueError, OSError):
        result["probe_summary"] = None
    result["probe_status"] = assess_probes(result["probe_summary"])
    if result["probe_status"] != "PASS" and "git-probes" not in failures:
        failures.append("git-probes")
    command("regression-tests", [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"])
    command("git-version", ["/usr/bin/git", "--version"])

    codex = shutil.which("codex")
    if codex:
        with tempfile.TemporaryDirectory(prefix="git-planner-host-schema-") as temporary:
            base = Path(temporary)
            home = base / "home"
            home.mkdir()
            env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "CODEX_HOME": str(home),
                   "XDG_CONFIG_HOME": str(home / "xdg"), "LC_ALL": "C"}
            command("codex-version", [codex, "--version"], env=env)
            command("codex-help", [codex, "--help"], env=env)
            schema = base / "schema"
            entry = command("host-schema", [codex, "app-server", "generate-json-schema", "--out", str(schema)], env=env)
            result["host_schema_scope"] = "Static schema only; no lifecycle delivery or plugin integration verified"
            if entry["returncode"] == 0:
                for relative in ["v2/TurnStartedNotification.json", "v2/TurnCompletedNotification.json",
                                 "v2/HookStartedNotification.json", "DynamicToolCallResponse.json"]:
                    source = schema / relative
                    if source.is_file():
                        shutil.copyfile(source, output / ("schema-" + source.name))
    else:
        result["host_schema_scope"] = "UNVERIFIED: codex CLI not found"
        failures.append("host-schema-unavailable")

    result["failed_checks"] = failures
    result["preflight_command_status"] = "PASS" if not failures else ("INCOMPLETE" if failures == ["git-probes"] and result["probe_status"] == "INCOMPLETE" else "FAIL")
    result["q004_status"] = "OPEN: runtime integration, dual-channel completeness, credential security, model isolation and budgets unverified"
    (output / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"evidence": str(output), "failed_checks": failures,
                      "product_acceptance": result["product_acceptance"]}, ensure_ascii=False, indent=2))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
