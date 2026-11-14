"""Run only isolated fictional samples: --work-root ABS_EXISTING_TEST_PARENT.

No reconstruction script is ever executed; inputs are metadata-only and kept.
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
from unittest import mock

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, rest = parser.parse_known_args()
base = Path(opts.work_root).absolute(); base.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="generated-artifact-tests-", dir=base))
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import generated_artifact_guard as A
import storage_guard as G
import relocation_guard as R


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class GeneratedTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project"; self.project.mkdir()
        self.codex = self.area / "empty-state"; self.codex.mkdir()
        self.source = self.project / "task-work" / "frames"; self.source.mkdir(parents=True)
        self.input = self.project / "assets" / "input.bin"; self.input.parent.mkdir()
        self.input.write_bytes(b"retained fictional input\x00\xff\n" * 64)
        self.producer = self.project / "decode.py"
        self.producer.write_text('OUTPUT="task-work/frames"\n# fictional decoder, never execute\n', encoding="utf-8")
        for name in ("frame-01.png", "frame-02.png"):
            p = self.source / name; p.write_bytes(b"generated frame\x00\x1a\xff\n")
            old = time.time() - 96 * 3600; os.utime(p, (old, old))
        self.assessment = self.area / "assessment.json"
        self.value = {"source": "task-work/frames", "classification": "generated-artifacts",
            "artifact_family": "decoded-frames", "purpose": "fictional decoded temporary frames",
            "producer_evidence": {"description": "fixture decoder declares exact output", "paths": ["decode.py"]},
            "references_checked": True, "no_live_references": True, "writers_idle": True, "original_assets": False,
            "recreation_method": "re-run the known local decoder with retained fixture input", "rebuild_inputs": ["assets/input.bin"],
            "deterministic_rebuild": True, "rebuild_dependencies_available": True, "not_unique_ai_output": True,
            "requires_external_service": False}
        self.save_assessment()
        self.plan = self.area / "plan.json"
        self.env = dict(os.environ, CODEX_HOME=str(self.codex), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")

    def save_assessment(self):
        self.assessment.write_text(json.dumps(self.value), encoding="utf-8")

    def cli(self, *args, ok=True):
        p = subprocess.run([sys.executable, "-B", str(SCRIPTS / "generated_artifact_guard.py"), *map(str, args)],
                           text=True, capture_output=True, encoding="utf-8", env=self.env)
        if ok: self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        else: self.assertNotEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def make_plan(self, ok=True, extra=()):
        return self.cli("plan", "--project", self.project, "--source", "task-work/frames", "--assessment", self.assessment,
                        "--output", self.plan, "--codex-home", self.codex, *extra, ok=ok)

    def apply(self, ok=True, digest=None):
        receipt = self.area / "receipt.json"
        extra = ["--confirm-idle"] if os.name != "nt" else []
        self.cli("apply", "--plan", self.plan, "--receipt", receipt, "--authorize-plan", digest or sha(self.plan), *extra, ok=ok)
        return json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else None

    def test_exact_intermediates_deleted_inputs_and_evidence_kept(self):
        before = sha(self.input), sha(self.producer), sha(self.assessment)
        self.make_plan(); result = self.apply()
        self.assertEqual(result["deleted_files"], 2)
        self.assertEqual(list(self.source.iterdir()), [])
        self.assertEqual((sha(self.input), sha(self.producer), sha(self.assessment)), before)
        self.assertEqual(result["input_content_bytes_read"], 0)
        self.assertFalse(result["rebuild_executed"])

    def test_input_inside_tree_refused(self):
        self.value["rebuild_inputs"] = ["task-work/frames/frame-01.png"]; self.save_assessment()
        self.make_plan(ok=False); self.assertFalse(self.plan.exists())

    def test_missing_input_refused(self):
        self.input.unlink(); self.make_plan(ok=False)
        self.assertTrue((self.source / "frame-01.png").exists())

    def test_empty_input_refused(self):
        self.input.write_bytes(b""); self.make_plan(ok=False)

    def test_changed_input_refuses_apply(self):
        self.make_plan(); self.input.write_bytes(b"new version")
        self.apply(ok=False); self.assertTrue((self.source / "frame-01.png").exists())

    def test_changed_evidence_refuses_apply(self):
        self.make_plan(); self.producer.write_text("# changed producer\n", encoding="utf-8")
        self.apply(ok=False); self.assertTrue((self.source / "frame-01.png").exists())

    def test_completed_export_not_treated_as_intermediate(self):
        self.value["classification"] = "completed-exports"; self.save_assessment()
        self.make_plan(ok=False)

    def test_unique_ai_generation_retained(self):
        self.value["not_unique_ai_output"] = False; self.save_assessment()
        self.make_plan(ok=False)

    def test_external_service_rebuild_not_accepted(self):
        self.value["requires_external_service"] = True; self.save_assessment()
        self.make_plan(ok=False)

    def test_final_and_critical_mix_retained(self):
        for name in ("final.mp4", "business.sqlite", "source.py"):
            p = self.source / name; p.write_bytes(b"retained critical dummy")
            old = time.time() - 96 * 3600; os.utime(p, (old, old))
        self.make_plan(ok=False)
        self.assertTrue((self.source / "final.mp4").exists())

    def test_recent_frame_retained(self):
        p = self.source / "frame-01.png"; os.utime(p, None)
        self.make_plan(ok=False)

    def test_final_output_directory_retained(self):
        self.source.rename(self.source.parent / "final-renders")
        self.value["source"] = "task-work/final-renders"; self.save_assessment()
        self.cli("plan", "--project", self.project, "--source", "task-work/final-renders", "--assessment", self.assessment,
                 "--output", self.plan, "--codex-home", self.codex, ok=False)

    def test_wrong_authorization_retained(self):
        self.make_plan(); self.apply(ok=False, digest="0" * 64)
        self.assertTrue((self.source / "frame-01.png").exists())

    def test_new_member_after_plan_retained(self):
        self.make_plan(); (self.source / "new.png").write_bytes(b"new active output")
        self.apply(ok=False); self.assertTrue((self.source / "frame-01.png").exists())

    def test_no_input_payload_read_and_input_guard_held(self):
        self.make_plan()
        native_digest = R.digest_fd
        input_id = G.fingerprint(self.input.stat())
        def checked(fd, size, budget, writer=None):
            self.assertNotEqual((os.fstat(fd).st_dev, os.fstat(fd).st_ino), (input_id["device"], input_id["inode"]))
            return native_digest(fd, size, budget, writer)
        args = argparse.Namespace(plan=str(self.plan), receipt=str(self.area / "direct.json"), authorize_plan=sha(self.plan), confirm_idle=True)
        with mock.patch.object(R, "digest_fd", side_effect=checked), contextlib.redirect_stdout(io.StringIO()):
            result = A.apply_command(args)
        self.assertEqual(result, 0)
        self.assertTrue(self.input.exists())

    def test_source_subtree_cannot_be_relabelled_as_dependency_project(self):
        nested = self.project / "node_modules" / "vendor"; nested.mkdir(parents=True)
        self.cli("plan", "--project", nested, "--source", "frames", "--assessment", self.assessment,
                 "--output", self.area / "bad.json", "--codex-home", self.codex, ok=False)

    def test_producer_can_be_input_and_read_is_reported_honestly(self):
        self.value["rebuild_inputs"] = ["decode.py"]; self.save_assessment()
        self.make_plan(); result = self.apply()
        self.assertEqual(result["input_content_bytes_read"], self.producer.stat().st_size)
        self.assertTrue(self.producer.exists())


if __name__ == "__main__":
    print("Isolated evidence directory:", RUN, flush=True)
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
