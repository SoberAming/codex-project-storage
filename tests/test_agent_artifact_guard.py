"""Fictional Agent-task artifacts only; no real projects or session body reads."""
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
import unittest
import uuid
from unittest import mock

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, rest = parser.parse_known_args()
base = Path(opts.work_root).absolute(); base.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="agent-artifact-tests-", dir=base))
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/agent_artifact_guard.py"
spec = importlib.util.spec_from_file_location("agent_artifact_tested", SCRIPT)
T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fake_activity(source):
    records = [{"pid": 999999, "name": "fictional unit-test only"}]
    return {"status": "clear", "records": records, "visible_processes": 1, "records_sha256": T.t.digest(records)}


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project"; self.project.mkdir()
        self.codex = self.area / "empty-code-home"; self.codex.mkdir()
        self.run_id = "capture-" + str(uuid.uuid4())
        self.relative = "task-runs/" + self.run_id + "/captures"
        self.source = self.project.joinpath(*self.relative.split("/")); self.source.mkdir(parents=True)
        self.payload = self.source / "page-preview.png"; self.payload.write_bytes(b"fictional screenshot payload" * 4096)
        (self.source / "recording.webm").write_bytes(b"fictional browser recording" * 4096)
        self.producer = self.project / "tools/capture.mjs"; self.producer.parent.mkdir()
        self.quote = "await page.screenshot({path: capturePath});"
        self.path_quote = "const capturePath = path.join(root, 'task-runs', runId, 'captures', 'page-preview.png');"
        self.producer.write_text("// fictional retained producer, never run\n" + self.path_quote + "\n" + self.quote + "\n", encoding="utf-8")
        self.completion = self.source.parent / "run.log"
        self.binding = "run=" + self.run_id + " source=" + self.relative
        self.producer_binding = "producer=tools/capture.mjs"
        self.terminal = "task completed successfully"
        self.stopped = "browser closed; all task writers exited"
        self.completion.write_text("\n".join((self.binding, self.producer_binding, self.terminal, self.stopped)), encoding="utf-8")
        self.result = self.project / "results/report.md"; self.result.parent.mkdir()
        self.result.write_text("Fictional retained useful summary. Screenshots were disposable debugging aids.", encoding="utf-8")
        self.sentinels = [self.result, self.producer, self.completion]
        for rel in ("src/app.py", ".codex/sessions/current.jsonl", ".codex/session_index.jsonl",
                    ".claude/projects/active.jsonl", ".kimi-code/sessions/current.jsonl", ".workbuddy/state/index.json",
                    ".env", "business.sqlite", "recovery/restore.zip", "deliverables/final.mp4"):
            p = self.project.joinpath(*rel.split("/")); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"Fictional protected sentinel must remain byte-identical\0"); self.sentinels.append(p)
        self.assessment = self.area / "assessment.json"
        self.value = {"schema": T.ASSESSMENT, "source": self.relative, "run_id": self.run_id,
            "family": "browser-captures", "agent": "fictional cross-Agent test",
            "review": {"reviewer": "Isolated fixture reviewer", "origin_reason": "Retained producer and exact terminal record bind this capture task.",
                "discardability_reason": "Only expendable diagnostic captures are present; useful report remains.",
                "no_unique_value_reason": "No unique model-generated result or acceptance baseline is present.",
                "reference_scope_reason": "Reviewed known task output flow and current non-sensitive references.",
                "retained_results_reason": "The independent report is the useful result and is retained."},
            "producer": {"path": self.producer.relative_to(self.project).as_posix(), "sha256": sha(self.producer),
                "output_quote": self.quote, "output_path_quote": self.path_quote, "path_symbol": "capturePath"},
            "completion": {"path": self.completion.relative_to(self.project).as_posix(), "sha256": sha(self.completion),
                "source_quote": self.binding, "producer_quote": self.producer_binding, "terminal_quote": self.terminal, "writer_stop_quote": self.stopped},
            "retained_results": [{"path": self.result.relative_to(self.project).as_posix(), "sha256": sha(self.result)}]}
        self.save(); self.plan = self.area / "plan.json"; self.receipt = self.area / "receipt.json"

    def save(self): self.assessment.write_text(json.dumps(self.value), encoding="utf-8")

    def finish_fixture(self):
        self.completion.write_text("\n".join((self.binding, self.producer_binding, self.terminal, self.stopped)), encoding="utf-8")
        self.value["completion"]["sha256"] = sha(self.completion); self.save()

    def args(self):
        return argparse.Namespace(project=str(self.project), source=self.relative, assessment=str(self.assessment), output=str(self.plan),
            codex_home=str(self.codex), confirm_idle=True, max_files=10000, max_bytes=128 * 1024**2, idle_seconds=1)

    def make_plan(self):
        with mock.patch.object(T, "capture_activity", side_effect=fake_activity), mock.patch.object(T.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            return T.plan_command(self.args())

    def apply(self, fail=False, **changes):
        values = dict(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=True)
        values.update(changes)
        with mock.patch.object(T, "capture_activity", side_effect=fake_activity), mock.patch.object(T.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            if fail:
                with self.assertRaises((T.g.GuardError, OSError, ValueError, KeyError, TypeError)):
                    T.apply_command(argparse.Namespace(**values))
                return json.loads(self.receipt.read_text()) if self.receipt.exists() else None
            return T.apply_command(argparse.Namespace(**values))

    def test_recent_completed_task_deletes_exact_payload_and_preserves_project_and_state(self):
        original = {str(p): sha(p) for p in self.sentinels + [self.assessment]}
        plan = self.make_plan(); result = self.apply()
        self.assertEqual(plan["minimum_age_hours"], 0)
        self.assertEqual(result["status"], "completed"); self.assertEqual(result["deleted_files"], 2)
        self.assertEqual(result["deleted_logical_bytes"], plan["logical_bytes"])
        self.assertFalse(self.source.exists())
        self.assertEqual(original, {p: sha(p) for p in original})
        self.assertFalse(result["project_code_executed"]); self.assertFalse(result["database_connected"])

    def test_download_fragments_supported_with_their_own_provenance(self):
        for p in self.source.iterdir(): p.unlink()
        (self.source / "payload.part").write_bytes(b"fictional failed download chunk")
        self.value["family"] = "download-fragments"
        self.path_quote = "const capturePath = path.join(root, 'task-runs', runId, 'captures', 'payload.part');"
        self.quote = "download.write(capturePath, chunk)"
        self.producer.write_text(self.path_quote + "\n" + self.quote, encoding="utf-8")
        self.value["producer"].update(sha256=sha(self.producer), output_quote=self.quote, output_path_quote=self.path_quote)
        self.finish_fixture(); self.make_plan(); result = self.apply()
        self.assertEqual(result["deleted_files"], 1)

    def test_tool_scratch_logs_supported_only_with_retained_useful_result(self):
        for p in self.source.iterdir(): p.unlink()
        (self.source / "debug.log").write_bytes(b"fictional disposable verbose debug")
        self.path_quote = "const capturePath = path.join(root, 'task-runs', runId, 'captures', 'debug.log');"
        self.value["family"] = "tool-scratch"; self.quote = "write(capturePath, debug_output)"
        self.producer.write_text(self.path_quote + "\n" + self.quote, encoding="utf-8")
        self.value["producer"].update(sha256=sha(self.producer), output_quote=self.quote, output_path_quote=self.path_quote)
        self.finish_fixture(); self.make_plan(); self.assertEqual(self.apply()["deleted_files"], 1)

    def test_no_terminal_evidence_refuses_even_with_idle_boolean(self):
        self.value["completion"] = {"idle": True, "completed": True}; self.save()
        with self.assertRaises(T.g.GuardError): self.make_plan()

    def test_running_status_cannot_authorize(self):
        self.completion.write_text("\n".join((self.binding, self.producer_binding, "task running", self.stopped)), encoding="utf-8")
        self.value["completion"].update(sha256=sha(self.completion), terminal_quote="task running"); self.save()
        with self.assertRaisesRegex(T.g.GuardError, "terminal status"): self.make_plan()

    def test_writer_shutdown_required_independently(self):
        self.completion.write_text("\n".join((self.binding, self.producer_binding, self.terminal, "writer still active")), encoding="utf-8")
        self.value["completion"].update(sha256=sha(self.completion), writer_stop_quote="writer still active"); self.save()
        with self.assertRaisesRegex(T.g.GuardError, "writer shutdown"): self.make_plan()

    def test_negative_terminal_or_writer_phrasing_cannot_enable_delete(self):
        for field, phrase in (("terminal_quote", "task not completed"), ("writer_stop_quote", "browser not closed")):
            self.setUp(); self.completion.write_text(self.completion.read_text() + "\n" + phrase, encoding="utf-8")
            self.value["completion"].update(sha256=sha(self.completion), **{field: phrase}); self.save()
            with self.subTest(field=field), self.assertRaisesRegex(T.g.GuardError, "negative"): self.make_plan()

    def test_terminal_record_must_link_real_retained_producer(self):
        self.value["completion"]["producer_quote"] = "producer=tools/unrelated.mjs"; self.save()
        with self.assertRaises(T.g.GuardError): self.make_plan()

    def test_similar_source_and_producer_suffixes_are_not_exact_binding(self):
        for field, wrong in (("source_quote", self.binding + "-old"), ("producer_quote", self.producer_binding + ".disabled")):
            self.setUp()
            if field == "source_quote": wrong = self.binding + "-old"
            self.completion.write_text(self.completion.read_text() + "\n" + wrong, encoding="utf-8")
            self.value["completion"].update(sha256=sha(self.completion), **{field: wrong}); self.save()
            with self.subTest(field=field), self.assertRaises(T.g.GuardError): self.make_plan()

    def test_similar_output_root_or_unit_component_cannot_enable_delete(self):
        for before, after in (("captures", "captures-old"), ("task-runs", "task-runs-other")):
            self.setUp(); wrong = self.path_quote.replace(before, after)
            self.producer.write_text(wrong + "\n" + self.quote, encoding="utf-8")
            self.value["producer"].update(sha256=sha(self.producer), output_path_quote=wrong); self.save()
            with self.subTest(component=before), self.assertRaisesRegex(T.g.GuardError, "path quote"): self.make_plan()

    def test_exact_absolute_path_tokens_accepted_but_extra_filename_suffix_refused(self):
        self.assertTrue(T.path_token('source="' + str(self.source) + '"', self.relative, self.project))
        self.assertFalse(T.path_token('source="' + str(self.source) + '-old"', self.relative, self.project))
        self.assertTrue(T.path_token("producer=" + self.producer_binding.split("=", 1)[1], "tools/capture.mjs", self.project))
        self.assertFalse(T.path_token("producer=tools/capture.mjs.disabled", "tools/capture.mjs", self.project))

    def test_payload_written_after_terminal_record_is_retained(self):
        terminal_ns = self.completion.stat().st_mtime_ns
        os.utime(self.payload, ns=(terminal_ns + 10**9, terminal_ns + 10**9))
        with self.assertRaisesRegex(T.g.GuardError, "after the terminal"): self.make_plan()

    def test_other_run_completion_refused(self):
        self.value["completion"]["source_quote"] = "run=unrelated source=elsewhere/captures"; self.save()
        with self.assertRaises(T.g.GuardError): self.make_plan()

    def test_producer_quote_must_exist_and_describe_family(self):
        self.value["producer"]["output_quote"] = "trust this disposable folder"; self.save()
        with self.assertRaises(T.g.GuardError): self.make_plan()

    def test_write_keyword_without_actual_output_path_relationship_is_insufficient(self):
        self.value["producer"]["output_path_quote"] = self.quote; self.save()
        with self.assertRaisesRegex(T.g.GuardError, "path quote"): self.make_plan()
        self.value["producer"]["output_path_quote"] = self.path_quote
        self.value["producer"]["path_symbol"] = "unrelatedPath"; self.save()
        with self.assertRaisesRegex(T.g.GuardError, "same reviewed path symbol"): self.make_plan()

    def test_oversized_assessment_refused_before_json_reader(self):
        self.assessment.write_bytes(b" " * (1024 * 1024 + 1))
        with mock.patch.object(T.g, "read_json", side_effect=AssertionError("body must not be read")):
            with self.assertRaisesRegex(T.g.GuardError, "1 MiB"): self.make_plan()

    def test_missing_or_overlapping_result_refused(self):
        self.value["retained_results"] = []; self.save()
        with self.assertRaisesRegex(T.g.GuardError, "retained result"): self.make_plan()
        self.value["retained_results"] = [self.value["producer"]]; self.save()
        with self.assertRaisesRegex(T.g.GuardError, "independent"): self.make_plan()

    def test_project_output_and_runtime_roots_refused(self):
        for rel in (".", ".runtime", "outputs", "task-runs/" + self.run_id, "src/" + self.run_id + "/scratch",
                    ".claude/" + self.run_id + "/scratch", ".kimi-code/" + self.run_id + "/scratch"):
            with self.subTest(rel=rel), self.assertRaises(T.g.GuardError): T.source_path(self.project, rel)

    def test_mixed_source_db_state_and_final_members_retain_whole_unit(self):
        for name in ("important.py", "records.sqlite", "session_index.jsonl", "final.png", "backup.zip", "unknown.bin"):
            p = self.source / name; p.write_bytes(b"fictional important member")
            with self.subTest(name=name), self.assertRaises(T.g.GuardError): self.make_plan()
            self.assertTrue(self.payload.exists()); p.unlink()

    def test_added_member_refuses_before_deletion(self):
        self.make_plan(); addition = self.source / "added.png"; addition.write_bytes(b"new output")
        result = self.apply(fail=True)
        self.assertEqual(result["status"], "refused_before_delete"); self.assertEqual(result["deleted_files"], 0)
        self.assertTrue(addition.exists()); self.assertTrue(self.payload.exists())

    def test_same_size_changed_content_with_restored_mtime_refused(self):
        self.make_plan(); original = self.payload.stat(); raw = self.payload.read_bytes()
        self.payload.write_bytes(b"X" + raw[1:]); os.utime(self.payload, ns=(original.st_atime_ns, original.st_mtime_ns))
        result = self.apply(fail=True); self.assertEqual(result["deleted_files"], 0)

    def test_replaced_same_content_file_refused(self):
        self.make_plan(); raw = self.payload.read_bytes(); self.payload.rename(self.source / "moved.png")
        self.payload.write_bytes(raw); (self.source / "moved.png").unlink()
        self.assertEqual(self.apply(fail=True)["deleted_files"], 0)

    def test_changed_producer_completion_result_assessment_refuses(self):
        for attr in ("producer", "completion", "result", "assessment"):
            with self.subTest(attr=attr):
                self.setUp(); self.make_plan(); p = getattr(self, attr); p.write_bytes(p.read_bytes() + b"\nchanged evidence")
                self.assertEqual(self.apply(fail=True)["deleted_files"], 0)

    def test_active_code_reference_refuses(self):
        (self.project / "src/active.mjs").write_text("const activeCapture = " + json.dumps(self.relative), encoding="utf-8")
        with self.assertRaisesRegex(T.g.GuardError, "reference"): self.make_plan()

    def test_reference_added_after_plan_refuses(self):
        self.make_plan(); (self.project / "src/active.mjs").write_text("const active = " + json.dumps(self.relative), encoding="utf-8")
        self.assertEqual(self.apply(fail=True)["deleted_files"], 0)

    def test_idle_confirmation_required_on_all_platforms(self):
        args = self.args(); args.confirm_idle = False
        with self.assertRaisesRegex(T.g.GuardError, "confirm-idle"): T.plan_command(args)
        self.make_plan(); self.apply(fail=True, confirm_idle=False)
        self.assertFalse(self.receipt.exists()); self.assertTrue(self.source.exists())

    def test_forged_idle_and_unknown_visibility_refused(self):
        for value in (True, {"status": "clear", "visible_processes": 0, "records": []}):
            with mock.patch.object(T, "capture_activity", return_value=value), self.assertRaises(T.g.GuardError):
                T.require_activity(self.source)

    def test_exact_authorization_and_edited_family_refused(self):
        self.make_plan(); self.apply(fail=True, authorize_plan="0" * 64)
        value = json.loads(self.plan.read_text()); value["family"] = "tool-scratch"
        self.plan.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(self.apply(fail=True)["deleted_files"], 0)

    def test_retry_with_other_receipt_refused(self):
        self.make_plan(); (self.source / "extra.png").write_bytes(b"new member"); self.apply(fail=True)
        with self.assertRaisesRegex(T.g.GuardError, "claim already exists"):
            T.apply_command(argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan),
                receipt=str(self.area / "different-receipt.json"), confirm_idle=True))

    def test_preexisting_event_directory_refuses_before_claim_and_preserves_authorization(self):
        self.make_plan(); event_root = Path(str(self.receipt) + ".in-progress"); event_root.mkdir()
        sentinel = event_root / "previous-events.jsonl"; sentinel.write_text("must retain prior record", encoding="utf-8")
        before = sha(sentinel); errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = T.main(["apply", "--plan", str(self.plan), "--authorize-plan", sha(self.plan), "--receipt", str(self.receipt), "--confirm-idle"])
        result = json.loads(errors.getvalue()); self.assertEqual(code, 2)
        self.assertEqual(result["phase"], "initialization"); self.assertFalse(result["new_apply_claim_created"])
        self.assertEqual(result["deleted_files"], 0); self.assertEqual(sha(sentinel), before)
        self.assertFalse((self.project / T.CLAIMS_DIR).exists()); self.assertFalse(self.receipt.exists())
        result = self.apply(receipt=str(self.area / "fresh-receipt.json"))
        self.assertEqual(result["status"], "completed")

    def test_event_creation_or_initial_flush_failure_never_creates_source_claim(self):
        self.make_plan(); original = T.g.new_file
        def fail_events(path):
            if Path(path).name == "events.jsonl": raise OSError("fictional event log initialization failure")
            return original(path)
        with mock.patch.object(T.g, "new_file", side_effect=fail_events) if os.name == "nt" else mock.patch.object(T.os, "fdopen", side_effect=OSError("fictional event log initialization failure")):
            with self.assertRaises(T.InitializationError) as caught:
                T.apply_command(argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=True))
        self.assertFalse(caught.exception.details["new_apply_claim_created"])
        self.assertFalse((self.project / T.CLAIMS_DIR).exists()); self.assertTrue(self.payload.exists())

    def test_event_log_initial_fsync_failure_is_structured_and_does_not_claim_source(self):
        self.make_plan()
        with mock.patch.object(T.os, "fsync", side_effect=OSError("fictional initial log durability failure")):
            with self.assertRaises(T.InitializationError) as caught:
                T.apply_command(argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=True))
        self.assertEqual(caught.exception.details["phase"], "initialization")
        self.assertFalse(caught.exception.details["new_apply_claim_created"])
        self.assertFalse((self.project / T.CLAIMS_DIR).exists()); self.assertTrue(self.payload.exists())

    def test_event_directory_race_refuses_atomically_without_creating_source_claim(self):
        self.make_plan(); event_root = Path(str(self.receipt) + ".in-progress"); original = T.os.mkdir; raced = []
        def create_first(path, *args, **kwargs):
            if Path(path).name == event_root.name and not raced:
                raced.append(True); original(path, *args, **kwargs)
            return original(path, *args, **kwargs)
        with mock.patch.object(T.os, "mkdir", side_effect=create_first):
            with self.assertRaises(T.InitializationError) as caught:
                T.apply_command(argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=True))
        self.assertTrue(raced); self.assertFalse(caught.exception.details["new_apply_claim_created"])
        self.assertFalse((self.project / T.CLAIMS_DIR).exists()); self.assertTrue(self.payload.exists())

    def test_existing_claim_is_never_removed_or_overwritten_by_event_initialization(self):
        plan = self.make_plan()
        existing = T.claim(self.project, self.source, plan, sha(self.plan), self.area / "original-receipt.json")
        before = sha(existing["path"])
        with self.assertRaisesRegex(T.InitializationError, "claim already exists"):
            T.apply_command(argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=True))
        self.assertEqual(sha(existing["path"]), before); self.assertTrue(self.payload.exists())

    def test_event_symlink_or_reparse_is_never_followed(self):
        self.make_plan(); event_root = Path(str(self.receipt) + ".in-progress")
        target = self.area / "unrelated-output"; target.mkdir()
        try: os.symlink(target, event_root, target_is_directory=True)
        except OSError as exc: self.skipTest("Fixture cannot create directory link: " + str(exc))
        with self.assertRaises(T.InitializationError):
            T.apply_command(argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), receipt=str(self.receipt), confirm_idle=True))
        self.assertFalse((self.project / T.CLAIMS_DIR).exists()); self.assertEqual(list(target.iterdir()), [])

    def test_hardlink_payload_refused_where_supported(self):
        linked = self.area / "linked.png"
        try: os.link(self.payload, linked)
        except OSError as exc: self.skipTest("Fixture filesystem lacks hardlinks: " + str(exc))
        with self.assertRaises(T.g.GuardError): self.make_plan()
        self.assertTrue(linked.exists())

    def test_symlink_payload_refused_where_supported(self):
        linked = self.source / "linked.png"
        try: os.symlink(self.result, linked)
        except OSError as exc: self.skipTest("Fixture filesystem lacks symlinks: " + str(exc))
        with self.assertRaises((T.g.GuardError, OSError)): self.make_plan()
        self.assertTrue(self.result.exists())

    def test_native_exclusive_payload_lock_refuses_before_delete(self):
        self.make_plan()
        with T.g.guarded_file(self.payload):
            result = self.apply(fail=True)
        self.assertEqual(result["deleted_files"], 0); self.assertTrue(self.payload.exists())

    def test_plan_receipt_assessment_under_state_refused_before_body_read(self):
        state = self.project / ".claude"
        for value in (state / "plan.json", state / "receipt.json", state / "assessment.json"):
            with self.assertRaises(T.g.GuardError): T.admin_path(value, codex_home=str(self.codex))

    def test_lost_completion_keeps_durable_pending_batch_and_refuses_retry(self):
        plan = self.make_plan(); original = T.t.file_hash; deleted = []
        event_file = Path(str(self.receipt) + ".in-progress") / "events.jsonl"
        def fail_after_unlink(path, expected, budget, delete=False):
            result = original(path, expected, budget, delete=delete)
            if delete:
                events = [json.loads(s)["event"] for s in event_file.read_text().splitlines()]
                pending = [e for e in events if e["status"] == "batch_delete_pending"][-1]
                self.assertEqual({x["relative"] for x in pending["members"]}, set(plan["snapshot"]["files"]))
                deleted.append(str(path)); raise OSError("fictional lost completion after guarded unlink")
            return result
        with mock.patch.object(T.t, "file_hash", side_effect=fail_after_unlink): result = self.apply(fail=True)
        self.assertEqual(result["status"], "partial_or_uncertain"); self.assertEqual(result["deleted_files"], 0)
        self.assertEqual(len(deleted), 1); self.assertIn(result["current_file"], result["pending_batch"])
        self.assertFalse(Path(deleted[0]).exists()); self.assertTrue(self.result.exists())

    def test_unknown_new_member_is_never_swept_up(self):
        self.make_plan(); original = T.t.file_hash; inserted = []
        def create_during_release(path, expected, budget, delete=False):
            result = original(path, expected, budget, delete=delete)
            if delete and not inserted:
                p = self.source / "new-important.png"; p.write_bytes(b"new output not authorized"); inserted.append(p)
            return result
        with mock.patch.object(T.t, "file_hash", side_effect=create_during_release): result = self.apply(fail=True)
        self.assertEqual(result["status"], "partial_or_uncertain"); self.assertTrue(inserted[0].exists())

    def test_linear_payload_traversals_for_many_members(self):
        for i in range(256): (self.source / ("capture-%04d.png" % i)).write_bytes(b"fictional capture")
        self.finish_fixture()
        original = os.scandir; calls = {}
        def counted(path):
            key = str(path); calls[key] = calls.get(key, 0) + 1; return original(path)
        with mock.patch.object(T.os, "scandir", side_effect=counted):
            self.make_plan(); result = self.apply()
        self.assertEqual(result["deleted_files"], 258)
        # Four source snapshots plus four source reference walks; never a full
        # tree scan for every payload file.
        self.assertLessEqual(calls[str(self.source)], 10)

    def test_native_process_reference_is_rejected_without_killing(self):
        if os.name != "nt": self.skipTest("Windows CIM parser exercise")
        values = [{"ProcessId": os.getpid(), "ParentProcessId": 0, "Name": "python.exe", "CommandLine": "unit-test"},
            {"ProcessId": 999998, "ParentProcessId": 1, "Name": "node.exe", "CommandLine": "node --output " + str(self.source)}]
        response = subprocess.CompletedProcess([], 0, json.dumps(values), "")
        with mock.patch.object(T.t, "_run", return_value=response), self.assertRaisesRegex(T.g.GuardError, "Active process"):
            T.capture_activity(self.source)

    def test_inaccessible_known_agent_shell_runtime_refuses_until_os_confirms_exit(self):
        if os.name != "nt": self.skipTest("Windows native inventory parser exercise")
        for name in ("codex.exe", "claude.exe", "kimi.exe", "workbuddy.exe", "codebuddy.exe", "pwsh.exe", "powershell.exe", "cmd.exe", "bun.exe", "deno.exe", "pythonw.exe", "bash", "zsh", "sh", "wscript.exe", "cscript.exe"):
            values = [{"ProcessId": os.getpid(), "ParentProcessId": 0, "Name": "python.exe", "CommandLine": "unit-test"},
                {"ProcessId": 999998, "ParentProcessId": 1, "Name": name, "CommandLine": None}]
            response = subprocess.CompletedProcess([], 0, json.dumps(values), "")
            with self.subTest(name=name), mock.patch.object(T.t, "_run", return_value=response), mock.patch.object(T.t, "confirmed_exited_windows", return_value=False):
                with self.assertRaisesRegex(T.g.GuardError, "inaccessible"): T.capture_activity(self.source)
            with mock.patch.object(T.t, "_run", return_value=response), mock.patch.object(T.t, "confirmed_exited_windows", return_value=True):
                self.assertEqual(T.capture_activity(self.source)["status"], "clear")

    def test_current_execution_ancestors_remain_exempt_from_unknown_command_line(self):
        if os.name != "nt": self.skipTest("Windows native inventory parser exercise")
        values = [{"ProcessId": os.getpid(), "ParentProcessId": 999998, "Name": "python.exe", "CommandLine": "unit-test"},
            {"ProcessId": 999998, "ParentProcessId": 0, "Name": "powershell.exe", "CommandLine": None}]
        response = subprocess.CompletedProcess([], 0, json.dumps(values), "")
        with mock.patch.object(T.t, "_run", return_value=response), mock.patch.object(T.t, "confirmed_exited_windows", return_value=False):
            self.assertEqual(T.capture_activity(self.source)["status"], "clear")

    def test_real_isolated_recent_task_cli_cleanup_and_protected_hashes(self):
        if os.name != "nt" and sys.platform != "darwin": self.skipTest("Native Windows/macOS provider only")
        before = {str(p): sha(p) for p in self.sentinels + [self.assessment]}
        env = dict(os.environ, CODEX_HOME=str(self.codex), PYTHONIOENCODING="utf-8")
        def cli(*args):
            result = subprocess.run([sys.executable, "-I", "-B", str(SCRIPT), *map(str, args)], capture_output=True,
                text=True, encoding="utf-8", env=env, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cli("plan", "--project", self.project, "--source", self.relative, "--assessment", self.assessment,
            "--output", self.plan, "--codex-home", self.codex, "--confirm-idle")
        cli("apply", "--plan", self.plan, "--authorize-plan", sha(self.plan), "--receipt", self.receipt, "--confirm-idle")
        result = json.loads(self.receipt.read_text()); self.assertEqual(result["status"], "completed")
        self.assertEqual(result["deleted_files"], 2); self.assertFalse(self.source.exists())
        self.assertEqual(before, {p: sha(p) for p in before})
        print("\nAGENT_ARTIFACT_INTEGRATION=" + json.dumps({"platform": sys.platform, "status": result["status"],
            "deleted_files": result["deleted_files"], "logical_deleted_bytes": result["deleted_logical_bytes"],
            "volume_free_delta_bytes": result["source_free_delta_bytes"], "protected_sentinels_unchanged": len(before),
            "recent_task": True, "project_code_executed": False, "database_connected": False}))

    def test_real_visible_writer_refuses_without_stopping_it(self):
        if os.name != "nt" and sys.platform != "darwin": self.skipTest("Native Windows/macOS provider only")
        child = subprocess.Popen([sys.executable, "-I", "-c", "import time;time.sleep(45)", str(self.source)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with self.assertRaisesRegex(T.g.GuardError, "Active process"):
                T.capture_activity(self.source)
            self.assertIsNone(child.poll())
            self.assertTrue(self.payload.exists())
            print("\nAGENT_ARTIFACT_LIVE_WRITER=" + json.dumps({"platform": sys.platform, "status": "refused", "writer_left_running": True}))
        finally:
            child.terminate(); child.wait(timeout=10)  # Only this test-owned helper PID.


if __name__ == "__main__":
    print("Fictional Agent-task fixtures retained at:", RUN)
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
