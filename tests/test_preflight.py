import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import capability_probe
from probe_support import run_bounded
from verify_preflight import assess_probes, check_archive, EXPECTED_PROBES, FILES, REVISION_FILES


class PreflightRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="git-planner-regression-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def make_archive(self, names):
        archive = self.root / "input.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(archive, "w") as zipped:
                for name in names:
                    zipped.writestr(name, b"synthetic fixture")
                    if name in set(FILES) | REVISION_FILES:
                        target = self.root / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(b"synthetic fixture")
        return archive

    def test_empty_archives_rejected(self):
        for expected in [set(FILES), REVISION_FILES]:
            with self.subTest(size=len(expected)):
                result = check_archive(self.make_archive([]), self.root, expected)
                self.assertEqual(len(result["errors"]), len(expected))

    def test_exact_baseline_and_revision_sets_match(self):
        for expected in [set(FILES), REVISION_FILES]:
            with self.subTest(size=len(expected)):
                result = check_archive(self.make_archive(sorted(expected)), self.root, expected)
                self.assertEqual(result["errors"], [])
                self.assertEqual(len(result["files"]), len(expected))

    def test_missing_duplicate_and_extra_entries_rejected(self):
        for names in [FILES[:-1], FILES + (FILES[0],), FILES + ("extra.txt",)]:
            with self.subTest(names=names):
                self.assertTrue(check_archive(self.make_archive(names), self.root, set(FILES))["errors"])

    def test_corrupt_archive_rejected(self):
        path = self.root / "invalid.zip"
        path.write_bytes(b"not a zip")
        self.assertIn("BadZipFile", check_archive(path, self.root, set(FILES))["errors"])

    def test_symlink_entry_rejected(self):
        path = self.make_archive(FILES)
        with zipfile.ZipFile(path, "w") as zipped:
            for name in FILES:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (0o120777 if name == FILES[0] else 0o100644) << 16
                zipped.writestr(info, b"synthetic fixture")
        self.assertTrue(check_archive(path, self.root, set(FILES))["errors"])

    def test_path_traversal_rejected_without_reading_target(self):
        path = self.make_archive(FILES + ("../escape",))
        self.assertIn("unexpected:../escape", check_archive(path, self.root, set(FILES))["errors"])

    def test_timeout_kills_delayed_child(self):
        marker = self.root / "escaped-child"
        child = "import pathlib,time; time.sleep(1); pathlib.Path(" + repr(str(marker)) + ").write_text('escaped')"
        parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); print('started',flush=True); time.sleep(10)"
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            run_bounded([sys.executable, "-c", parent], cwd=self.root, timeout=0.25)
        self.assertIn(b"started", caught.exception.stdout)
        time.sleep(1.1)
        self.assertFalse(marker.exists())

    def test_normal_exit_also_cleans_background_child(self):
        marker = self.root / "background-child"
        child = "import pathlib,time; time.sleep(1); pathlib.Path(" + repr(str(marker)) + ").write_text('escaped')"
        parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child) + "],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
        result = run_bounded([sys.executable, "-c", parent], cwd=self.root)
        self.assertEqual(result.returncode, 0)
        time.sleep(1.1)
        self.assertFalse(marker.exists())

    def test_outer_timeout_cleans_nested_independent_group(self):
        marker = self.root / "nested-child"
        child = "import pathlib,time; time.sleep(0.8); pathlib.Path(" + repr(str(marker)) + ").write_text('escaped')"
        middle = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); print('inner-ready',flush=True); time.sleep(10)"
        supervisor = (
            "import sys; sys.path.insert(0," + repr(str(Path(__file__).resolve().parents[1] / "tools")) + "); "
            "from probe_support import run_bounded; "
            "run_bounded([sys.executable,'-c'," + repr(middle) + "],cwd=" + repr(str(self.root)) + ",timeout=5)"
        )
        with self.assertRaises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, "-B", "-c", supervisor], cwd=self.root, timeout=0.3)
        time.sleep(1)
        self.assertFalse(marker.exists())

    def test_structured_probe_counts_require_complete_set(self):
        good = {"status": "PASS", "counts": {"run": 8, "failures": 0, "errors": 0, "skipped": 0},
                "executed": EXPECTED_PROBES, "expected": EXPECTED_PROBES, "skips": []}
        self.assertEqual(assess_probes(good), "PASS")
        for field, value in [("executed", EXPECTED_PROBES[:-1]), ("skips", [{"reason": "absent"}]),
                             ("counts", {"run": 8, "failures": 0, "errors": 0, "skipped": 1})]:
            with self.subTest(field=field):
                self.assertEqual(assess_probes({**good, field: value}), "INCOMPLETE")

    def test_missing_strace_returns_incomplete_not_success(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(capability_probe.shutil, "which", return_value=None), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = capability_probe.run_probes()
        self.assertEqual(code, 2, err.getvalue())
        summary = json.loads(out.getvalue())
        self.assertEqual(summary["counts"]["skipped"], 2)
        self.assertEqual(assess_probes(summary), "INCOMPLETE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
