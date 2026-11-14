"""Portable isolated state-boundary checks.

Run: python -B tests/test_state_boundaries.py --work-root ABS_EXISTING_TEST_PARENT
Only a new fictional fixture tree is written beneath that explicitly named parent.
Fixtures and the result report are retained. No real cache purge or build runs.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import py_compile
import sys
import tempfile
import time
import unittest
from unittest import mock

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, remaining = parser.parse_known_args()
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import storage_guard as G
import native_cache_guard as N
import generated_artifact_guard as A
import project_profiler as P

BASE = Path(opts.work_root).absolute()
G.ancestors(BASE)
RUN = Path(tempfile.mkdtemp(prefix="state-boundary-tests-", dir=BASE))
ALIAS_EVIDENCE = []


class StateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project"
        self.state = self.area / "ordinary-state-root"
        self.codex = self.area / "codex-state"
        self.home = self.area / "fictional-home"
        for path in (self.project, self.state, self.codex, self.home):
            path.mkdir()
        self.child = self.state / "ordinary-child"
        self.child.mkdir()
        (self.state / "state.sqlite").write_bytes(b"fictional-state-never-read")
        self.env = mock.patch.dict(os.environ, {
            "CODEX_HOME": str(self.codex), "CODEX_SQLITE_HOME": str(self.state),
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "LOCALAPPDATA": str(self.home / "AppData/Local"),
            "APPDATA": str(self.home / "AppData/Roaming"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def assert_entry_refuses(self, target, *, sqlite=True):
        expression = "CODEX_SQLITE_HOME" if sqlite else None
        with self.assertRaisesRegex(G.GuardError, expression) if expression else self.assertRaises(G.GuardError):
            G.project_root(target)
        # The native adapter loads a private copy of storage_guard. Test its real
        # entry point and ensure no native probe runs before rejecting the root.
        with mock.patch.object(N, "probe_pip", side_effect=AssertionError("native probe must not run")):
            with self.assertRaisesRegex(N.guard.GuardError, expression) if expression else self.assertRaises(N.guard.GuardError):
                N.inspect(target, "pip", ".cache/pip")
        args = argparse.Namespace(project=str(target), source="previews", assessment=str(self.area / "absent.json"),
            output=str(self.area / "must-not-create.json"), codex_home=os.environ.get("CODEX_HOME", str(self.codex)),
            max_files=10, max_bytes=1024)
        with mock.patch.object(A, "collect_source", side_effect=AssertionError("candidate scan must not run")):
            with self.assertRaisesRegex(G.GuardError, expression) if expression else self.assertRaises(G.GuardError):
                A.plan_command(args)
        self.assertFalse((self.area / "must-not-create.json").exists())

    def test_sqlite_root_is_not_a_project_at_any_executor_entry(self):
        self.assert_entry_refuses(self.state)

    def test_sqlite_descendant_is_not_a_project_at_any_executor_entry(self):
        self.assert_entry_refuses(self.child)

    def test_project_containing_sqlite_state_is_refused_even_before_state_exists(self):
        for existing in (True, False):
            nested = self.project / ("existing-runtime" if existing else "future-runtime") / "ordinary-data"
            if existing:
                nested.mkdir(parents=True)
                (nested / "state.sqlite").write_bytes(b"fictional-state-never-read")
            with self.subTest(existing=existing), mock.patch.dict(os.environ, {"CODEX_SQLITE_HOME": str(nested)}):
                self.assert_entry_refuses(self.project)
            self.assertEqual(nested.exists(), existing)
        # Model a mounted/path alias whose configured state ancestor has the
        # selected project's actual identity, without claiming native link QA.
        alias_parent = self.area / "external-sqlite-alias-parent"
        alias_state = alias_parent / "ordinary-data"
        alias_state.mkdir(parents=True)
        real_samefile = os.path.samefile
        pair = {G.key(alias_parent), G.key(self.project)}
        def identity_alias(left, right):
            if {G.key(left), G.key(right)} == pair:
                return True
            return real_samefile(left, right)
        ALIAS_EVIDENCE.append({"test": self.id(), "mode": "configured_state_ancestor_identity_simulation",
            "native_alias_verified": False})
        with mock.patch.dict(os.environ, {"CODEX_SQLITE_HOME": str(alias_state)}), \
                mock.patch.object(os.path, "samefile", side_effect=identity_alias):
            self.assert_entry_refuses(self.project)

    def test_project_containing_codex_home_is_refused_even_before_state_exists(self):
        for existing in (True, False):
            nested = self.project / ("existing-codex" if existing else "future-codex") / "ordinary-data"
            if existing:
                nested.mkdir(parents=True)
                (nested / "state.sqlite").write_bytes(b"fictional-state-never-read")
            with self.subTest(existing=existing), mock.patch.dict(os.environ, {"CODEX_HOME": str(nested)}):
                self.assert_entry_refuses(self.project, sqlite=False)
            self.assertEqual(nested.exists(), existing)
        alias_parent = self.area / "external-codex-alias-parent"
        alias_state = alias_parent / "ordinary-data"
        alias_state.mkdir(parents=True)
        real_samefile = os.path.samefile
        pair = {G.key(alias_parent), G.key(self.project)}
        def identity_alias(left, right):
            if {G.key(left), G.key(right)} == pair:
                return True
            return real_samefile(left, right)
        ALIAS_EVIDENCE.append({"test": self.id(), "mode": "configured_state_ancestor_identity_simulation",
            "native_alias_verified": False})
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(alias_state)}), \
                mock.patch.object(os.path, "samefile", side_effect=identity_alias):
            self.assert_entry_refuses(self.project, sqlite=False)

    def test_codex_home_and_descendant_remain_protected(self):
        child = self.codex / "ordinary-child"
        child.mkdir()
        for target in (self.codex, child):
            with self.subTest(target=target.name):
                self.assert_entry_refuses(target, sqlite=False)

    def test_sqlite_alias_root_and_descendant_are_refused(self):
        alias = self.area / "state-alias"
        try:
            os.symlink(self.state, alias, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            if os.path.lexists(alias):
                self.fail("Unverified partial alias was retained; choose a fresh test parent")
            alias.mkdir()
            (alias / "ordinary-child").mkdir()
            real_samefile = os.path.samefile
            pair = {G.key(alias), G.key(self.state)}

            def identity_alias(left, right):
                if {G.key(left), G.key(right)} == pair:
                    return True
                return real_samefile(left, right)

            ALIAS_EVIDENCE.append({"test": self.id(), "mode": "controlled_samefile_identity_simulation",
                "reason": type(exc).__name__, "native_alias_verified": False})
            with mock.patch.object(os.path, "samefile", side_effect=identity_alias):
                self.assert_entry_refuses(alias)
                self.assert_entry_refuses(alias / "ordinary-child")
        else:
            ALIAS_EVIDENCE.append({"test": self.id(), "mode": "real_directory_symlink",
                "native_alias_verified": True})
            # The existing no-link boundary may reject before the state-role test.
            self.assert_entry_refuses(alias, sqlite=False)
            self.assert_entry_refuses(alias / "ordinary-child", sqlite=False)

    def test_nonexistent_sqlite_setting_does_not_create_state_or_block_project(self):
        missing = self.area / "absent-state"
        with mock.patch.dict(os.environ, {"CODEX_SQLITE_HOME": str(missing)}):
            self.assertEqual(G.project_root(self.project), self.project)
        self.assertFalse(missing.exists())

    def test_confirmed_codex_worktree_exception_is_retained(self):
        repo = self.codex / "worktrees" / "test-id" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").write_text("gitdir: fictional-pointer-not-followed\n", encoding="utf-8")
        self.assertEqual(G.project_root(repo), repo)

    def test_managed_project_relabel_refused(self):
        root = self.project / "node_modules" / "dependency"
        root.mkdir(parents=True)
        with self.assertRaises(G.GuardError):
            G.project_root(root)

    def test_cache_scan_prunes_managed_trees_but_profiler_counts_them(self):
        source = self.project / "module.py"
        source.write_text("VALUE = 1\n", encoding="utf-8")
        cache = Path(py_compile.compile(str(source), doraise=True))
        old = time.time() - 72 * 3600
        os.utime(cache, (old, old))
        protected = ("node_modules", ".venv", "assets", "build")
        for name in protected:
            directory = self.project / name
            directory.mkdir()
            for index in range(25):
                (directory / ("sample-%02d.bin" % index)).write_bytes(b"fixture")
        scan_out = self.area / "cache-scan"
        with contextlib.redirect_stdout(io.StringIO()):
            G.scan(argparse.Namespace(project=str(self.project), output=str(scan_out), codex_home=str(self.codex),
                min_age_hours=48.0, max_files=3, baseline=None))
        scan = json.loads((scan_out / "scan.json").read_text(encoding="utf-8"))
        self.assertTrue(scan["coverage"]["complete"])
        self.assertFalse(scan["coverage"]["read_limit_hit"])
        self.assertEqual(scan["totals"]["files"], 2)
        self.assertEqual(len(scan["candidates"]), 1)
        self.assertTrue(set(protected).issubset(scan["coverage"]["pruned_subtrees"]))
        profile_out = self.area / "profile.json"
        with contextlib.redirect_stdout(io.StringIO()):
            P.inspect(argparse.Namespace(project=str(self.project), output=str(profile_out), codex_home=str(self.codex),
                max_files=500, max_config_bytes=1048576, related_root=[], scan_json=None))
        profile = json.loads(profile_out.read_text(encoding="utf-8"))
        self.assertTrue(profile["coverage"]["project_traversal_complete"])
        self.assertEqual(profile["project_measurement"]["files"], 102)
        self.assertGreater(profile["project_measurement"]["logical_bytes"], scan["totals"]["logical_bytes"])
        self.assertFalse(profile["execution_boundary"]["profile_grants_action_authority"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StateBoundaryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"test": "isolated-state-boundaries", "work_root": str(RUN), "tests_run": result.testsRun,
        "successful": result.wasSuccessful(), "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "alias_checks": ALIAS_EVIDENCE,
        "storage_guard_sha256": hashlib.sha256((SCRIPTS / "storage_guard.py").read_bytes()).hexdigest(),
        "scope": "Fresh explicitly selected test-parent fixtures only; no real state read, build, native purge or recursive cleanup"}
    path = RUN / "state-boundary-result.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(path), "successful": report["successful"], "tests_run": report["tests_run"]}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
