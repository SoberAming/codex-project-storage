import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock
import uuid

ROOT = None
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "native_cache_guard.py"
spec = importlib.util.spec_from_file_location("native_cache_guard", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class NativeCacheTests(unittest.TestCase):
    def setUp(self):
        if ROOT is None:
            self.fail("Run this test script with required --work-root PATH")
        self.fixture = tempfile.TemporaryDirectory(prefix="native-cache-fixture-", dir=str(ROOT))
        self.base = Path(self.fixture.name)
        self.addCleanup(self.cleanup_fixture)
        self.project = self.base / "project"
        self.project.mkdir(parents=True)
        self.cache = self.project / ".cache" / "pip"
        self.cache.mkdir(parents=True)
        (self.cache / "CACHEDIR.TAG").write_bytes(m.TAG + b"\n# Existing project cache marker\n")
        self.payload = self.cache / "http-v2" / "a" / "b" / "c" / "d" / "e" / ("abcde" + "0" * 51)
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(b"fake-cache-payload")
        self.exe = self.base / "trusted-tool" / "python.exe"
        self.exe.parent.mkdir()
        self.exe.write_bytes(b"FAKE NATIVE EXECUTABLE; never launched")
        self.pkg = self.base / "trusted-tool" / "pip"
        self.pkg.mkdir()
        for rel in ("_internal/commands/cache.py", "_internal/configuration.py", "_internal/utils/filesystem.py",
                    "_internal/cli/base_command.py", "_internal/cli/cmdoptions.py"):
            p = self.pkg / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# inert fake installed package\n", encoding="utf-8")
        self.config = self.project / ".storage-cache" / "pip.ini"
        self.config.parent.mkdir()
        self.config.write_text("[global]\ncache-dir = " + str(self.cache) + "\n", encoding="utf-8")
        (self.project / "requirements.txt").write_text("# inert fixture, no dependencies\n", encoding="utf-8")
        self.producer = self.project / ".storage-cache" / "producer.json"
        dump(self.producer, {"schema": "pip-cache-producer-v1", "project": str(self.project), "cwd": str(self.project),
            "executable": str(self.exe), "executable_sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
            "config": ".storage-cache/pip.ini", "config_sha256": hashlib.sha256(self.config.read_bytes()).hexdigest(),
            "config_loading": "PIP_CONFIG_FILE", "resolved_cache": str(self.cache),
            "operation": "install", "returncode": 0,
            "argv": m.pip_prefix(self.exe, self.cache) + ["install", "-r", "requirements.txt"]})
        self.binding = self.project / m.BINDING
        dump(self.binding, {"schema": "project-native-cache-binding-v1", "project": str(self.project),
             "tool": "pip", "cache": ".cache/pip", "ownership": "project-exclusive",
             "audit": {"reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "reviewed_by": "fixture-only",
                       "checked_project_roots": [str(self.project)], "external_references": "none-found",
                       "evidence": "Fictional test audit, never a production cache ownership assertion."},
             "producer_config": ".storage-cache/pip.ini", "producer_receipt": ".storage-cache/producer.json"})
        self.calls = []
        self.timeout = False
        self.remove_tag = False
        self.patches = [mock.patch.object(m, "executable_path", return_value=self.exe),
                        mock.patch.object(m, "run_native", side_effect=self.fake_native)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def cleanup_fixture(self):
        # Only this newly created fixture may be recursively removed.
        resolved_fixture = self.base.resolve()
        resolved_root = ROOT.resolve()
        if resolved_fixture == resolved_root or not m.guard.below(resolved_fixture, resolved_root):
            raise AssertionError("Temporary fixture escaped the explicit work root; retained")
        self.fixture.cleanup()

    def fake_native(self, argv, cwd, timeout=m.CHILD_SECONDS):
        self.calls.append((list(argv), str(cwd), m.clean_env(argv[0])))
        expected = m.pip_prefix(self.exe)
        if argv == expected + ["--version"]:
            output = "pip 26.1.1 from " + str(self.pkg) + " (python 3.13)\n"
        elif argv == expected + ["cache", "--help"]:
            output = "--isolated --cache-dir --disable-pip-version-check --no-input --no-color --log purge"
        elif argv == m.pip_prefix(self.exe, self.cache) + ["cache", "dir"]:
            output = str(self.cache) + "\n"
        elif argv == m.pip_prefix(self.exe, self.cache) + ["cache", "purge"]:
            if not self.timeout:
                self.payload.unlink()
                if self.remove_tag:
                    (self.cache / "CACHEDIR.TAG").unlink()
            return {"returncode": 1 if self.timeout else 0, "timed_out": self.timeout, "pid": 123456,
                    "output": "fixture native purge", "output_bytes": 20, "output_truncated": False}
        else:
            raise AssertionError("Unexpected native argv: " + repr(argv))
        return {"returncode": 0, "timed_out": False, "pid": 123456, "output": output,
                "output_bytes": len(output), "output_truncated": False}

    def plan(self):
        return m.inspect(self.project, "pip", ".cache/pip")

    def save_plan(self, plan=None):
        plan = self.plan() if plan is None else plan
        path = self.base / ("plan-" + uuid.uuid4().hex + ".json")
        digest = m.write_bounded(path, plan)
        args = argparse.Namespace(plan=str(path), receipt=str(self.base / ("receipt-" + uuid.uuid4().hex + ".json")),
                                  authorize_plan=digest, confirm_idle=True)
        return plan, args

    def apply(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return m.apply(args)

    def assert_no_purge(self):
        self.assertFalse(any(argv[-2:] == ["cache", "purge"] for argv, _, _ in self.calls))

    def test_valid_plan_does_not_purge(self):
        plan = self.plan()
        self.assertEqual(plan["status"], "executable", plan["reasons"])
        self.assertEqual(plan["snapshot"]["member_count"], 8)
        self.assert_no_purge()

    def test_valid_apply_is_fixed_native_command_and_single_use(self):
        plan, args = self.save_plan()
        self.assertEqual(self.apply(args), 0)
        receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "native_completed_verified_scope")
        self.assertEqual(receipt["verification"]["observed_removed_file_count"], 1)
        self.assertFalse(self.payload.exists())
        self.assertEqual(sum(argv[-2:] == ["cache", "purge"] for argv, _, _ in self.calls), 1)
        self.assertEqual(self.calls[-1][0], m.pip_prefix(self.exe, self.cache) + ["cache", "purge"])
        with self.assertRaises(m.guard.GuardError):
            args.receipt = str(self.base / "replay.json")
            self.apply(args)

    def test_mixed_source_is_advice(self):
        (self.cache / "customer.py").write_text("important source", encoding="utf-8")
        self.assertEqual(self.plan()["status"], "advice_only")
        self.assert_no_purge()

    def test_nested_database_is_advice(self):
        (self.payload.parent / "session.db").write_bytes(b"protected")
        self.assertEqual(self.plan()["status"], "advice_only")

    def test_sessions_directory_is_advice(self):
        (self.cache / "sessions").mkdir()
        self.assertEqual(self.plan()["status"], "advice_only")

    def test_legacy_selfcheck_is_advice(self):
        (self.cache / "selfcheck.json").write_text("{}")
        self.assertEqual(self.plan()["status"], "advice_only")

    def test_tag_alone_is_not_binding(self):
        self.binding.unlink()
        self.assertEqual(self.plan()["status"], "advice_only")

    def test_missing_existing_tag_is_advice(self):
        (self.cache / "CACHEDIR.TAG").unlink()
        self.assertEqual(self.plan()["status"], "advice_only")

    def test_external_cache_is_advice(self):
        self.assertEqual(m.inspect(self.project, "pip", "../elsewhere")["status"], "advice_only")

    def test_uv_npm_always_advice(self):
        for tool in ("uv", "npm"):
            self.assertEqual(m.inspect(self.project, tool, ".cache/pip")["status"], "advice_only")
        self.assert_no_purge()

    def test_forged_kind_does_not_bypass_mixed_file(self):
        plan, args = self.save_plan()
        (self.cache / "source.py").write_text("important", encoding="utf-8")
        plan["snapshot"]["members"].append({"path": "source.py", "kind": "http-payload", "type": "file"})
        plan["command"] = [str(self.exe), "--force"]
        _, args = self.save_plan(plan)
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assert_no_purge()

    def test_member_content_changed_with_restored_mtime_stops(self):
        _, args = self.save_plan()
        previous = self.payload.stat()
        self.payload.write_bytes(b"X" * previous.st_size)
        os.utime(self.payload, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assert_no_purge()

    def test_binding_changed_stops(self):
        _, args = self.save_plan()
        binding = json.loads(self.binding.read_text())
        binding["ownership"] = "shared"
        dump(self.binding, binding)
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assert_no_purge()

    def test_tool_changed_stops(self):
        _, args = self.save_plan()
        self.exe.write_bytes(b"replacement fake executable")
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assert_no_purge()

    def test_missing_idle_confirmation_stops(self):
        _, args = self.save_plan()
        args.confirm_idle = False
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assert_no_purge()

    def test_timeout_claim_blocks_automatic_replay(self):
        _, args = self.save_plan()
        self.timeout = True
        self.assertEqual(self.apply(args), 3)
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertEqual(receipt["status"], "native_failed_or_timed_out_no_retry")
        args.receipt = str(self.base / "retry.json")
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assertEqual(sum(argv[-2:] == ["cache", "purge"] for argv, _, _ in self.calls), 1)

    def test_host_environment_is_not_inherited(self):
        with mock.patch.dict(os.environ, {"PIP_LOG": "SECRET", "PIP_CACHE_DIR": "OTHER", "PYTHONPATH": "BAD",
                                        "PYTHONHOME": "BAD", "PYTHONSTARTUP": "BAD", "NODE_OPTIONS": "BAD",
                                        "LD_PRELOAD": "BAD", "HTTPS_PROXY": "BAD"}):
            env = m.clean_env(self.exe)
        self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
        self.assertFalse(any(k in env for k in ("PIP_LOG", "PIP_CACHE_DIR", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "LD_PRELOAD", "HTTPS_PROXY", "NODE_OPTIONS")))

    def test_malformed_ini_does_not_leak_source(self):
        self.config.write_text("_authToken=SECRET_SENTINEL\n", encoding="utf-8")
        plan = self.plan()
        self.assertEqual(plan["status"], "advice_only")
        self.assertNotIn("SECRET_SENTINEL", json.dumps(plan))

    def test_plan_sha_mismatch_stops(self):
        _, args = self.save_plan()
        args.authorize_plan = "0" * 64
        with self.assertRaises(m.guard.GuardError):
            self.apply(args)
        self.assert_no_purge()

    def test_guard_lock_conflict_stops(self):
        _, args = self.save_plan()
        lock = self.project / (".native-cache-lock-" + hashlib.sha256(str(self.cache).encode()).hexdigest()[:24])
        lock.write_text("other active operation")
        with self.assertRaises(OSError):
            self.apply(args)
        self.assertEqual(lock.read_text(), "other active operation")
        self.assert_no_purge()

    def test_output_inside_project_refused(self):
        with self.assertRaises(m.guard.GuardError):
            m.output_path(self.project / "plan.json", self.project)

    def test_protected_config_evidence_is_not_read(self):
        critical = self.project / "sessions" / "config.ini"
        critical.parent.mkdir()
        critical.write_text("_authToken=CRITICAL_SENTINEL", encoding="utf-8")
        binding = json.loads(self.binding.read_text())
        binding["producer_config"] = "sessions/config.ini"
        dump(self.binding, binding)
        original = m.read_small
        def checked(path):
            if Path(path) == critical:
                raise AssertionError("Protected content must never be opened")
            return original(path)
        with mock.patch.object(m, "read_small", side_effect=checked):
            plan = self.plan()
        self.assertEqual(plan["status"], "advice_only")
        self.assertNotIn("CRITICAL_SENTINEL", json.dumps(plan))

    def test_scandir_error_prevents_complete_snapshot(self):
        original = os.scandir
        def denied(path):
            if str(path) == str(self.payload.parent):
                raise PermissionError("fixture unreadable subtree")
            return original(path)
        with mock.patch.object(m.os, "scandir", side_effect=denied):
            plan = self.plan()
        self.assertEqual(plan["status"], "advice_only")
        self.assertNotIn("snapshot", plan)

    def test_second_pass_budget_is_bounded(self):
        original = os.walk
        count = [0]
        def walking(*args, **kwargs):
            count[0] += 1
            for directory, dirs, files in original(*args, **kwargs):
                if count[0] == 2 and Path(directory) == self.cache:
                    files = files + ["CACHEDIR.TAG"]
                yield directory, dirs, files
        with mock.patch.object(m.os, "walk", side_effect=walking), mock.patch.object(m, "MAX_MEMBERS", 8):
            with self.assertRaises(m.guard.GuardError):
                m.snapshot(self.cache)

    def test_unexpected_marker_removal_is_not_verified_success(self):
        _, args = self.save_plan()
        self.remove_tag = True
        self.assertEqual(self.apply(args), 3)
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertIn("CACHEDIR.TAG", receipt["verification"]["unexpected_removed_files"])
        self.assertNotEqual(receipt["status"], "native_completed_verified_scope")


def main():
    global ROOT
    parser = argparse.ArgumentParser(description="Run 25 native-cache guard tests using isolated temporary fixtures.", allow_abbrev=False)
    parser.add_argument("--work-root", required=True, type=Path, help="Explicit directory below which temporary test fixtures may be created")
    options, unittest_args = parser.parse_known_args()
    ROOT = options.work_root.expanduser().absolute()
    m.guard.ancestors(ROOT, missing=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    m.guard.ancestors(ROOT)
    # Consume only this harness's option; unittest receives its own arguments.
    unittest.main(argv=[sys.argv[0], *unittest_args], verbosity=2)


if __name__ == "__main__":
    main()
