#!/usr/bin/env python3
"""TASK-002 isolated experiments, not a production Git adapter or plugin.

Only generated repositories below TemporaryDirectory are used. No repository,
credential, remote URL or shell command is accepted from the caller.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from probe_support import run_bounded


GIT = "/usr/bin/git"
HARDENING = [
    "--no-pager", "--no-optional-locks", "--no-lazy-fetch",
    "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
    "-c", "core.hooksPath=/dev/null", "-c", "protocol.allow=never",
]
EXPECTED_PROBES = [f"P{i:02d}" for i in range(1, 9)]
SUPERVISED_GROUP = False


def run_probe_command(argv, *, cwd, env, timeout=15, check=False):
    return run_bounded(argv, cwd=cwd, env=env, timeout=timeout, check=check,
                       own_group=not SUPERVISED_GROUP)


def executable_paths(trace):
    """Read strace execve records for these synthetic, ASCII executable paths."""
    import re
    return re.findall(r'execve\("([^"\n]+)"', trace)


def snapshot(root):
    """Ignore read access times, but retain contents and mutation metadata."""
    result = {}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        value = (stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if path.is_symlink():
            value += (os.readlink(path),)
        elif path.is_file():
            value += (hashlib.sha256(path.read_bytes()).hexdigest(),)
        result[str(path.relative_to(root))] = value
    return result


class CapabilityProbes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="git-planner-probe-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "synthetic repository"
        self.repo.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {
            "PATH": "/usr/bin:/bin", "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / "xdg"), "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_PAGER": "cat",
            "GIT_AUTHOR_NAME": "Synthetic Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Synthetic Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+0000",
            "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+0000",
        }
        self.git("init", "--initial-branch=main")
        (self.repo / "tracked.txt").write_text("synthetic initial\n")
        self.git("add", "--", "tracked.txt")
        self.git("commit", "-m", "feat: synthetic fixture")
        self.git("tag", "v1.0.0")

    def git(self, *args, cwd=None, readonly=False, check=True):
        cwd = (cwd or self.repo).resolve()
        if not cwd.is_relative_to(self.root.resolve()):
            raise ValueError("probe commands must stay in the generated temporary directory")
        command = [GIT, *(HARDENING if readonly else []), *args]
        return run_probe_command(command, cwd=cwd, env=self.env, check=check)

    def test_P01_supported_read_flags_and_nul_status(self):
        (self.repo / "tracked.txt").write_text("synthetic changed\n")
        strange = "line\n$(touch injected).txt"
        (self.repo / strange).write_text("synthetic untracked\n")
        output = self.git("status", "--porcelain=v2", "--branch", "-z", readonly=True).stdout
        records = output.split(b"\0")
        self.assertIn(b"? " + strange.encode(), records)
        self.assertTrue(any(row.startswith(b"1 .M ") for row in records))
        self.assertFalse((self.repo / "injected").exists())

    def test_P02_read_sequence_preserves_files_and_metadata(self):
        (self.repo / "tracked.txt").write_text("synthetic changed\n")
        before = snapshot(self.repo)
        for command in [
            ("status", "--porcelain=v2", "--branch", "-z"),
            ("rev-parse", "--show-toplevel", "--absolute-git-dir", "--git-common-dir"),
            ("for-each-ref", "--format=%(objectname)%00%(refname)%00", "refs/tags/"),
            ("log", "--format=%H%x00%P%x00%B%x00", "HEAD"),
        ]:
            self.git(*command, readonly=True)
        self.assertEqual(before, snapshot(self.repo))

    def test_P03_repository_fsmonitor_is_not_executed(self):
        marker = self.root / "fsmonitor-executed"
        helper = self.root / "untrusted-fsmonitor"
        helper.write_text("#!/bin/sh\nprintf called > '" + str(marker) + "'\n")
        helper.chmod(0o700)
        self.git("config", "core.fsmonitor", str(helper))
        before = snapshot(self.repo)
        self.git("status", "--porcelain=v2", "-z", readonly=True)
        self.assertFalse(marker.exists())
        self.assertEqual(before, snapshot(self.repo))

    def test_P04_linked_worktrees_have_distinct_git_directories(self):
        linked = self.root / "linked"
        self.git("worktree", "add", "--detach", str(linked), "HEAD")
        primary_git = self.git("rev-parse", "--absolute-git-dir", readonly=True).stdout.strip()
        linked_git = self.git("rev-parse", "--absolute-git-dir", cwd=linked, readonly=True).stdout.strip()
        primary_common = self.git("rev-parse", "--path-format=absolute", "--git-common-dir", readonly=True).stdout.strip()
        linked_common = self.git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=linked, readonly=True).stdout.strip()
        self.assertNotEqual(primary_git, linked_git)
        self.assertEqual(primary_common, linked_common)
        self.assertTrue((linked / ".git").is_file())

    def test_P05_unborn_and_bare_are_observable_not_product_classified(self):
        empty = self.root / "unborn"
        empty.mkdir()
        self.git("init", "--initial-branch=main", cwd=empty)
        missing = self.git("rev-parse", "--verify", "HEAD", cwd=empty, readonly=True, check=False)
        self.assertNotEqual(missing.returncode, 0)
        bare = self.root / "bare.git"
        bare.mkdir()
        self.git("init", "--bare", cwd=bare)
        self.assertEqual(self.git("rev-parse", "--is-bare-repository", cwd=bare, readonly=True).stdout, b"true\n")

    def test_P06_fixed_commit_difference_ignores_worktree_changes(self):
        base = self.git("rev-parse", "HEAD", readonly=True).stdout.decode().strip()
        (self.repo / "tracked.txt").write_text("synthetic committed fix\n")
        self.git("add", "--", "tracked.txt")
        self.git("commit", "-m", "fix: synthetic correction")
        head = self.git("rev-parse", "HEAD", readonly=True).stdout.decode().strip()
        (self.repo / "tracked.txt").write_text("synthetic uncommitted breaking change\n")
        actual = self.git("rev-list", head, "^" + base, "--", readonly=True).stdout.decode().splitlines()
        self.assertEqual(actual, [head])

    def test_P07_missing_promisor_object_does_not_launch_transport(self):
        marker = self.root / "transport-executed"
        helpers = self.root / "helpers"
        helpers.mkdir()
        helper = helpers / "git-remote-probe"
        helper.write_text("#!/bin/sh\nprintf called > '" + str(marker) + "'\nexit 91\n")
        helper.chmod(0o700)
        self.env["PATH"] = str(helpers) + ":/usr/bin:/bin"
        self.git("config", "remote.origin.url", "probe::synthetic")
        self.git("config", "remote.origin.promisor", "true")
        self.git("config", "remote.origin.partialclonefilter", "blob:none")
        oid = self.git("rev-parse", "HEAD:tracked.txt", readonly=True).stdout.decode().strip()
        (self.repo / ".git" / "objects" / oid[:2] / oid[2:]).unlink()
        before = snapshot(self.repo)
        tracer = shutil.which("strace", path="/usr/bin:/bin")
        if not tracer:
            self.skipTest("strace unavailable; no implicit-fetch process audit evidence")
        trace = self.root / "missing-object.trace"
        result = run_probe_command(
            [tracer, "-f", "-qq", "-s", "4096", "-e", "trace=execve", "-o", str(trace),
             GIT, *HARDENING, "cat-file", "-e", oid], cwd=self.repo, env=self.env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(executable_paths(trace.read_text()), [GIT])
        self.assertFalse(marker.exists())
        self.assertEqual(before, snapshot(self.repo))

        # A deliberately weakened, still-offline control must expose fetch.
        control = self.root / "missing-object-control.trace"
        env = dict(self.env)
        env.pop("GIT_NO_LAZY_FETCH")
        result = run_probe_command(
            [tracer, "-f", "-qq", "-s", "4096", "-e", "trace=execve", "-o", str(control),
             GIT, *(flag for flag in HARDENING if flag != "--no-lazy-fetch"),
             "cat-file", "-e", oid], cwd=self.repo, env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('"fetch"', control.read_text())
        self.assertGreater(len(executable_paths(control.read_text())), 1)
        self.assertFalse(marker.exists())

    def test_P08_strace_records_no_network_syscall_for_status(self):
        tracer = shutil.which("strace", path="/usr/bin:/bin")
        if not tracer:
            self.skipTest("strace unavailable; no network audit evidence")
        trace = self.root / "network.trace"
        before = snapshot(self.repo)
        result = run_probe_command(
            [tracer, "-f", "-qq", "-e", "trace=network", "-o", str(trace),
             GIT, *HARDENING, "status", "--porcelain=v2", "-z"],
            cwd=self.repo, env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertEqual(trace.read_text(), "")
        self.assertEqual(before, snapshot(self.repo))


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started = []

    def startTest(self, test):
        self.started.append(test._testMethodName.split("_")[1])
        super().startTest(test)


def run_probes():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CapabilityProbes)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    counts = {"run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped)}
    status = "PASS"
    if result.failures or result.errors:
        status = "FAIL"
    elif result.skipped or sorted(result.started) != EXPECTED_PROBES:
        status = "INCOMPLETE"
    summary = {"status": status, "counts": counts, "executed": result.started,
               "expected": EXPECTED_PROBES, "skips": [{"test": str(t), "reason": reason} for t, reason in result.skipped]}
    print(json.dumps(summary))
    return 0 if status == "PASS" else (2 if status == "INCOMPLETE" else 1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supervised-group", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    SUPERVISED_GROUP = options.supervised_group
    if not Path(GIT).is_file():
        print(json.dumps({"status": "blocked", "reason": "expected /usr/bin/git not available"}))
        sys.exit(2)
    sys.exit(run_probes())
