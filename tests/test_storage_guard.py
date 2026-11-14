"""Isolated behavioral tests; never operates on a real project.

python -B tests/test_storage_guard.py --work-root ABS_TEST_DIRECTORY
On macOS choose an isolated writable test directory. Fixtures and reports remain
available for inspection; there is no recursive test cleanup.
"""
import argparse
import contextlib
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storage_guard.py"
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, remaining = parser.parse_known_args()
BASE = Path(opts.work_root).absolute()
BASE.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="regression-", dir=BASE))
SPEC = importlib.util.spec_from_file_location("storage_guard_under_test", SCRIPT)
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "项目 with spaces"
        self.project.mkdir()
        self.codex = self.area / "codex-state"
        self.codex.mkdir()
        (self.codex / "auth.json").write_text('{"secret":"DO_NOT_REPORT"}', encoding="utf-8")
        self.env = dict(os.environ, CODEX_HOME=str(self.codex), PYTHONDONTWRITEBYTECODE="1",
                        PYTHONIOENCODING="utf-8")

    def cli(self, *args, ok=True):
        completed = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)],
                                   capture_output=True, text=True, encoding="utf-8", env=self.env)
        if ok:
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        else:
            self.assertNotEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed

    def cache(self, name="module", parent=None, aged=True):
        root = parent or self.project
        root.mkdir(parents=True, exist_ok=True)
        source = root / (name + ".py")
        source.write_text("VALUE = 123\n", encoding="utf-8")
        cached = Path(importlib.util.cache_from_source(str(source)))
        cached.parent.mkdir(exist_ok=True)
        py_compile.compile(str(source), cfile=str(cached), doraise=True)
        if aged:
            old = time.time() - 96 * 3600
            os.utime(cached, (old, old))
        return source, cached

    def scan(self, output="scan", *args, ok=True):
        folder = self.area / output
        completed = self.cli("scan", "--project", self.project, "--codex-home", self.codex,
                             "--output", folder, *args, ok=ok)
        return json.loads((folder / "scan.json").read_text(encoding="utf-8")) if (folder / "scan.json").exists() else completed

    def plan(self, report=None, name="plan.json"):
        report = report or self.scan()
        ids = ",".join(c["id"] for c in report["candidates"])
        path = self.area / name
        self.cli("plan", "--scan", self.area / "scan" / "scan.json", "--ids", ids, "--output", path)
        return path

    def apply(self, plan, ok=True, name="receipt.json", digest=None):
        path = self.area / name
        flags = ["--confirm-idle"] if os.name != "nt" else []
        completed = self.cli("apply", "--plan", plan, "--receipt", path,
                             "--authorize-plan", digest or sha(plan), *flags, ok=ok)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else completed

    def test_precise_cleanup_and_protected_data(self):
        source, cached = self.cache()
        important = [".codex/session_index.jsonl", ".agents/rules.md", ".git/index",
                     "db/project.sqlite", "db/project.sqlite-wal", "assets/film.mp4",
                     "__pycache__/source.py", "__pycache__/history.jsonl",
                     "backup/original.py", "src/index.ts", "prepared/recovery.zip"]
        before = {}
        for rel in important:
            p = self.project / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"unique business data\x00")
            before[rel] = sha(p)
        report = self.scan()
        self.assertEqual(len(report["candidates"]), 1)
        self.assertNotIn("DO_NOT_REPORT", json.dumps(report))
        source_sha = sha(source)
        receipt = self.apply(self.plan(report))
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["deleted_files"], 1)
        self.assertFalse(cached.exists())
        self.assertEqual(sha(source), source_sha)
        for rel, digest in before.items():
            self.assertEqual(sha(self.project / rel), digest, rel)

    def test_wrong_authorization_preserves_all(self):
        _, cached = self.cache()
        plan = self.plan()
        self.apply(plan, ok=False, digest="0" * 64)
        self.assertTrue(cached.exists())

    def test_same_size_hash_change_aborts_all(self):
        _, a = self.cache("a")
        _, z = self.cache("z")
        plan = self.plan()
        meta = a.stat()
        data = bytearray(a.read_bytes())
        data[-1] ^= 1
        a.write_bytes(data)
        os.utime(a, ns=(meta.st_atime_ns, meta.st_mtime_ns))
        receipt = self.apply(plan, ok=False)
        self.assertEqual(receipt["deleted_files"], 0)
        self.assertTrue(a.exists())
        self.assertTrue(z.exists())

    def test_changed_source_aborts_all(self):
        source, a = self.cache("a")
        _, z = self.cache("z")
        plan = self.plan()
        source.write_text("VALUE = 'new business work'\n", encoding="utf-8")
        receipt = self.apply(plan, ok=False)
        self.assertEqual(receipt["deleted_files"], 0)
        self.assertTrue(a.exists())
        self.assertTrue(z.exists())

    def test_forged_traversal_is_rejected(self):
        _, cache = self.cache()
        plan = self.plan()
        outside = self.area / "important.pyc"
        outside.write_bytes(cache.read_bytes())
        data = json.loads(plan.read_text(encoding="utf-8"))
        data["items"][0]["path"] = "../important.pyc"
        forged = self.area / "forged.json"
        forged.write_text(json.dumps(data), encoding="utf-8")
        self.apply(forged, ok=False)
        self.assertTrue(cache.exists())
        self.assertTrue(outside.exists())

    def test_forged_protected_target_is_rejected(self):
        _, cache = self.cache()
        plan = self.plan()
        target = self.project / ".codex" / "session_index.jsonl"
        target.parent.mkdir()
        target.write_bytes(cache.read_bytes())
        meta = cache.stat()
        os.utime(target, ns=(meta.st_atime_ns, meta.st_mtime_ns))
        s = target.stat()
        data = json.loads(plan.read_text(encoding="utf-8"))
        item = data["items"][0]
        item["path"] = ".codex/session_index.jsonl"
        item["identity"] = {"device": s.st_dev, "inode": s.st_ino, "size": s.st_size,
                            "mtime_ns": s.st_mtime_ns, "links": s.st_nlink}
        item["sha256"] = sha(target)
        forged = self.area / "forged.json"
        forged.write_text(json.dumps(data), encoding="utf-8")
        self.apply(forged, ok=False)
        self.assertTrue(target.exists())
        self.assertTrue(cache.exists())

    def test_fake_bytecode_never_deleted(self):
        _, cache = self.cache()
        meta = cache.stat()
        cache.write_bytes(b"not bytecode, possibly user material")
        os.utime(cache, ns=(meta.st_atime_ns, meta.st_mtime_ns))
        report = self.scan()
        if report["candidates"]:
            self.cli("plan", "--scan", self.area / "scan" / "scan.json", "--ids",
                     report["candidates"][0]["id"], "--output", self.area / "invalid-plan.json", ok=False)
        self.assertTrue(cache.exists())

    def test_webpack_is_review(self):
        pack = self.project / ".next/cache/webpack/client/0.pack"
        pack.parent.mkdir(parents=True)
        pack.write_bytes(b"valuable unique data in a cache-looking directory")
        (self.project / "package.json").write_text("{}", encoding="utf-8")
        old = time.time() - 96 * 3600
        os.utime(pack, (old, old))
        report = self.scan()
        self.assertEqual(report["candidates"], [])
        self.assertTrue(pack.exists())

    def test_recent_or_missing_source_is_retained(self):
        _, recent = self.cache("recent", aged=False)
        missing, orphan = self.cache("orphan")
        missing.unlink()
        self.assertEqual(self.scan()["candidates"], [])
        self.assertTrue(recent.exists())
        self.assertTrue(orphan.exists())

    def test_partial_scan_cannot_plan(self):
        self.cache()
        report = self.scan("scan", "--max-files", "1")
        self.assertFalse(report["coverage"]["complete"])
        self.cli("plan", "--scan", self.area / "scan" / "scan.json", "--ids", "C000001",
                 "--output", self.area / "plan.json", ok=False)

    def test_baseline_scope_and_growth(self):
        self.cache()
        report = self.scan()
        new_file = self.project / "business.txt"
        new_file.write_bytes(b"new data")
        current = self.scan("scan2", "--baseline", self.area / "scan/scan.json")
        self.assertTrue(current["baseline"]["comparable"])
        self.assertEqual(current["baseline"]["logical_bytes_delta"], 8)
        limited = self.scan("scan3", "--max-files", "1", "--baseline", self.area / "scan/scan.json")
        self.assertFalse(limited["baseline"]["comparable"])

    def test_directory_growth_evidence(self):
        self.cache()
        first = self.scan()
        # Cache-only scan deliberately prunes protected media in v1.3.
        # Exercise growth in its supported traversal scope; full attribution
        # of media/managed directories is tested by the project profiler.
        media = self.project / "task-output" / "new.bin"
        media.parent.mkdir()
        media.write_bytes(b"new task output")
        second = self.scan("scan2", "--baseline", self.area / "scan/scan.json")
        self.assertTrue(second["baseline"]["comparable"])
        deltas = {d["path"]: d["logical_bytes_delta"] for d in second["baseline"]["directory_deltas"]}
        self.assertEqual(deltas["task-output"], len(b"new task output"))
        summary = (self.area / "scan2/scan.md").read_text(encoding="utf-8")
        self.assertIn("task-output", summary)
        self.assertIn("15", summary)

    def test_old_baseline_without_directory_snapshot_is_not_fabricated(self):
        self.cache()
        first = self.scan()
        first.pop("directory_totals", None)
        old = self.area / "older-schema.json"
        old.write_text(json.dumps(first), encoding="utf-8")
        current = self.scan("scan2", "--baseline", old)
        self.assertFalse(current["baseline"].get("directory_deltas", []))

    def test_repeated_apply_stops_without_extra_deletion(self):
        _, cache = self.cache()
        plan = self.plan()
        self.apply(plan)
        self.assertFalse(cache.exists())
        self.apply(plan, ok=False, name="receipt-2.json")

    def test_root_and_codex_root_are_rejected(self):
        for i, root in enumerate((Path(self.project.anchor), Path.home(), self.codex)):
            self.cli("scan", "--project", root, "--codex-home", self.codex,
                     "--output", self.area / f"invalid-{i}", ok=False)

    def test_link_is_not_traversed(self):
        external = self.area / "external"
        _, external_cache = self.cache(parent=external)
        alias = self.project / "linked"
        try:
            alias.symlink_to(external, target_is_directory=True)
        except OSError as exc:
            self.skipTest("OS does not permit symlink creation: " + str(exc))
        report = self.scan()
        self.assertEqual(report["candidates"], [])
        self.assertTrue(external_cache.exists())

    def test_hardlink_not_a_cleanup_candidate(self):
        _, cache = self.cache()
        alias = self.area / "hardlink.pyc"
        try:
            os.link(cache, alias)
        except OSError as exc:
            self.skipTest("Test filesystem does not support hardlinks: " + str(exc))
        self.assertEqual(self.scan()["candidates"], [])
        self.assertTrue(cache.exists())
        self.assertTrue(alias.exists())

    def test_known_build_lock_retains_cache(self):
        _, cache = self.cache()
        lock = self.project / ".next/lock"
        lock.parent.mkdir()
        lock.write_bytes(b"writer")
        self.assertEqual(self.scan()["candidates"], [])
        self.assertTrue(cache.exists())

    def test_occupied_cache_aborts_batch(self):
        _, a = self.cache("a")
        _, z = self.cache("z")
        plan = self.plan()
        with GUARD.guarded_file(a):
            receipt = self.apply(plan, ok=False)
        self.assertEqual(receipt["deleted_files"], 0)
        self.assertTrue(a.exists())
        self.assertTrue(z.exists())

    def test_injected_io_error_stops_batch(self):
        _, a = self.cache("a")
        _, z = self.cache("z")
        plan = self.plan()
        receipt_path = self.area / "io-receipt.json"
        args = argparse.Namespace(plan=str(plan), receipt=str(receipt_path),
                                  authorize_plan=sha(plan), confirm_idle=True)
        with mock.patch.object(GUARD, "hash_fd", side_effect=OSError(errno.EIO, "injected fixture I/O error")):
            with contextlib.redirect_stdout(io.StringIO()):
                code = GUARD.apply(args)
        self.assertNotEqual(code, 0)
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "aborted_io_error")
        self.assertEqual(receipt["deleted_files"], 0)
        self.assertTrue(a.exists())
        self.assertTrue(z.exists())

    def test_bytecode_size_read_budget(self):
        _, cache = self.cache()
        with mock.patch.object(GUARD, "CACHE_MAX_BYTES", 1):
            evidence, reason = GUARD.classify(self.project, cache.relative_to(self.project).as_posix(),
                                              cache.stat(), 48)
        self.assertIsNone(evidence)
        self.assertIn("read limit", reason)
        self.assertTrue(cache.exists())

    def test_explicit_managed_worktree_and_container_boundary(self):
        repo = self.codex / "worktrees" / "job1" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").write_text("gitdir: metadata-not-opened\n", encoding="utf-8")
        _, cache = self.cache(parent=repo)
        self.project = repo
        self.assertEqual(len(self.scan()["candidates"]), 1)
        self.apply(self.plan(json.loads((self.area / "scan/scan.json").read_text(encoding="utf-8"))))
        self.assertFalse(cache.exists())
        for name, root in (("tree", repo.parent.parent), ("container", repo.parent)):
            self.cli("scan", "--project", root, "--codex-home", self.codex,
                     "--output", self.area / name, ok=False)

    def test_managed_dependency_and_recovery_boundaries(self):
        caches = []
        for parent in (".venv/lib/pkg", "node_modules/pkg", ".uv-cache/pkg", ".cache/uv/pkg",
                       ".cache/pip/pkg", "prepared/pkg", "rollback/pkg", ".pnpm-store/pkg"):
            _, cache = self.cache(parent=self.project / parent)
            caches.append(cache)
        self.assertEqual(self.scan()["candidates"], [])
        self.assertTrue(all(p.exists() for p in caches))

    def test_custom_environment_and_cache_markers_are_respected(self):
        caches = []
        for name, marker in (("custom-python", "pyvenv.cfg"), ("tool-native-cache", "CACHEDIR.TAG")):
            top = self.project / name
            _, cache = self.cache(parent=top / "pkg")
            (top / marker).write_text("tool-managed boundary", encoding="utf-8")
            caches.append(cache)
        self.assertEqual(self.scan()["candidates"], [])
        self.assertTrue(all(p.exists() for p in caches))

    def test_cache_marker_added_after_plan_stops_execution(self):
        _, cache = self.cache()
        plan = self.plan()
        (self.project / "CACHEDIR.TAG").write_text("native cache", encoding="utf-8")
        receipt = self.apply(plan, ok=False)
        self.assertEqual(receipt["deleted_files"], 0)
        self.assertTrue(cache.exists())


if __name__ == "__main__":
    print("Isolated evidence directory:", RUN, flush=True)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
