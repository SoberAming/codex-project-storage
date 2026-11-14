"""Isolated cross-Agent state and administrative-IO boundary tests.

Fixtures remain under the selected work parent. No real Agent state is read,
no services are started, and no project command or native cache cleanup runs.
"""
from __future__ import annotations

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
opts, _ = parser.parse_known_args()
BASE = Path(opts.work_root).absolute()
BASE.mkdir(parents=True, exist_ok=True)
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import storage_guard as G
import npm_cache_guard as N
import native_cache_guard as C
import generated_artifact_guard as A
import relocation_guard as R
import retired_runtime_guard as T

RUN = Path(tempfile.mkdtemp(prefix="agent-state-boundaries-", dir=BASE))
ALIASES = []
NAMES = (".claude", ".kimi", ".kimi-code", ".workbuddy", ".codebuddy")


class AgentStateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project"
        self.home = self.area / "fictional-home"
        self.codex = self.area / "codex-state"
        self.sqlite = self.area / "sqlite-state"
        self.claude = self.area / "ordinary-claude-config"
        self.kimi = self.area / "ordinary-kimi-root"
        for path in (self.project, self.home, self.codex, self.sqlite, self.claude, self.kimi):
            path.mkdir()
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "CODEX_HOME": str(self.codex), "CODEX_SQLITE_HOME": str(self.sqlite),
            "CLAUDE_CONFIG_DIR": str(self.claude), "KIMI_CODE_HOME": str(self.kimi),
            "PROJECT_STORAGE_STATE_ROOTS": "[]",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def assert_admin_refused_before_io(self, path):
        with mock.patch.object(G, "guarded_file", side_effect=AssertionError("body reader reached")):
            with self.assertRaises(G.GuardError):
                G.read_json(path)
        output = path.parent / "never-created" / "receipt.json"
        with self.assertRaises(G.GuardError):
            G.safe_output(output)
        self.assertFalse(output.parent.exists())
        with self.assertRaises(N.g.GuardError):
            N.private_io_path(path)

    def test_named_agent_state_roots_refuse_project_and_administrative_io(self):
        for name in NAMES:
            state = self.project / name
            state.mkdir()
            (state / "ordinary.json").write_text('{"fictional":true}', encoding="utf-8")
            child = state / "ordinary"
            child.mkdir()
            with self.subTest(name=name):
                with self.assertRaises(G.GuardError):
                    G.project_root(child)
                self.assert_admin_refused_before_io(state / "ordinary.json")

    def test_named_state_pyc_never_enters_cleanup_scan(self):
        for name in NAMES:
            state = self.project / name
            state.mkdir()
            source = state / "module.py"
            source.write_text("VALUE = 1\n", encoding="utf-8")
            pyc = Path(py_compile.compile(str(source), doraise=True))
            old = time.time() - 72 * 3600
            os.utime(pyc, (old, old))
            before = hashlib.sha256(pyc.read_bytes()).hexdigest()
            output = self.area / (name[1:] + "-scan")
            args = argparse.Namespace(project=str(state), output=str(output), codex_home=str(self.codex),
                min_age_hours=48.0, max_files=1000, baseline=None)
            with self.subTest(name=name), self.assertRaises(G.GuardError):
                G.scan(args)
            self.assertFalse(output.exists())
            self.assertEqual(before, hashlib.sha256(pyc.read_bytes()).hexdigest())
        output = self.area / "outer-scan"
        with contextlib.redirect_stdout(io.StringIO()):
            G.scan(argparse.Namespace(project=str(self.project), output=str(output), codex_home=str(self.codex),
                min_age_hours=48.0, max_files=1000, baseline=None))
        report = json.loads((output / "scan.json").read_text(encoding="utf-8"))
        self.assertEqual(report["candidates"], [])
        self.assertTrue(set(NAMES).issubset(report["coverage"]["pruned_subtrees"]))

    def test_real_configured_roots_are_protected_with_plain_names(self):
        for state in (self.codex, self.sqlite, self.claude, self.kimi):
            file = state / "ordinary.json"
            file.write_text('{"fictional":true}', encoding="utf-8")
            with self.subTest(state=state.name):
                with self.assertRaises(G.GuardError):
                    G.project_root(state)
                self.assert_admin_refused_before_io(file)

    def test_explicit_custom_root_and_descendant_are_protected(self):
        state = self.area / "unknown-host-runtime"
        state.mkdir()
        child = state / "ordinary"
        child.mkdir()
        file = child / "ordinary.json"
        file.write_text('{"fictional":true}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"PROJECT_STORAGE_STATE_ROOTS": json.dumps([str(state)])}):
            for path in (state, child):
                with self.subTest(path=path.name), self.assertRaises(G.GuardError):
                    G.project_root(path)
            self.assert_admin_refused_before_io(file)
            self.assertEqual(G.project_root(self.project), self.project)

    def test_native_small_reader_refuses_custom_state_before_body_access(self):
        state = self.area / "unknown-host-runtime"
        state.mkdir()
        file = state / "opaque.state.json"
        file.write_text('{"schema":"innocent-looking-schema","fictional":true}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"PROJECT_STORAGE_STATE_ROOTS": json.dumps([str(state)])}), \
                mock.patch.object(N.n.guard, "guarded_file", side_effect=AssertionError("native body reader reached")):
            with self.assertRaises(N.n.guard.GuardError):
                N.n.read_small(file)
            with self.assertRaises(N.n.guard.GuardError):
                N.n.file_record(file)

    def test_existing_executor_entries_refuse_cross_agent_state_before_probes(self):
        named = self.project / ".claude"
        named.mkdir()
        for state in (named, self.claude):
            args = argparse.Namespace(project=str(state), source="scratch", assessment=str(self.area / "missing.json"),
                output=str(self.area / "never-plan.json"), target=str(self.area / "target"), action="migrate",
                codex_home=str(self.codex), max_files=50, max_bytes=1048576, reserve_bytes=0,
                min_age_hours=48, idle_seconds=1, confirm_idle=True)
            with self.subTest(state=state.name, executor="pip"), \
                    mock.patch.object(C, "probe_pip", side_effect=AssertionError("native probe reached")):
                with self.assertRaises(C.guard.GuardError):
                    C.inspect(state, "pip", ".cache/pip")
            with self.subTest(state=state.name, executor="npm"), \
                    mock.patch.object(N.g, "guarded_file", side_effect=AssertionError("npm content reader reached")):
                with self.assertRaises(N.g.GuardError):
                    N.inspect(state, ".npm", self.area / "missing.json", self.area / "node", self.area / "npm.js")
            with self.subTest(state=state.name, executor="media"), \
                    mock.patch.object(A, "collect_source", side_effect=AssertionError("payload scan reached")):
                with self.assertRaises(A.g.GuardError):
                    A.plan_command(args)
            with self.subTest(state=state.name, executor="relocation"), \
                    mock.patch.object(R, "source_policy", side_effect=AssertionError("source policy reached")):
                with self.assertRaises(R.g.GuardError):
                    R.plan_command(args)
            with self.subTest(state=state.name, executor="synthetic-PG"), \
                    mock.patch.object(T, "source_path", side_effect=AssertionError("source scan reached")):
                with self.assertRaises(T.g.GuardError):
                    T.plan_command(args)
        self.assertFalse((self.area / "never-plan.json").exists())

    def test_project_containing_future_state_is_refused_without_creation(self):
        future = self.project / "future-agent-state" / "ordinary-data"
        for variable, value in (("CLAUDE_CONFIG_DIR", str(future)), ("KIMI_CODE_HOME", str(future)),
                                ("PROJECT_STORAGE_STATE_ROOTS", json.dumps([str(future)]))):
            with self.subTest(variable=variable), mock.patch.dict(os.environ, {variable: value}):
                with self.assertRaises(G.GuardError):
                    G.project_root(self.project)
                with self.assertRaises(G.GuardError):
                    G.safe_output(future / "receipt.json")
            self.assertFalse(future.parent.exists())

    def test_invalid_explicit_root_configuration_fails_closed(self):
        invalid = ("", "not-json", "{}", '"absolute-string-is-not-an-array"', '[1]', '[null]',
                   '[true]', '["relative"]', '["~/relative"]', '[NaN]', '["\\u0000"]')
        for value in invalid:
            with self.subTest(value=value), mock.patch.dict(os.environ, {"PROJECT_STORAGE_STATE_ROOTS": value}):
                with self.assertRaises(G.GuardError):
                    G.agent_state_roots()
                with self.assertRaises(G.GuardError):
                    G.safe_output(self.area / "new-parent" / "receipt.json")
                with self.assertRaises(G.GuardError):
                    G.project_root(self.project)
            self.assertFalse((self.area / "new-parent").exists())

    def test_invalid_host_root_configuration_fails_closed(self):
        for variable in ("CODEX_HOME", "CODEX_SQLITE_HOME", "CLAUDE_CONFIG_DIR", "KIMI_CODE_HOME"):
            for value in ("", "relative-path"):
                with self.subTest(variable=variable, value=value), mock.patch.dict(os.environ, {variable: value}):
                    with self.assertRaises(G.GuardError):
                        G.protect_agent_state_path(self.area / "unused.json")

    def test_roots_are_deduplicated_without_enumerating_or_opening_state(self):
        with mock.patch.dict(os.environ, {"PROJECT_STORAGE_STATE_ROOTS": json.dumps([str(self.claude), str(self.claude)])}), \
                mock.patch.object(os, "scandir", side_effect=AssertionError("state enumeration reached")), \
                mock.patch.object(Path, "open", side_effect=AssertionError("body read reached")):
            roots = G.agent_state_roots()
            self.assertEqual(len(roots), len({G.key(path) for path in roots}))
            self.assertIn(self.claude, roots)
            self.assertEqual(G.protect_agent_state_path(self.area / "ordinary.json"), self.area / "ordinary.json")

    def test_physical_alias_refused_with_metadata_only(self):
        alias = self.area / "plain-alias"
        try:
            os.symlink(self.claude, alias, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.assertFalse(os.path.lexists(alias))
            alias.mkdir()
            actual_same = os.path.samefile
            pair = {G.key(alias), G.key(self.claude)}
            def samefile(left, right):
                if {G.key(left), G.key(right)} == pair:
                    return True
                return actual_same(left, right)
            ALIASES.append({"mode": "controlled_directory_identity_alias", "native_alias_verified": False,
                            "reason": type(exc).__name__})
            manager = mock.patch.object(os.path, "samefile", side_effect=samefile)
        else:
            ALIASES.append({"mode": "native_directory_symlink", "native_alias_verified": True})
            manager = contextlib.nullcontext()
        with manager, mock.patch.object(G, "guarded_file", side_effect=AssertionError("body reader reached")):
            with self.assertRaises(G.GuardError):
                G.protect_agent_state_path(alias / "ordinary.json")
            with self.assertRaises(G.GuardError):
                G.safe_output(alias / "new-parent" / "receipt.json")
        self.assertFalse((self.claude / "new-parent").exists())

    def test_codex_worktree_payload_exception_does_not_allow_state_admin_io(self):
        repo = self.codex / "worktrees" / "run-id" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").write_text("gitdir: fictional-not-followed\n", encoding="utf-8")
        self.assertEqual(G.project_root(repo), repo)
        with self.assertRaises(G.GuardError):
            G.safe_output(repo / "receipt.json")
        self.assertFalse((repo / "receipt.json").exists())

    def test_other_state_root_inside_codex_worktree_still_wins(self):
        repo = self.codex / "worktrees" / "run-id" / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").write_text("gitdir: fictional-not-followed\n", encoding="utf-8")
        future = repo / "future-state"
        with mock.patch.dict(os.environ, {"PROJECT_STORAGE_STATE_ROOTS": json.dumps([str(future)])}):
            with self.assertRaises(G.GuardError):
                G.project_root(repo)
        self.assertFalse(future.exists())

    def test_case_variant_state_names_are_protected(self):
        for name in (".CLAUDE", ".KiMi-CoDe", ".WORKBUDDY", ".CODEBUDDY"):
            with self.subTest(name=name), self.assertRaises(G.GuardError):
                G.protect_agent_state_path(self.project / name / "receipt.json")

    def test_future_configured_state_case_alias_does_not_create_a_directory(self):
        state = self.area / "FutureAgentState"
        variant = self.area / "futureagentstate"
        with mock.patch.dict(os.environ, {"PROJECT_STORAGE_STATE_ROOTS": json.dumps([str(state)])}):
            with self.assertRaises(G.GuardError):
                G.safe_output(variant / "receipt.json")
        self.assertFalse(state.exists())
        self.assertFalse(variant.exists())


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AgentStateBoundaryTests))
    report = {"test": "cross-agent-state-boundaries", "tests_run": result.testsRun,
        "successful": result.wasSuccessful(), "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "work_root": str(RUN), "alias_checks": ALIASES,
        "scope": "Fictional isolated metadata/admin-IO fixtures only; no real Agent state or native cleanup",
        "storage_guard_sha256": hashlib.sha256((SCRIPTS / "storage_guard.py").read_bytes()).hexdigest()}
    output = RUN / "agent-state-result.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(output), "successful": result.wasSuccessful(), "tests_run": result.testsRun}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
