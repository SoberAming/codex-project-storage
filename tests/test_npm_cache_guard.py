"""Isolated npm cache safety tests; no real user cache or project is touched."""
import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

ROOT = None
INTEGRATION_NODE = None
INTEGRATION_CLI = None
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "npm_cache_guard.py"
spec = importlib.util.spec_from_file_location("npm_cache_guard", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class NpmCacheTests(unittest.TestCase):
    def setUp(self):
        if ROOT is None:
            self.fail("Run with --work-root to constrain disposable test fixtures")
        self.temp = tempfile.TemporaryDirectory(prefix="npm-cache-test-", dir=ROOT)
        self.base = Path(self.temp.name)
        self.addCleanup(self.cleanup)
        self.project = self.base / "project"
        self.cache = self.project / ".runtime" / "npm-cache"
        self.source = self.cache / "_cacache"
        self.source.mkdir(parents=True)
        self.keep = self.project / "main.ts"
        self.keep.write_text("export const unique = 'keep';\n", encoding="utf-8")
        self.producer = self.project / "start.ps1"
        self.producer.write_text("# Fixture producer, never executed\nnpm install --cache " + str(self.cache) + "\n", encoding="utf-8")
        self.log = self.cache / "_logs" / "fixture-debug.log"
        self.log.parent.mkdir()
        self.log.write_text('1 verbose argv "install" "--cache" "' + str(self.cache) + '"\n2 verbose exit 0\n', encoding="utf-8")
        data = b"Fixture disposable npm package cache data\n" * 8
        address = hashlib.sha512(data).hexdigest()
        self.payload = self.source / "content-v2" / "sha512" / address[:2] / address[2:4] / address[4:]
        self.payload.parent.mkdir(parents=True)
        self.payload.write_bytes(data)
        index_key = "make-fetch-happen:request-cache:https://registry.example.invalid/fixture"
        key_hash = hashlib.sha256(index_key.encode()).hexdigest()
        self.index = self.source / "index-v5" / key_hash[:2] / key_hash[2:4] / key_hash[4:]
        self.index.parent.mkdir(parents=True)
        payload = json.dumps({"key": index_key, "integrity": "sha512-QUFBQQ==", "time": 1, "size": len(data)}).encode()
        self.index.write_bytes(b"\n" + hashlib.sha1(payload).hexdigest().encode() + b"\t" + payload)
        self.node = self.base / "trusted" / "node.exe"
        self.cli = self.base / "trusted" / "npm" / "bin" / "npm-cli.js"
        self.assessment = self.base / "review.json"
        self.review = {
            "schema": m.ASSESSMENT, "project": str(self.project), "cache": ".runtime/npm-cache",
            "ownership": "project-exclusive-refetchable",
            "producer": {"path": "start.ps1", "excerpts": ["npm install --cache " + str(self.cache)],
                         "explanation": "Inert synthetic fixture explicitly directs npm package payloads to this one isolated project cache."},
            "existing_log": ".runtime/npm-cache/_logs/fixture-debug.log",
            "review": {
                "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "reviewed_by": "synthetic-unit-test",
                "checked_project_roots": [str(self.project)], "external_references": "none-found", "writers": "none-found",
                "reference_findings": "Synthetic fixture has one project only; startup script contains the explicit dedicated cache path and no other consumer exists.",
                "refetch_findings": "All payloads here are synthetic disposable package fetch artifacts; no private offline-only tarball or authoritative input is stored here.",
                "activity_checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "activity_findings": "Only this unittest owns the new temporary fixture; no npm producer is running and no external process was given its random path."}}
        dump(self.assessment, self.review)
        self.tool = {"node": str(self.node), "npm_cli": str(self.cli), "npm_version": "10.9.2", "test_tool": True}
        self.fail_native = False
        self.recreate_source = False
        self.calls = []
        self.patches = [mock.patch.object(m, "probe_tool", return_value=self.tool),
                        mock.patch.object(m, "run_native", side_effect=self.fake_native)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def cleanup(self):
        fixture = self.base.resolve()
        root = Path(ROOT).resolve()
        if fixture == root or not m.g.below(fixture, root):
            raise AssertionError("Temporary test fixture escaped explicit work root; retained")
        self.temp.cleanup()

    def fake_native(self, argv, cwd, home, timeout=m.CHILD_SECONDS):
        self.calls.append(list(argv))
        stage = Path(cwd)
        self.assertTrue(m.g.below(stage, self.cache))
        self.assertEqual(argv, m.npm_command(self.tool, stage))
        if self.recreate_source:
            self.source.mkdir()
            (self.source / "new-running-data").write_text("must survive", encoding="utf-8")
        if not self.fail_native:
            target = stage / "_cacache"
            self.assertTrue(m.g.below(target.resolve(), self.base.resolve()))
            shutil.rmtree(target)  # Only the newly made synthetic fixture.
        return {"returncode": 1 if self.fail_native else 0, "timed_out": self.fail_native,
                "pid": 123, "output": "synthetic native result", "output_bytes": 23, "output_truncated": False}

    def plan(self):
        return m.inspect(self.project, ".runtime/npm-cache", self.assessment, self.node, self.cli)

    def saved(self):
        plan = self.plan()
        self.assertEqual(plan["status"], "executable", plan["reasons"])
        output = self.base / "plan.json"
        digest = m.n.write_bounded(output, plan)
        args = argparse.Namespace(plan=str(output), authorize_plan=digest,
                                  receipt=str(self.base / "receipt.json"), confirm_idle=True)
        return plan, args

    def apply(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return m.apply(args)

    def assert_blocked(self):
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(plan["reasons"])
        self.assertTrue(self.payload.exists())
        self.assertFalse(self.calls)

    def test_real_bytes_can_be_retired_and_siblings_survive(self):
        plan, args = self.saved()
        self.assertEqual(self.apply(args), 0)
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertEqual(receipt["observed_removed_logical_bytes"], plan["snapshot"]["logical_bytes"])
        self.assertGreater(receipt["observed_removed_logical_bytes"], 0)
        self.assertTrue(self.log.exists())
        self.assertTrue(self.keep.exists())
        self.assertTrue(self.producer.exists())
        self.assertFalse(self.source.exists())
        self.assertFalse(receipt["exact_delete_manifest"])

    def test_unknown_manual_note_refuses_whole_scope(self):
        (self.source / "important-notes.md").write_text("unique")
        self.assert_blocked()

    def test_content_address_mismatch_is_not_permission_to_delete(self):
        self.payload.write_bytes(b"unexpected user data")
        self.assert_blocked()

    def test_corrupt_index_is_retained(self):
        self.index.write_bytes(b"business rows\n")
        self.assert_blocked()

    def test_nonempty_tmp_is_retained(self):
        (self.source / "tmp").mkdir()
        (self.source / "tmp" / "work-in-progress").write_text("active")
        self.assert_blocked()

    def test_boolean_provenance_is_insufficient(self):
        dump(self.assessment, {"test": True, "safe": True})
        self.assert_blocked()

    def test_missing_historical_log_is_not_recreated(self):
        self.log.unlink()
        self.assert_blocked()
        self.assertFalse(self.log.exists())

    def test_log_of_another_cache_is_not_ownership(self):
        self.log.write_text('verbose argv "install" "--cache" "somewhere-else"\nverbose exit 0')
        self.assert_blocked()

    def test_unsupported_native_contract_is_blocked(self):
        with mock.patch.object(m, "probe_tool", side_effect=m.g.GuardError("unsupported version")):
            self.assert_blocked()

    def test_nonexistent_producer_excerpt_is_rejected(self):
        self.review["producer"]["excerpts"] = ["npm install --cache unknown"]
        dump(self.assessment, self.review)
        self.assert_blocked()

    def test_shared_reference_is_not_eligible(self):
        self.review["review"]["external_references"] = "another-project-uses-it"
        dump(self.assessment, self.review)
        self.assert_blocked()

    def test_unknown_activity_is_not_idle(self):
        self.review["review"]["writers"] = "unknown"
        dump(self.assessment, self.review)
        self.assert_blocked()

    def test_stale_activity_review_is_refused(self):
        self.review["review"]["activity_checked_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        dump(self.assessment, self.review)
        self.assert_blocked()

    def test_producer_below_cleanup_scope_is_not_evidence(self):
        self.review["producer"]["path"] = ".runtime/npm-cache/_cacache/proof.js"
        (self.source / "proof.js").write_text("npm install --cache something")
        dump(self.assessment, self.review)
        self.assert_blocked()

    def test_links_are_refused(self):
        target = self.source / "content-v2" / "link"
        try:
            target.symlink_to(self.keep)
        except OSError:
            self.skipTest("Platform account cannot create symlinks")
        self.assert_blocked()

    def test_hardlinked_payload_is_refused(self):
        try:
            os.link(self.payload, self.base / "outside-link")
        except OSError:
            self.skipTest("Fixture filesystem cannot create hardlinks")
        self.assert_blocked()

    def test_plan_then_new_member_refuses_before_detach(self):
        _, args = self.saved()
        (self.source / "unique.patch").write_text("keep")
        with self.assertRaises(m.g.GuardError):
            self.apply(args)
        self.assertTrue(self.payload.exists())
        self.assertFalse(self.calls)

    def test_plan_then_provenance_change_refuses_before_detach(self):
        _, args = self.saved()
        self.producer.write_text("edited producer")
        with self.assertRaises(m.g.GuardError):
            self.apply(args)
        self.assertTrue(self.payload.exists())
        self.assertFalse(self.calls)

    def test_producer_change_during_second_tool_probe_stops_before_native(self):
        _, args = self.saved()
        calls = []
        def probing(*_):
            calls.append(1)
            if len(calls) == 2:
                self.producer.write_text("npm producer changed after source detach", encoding="utf-8")
            return self.tool
        with mock.patch.object(m, "probe_tool", side_effect=probing):
            with self.assertRaises(m.g.GuardError):
                self.apply(args)
        self.assertFalse(self.calls, "No native clean may run after its producer changed")
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertEqual(receipt["status"], "stopped_requires_review_no_retry")
        self.assertTrue(Path(receipt["detached_source"]).exists())
        self.assertEqual(receipt["observed_removed_logical_bytes"], 0)

    def test_assessment_change_during_second_tool_probe_stops_before_native(self):
        _, args = self.saved()
        calls = []
        def probing(*_):
            calls.append(1)
            if len(calls) == 2:
                self.review["review"]["writers"] = "active"
                dump(self.assessment, self.review)
            return self.tool
        with mock.patch.object(m, "probe_tool", side_effect=probing):
            with self.assertRaises(m.g.GuardError):
                self.apply(args)
        self.assertFalse(self.calls)
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertTrue(Path(receipt["detached_source"]).exists())

    @unittest.skipUnless(os.name == "nt", "Windows mandatory sharing denial only")
    def test_evidence_is_write_protected_until_native_returns(self):
        _, args = self.saved()
        original = self.fake_native
        denied = []
        def native(argv, cwd, home, timeout=m.CHILD_SECONDS):
            for path in (self.assessment, self.producer, self.log):
                with self.assertRaises(OSError):
                    with open(path, "wb") as output:
                        output.write(b"must not replace evidence")
                denied.append(str(path))
            return original(argv, cwd, home, timeout)
        with mock.patch.object(m, "run_native", side_effect=native):
            self.assertEqual(self.apply(args), 0)
        self.assertEqual(len(denied), 3)

    def test_observed_post_native_evidence_drift_preserves_known_native_result(self):
        _, args = self.saved()
        original = m.evidence_fd_record
        calls = []
        def recording(fd, path):
            result = original(fd, path)
            if Path(path) == self.producer:
                calls.append(1)
                if len(calls) > 1:
                    return {**result, "sha256": "0" * 64}
            return result
        with mock.patch.object(m, "evidence_fd_record", side_effect=recording):
            with self.assertRaises(m.g.GuardError):
                self.apply(args)
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertEqual(receipt["status"], "stopped_requires_review_no_retry")
        self.assertIsNotNone(receipt["native_result"])
        self.assertEqual(receipt["native_result"]["returncode"], 0)
        self.assertEqual(receipt["observed_removed_logical_bytes"], 0)
        self.assertEqual(len(self.calls), 1)

    def test_plan_then_payload_change_refuses_before_detach(self):
        _, args = self.saved()
        self.payload.write_bytes(b"changed")
        with self.assertRaises(m.g.GuardError):
            self.apply(args)
        self.assertTrue(self.payload.exists())

    def test_hash_authorization_required(self):
        _, args = self.saved()
        args.authorize_plan = "0" * 64
        with self.assertRaises(m.g.GuardError):
            self.apply(args)
        self.assertTrue(self.payload.exists())

    def test_explicit_idle_confirmation_required(self):
        _, args = self.saved()
        args.confirm_idle = False
        with self.assertRaises(m.g.GuardError):
            self.apply(args)
        self.assertTrue(self.payload.exists())

    def test_native_timeout_keeps_detached_path_and_forbids_replay(self):
        _, args = self.saved()
        self.fail_native = True
        self.assertEqual(self.apply(args), 3)
        receipt = json.loads(Path(args.receipt).read_text())
        self.assertTrue(Path(receipt["detached_source"]).exists())
        self.assertEqual(receipt["observed_removed_logical_bytes"], 0)
        args.receipt = str(self.base / "other-receipt.json")
        with self.assertRaises(m.g.GuardError):
            self.apply(args)
        self.assertEqual(len(self.calls), 1)

    def test_source_recreated_by_new_writer_is_never_touched(self):
        _, args = self.saved()
        self.recreate_source = True
        self.assertEqual(self.apply(args), 0)
        self.assertEqual((self.source / "new-running-data").read_text(), "must survive")

    def test_environment_injection_is_not_inherited(self):
        with mock.patch.dict(os.environ, {"NODE_OPTIONS": "--require secret.js", "NODE_PATH": "evil",
                                         "NPM_CONFIG_CACHE": "elsewhere", "HTTP_PROXY": "secret", "LD_PRELOAD": "evil"}):
            env = m.clean_env(self.node, self.base)
        for key in ("NODE_OPTIONS", "NODE_PATH", "NPM_CONFIG_CACHE", "HTTP_PROXY", "LD_PRELOAD"):
            self.assertNotIn(key, env)
        self.assertEqual(env["PATH"], str(self.node.parent))

    def test_command_has_only_scoped_cache_clean_and_required_force(self):
        command = m.npm_command(self.tool, self.base)
        self.assertEqual(command[-3:], ["cache", "clean", "--force"])
        self.assertIn("--offline=true", command)
        self.assertIn("--ignore-scripts=true", command)
        self.assertIn("--cache=" + str(self.base), command)
        self.assertNotIn("install", command)

    def test_source_must_be_project_relative(self):
        with self.assertRaises(m.g.GuardError):
            m.cache_scope(self.project, "../shared-cache")

    def test_business_pgdata_cannot_be_adopted_as_cache(self):
        with self.assertRaises(m.g.GuardError):
            m.cache_scope(self.project, ".runtime/pgdata")

    def test_working_home_cannot_be_selected_as_project(self):
        with self.assertRaises(m.g.GuardError):
            m.g.project_root(Path.home())

    def assert_assessment_zero_content_reads(self, path):
        with mock.patch.object(m.os, "read", side_effect=AssertionError("Private body read attempted")) as reader:
            plan = m.inspect(self.project, ".runtime/npm-cache", path, self.node, self.cli)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(reader.call_count, 0)
        self.assertFalse(self.calls)

    def test_sensitive_assessment_names_are_rejected_before_any_body_read(self):
        for name in ("auth.json", "config.toml", "state_5.sqlite", "history.jsonl", "passwords.json"):
            with self.subTest(name=name):
                path = self.base / name
                path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
                self.assert_assessment_zero_content_reads(path)

    def test_configured_codex_home_assessment_rejected_before_any_body_read(self):
        state = self.base / "opaque-profile"
        state.mkdir()
        path = state / "ordinary.json"
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(state)}):
            self.assert_assessment_zero_content_reads(path)

    def test_default_codex_home_assessment_rejected_before_any_body_read(self):
        home = self.base / "fictional-home"
        path = home / ".codex" / "ordinary.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        with mock.patch.object(m.Path, "home", return_value=home):
            self.assert_assessment_zero_content_reads(path)

    def test_configured_sqlite_home_assessment_rejected_before_any_body_read(self):
        state = self.base / "opaque-database-store"
        state.mkdir()
        path = state / "ordinary.json"
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"CODEX_SQLITE_HOME": str(state)}):
            self.assert_assessment_zero_content_reads(path)

    def test_known_state_identity_alias_rejected_before_any_body_read(self):
        state, alias = self.base / "opaque-profile", self.base / "alternate-name"
        state.mkdir()
        alias.mkdir()
        path = alias / "ordinary.json"
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        original = m.os.path.samefile
        def samefile(a, b):
            if m.g.key(a) == m.g.key(alias) and m.g.key(b) == m.g.key(state):
                return True  # Model a known metadata identity alias, no link privilege needed.
            return original(a, b)
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(state)}), mock.patch.object(m.os.path, "samefile", side_effect=samefile):
            self.assert_assessment_zero_content_reads(path)

    def test_physical_state_alias_rejected_before_any_body_read(self):
        state, alias = self.base / "opaque-profile", self.base / "alternate-name"
        state.mkdir()
        alias.mkdir()
        path = alias / "ordinary.json"
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        original = m.os.path.realpath
        def realpath(value, *args, **kwargs):
            if m.g.below(value, alias):
                return str(state / m.g.absolute(value).relative_to(alias))
            return original(value, *args, **kwargs)
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(state)}), mock.patch.object(m.os.path, "realpath", side_effect=realpath):
            self.assert_assessment_zero_content_reads(path)

    def test_sensitive_plan_rejected_before_any_body_read(self):
        path = self.base / "auth.json"
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        args = argparse.Namespace(plan=str(path), authorize_plan="0" * 64, receipt=str(self.base / "safe-receipt.json"), confirm_idle=True)
        with mock.patch.object(m.os, "read", side_effect=AssertionError("Private plan body read attempted")) as reader:
            with self.assertRaises(m.g.GuardError):
                self.apply(args)
        self.assertEqual(reader.call_count, 0)
        self.assertTrue(self.payload.exists())

    def test_configured_state_plan_rejected_before_any_body_read(self):
        state = self.base / "opaque-profile"
        state.mkdir()
        path = state / "ordinary.json"
        path.write_text('{"inert-private-fixture":true}', encoding="utf-8")
        args = argparse.Namespace(plan=str(path), authorize_plan="0" * 64, receipt=str(self.base / "safe-receipt.json"), confirm_idle=True)
        with mock.patch.dict(os.environ, {"CODEX_HOME": str(state)}), mock.patch.object(m.os, "read", side_effect=AssertionError("Private plan body read attempted")) as reader:
            with self.assertRaises(m.g.GuardError):
                self.apply(args)
        self.assertEqual(reader.call_count, 0)

    def test_sensitive_outputs_are_rejected_before_writer(self):
        state = self.base / "opaque-profile"
        state.mkdir()
        for path in (self.base / "auth.json", state / "ordinary.json"):
            with self.subTest(path=path), mock.patch.dict(os.environ, {"CODEX_HOME": str(state)}):
                with mock.patch.object(m.n, "write_bounded", side_effect=AssertionError("Private output writer attempted")) as writer:
                    with self.assertRaises(m.g.GuardError):
                        m.write_report(path, {"safe-looking": True})
                self.assertEqual(writer.call_count, 0)
                self.assertFalse(path.exists())

    def test_receipt_private_destination_is_refused_before_plan_body_read(self):
        path = self.base / "ordinary-plan.json"
        path.write_text('{"fixture":true}', encoding="utf-8")
        args = argparse.Namespace(plan=str(path), authorize_plan="0" * 64, receipt=str(self.base / "auth.json"), confirm_idle=True)
        with mock.patch.object(m.os, "read", side_effect=AssertionError("Unneeded plan body read attempted")) as reader:
            with self.assertRaises(m.g.GuardError):
                self.apply(args)
        self.assertEqual(reader.call_count, 0)

    def test_cli_private_output_is_refused_before_assessment_body_read(self):
        argv = [str(SCRIPT), "plan", "--project", str(self.project), "--cache", ".runtime/npm-cache",
                "--assessment", str(self.assessment), "--node", str(self.node), "--npm-cli", str(self.cli),
                "--output", str(self.base / "auth.json")]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(m.os, "read", side_effect=AssertionError("Unneeded assessment body read attempted")) as reader:
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(m.main(), 2)
        self.assertEqual(reader.call_count, 0)
        self.assertFalse((self.base / "auth.json").exists())

    def test_member_budget_refuses_without_mutation(self):
        with mock.patch.object(m, "MAX_MEMBERS", 2):
            self.assert_blocked()

    def test_byte_budget_refuses_without_mutation(self):
        with mock.patch.object(m, "MAX_BYTES", 1):
            self.assert_blocked()

    def test_unknown_root_metadata_blocks_native_deletion(self):
        original = m.metadata_guard.metadata
        def checking(path, directory=False):
            if Path(path) == self.source:
                raise m.g.GuardError("Additional root data stream/resource fork refused")
            return original(path, directory)
        with mock.patch.object(m.metadata_guard, "metadata", side_effect=checking):
            self.assert_blocked()

    def test_unknown_root_identity_is_refused(self):
        original = m.g.root_identity
        def identity(path):
            value = original(path)
            return {**value, "inode": 0} if Path(path) == self.source else value
        with mock.patch.object(m.g, "root_identity", side_effect=identity):
            self.assert_blocked()

    def test_unknown_member_identity_is_refused(self):
        original = m.g.plain
        def plain(path, directory=None):
            value = original(path, directory)
            if Path(path) == self.payload:
                values = {key: getattr(value, key) for key in dir(value) if key.startswith("st_")}
                values["st_ino"] = 0
                return types.SimpleNamespace(**values)
            return value
        with mock.patch.object(m.g, "plain", side_effect=plain):
            self.assert_blocked()

    def test_unknown_directory_metadata_is_not_ignored(self):
        original = m.metadata_guard.metadata
        def checking(path, directory=False):
            if Path(path) == self.source / "content-v2":
                raise m.g.GuardError("Additional directory data stream/resource fork refused")
            return original(path, directory)
        with mock.patch.object(m.metadata_guard, "metadata", side_effect=checking):
            self.assert_blocked()

    def test_metadata_drift_is_detected_by_second_pass(self):
        original = m.metadata_guard.metadata
        count = []
        def checking(path, directory=False):
            result = original(path, directory)
            if Path(path) == self.payload:
                count.append(1)
                if len(count) > 1:
                    result = {**result, "unexpected-metadata-change": True}
            return result
        with mock.patch.object(m.metadata_guard, "metadata", side_effect=checking):
            self.assert_blocked()

    def test_linear_tree_walk_count_is_constant(self):
        for i in range(100):
            data = ("package-%d" % i).encode()
            address = hashlib.sha512(data).hexdigest()
            p = self.source / "content-v2" / "sha512" / address[:2] / address[2:4] / address[4:]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        original = m.os.walk
        calls = []
        def walking(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)
        with mock.patch.object(m.os, "walk", side_effect=walking):
            view = m.snapshot(self.source)
        self.assertEqual(len(calls), 2)
        self.assertEqual(view["tree_passes"], 2)
        self.assertGreater(view["member_count"], 100)


class NativeNpmIntegration(unittest.TestCase):
    def test_installed_native_npm_cleans_only_new_isolated_cache(self):
        if not INTEGRATION_NODE or not INTEGRATION_CLI:
            self.skipTest("Optional real native test requires explicitly selected installed Node/npm")
        temp = tempfile.TemporaryDirectory(prefix="npm-real-native-", dir=ROOT)
        base = Path(temp.name)
        try:
            project = base / "project"
            cache = project / ".runtime" / "npm-cache"
            cache.mkdir(parents=True)
            package = base / "fixture-package.tgz"
            package_bytes = json.dumps({"name": "storage-guard-local-fixture", "version": "1.0.0"}).encode()
            with tarfile.open(package, "w:gz") as archive:
                item = tarfile.TarInfo("package/package.json")
                item.size = len(package_bytes)
                archive.addfile(item, io.BytesIO(package_bytes))
            producer = project / "producer.txt"
            producer.write_text("npm cache add --offline --cache " + str(cache) + " " + str(package), encoding="utf-8")
            user_config, global_config = base / "empty-user.npmrc", base / "empty-global.npmrc"
            user_config.write_bytes(b"")
            global_config.write_bytes(b"")
            argv = [str(INTEGRATION_NODE), str(INTEGRATION_CLI), "--userconfig=" + str(user_config),
                    "--globalconfig=" + str(global_config), "--cache=" + str(cache), "--prefix=" + str(base),
                    "--update-notifier=false", "--ignore-scripts=true", "--offline=true", "--loglevel=verbose",
                    "cache", "add", str(package)]
            result = m.run_native(argv, base, base)
            self.assertEqual(result["returncode"], 0, result)
            logs = sorted((cache / "_logs").glob("*-debug-0.log"))
            self.assertTrue(logs, "Real npm must emit its own historical producer debug log")
            log = logs[-1]
            review = {"schema": m.ASSESSMENT, "project": str(project), "cache": ".runtime/npm-cache",
                      "ownership": "project-exclusive-refetchable",
                      "producer": {"path": "producer.txt", "excerpts": [producer.read_text()],
                                   "explanation": "This retained source records the actual native offline cache-add operation of an inert locally generated test tarball."},
                      "existing_log": log.relative_to(project).as_posix(),
                      "review": {"reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "reviewed_by": "actual-isolated-native-test",
                                 "checked_project_roots": [str(project)], "external_references": "none-found", "writers": "none-found",
                                 "reference_findings": "New randomly named fixture cache was supplied only to the completed native cache-add child; no outside project knows or references it.",
                                 "refetch_findings": "Original inert generated tarball is retained outside cleanup scope and can refill this cache without network access or project hooks.",
                                 "activity_checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                 "activity_findings": "The exact cache-add child returned and its output pipe closed; this single-owner temporary fixture has no other producer or consumer."}}
            assessment = base / "assessment.json"
            dump(assessment, review)
            plan = m.inspect(project, ".runtime/npm-cache", assessment, INTEGRATION_NODE, INTEGRATION_CLI)
            self.assertEqual(plan["status"], "executable", plan["reasons"])
            output = base / "plan.json"
            digest = m.n.write_bounded(output, plan)
            args = argparse.Namespace(plan=str(output), authorize_plan=digest, receipt=str(base / "receipt.json"), confirm_idle=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.apply(args), 0)
            receipt = json.loads(Path(args.receipt).read_text())
            self.assertGreater(receipt["observed_removed_logical_bytes"], 0)
            self.assertEqual(receipt["observed_removed_logical_bytes"], plan["snapshot"]["logical_bytes"])
            self.assertTrue(package.exists())
            self.assertTrue(log.exists())
            self.assertTrue(producer.exists())
            evidence = {"npm": "10.9.2", "node_version": plan["native_tool"]["node_version"],
                        "native_child_pid": receipt["native_result"]["pid"],
                        "released_logical_bytes": receipt["observed_removed_logical_bytes"],
                        "removed_file_count": receipt["observed_removed_file_count"],
                        "source_volume_free_delta": receipt["source_volume_free_delta"],
                        "status": receipt["status"], "real_user_cache_touched": False}
            print("\nNATIVE_INTEGRATION=" + json.dumps(evidence))
        finally:
            if base.resolve() == Path(ROOT).resolve() or not m.g.below(base.resolve(), Path(ROOT).resolve()):
                raise AssertionError("Native fixture escaped selected root; retained")
            temp.cleanup()


def main():
    global ROOT, INTEGRATION_NODE, INTEGRATION_CLI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--integration-node", type=Path)
    parser.add_argument("--integration-npm-cli", type=Path)
    options, remaining = parser.parse_known_args()
    ROOT = options.work_root.expanduser().absolute()
    m.g.ancestors(ROOT, missing=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    m.g.ancestors(ROOT)
    INTEGRATION_NODE, INTEGRATION_CLI = options.integration_node, options.integration_npm_cli
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)


if __name__ == "__main__":
    main()
