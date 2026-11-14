"""Isolated volume/migration regressions; no real project is touched.

python -B tests/test_storage_modes.py --work-root ABS_TEST_DIRECTORY
Fixtures remain for inspection. Simulated volume tests are explicitly named;
they do not establish real cross-volume or macOS acceptance.
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
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, remaining = parser.parse_known_args()
BASE = Path(opts.work_root).absolute()
BASE.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="storage-modes-", dir=BASE))
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import storage_guard as G
import relocation_guard as R
import volume_advisor as V


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class IsolatedCase(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project with spaces"
        self.project.mkdir()
        self.codex = self.area / "empty-codex"
        self.codex.mkdir()
        self.env = dict(os.environ, CODEX_HOME=str(self.codex), PYTHONDONTWRITEBYTECODE="1",
                        PYTHONIOENCODING="utf-8")

    def cli(self, script, *args, ok=True):
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / script), *map(str, args)],
                                text=True, capture_output=True, encoding="utf-8", env=self.env)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result


class VolumeTests(IsolatedCase):
    def inspect(self, name="volume.json", *args, ok=True):
        output = self.area / name
        self.cli("volume_advisor.py", "inspect", "--project", self.project,
                 "--codex-home", self.codex, "--no-discover", "--output", output, *args, ok=ok)
        return json.loads(output.read_text(encoding="utf-8")) if output.exists() else None

    def test_optional_goal_and_no_project_mutation(self):
        marker = self.project / "business.txt"
        marker.write_text("unique business sample", encoding="utf-8")
        before = marker.read_bytes(), self.project.stat().st_mtime_ns
        report = self.inspect()
        self.assertTrue(report["read_only"])
        self.assertFalse(report["goal_user_specified"])
        self.assertIsNone(report["decision_basis"]["goal_gap"])
        self.assertEqual((marker.read_bytes(), self.project.stat().st_mtime_ns), before)

    def test_same_volume_new_target_not_created(self):
        target = self.area / "arbitrary-archive-name"
        report = self.inspect("volume.json", "--target", target)
        found = next(r for r in report["target_locations"] if r["requested_path"] == str(target))
        self.assertTrue(found["same_volume_as_project"])
        self.assertFalse(found["eligible_different_volume_location"])
        self.assertFalse(target.exists())

    def test_goal_gap_is_based_on_reported_source_free(self):
        report = self.inspect("volume.json", "--goal-free-gib", "1000")
        basis = report["decision_basis"]
        self.assertTrue(report["goal_user_specified"])
        self.assertEqual(basis["goal_gap"], max(0, 1000 * 1024**3 - basis["source_volume_free"]))

    def test_bad_goals_refused(self):
        for n, value in enumerate(("-1", "nan", "inf")):
            self.inspect(f"invalid-{n}.json", "--goal-free-gib", value, ok=False)

    def test_report_inside_project_refused(self):
        output = self.project / "volume.json"
        self.cli("volume_advisor.py", "inspect", "--project", self.project, "--codex-home", self.codex,
                 "--no-discover", "--output", output, ok=False)
        self.assertFalse(output.exists())

    def test_existing_reports_never_overwritten(self):
        self.inspect()
        before = sha(self.area / "volume.json"), sha(self.area / "volume.md")
        self.inspect(ok=False)
        self.assertEqual((sha(self.area / "volume.json"), sha(self.area / "volume.md")), before)


class RelocationTests(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.source_rel = "exports/closed-run"
        self.source = self.project / self.source_rel
        self.source.mkdir(parents=True)
        (self.source / "empty").mkdir()
        (self.source / "clip.mp4").write_bytes(b"generated clip sample\x00\x1a\n\r\n\xff" * 32)
        (self.source / "thumb.png").write_bytes(b"generated thumbnail sample")
        self.producer = self.project / "render.py"
        self.producer.write_text('OUTPUT = "exports/closed-run"\n', encoding="utf-8")
        self.target = self.area / "selected-retention-location"
        self.assessment = self.area / "assessment.json"
        self.assessment.write_text(json.dumps({
            "source": self.source_rel, "classification": "completed-exports", "purpose": "finished disposable fixture exports",
            "producer_evidence": {"description": "fixture producer declares the exact output path", "paths": ["render.py"]},
            "references_checked": True, "no_live_references": True, "writers_idle": True, "original_assets": False
        }), encoding="utf-8")
        self.plan = self.area / "plan.json"

    def retained_copy(self):
        shutil.copytree(self.source, self.target, copy_function=shutil.copy2)

    def plan_cli(self, action="deduplicate", ok=True, extra=()):
        return self.cli("relocation_guard.py", "plan", "--project", self.project, "--source", self.source_rel,
                        "--target", self.target, "--action", action, "--assessment", self.assessment,
                        "--output", self.plan, "--metadata-policy", "portable-export", "--codex-home", self.codex,
                        *extra, ok=ok)

    def phase(self, command, *, ok=True, receipt="receipt.json", accept=None, digest=None):
        output = self.area / receipt
        args = [command, "--plan", self.plan, "--authorize-plan", digest or sha(self.plan)]
        if os.name != "nt":
            args += ["--confirm-idle"]
        if command == "accept":
            args += ["--output", output, "--confirm-accepted"]
        else:
            args += ["--receipt", output]
        if accept:
            args += ["--accept", accept]
        self.cli("relocation_guard.py", *args, ok=ok)
        return output

    def test_deduplicate_exact_copy_releases_only_source(self):
        self.retained_copy()
        expected = {p.name: sha(p) for p in self.source.iterdir() if p.is_file()}
        self.plan_cli()
        accepted = self.phase("accept", receipt="accept.json")
        result = self.phase("release", accept=accepted)
        record = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["deleted_files"], 2)
        self.assertEqual(list(self.source.glob("*.mp4")), [])
        self.assertTrue((self.source / "empty").is_dir())
        self.assertTrue(self.producer.exists())
        for name, digest in expected.items():
            self.assertEqual(sha(self.target / name), digest)

    def test_same_volume_migration_refused_without_target_creation(self):
        self.plan_cli("migrate", ok=False)
        self.assertFalse(self.target.exists())
        self.assertFalse(self.plan.exists())
        self.assertTrue((self.source / "clip.mp4").exists())

    def test_unknown_live_references_cannot_plan(self):
        self.retained_copy()
        a = json.loads(self.assessment.read_text(encoding="utf-8"))
        a["no_live_references"] = False
        self.assessment.write_text(json.dumps(a), encoding="utf-8")
        self.plan_cli(ok=False)
        self.assertFalse(self.plan.exists())

    def test_mixed_critical_data_refuses_entire_directory(self):
        (self.source / "history.jsonl").write_text("critical history sample", encoding="utf-8")
        self.retained_copy()
        self.plan_cli(ok=False)
        self.assertTrue((self.source / "history.jsonl").exists())

    def test_missing_acceptance_refuses_release(self):
        self.retained_copy(); self.plan_cli()
        self.phase("release", accept=self.area / "missing-accept.json", ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())
        self.assertTrue((self.source / "thumb.png").exists())

    def test_source_new_empty_directory_after_plan_refused(self):
        self.retained_copy(); self.plan_cli()
        (self.source / "new-empty").mkdir()
        self.phase("accept", receipt="accept.json", ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())

    def test_source_new_file_after_acceptance_refused(self):
        self.retained_copy(); self.plan_cli()
        accepted = self.phase("accept", receipt="accept.json")
        (self.source / "new.png").write_bytes(b"new active output")
        self.phase("release", accept=accepted, ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())
        self.assertTrue((self.source / "new.png").exists())

    def test_changed_retained_bytes_refuses_release(self):
        self.retained_copy(); self.plan_cli()
        accepted = self.phase("accept", receipt="accept.json")
        p = self.target / "clip.mp4"; s = p.stat()
        data = bytearray(p.read_bytes()); data[-1] ^= 1; p.write_bytes(data)
        os.utime(p, ns=(s.st_atime_ns, s.st_mtime_ns))
        self.phase("release", accept=accepted, ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())

    def test_changed_producer_evidence_refuses_release(self):
        self.retained_copy(); self.plan_cli()
        accepted = self.phase("accept", receipt="accept.json")
        self.producer.write_text('OUTPUT = "new-location"\n', encoding="utf-8")
        self.phase("release", accept=accepted, ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())

    def test_wrong_authorization_refuses_before_deletion(self):
        self.retained_copy(); self.plan_cli()
        self.phase("accept", digest="0" * 64, ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())

    def test_budget_insufficient_cannot_plan(self):
        self.retained_copy()
        self.plan_cli(ok=False, extra=("--max-bytes", "1"))
        self.assertFalse(self.plan.exists())

    def test_target_inside_project_refused(self):
        self.target = self.project / "new-target"
        self.plan_cli("migrate", ok=False)
        self.assertFalse(self.target.exists())

    def test_metadata_policy_cannot_change_between_accept_and_release(self):
        self.retained_copy(); self.plan_cli()
        accepted = self.phase("accept", receipt="accept.json")
        data = json.loads(accepted.read_text(encoding="utf-8")); data["metadata_policy"] = "preserve"
        edited = self.area / "edited-accept.json"; edited.write_text(json.dumps(data), encoding="utf-8")
        self.phase("release", accept=edited, ok=False)
        self.assertTrue((self.source / "clip.mp4").exists())

    @contextlib.contextmanager
    def simulated_volumes(self):
        native = R.volume
        def mapped(path):
            result = native(path)
            if G.key(path) == G.key(self.target.parent) or G.below(path, self.target):
                result["simulated_volume"] = "retention"
            return result
        with mock.patch.object(R, "volume", side_effect=mapped):
            yield

    def direct_plan(self, action="migrate"):
        args = argparse.Namespace(project=str(self.project), source=self.source_rel, target=str(self.target),
            action=action, assessment=str(self.assessment), output=str(self.plan), metadata_policy="portable-export",
            codex_home=str(self.codex), max_files=10000, max_bytes=107374182400, reserve_bytes=0)
        with contextlib.redirect_stdout(io.StringIO()):
            R.plan_command(args)

    def test_mismatched_copy_size_refused_before_any_payload_hash(self):
        self.retained_copy()
        p = self.target / "clip.mp4"
        with p.open("ab") as f:
            f.write(b"new byte")
        with mock.patch.object(R, "digest_fd", side_effect=AssertionError("metadata must refuse before content reads")) as digest:
            with self.assertRaises(G.GuardError):
                self.direct_plan(action="deduplicate")
        digest.assert_not_called()
        self.assertFalse(self.plan.exists())
        self.assertTrue((self.source / "clip.mp4").exists())

    def direct_phase(self, function, **kwargs):
        args = argparse.Namespace(plan=str(self.plan), authorize_plan=sha(self.plan), confirm_idle=True, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            return function(args)

    def test_simulated_cross_volume_full_copy_accept_release(self):
        original = {p.name: sha(p) for p in self.source.iterdir() if p.is_file()}
        with self.simulated_volumes():
            self.direct_plan()
            copy_receipt = self.area / "copy.json"
            self.assertEqual(self.direct_phase(R.copy_command, receipt=str(copy_receipt)), 0)
            for name, digest in original.items():
                self.assertEqual(sha(self.source / name), digest)
                self.assertEqual(sha(self.target / name), digest)
            accepted = self.area / "accept.json"
            self.assertEqual(self.direct_phase(R.accept_command, copy_receipt=str(copy_receipt), output=str(accepted), confirm_accepted=True), 0)
            self.assertEqual(self.direct_phase(R.release_command, accept=str(accepted), receipt=str(self.area / "release.json")), 0)
        self.assertTrue((self.target / "empty").is_dir())
        self.assertFalse((self.source / "clip.mp4").exists())

    def test_simulated_cross_volume_copy_io_failure_preserves_source(self):
        original = {p.name: sha(p) for p in self.source.iterdir() if p.is_file()}
        digest_native = R.digest_fd
        def fail_copy(fd, size, budget, writer=None):
            if writer is not None:
                raise OSError(errno.EIO, "injected fixture copy error")
            return digest_native(fd, size, budget, writer)
        with self.simulated_volumes():
            self.direct_plan()
            with mock.patch.object(R, "digest_fd", side_effect=fail_copy):
                self.assertNotEqual(self.direct_phase(R.copy_command, receipt=str(self.area / "copy-fail.json")), 0)
        for name, digest in original.items():
            self.assertEqual(sha(self.source / name), digest)


if __name__ == "__main__":
    print("Isolated evidence directory:", RUN, flush=True)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
