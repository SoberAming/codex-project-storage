"""Optional real-volume smoke test, using only newly created tiny fixtures.

python -B tests/test_cross_volume_optional.py --source-parent ABS_EXISTING_DIR \
    --target-parent ABS_OTHER_VOLUME_DIR --report-dir ABS_EXISTING_REPORT_DIR

No paths or drive letters are predefined. Both parents must be ordinary, existing
directories on different actual volumes. The test never reads an existing user's
project. Small fixtures and reports remain for inspection. Run only on healthy
storage chosen by the operator. macOS needs explicit --confirm-idle.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import relocation_guard as R
import storage_guard as G


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-parent", required=True)
    parser.add_argument("--target-parent", required=True)
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--confirm-idle", action="store_true")
    parser.add_argument("--test-platform-features", action="store_true")
    args = parser.parse_args()
    if os.name != "nt" and not args.confirm_idle:
        parser.error("Confirm this new fixture will have no concurrent writer with --confirm-idle")
    src_parent, dst_parent, reports = map(G.absolute, (args.source_parent, args.target_parent, args.report_dir))
    for p in (src_parent, dst_parent, reports):
        G.ancestors(p)
    assert R.volume(src_parent) != R.volume(dst_parent), "Two actually different volumes are required; no fixture created"
    run_id = uuid.uuid4().hex[:12]
    project = src_parent / (".storage-skill-qa-" + run_id)
    target = dst_parent / ("storage-skill-retained-" + run_id)
    area = reports / ("cross-volume-" + run_id)
    area.mkdir(mode=0o700)
    project.mkdir(mode=0o700)
    source = project / "exports" / "closed-run"
    source.mkdir(parents=True)
    (source / "empty").mkdir()
    payloads = {"clip.mp4": b"fictional generated clip\x00\x1a\n\r\n\xff" * 4,
                "thumb.png": b"fictional generated thumbnail\x00\x1a\n\xff"}
    for name, data in payloads.items():
        (source / name).write_bytes(data)
    producer = project / "render.py"
    producer.write_text('OUTPUT = "exports/closed-run"\n', encoding="utf-8")
    codex = area / "empty-state"; codex.mkdir()
    env = dict(os.environ, CODEX_HOME=str(codex), PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    checks, commands = {}, []
    report = {"fixture_project": str(project), "retained_target": str(target),
              "real_project_data_touched": False, "source_volume": R.volume(project),
              "target_volume": R.volume(dst_parent), "script_sha256": sha(SCRIPTS / "relocation_guard.py"),
              "checks": checks, "commands": commands, "fixture_payload_bytes": sum(map(len, payloads.values()))}

    def assessment(relative, name):
        path = area / name
        path.write_text(json.dumps({"source": relative, "classification": "completed-exports", "purpose": "tiny fictional smoke fixture",
            "producer_evidence": {"description": "newly generated fixture export; no live use", "paths": ["render.py"]},
            "references_checked": True, "no_live_references": True, "writers_idle": True, "original_assets": False}), encoding="utf-8")
        return path

    def cli(command, *extra, ok=True):
        argv = [sys.executable, "-B", str(SCRIPTS / "relocation_guard.py"), command, *map(str, extra)]
        if os.name != "nt" and command != "plan":
            argv.append("--confirm-idle")
        result = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", env=env)
        commands.append({"command": command, "returncode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        if ok:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, "Unexpected acceptance"

    try:
        plan = area / "plan.json"
        proof = assessment("exports/closed-run", "assessment.json")
        before = {name: {"sha256": sha(source / name), "identity": G.fingerprint((source / name).stat())} for name in payloads}
        cli("plan", "--project", project, "--source", "exports/closed-run", "--target", target,
            "--action", "migrate", "--metadata-policy", "portable-export", "--assessment", proof,
            "--output", plan, "--codex-home", codex, "--reserve-bytes", "0")
        checks["real_cross_volume_plan"] = True
        plan_sha = sha(plan)
        copied, accepted, released = area / "copy.json", area / "accept.json", area / "release.json"
        cli("copy", "--plan", plan, "--authorize-plan", plan_sha, "--receipt", copied)
        for name, record in before.items():
            assert G.fingerprint((source / name).stat()) == record["identity"]
            assert sha(source / name) == sha(target / name) == record["sha256"]
        assert (target / "empty").is_dir()
        checks["copy_verified_and_source_unchanged"] = True
        cli("accept", "--plan", plan, "--authorize-plan", plan_sha, "--copy-receipt", copied,
            "--output", accepted, "--confirm-accepted")
        checks["explicit_portable_outcome_accepted"] = True
        cli("release", "--plan", plan, "--authorize-plan", plan_sha, "--accept", accepted, "--receipt", released)
        for name, record in before.items():
            assert not (source / name).exists()
            assert sha(target / name) == record["sha256"]
        assert producer.exists() and (source / "empty").is_dir()
        checks["release_only_planned_source_and_retained_copy_usable"] = True
        record = json.loads(released.read_text(encoding="utf-8"))
        report["deleted_files"] = record["deleted_files"]
        report["deleted_logical_bytes"] = record["deleted_logical_bytes"]
        report["source_free_delta_bytes"] = record["source_free_delta_bytes"]
        report["portable_metadata_differences"] = record.get("metadata_differences")

        if args.test_platform_features:
            hard = project / "exports" / "hardlinks"; hard.mkdir()
            a, b = hard / "a.png", hard / "b.png"
            a.write_bytes(b"new hardlink fixture")
            try:
                os.link(a, b)
            except OSError as exc:
                report["hardlink_test_skip"] = str(exc)
            else:
                cli("plan", "--project", project, "--source", "exports/hardlinks", "--target", dst_parent / ("unused-hard-" + run_id),
                    "--action", "migrate", "--metadata-policy", "portable-export", "--assessment", assessment("exports/hardlinks", "hard-assessment.json"),
                    "--output", area / "hard-plan.json", "--codex-home", codex, ok=False)
                assert a.exists() and b.exists()
                checks["real_hardlink_rejected"] = True
            if os.name == "nt":
                ads = project / "exports" / "streams"; ads.mkdir()
                f = ads / "a.png"; f.write_bytes(b"new ADS fixture")
                try:
                    Path(str(f) + ":qa-note").write_bytes(b"unique stream")
                except OSError as exc:
                    report["ads_test_skip"] = str(exc)
                else:
                    cli("plan", "--project", project, "--source", "exports/streams", "--target", dst_parent / ("unused-stream-" + run_id),
                        "--action", "migrate", "--metadata-policy", "portable-export", "--assessment", assessment("exports/streams", "stream-assessment.json"),
                        "--output", area / "stream-plan.json", "--codex-home", codex, ok=False)
                    assert f.exists() and Path(str(f) + ":qa-note").read_bytes() == b"unique stream"
                    checks["real_ads_rejected"] = True
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=repr(exc))
    finally:
        report["script_sha256_after"] = sha(SCRIPTS / "relocation_guard.py")
        report["script_unchanged"] = report["script_sha256_after"] == report["script_sha256"]
        path = area / "real-volume-result.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "report": str(path), "checks": checks,
                          "script_unchanged": report["script_unchanged"]}, ensure_ascii=False))
    return 0 if report["status"] == "passed" and report["script_unchanged"] else 1


if __name__ == "__main__":
    sys.exit(main())
