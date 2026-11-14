"""Only fictional E:/temporary fixtures; never start PostgreSQL or project code.

Run: python -I -B tests/test_retired_runtime_guard.py --work-root E:/StorageSkillTests
Real Windows/macOS CLI coverage is distinct from mocked activity/race unit tests.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest import mock

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, rest = parser.parse_known_args()
base = Path(opts.work_root).absolute(); base.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="retired-runtime-tests-", dir=base))
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "retired_runtime_guard.py"
spec = importlib.util.spec_from_file_location("retired_runtime_tested", SCRIPT)
T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fake_activity(*_args):
    records = [{"pid": 999999, "ppid": 1, "name": "fictional-unit-test", "command_sha256": "a" * 64}]
    return {"status": "clear", "visible_processes": 1, "records": records, "records_sha256": T.digest(records),
            "method": "mocked only in isolated unit tests", "limitations": T.CONCURRENCY}


class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project"; self.project.mkdir()
        self.codex = self.area / "empty-codex-home"; self.codex.mkdir()
        self.relative = ".runtime/analytics-pg-" + str(uuid.uuid4()) + "/data"
        self.source = self.project.joinpath(*self.relative.split("/")); self.source.mkdir(parents=True)
        for rel in ("base/1", "global", "pg_wal/archive_status"):
            self.source.joinpath(*rel.split("/")).mkdir(parents=True, exist_ok=True)
        for rel, body in {"PG_VERSION": b"18\n", "postgresql.conf": b"# fictional synthetic initdb configuration\nlisten_addresses='localhost'\n",
                          "base/1/1234": b"FICTIONAL DATA NOT A REAL DATABASE\0" * 2048,
                          "global/pg_control": b"fictional control\0" * 64,
                          "pg_wal/000000010000000000000001": b"fictional WAL\0" * 2048}.items():
            self.source.joinpath(*rel.split("/")).write_bytes(body)
        self.producer = self.project / "tests/producer.mjs"; self.producer.parent.mkdir()
        self.claims = {
            "fresh_initdb": "await run('initdb', ['-D', data]);",
            "unique_generated_directory": "const fixtureRoot = path.join(root, '.runtime', 'analytics-pg-' + randomUUID());",
            "loopback_only": "await run('pg_ctl', ['-o', '-h 127.0.0.1']);",
            "stop_in_finally": "finally { await run('pg_ctl', ['-D', data, 'stop']); }",
        }
        self.producer.write_text("\n".join(self.claims.values()) + "\nawait run('node', ['tests/synthetic-fixture.mjs']);\n", encoding="utf-8")
        self.input = self.project / "tests/synthetic-fixture.mjs"
        self.synthetic_quote = "// Synthetic fictional fixtures only; no customer or business input."
        self.input.write_text(self.synthetic_quote + '\nconst rows = [{name:"Fictional fixture",email:"fixture@example.invalid"}];\n', encoding="utf-8")
        self.completion = self.source.parent / "commands.log"
        self.terminal = '{"tests":42,"externalRequests":0,"actualEmailsSent":0}'
        self.completion.write_text("initdb successful\n" + self.terminal + "\nserver stopped\n", encoding="utf-8")
        self.assessment = self.area / "assessment.json"
        self.value = {"schema": T.ASSESSMENT, "source": self.relative, "data_class": "synthetic-rebuildable-only",
            "review": {"reviewer": "Codex fixture reviewer", "synthetic_data_reason": "Producer and retained fixture only create fictional local rows.",
                       "rebuild_recipe": "Re-run the retained synthetic producer with the same local PostgreSQL tool version; never executed by cleanup.",
                       "unique_value_review": "Only independently generated data is selected; sibling logs and test source remain retained.",
                       "reference_scope_reason": "Reviewed source/config flow; generated runtime siblings are not active project inputs."},
            "producer": {"path": "tests/producer.mjs", "sha256": sha(self.producer), "claims": self.claims},
            "inputs": [{"path": "tests/synthetic-fixture.mjs", "sha256": sha(self.input), "kind": "synthetic-generator",
                        "synthetic_quote": self.synthetic_quote, "reason": "Fictional fixtures are declared and used by the retained producer.",
                        "referenced_by": "tests/producer.mjs"}],
            "completion": {"path": self.completion.relative_to(self.project).as_posix(), "sha256": sha(self.completion),
                           "stop_quote": "server stopped", "terminal_quote": self.terminal}}
        self.save_assessment()
        self.plan = self.area / "plan.json"; self.receipt = self.area / "receipt.json"
        self.age_tree()

    def age_tree(self):
        old = time.time() - 96 * 3600
        for p in sorted(self.source.rglob("*"), reverse=True):
            if not p.is_symlink():
                os.utime(p, (old, old))
        os.utime(self.source, (old, old))

    def save_assessment(self):
        self.assessment.write_text(json.dumps(self.value), encoding="utf-8")

    def plan_args(self):
        return argparse.Namespace(project=str(self.project), source=self.relative, assessment=str(self.assessment),
            output=str(self.plan), codex_home=str(self.codex), confirm_idle=True, max_files=100000,
            max_bytes=64 * 1024**2, min_age_hours=48.0, idle_seconds=1.0)

    def make_plan(self):
        with mock.patch.object(T, "capture_activity", side_effect=fake_activity), mock.patch.object(T.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            return T.plan_command(self.plan_args())

    def apply(self, fail=False, digest=None):
        args = argparse.Namespace(plan=str(self.plan), authorize_plan=digest or sha(self.plan), receipt=str(self.receipt), confirm_idle=True)
        with mock.patch.object(T, "capture_activity", side_effect=fake_activity), mock.patch.object(T.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            if fail:
                with self.assertRaises(T.g.GuardError):
                    T.apply_command(args)
                return json.loads(self.receipt.read_text()) if self.receipt.exists() else None
            return T.apply_command(args)

    def test_exact_synthetic_data_deleted_without_backup_and_unique_evidence_kept(self):
        kept = {p: sha(p) for p in (self.input, self.producer, self.completion, self.assessment)}
        plan = self.make_plan(); receipt = self.apply()
        self.assertEqual(receipt["status"], "completed")
        self.assertEqual(receipt["deleted_files"], plan["planned_files"])
        self.assertEqual(receipt["deleted_logical_bytes"], plan["logical_bytes"])
        self.assertFalse(self.source.exists())
        self.assertEqual(kept, {p: sha(p) for p in kept})
        self.assertFalse(receipt["database_connected"])
        self.assertFalse(receipt["project_code_executed"])

    def test_business_runtime_pgdata_always_refused(self):
        self.plan_args().source = ".runtime/pgdata"
        with self.assertRaisesRegex(T.g.GuardError, "business .runtime/pgdata"):
            T.source_path(self.project, ".runtime/pgdata")

    def test_false_boolean_assessment_cannot_enable_delete(self):
        self.value = {"source": self.relative, "is_test": True, "rebuildable": True, "writers_idle": True}
        self.save_assessment()
        with self.assertRaises(T.g.GuardError): self.make_plan()
        self.assertFalse(self.plan.exists()); self.assertTrue(self.source.exists())

    def test_quoted_claim_must_exist_in_real_producer(self):
        self.value["producer"]["claims"]["fresh_initdb"] = "initdb was run, trust this new declaration"
        self.save_assessment()
        with self.assertRaisesRegex(T.g.GuardError, "real quoted"): self.make_plan()

    def test_unrelated_synthetic_fixture_not_connected_to_producer_refused(self):
        self.value["inputs"][0]["referenced_by"] = "not-a-real-input-link"
        self.save_assessment()
        with self.assertRaisesRegex(T.g.GuardError, "actual retained producer"): self.make_plan()

    def test_completion_from_different_run_refused(self):
        another = self.project / "other-completion.log"; another.write_text(self.completion.read_text(), encoding="utf-8")
        self.value["completion"]["path"] = another.name; self.value["completion"]["sha256"] = sha(another)
        self.save_assessment()
        with self.assertRaisesRegex(T.g.GuardError, "exact historical run"): self.make_plan()

    def test_missing_completion_gives_specific_refusal(self):
        self.completion.unlink()
        with self.assertRaises((T.g.GuardError, OSError)): self.make_plan()

    def test_unknown_unique_note_retained_with_whole_unit(self):
        note = self.source / "important-note.md"; note.write_text("unique research not in producer", encoding="utf-8"); self.age_tree()
        with self.assertRaisesRegex(T.g.GuardError, "Unknown/credential/recovery/mixed"): self.make_plan()
        self.assertTrue(note.exists())

    def test_recovery_marker_or_live_pid_refused(self):
        marker = self.source / "recovery.signal"; marker.write_text("", encoding="utf-8"); self.age_tree()
        with self.assertRaises(T.g.GuardError): self.make_plan()

    def test_credential_configuration_refused(self):
        cfg = self.source / "postgresql.auto.conf"; cfg.write_text("primary_conninfo = 'password=retained'\n", encoding="utf-8"); self.age_tree()
        with self.assertRaisesRegex(T.g.GuardError, "Credential/recovery"): self.make_plan()

    def test_recent_data_cannot_retire(self):
        os.utime(self.source / "PG_VERSION", None)
        with self.assertRaisesRegex(T.g.GuardError, "too recent"): self.make_plan()

    def test_added_member_after_plan_refuses_before_any_delete(self):
        self.make_plan(); addition = self.source / "base/1/8888"; addition.write_bytes(b"unexpected fresh contents"); self.age_tree()
        result = self.apply(fail=True)
        self.assertEqual(result["deleted_files"], 0); self.assertTrue(addition.exists())

    def test_replacement_after_plan_refuses_even_same_content(self):
        self.make_plan(); p = self.source / "base/1/1234"; raw = p.read_bytes()
        p.rename(p.with_name("old-identity")); p.write_bytes(raw)
        p.with_name("old-identity").unlink(); self.age_tree()
        result = self.apply(fail=True)
        self.assertEqual(result["deleted_files"], 0); self.assertTrue(p.exists())

    def test_changed_producer_input_completion_or_assessment_refuses(self):
        for name in ("producer", "input", "completion", "assessment"):
            with self.subTest(name=name):
                self.setUp()  # Each scenario has a new source; never clear a production apply claim.
                self.make_plan(); p = getattr(self, name); raw = p.read_bytes()
                p.write_bytes(raw + b"\nmodified evidence\n")
                result = self.apply(fail=True)
                self.assertEqual(result["deleted_files"], 0); self.assertTrue(self.source.exists())
                p.write_bytes(raw)
                # Updating mtime alone is itself an evidence change; construct a fresh plan.

    def test_reference_added_after_plan_refuses(self):
        self.make_plan(); p = self.project / "server-config.json"
        p.write_text(json.dumps({"active_data": str(self.source)}), encoding="utf-8")
        result = self.apply(fail=True)
        self.assertEqual(result["deleted_files"], 0); self.assertTrue(self.source.exists())

    def test_live_reference_prevents_plan(self):
        (self.project / "server-config.mjs").write_text("export const activeData = " + json.dumps(self.relative), encoding="utf-8")
        with self.assertRaisesRegex(T.g.GuardError, "Unresolved exact runtime reference"): self.make_plan()

    def test_declared_safe_config_reference_is_not_automatically_whitelisted(self):
        config = self.project / "runtime.json"
        config.write_text(json.dumps({"active_data": self.relative}), encoding="utf-8")
        self.value["reference_files"] = [{"path": "runtime.json", "sha256": sha(config),
            "reason": "Reviewed only generated paths; no credential or customer fields."}]
        self.save_assessment()
        with self.assertRaisesRegex(T.g.GuardError, "Unresolved exact runtime reference"): self.make_plan()

    def test_credentials_and_customer_documents_never_read(self):
        private = [self.project / ".env", self.project / "customer-notes.txt", self.project / "customers.json",
                   self.project / "unclassified-document.json"]
        for path in private:
            path.write_text("FAKE SECRET AND CUSTOMER BODY; must remain unread", encoding="utf-8")
        seen = []
        original = T.bounded_text

        def watched(path, *args, **kwargs):
            seen.append(Path(path)); return original(path, *args, **kwargs)

        with mock.patch.object(T, "bounded_text", side_effect=watched):
            plan = self.make_plan()
        self.assertTrue(all(path not in seen for path in private))
        self.assertIn("unclassified-document.json", plan["reference_evidence"]["metadata_only"])
        self.assertIn(".env", plan["reference_evidence"]["skipped_scopes"])

    def test_sensitive_assessment_or_plan_refused_before_any_body_read(self):
        sensitive = self.codex / "auth.json"; sensitive.write_text('{"secret":"fictional-only"}', encoding="utf-8")
        args = self.plan_args(); args.assessment = str(sensitive)
        with mock.patch.object(T.g.os, "read", wraps=os.read) as reader:
            with self.assertRaises(T.g.GuardError): T.plan_command(args)
            self.assertEqual(reader.call_count, 0)
        apply_args = argparse.Namespace(plan=str(sensitive), authorize_plan="0" * 64,
                                       receipt=str(self.receipt), confirm_idle=True, codex_home=str(self.codex))
        with mock.patch.object(T.g.os, "read", wraps=os.read) as reader:
            with self.assertRaises(T.g.GuardError): T.apply_command(apply_args)
            self.assertEqual(reader.call_count, 0)

    def test_short_reads_still_hash_complete_evidence_and_detect_truncation(self):
        original = os.read

        def short(fd, count):
            return original(fd, min(count, 7))

        with mock.patch.object(T.os, "read", side_effect=short):
            body, rec = T.bounded_text(self.input, T.Budget(1024 * 1024))
        self.assertEqual(body, self.input.read_bytes().decode("utf-8"))
        self.assertEqual(rec["sha256"], sha(self.input))
        reads = [0]

        def premature_eof(fd, count):
            reads[0] += 1
            return original(fd, min(count, 7)) if reads[0] == 1 else b""

        with mock.patch.object(T.os, "read", side_effect=premature_eof):
            with self.assertRaises(T.g.GuardError): T.bounded_text(self.input, T.Budget(1024 * 1024))

    def test_plain_named_configured_state_and_alias_refused_before_read(self):
        state_plan = self.codex / "plan.json"; state_plan.write_text('{"fictional":"state"}', encoding="utf-8")
        alias = self.area / "state-alias-metadata-only"; alias.mkdir()
        realpath = os.path.realpath

        def mapped(path, *args, **kwargs):
            return str(self.codex) if T.g.key(path) == T.g.key(alias) else realpath(path, *args, **kwargs)

        with mock.patch.dict(os.environ, {"CODEX_HOME": str(alias)}), mock.patch.object(T.os.path, "realpath", side_effect=mapped):
            with mock.patch.object(T.g.os, "read", wraps=os.read) as reader:
                with self.assertRaises(T.g.GuardError): T.administrative_path(state_plan)
                self.assertEqual(reader.call_count, 0)

    def test_admin_output_and_receipt_cannot_enter_state(self):
        args = self.plan_args(); args.output = str(self.codex / "new-plan.json")
        with self.assertRaises(T.g.GuardError): T.plan_command(args)
        self.assertFalse((self.codex / "new-plan.json").exists())
        self.make_plan()
        args = argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan),
            receipt=str(self.codex / "new-receipt.json"), confirm_idle=True, codex_home=str(self.codex))
        with self.assertRaises(T.g.GuardError): T.apply_command(args)
        self.assertFalse((self.codex / "new-receipt.json").exists())
        self.assertFalse((self.project / T.CLAIMS_DIR).exists())

    def test_apply_claim_prevents_same_source_retry_with_another_receipt(self):
        self.make_plan()
        (self.source / "base/1/9876").write_bytes(b"new synthetic file"); self.age_tree()
        self.apply(fail=True)
        args = argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.area / "another-receipt.json"), confirm_idle=True)
        with self.assertRaisesRegex(T.g.GuardError, "apply claim already exists"):
            T.apply_command(args)
        self.assertFalse((self.area / "another-receipt.json").exists())

    def test_batch_pending_is_durable_and_lost_completion_remains_uncertain(self):
        plan = self.make_plan(); original = T.file_hash
        deleted = []
        event_path = Path(str(self.receipt) + ".in-progress") / "events.jsonl"

        def lost_completion(path, expected, budget, delete=False):
            if delete:
                events = [json.loads(line)["event"] for line in event_path.read_text().splitlines()]
                pending = [event for event in events if event["status"] == "batch_delete_pending"][-1]
                self.assertEqual({item["relative"] for item in pending["members"]}, set(plan["snapshot"]["files"]))
                result = original(path, expected, budget, delete=True)
                deleted.append(Path(path).relative_to(self.source).as_posix())
                if len(deleted) == 2:
                    raise OSError("fictional lost completion after actual guarded unlink")
                return result
            return original(path, expected, budget)

        with mock.patch.object(T, "file_hash", side_effect=lost_completion):
            result = self.apply(fail=True)
        self.assertEqual(result["status"], "partial_or_uncertain")
        self.assertEqual(result["deleted_files"], 1)
        self.assertEqual(result["current_file"], deleted[1])
        self.assertIn(deleted[1], result["pending_batch"])
        self.assertFalse(self.source.joinpath(*deleted[1].split("/")).exists())
        self.assertTrue(self.completion.exists())
        events = [json.loads(line)["event"] for line in event_path.read_text().splitlines()]
        self.assertEqual([e["relative"] for e in events if e["status"] == "deleted"], deleted[:1])

    def test_empty_directory_removal_failure_stops_and_reports_partial(self):
        self.make_plan(); original = os.rmdir

        def failing(path, *args, **kwargs):
            if T.g.key(path) == T.g.key(self.source / "base/1"):
                raise OSError("fictional directory-removal failure")
            return original(path, *args, **kwargs)

        with mock.patch.object(T.os, "rmdir", side_effect=failing):
            result = self.apply(fail=True)
        self.assertEqual(result["status"], "partial_or_uncertain")
        self.assertEqual(result["deleted_files"], 5)
        self.assertIn("directory-removal failure", result["error"])
        self.assertTrue(self.source.exists()); self.assertTrue(self.completion.exists())

    def test_unknown_activity_and_idle_boolean_refused(self):
        with mock.patch.object(T, "capture_activity", return_value={"status": "unknown"}):
            with self.assertRaisesRegex(T.g.GuardError, "Activity coverage unknown"):
                T.require_activity(self.project, self.source)
        with mock.patch.object(T, "capture_activity", return_value=True):
            with self.assertRaises(T.g.GuardError): T.require_activity(self.project, self.source)

    def test_live_pid_marker_refused(self):
        (self.source / "postmaster.pid").write_text("12345 fictional live marker", encoding="utf-8"); self.age_tree()
        with self.assertRaises(T.g.GuardError): self.make_plan()

    def test_live_project_process_and_inaccessible_runtime_refused(self):
        if os.name != "nt": self.skipTest("Windows CIM parser test")
        for name, args in (("node.exe", "node " + str(self.project / "server.mjs")), ("python.exe", None)):
            values = [{"ProcessId": os.getpid(), "ParentProcessId": 0, "Name": "python.exe", "CommandLine": "this test"},
                      {"ProcessId": 999998, "ParentProcessId": 1, "Name": name, "CommandLine": args}]
            result = subprocess.CompletedProcess([], 0, json.dumps(values), "")
            with self.subTest(name=name), mock.patch.object(T, "_run", return_value=result), mock.patch.object(T, "confirmed_exited_windows", return_value=False):
                with self.assertRaises(T.g.GuardError): T.capture_activity(self.project, self.source)

    def test_cim_stale_row_ignored_only_after_os_confirmed_exit(self):
        if os.name != "nt": self.skipTest("Windows process lifetime verification")
        self.assertFalse(T.confirmed_exited_windows(os.getpid()))
        values = [{"ProcessId": os.getpid(), "ParentProcessId": 0, "Name": "python.exe", "CommandLine": "this test"},
                  {"ProcessId": 999997, "ParentProcessId": 1, "Name": "python.exe", "CommandLine": None}]
        result = subprocess.CompletedProcess([], 0, json.dumps(values), "")
        with mock.patch.object(T, "_run", return_value=result), mock.patch.object(T, "confirmed_exited_windows", return_value=True):
            facts = T.capture_activity(self.project, self.source)
        self.assertEqual(facts["records"][0]["status"], "confirmed_exited_during_CIM_inventory")

    def test_retained_evidence_held_through_actual_deletion(self):
        self.make_plan(); original = T.file_hash; attempted = []
        kept = (self.producer, self.input, self.completion, self.assessment)
        original_sha = {p: sha(p) for p in kept}

        def attempt_rewrite(path, expected, budget, delete=False):
            if delete and not attempted:
                for retained in kept:
                    try:
                        retained.write_bytes(b"fictional evidence rewrite while releasing")
                    except OSError:
                        attempted.append((retained, "blocked"))
                    else:
                        attempted.append((retained, "changed"))
            return original(path, expected, budget, delete=delete)

        with mock.patch.object(T, "file_hash", side_effect=attempt_rewrite):
            if os.name == "nt":
                result = self.apply()
                self.assertEqual(result["status"], "completed")
                self.assertEqual([status for _, status in attempted], ["blocked"] * 4)
                self.assertEqual(original_sha, {p: sha(p) for p in kept})
            else:
                result = self.apply(fail=True)
                self.assertEqual(result["status"], "partial_or_uncertain")

    def test_clean_child_env_and_fixed_cwd_do_not_inherit_startup_variables(self):
        hostile = {"PSModulePath": str(self.area), "PSModuleAnalysisCachePath": str(self.area / "cache"),
                   "PSExecutionPolicyPreference": "Bypass", "DYLD_INSERT_LIBRARIES": "fake-library",
                   "LD_PRELOAD": "fake-library", "PYTHONPATH": str(self.project), "SystemRoot": str(self.area)}
        with mock.patch.dict(os.environ, hostile):
            environment, cwd = T.child_context()
        for key in hostile:
            if key in {"SystemRoot", "PSModulePath"} and os.name == "nt":
                self.assertNotEqual(environment[key], hostile[key])
            else:
                self.assertNotIn(key, environment)
        self.assertFalse(str(cwd).startswith(str(self.project)))

    def test_actual_psmodulepath_injection_is_not_loaded(self):
        if os.name != "nt": self.skipTest("Actual Windows PowerShell injection regression")
        modules = self.area / "hostile-modules"; module = modules / "CimCmdlets"; module.mkdir(parents=True)
        canary = self.area / "CANARY-MUST-NOT-EXIST.txt"
        escaped = str(canary).replace("'", "''")
        (module / "CimCmdlets.psm1").write_text(
            f"[System.IO.File]::WriteAllText('{escaped}','untrusted module executed');\n"
            "function Get-CimInstance { return @() }; Export-ModuleMember -Function Get-CimInstance\n", encoding="utf-8")
        (module / "CimCmdlets.psd1").write_text("@{RootModule='CimCmdlets.psm1';ModuleVersion='1.0.0';FunctionsToExport=@('Get-CimInstance')}\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PSModulePath": str(modules), "PSModuleAnalysisCachePath": str(canary),
                                         "PSExecutionPolicyPreference": "Bypass", "SystemRoot": str(self.area)}):
            facts = T.capture_activity(self.project, self.source)
        self.assertEqual(facts["status"], "clear"); self.assertFalse(canary.exists())

    def test_idle_confirmation_required_on_all_platforms(self):
        args = self.plan_args(); args.confirm_idle = False
        with self.assertRaisesRegex(T.g.GuardError, "confirm-idle"): T.plan_command(args)
        self.make_plan()
        args = argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=False)
        with self.assertRaises(T.g.GuardError): T.apply_command(args)

    def test_plan_authorization_must_match(self):
        self.make_plan(); self.apply(fail=True, digest="0" * 64)
        self.assertTrue(self.source.exists())

    def test_hardlink_member_refused_where_supported(self):
        src = self.source / "base/1/1234"; kept = self.area / "kept-linked-copy"
        try:
            os.link(src, kept)
        except OSError as exc:
            self.skipTest("Fixture filesystem does not support hardlinks: " + str(exc))
        with self.assertRaisesRegex(T.g.GuardError, "Hardlink"): self.make_plan()
        self.assertTrue(kept.exists())

    def test_symlink_member_refused_where_supported(self):
        try:
            os.symlink(self.input, self.source / "base/1/4321")
        except OSError as exc:
            self.skipTest("Fixture filesystem does not permit symlinks: " + str(exc))
        with self.assertRaises(T.g.GuardError): self.make_plan()
        self.assertTrue(self.input.exists())

    def test_post_plan_link_replacement_refused_where_supported(self):
        self.make_plan(); p = self.source / "base/1/1234"; p.unlink()
        try:
            os.symlink(self.input, p)
        except OSError as exc:
            self.skipTest("Fixture filesystem does not permit symlinks: " + str(exc))
        self.apply(fail=True); self.assertTrue(self.input.exists())

    def test_read_budget_fails_before_release(self):
        args = self.plan_args(); args.max_bytes = 10
        with self.assertRaises(T.g.GuardError):
            with mock.patch.object(T, "capture_activity", side_effect=fake_activity): T.plan_command(args)
        self.assertTrue(self.source.exists())

    def test_large_file_count_full_scans_constant_not_per_deleted_file(self):
        for i in range(1000):
            (self.source / "base/1" / str(10000 + i)).write_bytes(b"synthetic\0" * 16)
        self.age_tree()
        original = os.scandir; counts = {}

        def counted(path):
            k = str(path); counts[k] = counts.get(k, 0) + 1
            return original(path)

        with mock.patch.object(T.os, "scandir", side_effect=counted):
            plan = self.make_plan(); result = self.apply()
        self.assertEqual(result["deleted_files"], 1005)
        self.assertEqual(result["deleted_logical_bytes"], plan["logical_bytes"])
        self.assertLessEqual(counts.get(str(self.source), 0), 4)
        self.assertLessEqual(counts.get(str(self.source / "base/1"), 0), 4)

    def test_real_isolated_cli_and_measured_reclaim(self):
        if os.name != "nt" and sys.platform != "darwin":
            self.skipTest("Actual OS activity provider exists only on Windows/macOS")
        # Size deliberately exceeds routine fixture bookkeeping. Contents are fake.
        big = self.source / "base/1/7777"; big.write_bytes(b"synthetic temporary payload\0" * (1024 * 1024))
        self.age_tree()
        env = dict(os.environ, CODEX_HOME=str(self.codex), PYTHONIOENCODING="utf-8")

        def cli(*args):
            proc = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), *map(str, args)], capture_output=True,
                                  text=True, encoding="utf-8", env=env, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return proc

        cli("plan", "--project", self.project, "--source", self.relative, "--assessment", self.assessment,
            "--output", self.plan, "--codex-home", self.codex, "--confirm-idle", "--idle-seconds", 1)
        plan = json.loads(self.plan.read_text())
        cli("apply", "--plan", self.plan, "--authorize-plan", sha(self.plan), "--receipt", self.receipt, "--confirm-idle")
        result = json.loads(self.receipt.read_text())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["deleted_logical_bytes"], plan["logical_bytes"])
        self.assertIsInstance(result["source_free_delta_bytes"], int)
        self.assertFalse(self.source.exists()); self.assertTrue(self.completion.exists())
        (RUN / "actual-cli-reclaim.json").write_text(json.dumps({"fixture": str(self.area), "plan": str(self.plan),
            "receipt": str(self.receipt), "logical_deleted_bytes": result["deleted_logical_bytes"],
            "volume_free_delta_bytes": result["source_free_delta_bytes"], "platform": sys.platform}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    print("Isolated fictional fixtures retained at:", RUN)
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
