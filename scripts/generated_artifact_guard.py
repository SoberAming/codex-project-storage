#!/usr/bin/env python3
"""Exact deletion of assessed, rebuildable media intermediates; not final exports.

Python 3.10+, standard library only. Inputs and producer evidence are retained.
No build, project script, package manager, recursive deletion or process kill.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import storage_guard as g
import relocation_guard as r

VERSION = "1.3.0"
POLICY = "rebuildable-media-intermediates-v1"
MIN_AGE_HOURS = 48
FINAL = re.compile(r"(^|[_. -])(final|deliverable|approved|published|release|master|原件|成片|交付|定稿)([_. -]|$)", re.I)
RETAIN_DIRS = {"__snapshots__", "__image_snapshots__", "baselines", "golden", "evidence", "acceptance", "audit", "验收", "证据", "基准"}


def eligible(root, rel, snapshot, now_ns):
    """Re-evaluate hard boundaries; a purpose label never overrides them."""
    r.source_policy(root, rel, True)
    if any(p.lower() in RETAIN_DIRS or FINAL.search(p) for p in rel.split("/")):
        raise g.GuardError("Reference images, evidence and acceptance data are retained")
    for sub, record in snapshot["files"].items():
        r.source_policy(root, rel + "/" + sub)
        if any(p.lower() in RETAIN_DIRS or FINAL.search(p) for p in sub.split("/")):
            raise g.GuardError("Final/deliverable names are retained, not disposable intermediates")
        if now_ns - record["identity"]["mtime_ns"] < MIN_AGE_HOURS * 3600 * 10**9:
            raise g.GuardError("Recent/future-dated intermediate retained; minimum age is 48 hours")


def input_records(root, source, assessment, snapshot, evidence):
    values = assessment.get("rebuild_inputs")
    recipe = assessment.get("recreation_method")
    if (assessment.get("classification") != "generated-artifacts"
            or assessment.get("artifact_family") not in {"decoded-frames", "render-preview", "deterministic-transform"}
            or any(assessment.get(k) is not True for k in ("deterministic_rebuild", "rebuild_dependencies_available", "not_unique_ai_output"))
            or assessment.get("requires_external_service") is not False
            or not isinstance(recipe, str) or not recipe.strip()
            or not isinstance(values, list) or not 1 <= len(values) <= 32):
        raise g.GuardError("Rebuildable-intermediate assessment needs recreation_method and 1..32 retained inputs")
    records, seen = [], set()
    evidence_keys = {g.key(x["path"]) for x in evidence}
    output_ids = {(x["identity"]["device"], x["identity"]["inode"]) for x in snapshot["files"].values()}
    for rel in values:
        r.relative(rel)
        if r.credential(rel):
            raise g.GuardError("Credentials, state and session data cannot be reconstruction inputs")
        p = g.relative_file(root, rel)
        s = g.plain(p, False)
        if g.below(p, source) or (s.st_dev, s.st_ino) in output_ids:
            raise g.GuardError("Reconstruction input overlaps the deletion tree or output identity")
        if s.st_nlink != 1 or not s.st_ino or s.st_size <= 0:
            raise g.GuardError("Inputs must be present, nonempty ordinary independent files")
        if getattr(s, "st_file_attributes", 0) & (0x400 | 0x1000 | 0x4000 | 0x40000 | 0x400000):
            raise g.GuardError("Linked/encrypted/offline/recall input is not eligible")
        if getattr(s, "st_flags", 0):
            raise g.GuardError("Input filesystem flags are unsupported; input retained")
        k = g.key(p)
        if k in seen:
            raise g.GuardError("Duplicate reconstruction input")
        seen.add(k)
        records.append({"path": str(p), "relative_path": rel, "identity": g.fingerprint(s),
                        "content_read_as_producer_evidence": k in evidence_keys, "role": "retained_rebuild_input"})
    return records


def collect_source(root, rel, count):
    source = root.joinpath(*r.relative(rel).split("/"))
    g.ancestors(source)
    snap = r.collect(source, root, rel, count)
    if not snap["files"]:
        raise g.GuardError("No candidate intermediate files")
    import time
    eligible(root, rel, snap, time.time_ns())
    return source, snap


def evidence_and_assessment(root, source, assessment_path):
    assessment, _ = r.read_assessment(assessment_path, root, source, source)
    if assessment.get("classification") != "generated-artifacts":
        raise g.GuardError("Completed exports and unique deliverables cannot use intermediate deletion")
    records = r.evidence_records(root, assessment_path, assessment, source, source)
    return assessment, records


def report_path(value, root):
    path = g.absolute(value)
    if g.below(path, root):
        raise g.GuardError("Plans and receipts must be outside the project")
    for p in (path.parent, *path.parent.parents):
        try:
            if os.path.samefile(p, root):
                raise g.GuardError("Output resolves to a project alias")
        except FileNotFoundError:
            continue
    return g.safe_output(path)


def plan_command(args):
    root = g.project_root(args.project, args.codex_home)
    count = r.integer(args.max_files, "max-files", 10000)
    maximum = r.integer(args.max_bytes, "max-bytes")
    if not count or not maximum:
        raise g.GuardError("Positive file/read budgets required")
    source, snap = collect_source(root, args.source, count)
    output = report_path(args.output, root)
    assessment_path = g.absolute(args.assessment)
    assessment, evidence = evidence_and_assessment(root, source, assessment_path)
    inputs = input_records(root, source, assessment, snap, evidence)
    total = sum(x["identity"]["size"] for x in snap["files"].values())
    ebytes = sum(x["identity"]["size"] for x in evidence)
    budget = r.Budget(maximum, total + ebytes)
    r.Budget(maximum, 2 * total + ebytes)
    r.check_evidence(evidence, budget)
    r.verify_hashes(source, snap, budget)
    r.compare_source(r.collect(source, root, args.source, count), snap)
    if input_records(root, source, assessment, snap, evidence) != inputs:
        raise g.GuardError("Reconstruction input changed while planning")
    value = {"schema": POLICY, "tool_version": VERSION, "operation": "delete-rebuildable-intermediates",
        "created_at": g.utc(), "project": str(root), "project_identity": g.root_identity(root),
        "codex_home": args.codex_home, "source": args.source, "source_snapshot": snap,
        "source_volume": r.volume(source), "assessment_path": str(assessment_path), "assessment": assessment,
        "evidence": evidence, "rebuild_inputs": inputs, "logical_bytes": total,
        "limits": {"max_files": count, "max_bytes": maximum}, "min_age_hours": MIN_AGE_HOURS,
        "verification_limit": "Inputs are retained and metadata-bound; inputs also serving as producer evidence are hashed in that role. No rebuild was run.",
        "input_content_bytes_read": sum(x["identity"]["size"] for x in inputs if x["content_read_as_producer_evidence"]),
        "estimated_apply_payload_reads": 2 * total + ebytes,
        "user_impact": "Irreversible intermediate deletion; regeneration can take time and needs retained inputs/toolchain"}
    digest = r.atomic_json(output, value)
    print(json.dumps({"plan": str(output), "plan_sha256": digest, "files": len(snap["files"]), "logical_bytes": total}))
    return 0


def membership(source, snap, removed, count):
    dirs, files, stack = {}, set(), [(source, "")]
    while stack:
        folder, rel = stack.pop()
        g.ancestors(folder)
        dirs[rel] = g.root_identity(folder)
        with os.scandir(folder) as entries:
            for entry in entries:
                sub = (rel + "/" if rel else "") + entry.name
                r.relative(sub)
                s = g.plain(entry.path)
                if stat.S_ISDIR(s.st_mode):
                    stack.append((Path(entry.path), sub))
                elif stat.S_ISREG(s.st_mode):
                    files.add(sub)
                else:
                    raise g.GuardError("Special entry appeared during deletion")
                if len(files) > count or len(dirs) + len(stack) > count * 4:
                    raise g.GuardError("Membership budget exceeded")
    if dirs != {k: v["identity"] for k, v in snap["directories"].items()} or files != snap["files"].keys() - removed:
        raise g.GuardError("Intermediate tree membership or directory identity changed")


def apply_command(args):
    value, digest = r.read_json(args.plan)
    if args.authorize_plan.lower() != digest:
        raise g.GuardError("Authorization does not match the exact plan")
    if value.get("schema") != POLICY or value.get("operation") != "delete-rebuildable-intermediates":
        raise g.GuardError("Unsupported generated-artifact plan")
    if os.name != "nt" and not args.confirm_idle:
        raise g.GuardError("POSIX execution requires --confirm-idle; locks are advisory")
    root = g.project_root(value["project"], value.get("codex_home"))
    g.same_root(root, value["project_identity"])
    count = r.integer(value["limits"]["max_files"], "max-files", 10000)
    maximum = r.integer(value["limits"]["max_bytes"], "max-bytes")
    source, current = collect_source(root, value["source"], count)
    r.compare_source(current, value["source_snapshot"])
    if r.volume(source) != value["source_volume"]:
        raise g.GuardError("Source volume changed")
    assessment, fresh = evidence_and_assessment(root, source, g.absolute(value["assessment_path"]))
    if assessment != value["assessment"] or fresh != [{k: v for k, v in x.items() if k != "sha256"} for x in value["evidence"]]:
        raise g.GuardError("Recreation/producer evidence changed")
    inputs = input_records(root, source, assessment, current, fresh)
    if inputs != value["rebuild_inputs"]:
        raise g.GuardError("Retained reconstruction inputs changed")
    snap = value["source_snapshot"]
    total = sum(r.integer(x["identity"]["size"], "size") for x in snap["files"].values())
    ebytes = sum(r.integer(x["identity"]["size"], "evidence size") for x in value["evidence"])
    budget = r.Budget(maximum, 2 * total + ebytes)
    receipt = report_path(args.receipt, root)
    journal = r.Journal(receipt, source, source, digest, "delete-generated-intermediates")
    journal.value.update(schema=POLICY, tool_version=VERSION, planned_files=len(snap["files"]),
                         deleted_files=0, deleted_logical_bytes=0, input_content_bytes_read=0,
                         rebuild_executed=False, inputs_retained=True)
    removed = set()
    try:
        with contextlib.ExitStack() as locks:
            opened = {}
            # Inputs and evidence stay protected for the complete batch. A producer
            # can also be a reconstruction input; open it only once.
            for record in inputs + value["evidence"]:
                k = g.key(record["path"])
                if k not in opened:
                    fd, _ = locks.enter_context(g.guarded_file(record["path"]))
                    opened[k] = fd
                if g.fingerprint(os.fstat(opened[k])) != record["identity"]:
                    raise g.GuardError("Input/evidence identity changed before lock")
            for record in value["evidence"]:
                fd = opened[g.key(record["path"])]
                before = budget.used
                try:
                    actual = r.digest_fd(fd, record["identity"]["size"], budget)
                finally:
                    if any(g.key(x["path"]) == g.key(record["path"]) for x in inputs):
                        journal.value["input_content_bytes_read"] += budget.used - before
                if actual != record["sha256"]:
                    raise g.GuardError("Producer or assessment content changed")
            r.verify_hashes(source, snap, budget)
            r.compare_source(r.collect(source, root, value["source"], count), snap)
            for rel, record in snap["files"].items():
                item = {"path": rel, "status": "checking"}
                journal.value["items"].append(item); journal.save()
                path = source.joinpath(*rel.split("/"))
                with g.guarded_file(path, delete=True) as (fd, unlink):
                    if g.fingerprint(os.fstat(fd)) != record["identity"] or r.metadata(path) != record["metadata"]:
                        raise g.GuardError("Intermediate identity/metadata changed")
                    if r.digest_fd(fd, record["identity"]["size"], budget) != record["sha256"]:
                        raise g.GuardError("Intermediate bytes changed")
                    item["status"] = "delete_pending"; journal.save()
                    membership(source, snap, removed, count)
                    g.same_root(root, value["project_identity"])
                    r.source_policy(root, value["source"] + "/" + rel)
                    if g.fingerprint(os.fstat(fd)) != record["identity"] or r.metadata(path) != record["metadata"]:
                        raise g.GuardError("Intermediate changed before delete")
                    for retained in inputs + value["evidence"]:
                        if g.fingerprint(os.fstat(opened[g.key(retained["path"])])) != retained["identity"]:
                            raise g.GuardError("Retained input/evidence changed")
                    unlink()
                removed.add(rel); item["status"] = "deleted"
                journal.value["deleted_files"] += 1
                journal.value["deleted_logical_bytes"] += record["identity"]["size"]
                journal.save()
            membership(source, snap, removed, count)
        journal.value.update(status="completed", directories_retained=True)
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        r.stage_error(journal, exc)
    journal.value["not_attempted_files"] = len(snap["files"]) - len(journal.value["items"])
    journal.finish(source, budget)
    return 0 if journal.value["status"] == "completed" else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    for name in ("project", "source", "assessment", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--codex-home")
    p.add_argument("--max-files", type=int, default=1000)
    p.add_argument("--max-bytes", type=int, default=107374182400)
    p.set_defaults(run=plan_command)
    a = sub.add_parser("apply")
    for name in ("plan", "receipt", "authorize-plan"):
        a.add_argument("--" + name, required=True)
    a.add_argument("--confirm-idle", action="store_true")
    a.set_defaults(run=apply_command)
    args = parser.parse_args()
    try:
        return args.run(args)
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "no_automatic_retry": True}, ensure_ascii=False), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
