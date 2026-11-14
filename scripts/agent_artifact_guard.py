#!/usr/bin/env python3
"""Exact cleanup of positively reviewed, completed Agent-task scratch units.

No directory name, age, Agent brand, or extension proves disposability. Real
retained producer/terminal/result evidence and semantic review are mandatory.
The process never runs project code, kills processes, alters state or recursively
removes a tree. Native activity visibility and POSIX advisory locks have limits.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time


def load_sibling(name, filename):
    path = Path(__file__).absolute().with_name(filename)
    for p in (path, *path.parents):
        s = os.lstat(p)
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Guard code cannot load through links/reparse points")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


t = load_sibling("_agent_retained_runtime_helpers", "retired_runtime_guard.py")
g, r = t.g, t.r
VERSION = "1.5.0"
POLICY = "completed-agent-task-artifacts-v1"
ASSESSMENT = "completed-agent-task-assessment-v1"
CLAIMS_DIR = ".storage-agent-artifact-claims"
UNIT_NAMES = {"scratch", "captures", "traces", "previews", "download-fragments", "tmp", "temp"}
STATE = {".claude", ".kimi", ".kimi-code", ".workbuddy", ".codebuddy"}
RETAIN_NAMES = r.BLOCKED | STATE | {"evidence", "acceptance", "audit", "baselines", "golden",
    "results", "result", "deliverables", "deliverable", "final", "approved", "published",
    "__snapshots__", "__image_snapshots__", "交付", "验收", "定稿", "成片"}
RETAIN_RE = re.compile(r"(?:^|[._ -])(?:raw|original|backup|recovery|master|final|deliverable|approved|published|baseline|session|history|index|manifest)(?:[._ -]|$)", re.I)
FAMILIES = {
    "browser-captures": {".png", ".jpg", ".jpeg", ".webp", ".webm", ".mp4", ".trace", ".zip", ".har"},
    "download-fragments": {".part", ".partial", ".crdownload", ".download"},
    "tool-scratch": {".tmp", ".part", ".partial", ".log", ".trace", ".zip"},
}
PRODUCER_HINTS = {"browser-captures": ("screenshot", "record_video", "recordVideo", "tracing", "trace", "video"),
                  "download-fragments": ("download", "write", "open", "part"),
                  "tool-scratch": ("write", "mkdir", "tempfile", "mkdtemp", "scratch")}
CONCURRENCY = "Exact-unit visible native process/open-file checks; Windows exclusive handles or POSIX advisory locks. Noncooperating/new writers can race; explicit quiescence must remain true."


class InitializationError(g.GuardError):
    def __init__(self, message, **details):
        super().__init__(message)
        self.details = {"status": "refused_before_delete", "phase": "initialization", "deleted_files": 0, **details}


def normalized_paths(value):
    return re.sub(r"[\\/]+", "/", value)


def path_token(body, relative, root=None):
    """Exact path token, never a prefix of another path/filename."""
    candidates = [relative]
    if root is not None:
        candidates.append(str(root.joinpath(*relative.split("/"))))
    body = normalized_paths(body)
    flags = re.I if os.name == "nt" else 0
    for candidate in candidates:
        pattern = r'''(?:^|[\s"'`=(:,\[])''' + re.escape(normalized_paths(candidate)) + r'''(?=$|[\s"'`),;\]}])'''
        if re.search(pattern, body, flags):
            return True
    return False


def path_component(body, component):
    flags = re.I if os.name == "nt" else 0
    return bool(re.search(r"(?<![\w.-])" + re.escape(component) + r"(?![\w.-])", normalized_paths(body), flags))


def private(relative):
    parts = relative.lower().split("/")
    return r.credential(relative) or any(p in STATE for p in parts) or any(p.startswith(".env") for p in parts)


def source_path(root, relative):
    r.relative(relative)
    parts = relative.split("/")
    if len(parts) < 2 or parts[-1].lower() not in UNIT_NAMES or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{5,127}", parts[-2]):
        raise g.GuardError("Select a precise disposable task unit below an identified run, not a project/output/runtime root")
    if private(relative) or any(p.lower() in RETAIN_NAMES or RETAIN_RE.search(p) for p in parts):
        raise g.GuardError("Protected source/state/deliverable boundary")
    marker = g.managed_marker_reason(root, relative + "/_file")
    if marker:
        raise g.GuardError(marker)
    path = root.joinpath(*parts); g.ancestors(path); g.plain(path, True)
    return path, parts[-2]


def admin_path(value, root=None, codex_home=None, output=False):
    path = t.administrative_path(value, codex_home)
    if any(p.lower() in STATE for p in path.parts):
        raise g.GuardError("Agent-state administrative path refused before reading")
    if root is not None and g.below(path, root):
        raise g.GuardError("Assessments, plans and receipts must stay outside the project")
    return g.safe_output(path) if output else path


def unit_member(relative, family, directory=False):
    r.relative(relative)
    parts = relative.split("/")
    if private(relative) or any(p.lower() in RETAIN_NAMES or RETAIN_RE.search(p) for p in parts):
        raise g.GuardError("Protected/mixed task member retained: " + relative)
    if not directory and Path(parts[-1]).suffix.lower() not in FAMILIES[family]:
        raise g.GuardError("Unsupported/source/database/unique document format retained: " + relative)


def snapshot(source, family, count, budget=None):
    if family not in FAMILIES:
        raise g.GuardError("Unsupported disposable task family")
    directories, files, stack = {}, {}, [(source, "")]
    while stack:
        folder, rel = stack.pop()
        g.ancestors(folder)
        if rel:
            unit_member(rel, family, True)
        directories[rel] = t.record(folder, True)
        with os.scandir(folder) as entries:
            for entry in entries:
                sub = (rel + "/" if rel else "") + entry.name
                p = Path(entry.path); s = g.plain(p)
                if stat.S_ISDIR(s.st_mode):
                    unit_member(sub, family, True); stack.append((p, sub))
                elif stat.S_ISREG(s.st_mode):
                    unit_member(sub, family)
                    rec = t.record(p)
                    if budget is not None:
                        rec["sha256"] = t.file_hash(p, rec, budget)
                    files[sub] = rec
                else:
                    raise g.GuardError("Special task-unit member refused")
                if len(files) > count or len(files) + len(stack) + len(directories) > count * 4:
                    raise g.GuardError("Task-unit membership budget exceeded")
    if not files:
        raise g.GuardError("No disposable task payload found")
    return {"directories": directories, "files": files}


def assess(root, source, relative, run_id, assessment_path, budget):
    if not 0 < g.plain(assessment_path, False).st_size <= 1024 * 1024:
        raise g.GuardError("Assessment must be nonempty and no larger than 1 MiB before body read")
    value, assessment_sha = g.read_json(assessment_path)
    if (not isinstance(value, dict) or value.get("schema") != ASSESSMENT
            or value.get("source") != relative or value.get("run_id") != run_id
            or value.get("family") not in FAMILIES):
        raise g.GuardError("Exact source/run/family assessment is required")
    review = value.get("review", {})
    for field in ("reviewer", "origin_reason", "discardability_reason", "no_unique_value_reason", "reference_scope_reason", "retained_results_reason"):
        t.text(review.get(field), "semantic task review: " + field)
    evidence, bodies = {}, {}

    def retained(spec, label, body=False):
        if not isinstance(spec, dict):
            raise g.GuardError("Missing real retained " + label)
        rel = r.relative(spec.get("path")); path = g.relative_file(root, rel)
        if private(rel) or any(p.lower() in g.PRUNE | STATE for p in rel.split("/")) or g.below(path, source):
            raise g.GuardError("Retained evidence overlaps disposable/state/credential scope")
        if len(evidence) >= 32 and rel not in evidence:
            raise g.GuardError("Retained evidence limit exceeded")
        if body:
            content, rec = t.bounded_text(path, budget)
        else:
            content = None; rec = t.record(path)
            if rec["fingerprint"]["size"] <= 0:
                raise g.GuardError("Retained result/input must be nonempty")
            rec["sha256"] = t.file_hash(path, rec, budget)
        if not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", "")) or spec["sha256"] != rec["sha256"]:
            raise g.GuardError("Retained " + label + " hash missing/changed")
        evidence[rel] = rec
        if body:
            bodies[rel] = content
        return rel, path, content

    producer_rel, producer, producer_body = retained(value.get("producer"), "producer", True)
    if producer.suffix.lower() not in t.CODE:
        raise g.GuardError("Producer must be actual retained executable source")
    output_quote = value["producer"].get("output_quote")
    t.quote(producer_body, output_quote, "producer output")
    if not any(h.casefold() in output_quote.casefold() for h in PRODUCER_HINTS[value["family"]]):
        raise g.GuardError("Producer output quote does not describe the supported task family")
    path_quote = value["producer"].get("output_path_quote")
    t.quote(producer_body, path_quote, "actual producer output path relationship")
    parts = relative.split("/")
    if not path_component(path_quote, parts[-1]) or (len(parts) >= 3 and not path_component(path_quote, parts[0])):
        raise g.GuardError("Producer path quote does not bind this task-output root and unit")
    if not path_token(output_quote, relative, root):
        symbol = value["producer"].get("path_symbol", "")
        if (not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]{0,79}", symbol)
                or not re.search(r"(?<![\w$])" + re.escape(symbol) + r"(?![\w$])", path_quote)
                or not re.search(r"(?<![\w$])" + re.escape(symbol) + r"(?![\w$])", output_quote)):
            raise g.GuardError("Producer output operation must use the same reviewed path symbol or exact source path")
    completion_rel, _, completion_body = retained(value.get("completion"), "terminal run record", True)
    if completion_rel == producer_rel:
        raise g.GuardError("Terminal run evidence must be independent from producer source")
    complete = value["completion"]
    t.quote(completion_body, complete.get("producer_quote"), "actual run producer binding")
    if not path_token(complete["producer_quote"], producer_rel, root):
        raise g.GuardError("Terminal run record does not bind the retained producer path")
    t.quote(completion_body, complete.get("source_quote"), "exact run/source binding")
    if not path_token(complete["source_quote"], relative, root):
        raise g.GuardError("Terminal record is not bound to this exact source and run")
    t.quote(completion_body, complete.get("terminal_quote"), "terminal task result")
    if re.search(r"\b(?:not|never|still|pending|running)\b", complete["terminal_quote"], re.I):
        raise g.GuardError("Ambiguous/negative terminal status retained")
    if not re.search(r"\b(?:completed|finished|failed|cancelled|canceled|terminated)\b", complete["terminal_quote"], re.I):
        raise g.GuardError("Actual terminal status is required; a running task cannot be cleaned")
    t.quote(completion_body, complete.get("writer_stop_quote"), "task writer shutdown")
    if re.search(r"\b(?:not|never|still|pending|running)\b", complete["writer_stop_quote"], re.I):
        raise g.GuardError("Ambiguous/negative writer shutdown retained")
    if not re.search(r"\b(?:stopped|closed|exited|terminated)\b", complete["writer_stop_quote"], re.I):
        raise g.GuardError("Retained record must establish writer shutdown separately")
    results = value.get("retained_results")
    if not isinstance(results, list) or not 1 <= len(results) <= 24:
        raise g.GuardError("At least one separate useful retained result/input is required")
    result_paths = []
    for spec in results:
        rel, _, _ = retained(spec, "useful task result/input")
        if rel in {producer_rel, completion_rel} or rel in result_paths:
            raise g.GuardError("Retained result/input must be independent and distinct")
        result_paths.append(rel)
    safe_configs = []
    for spec in value.get("reference_files", []):
        if not isinstance(spec, dict) or not t.SAFE_CONFIG.fullmatch(Path(spec.get("path", "")).name):
            raise g.GuardError("Reference configuration must use an explicitly supported safe configuration name")
        rel, _, _ = retained(spec, "safe reference config", True)
        t.text(spec.get("reason"), "safe reference config privacy/scope review")
        safe_configs.append(rel)
    return {"family": value["family"], "agent": value.get("agent", "unspecified"), "run_id": run_id,
        "assessment_sha256": assessment_sha, "assessment_record": t.record(assessment_path),
        "evidence": evidence, "review": review, "producer": producer_rel, "completion": completion_rel,
        "retained_results": result_paths, "historical_reference_paths": [producer_rel, completion_rel],
        "safe_reference_configs": sorted(set(safe_configs)),
        "semantic_boundary": "The agent must verify historical provenance, value and terminal evidence. Quotes/hashes bind reviewed facts; they do not prove arbitrary code semantics. Never fabricate missing history."}


def capture_activity(source):
    """Native visibility of this disposable unit, not a whole-project shutdown."""
    if os.name == "nt":
        ps = t.system_directory() / "WindowsPowerShell/v1.0/powershell.exe"
        g.ancestors(ps.parent); g.plain(ps, False)
        modules = ps.parent / "Modules"
        paths = [modules / "Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1", modules / "CimCmdlets/CimCmdlets.psd1"]
        for p in paths:
            g.ancestors(p.parent); g.plain(p, False)
        utility, cim = [str(p).replace("'", "''") for p in paths]
        result = t._run([str(ps), "-NoProfile", "-NonInteractive", "-Command",
            "$ErrorActionPreference='Stop'; $PSModuleAutoLoadingPreference='None'; [Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            f"Import-Module -Name '{utility}' -ErrorAction Stop; Import-Module -Name '{cim}' -ErrorAction Stop; "
            "CimCmdlets\\Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | Microsoft.PowerShell.Utility\\Select-Object ProcessId,ParentProcessId,Name,CommandLine | Microsoft.PowerShell.Utility\\ConvertTo-Json -Compress"])
        if result.returncode or result.stderr.strip():
            raise g.GuardError("Activity unknown: native Windows process inventory failed")
        values = json.loads(result.stdout)
        if isinstance(values, dict): values = [values]
        processes = [{"pid": int(v["ProcessId"]), "ppid": int(v["ParentProcessId"]), "name": v["Name"], "args": v.get("CommandLine")} for v in values]
    elif sys.platform == "darwin":
        result = t._run(["/bin/ps", "-axo", "pid=,ppid=,args="])
        if result.returncode or result.stderr.strip():
            raise g.GuardError("Activity unknown: native macOS process inventory failed")
        processes = []
        for line in result.stdout.splitlines():
            fields = line.strip().split(None, 2)
            if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
                raise g.GuardError("Activity unknown: incomplete process inventory")
            processes.append({"pid": int(fields[0]), "ppid": int(fields[1]), "name": fields[2].split()[0], "args": fields[2]})
        opened = t._run(["/usr/sbin/lsof", "-nP", "+D", str(source), "-Fpcn"])
        if opened.returncode not in (0, 1) or opened.stderr.strip():
            raise g.GuardError("Activity unknown: lsof visibility/permissions incomplete")
        if opened.stdout.strip():
            raise g.GuardError("Active open files in exact task unit")
    else:
        raise g.GuardError("Native task-artifact execution currently supports Windows/macOS only")
    if not processes:
        raise g.GuardError("Activity unknown: empty native inventory")
    parents = {p["pid"]: p["ppid"] for p in processes}
    ignored, pid = set(), os.getpid()
    while pid and pid not in ignored:
        ignored.add(pid); pid = parents.get(pid, 0)
    needles = (str(source).replace("\\", "/").casefold(), source.parent.name.casefold())
    runtime = re.compile(r"(?:node|python|pythonw|ruby|java|dotnet|php|chrome|chromium|firefox|msedge|codex|claude|kimi|workbuddy|codebuddy|pwsh|powershell|cmd|bun|deno|bash|zsh|sh|wscript|cscript)(?:[0-9.]*)(?:\.exe)?$", re.I)
    records = []
    for p in processes:
        if p["pid"] in ignored: continue
        name = Path(str(p["name"]).replace("\\", "/")).name
        args = p["args"]
        if args is None or not str(args).strip():
            if runtime.fullmatch(name):
                if os.name == "nt" and t.confirmed_exited_windows(p["pid"]): continue
                raise g.GuardError("Activity unknown: inaccessible active runtime command line")
            continue
        normal = str(args).replace("\\", "/").casefold()
        if any(n in normal for n in needles):
            raise g.GuardError("Active process refers to this task unit; keep it running and retain these files")
        records.append({"pid": p["pid"], "ppid": p["ppid"], "name": name, "command_sha256": hashlib.sha256(str(args).encode()).hexdigest()})
    return {"status": "clear", "captured_at": g.utc(), "records": records, "records_sha256": t.digest(records),
        "visible_processes": len(processes), "scope": str(source), "limitations": CONCURRENCY}


def require_activity(source):
    value = capture_activity(source)
    if (not isinstance(value, dict) or value.get("status") != "clear" or value.get("visible_processes", 0) <= 0
            or not isinstance(value.get("records"), list) or value.get("records_sha256") != t.digest(value["records"])):
        raise g.GuardError("Activity unknown; a claimed idle boolean is insufficient")
    return value


def options(args):
    if not args.confirm_idle:
        raise g.GuardError("--confirm-idle is mandatory: this task's writers must remain stopped")
    if isinstance(args.idle_seconds, bool) or not isinstance(args.idle_seconds, (int, float)) or not math.isfinite(args.idle_seconds) or not 1 <= args.idle_seconds <= 60:
        raise g.GuardError("idle-seconds must be finite and 1..60")
    return {"max_files": t.integer(args.max_files, "max-files"), "max_bytes": t.integer(args.max_bytes, "max-bytes", 2**50), "idle_seconds": args.idle_seconds}


def refs(root, source, proof, excluded, budget):
    return t.references(root, source, proof["historical_reference_paths"], [*excluded, root / CLAIMS_DIR], budget,
                        safe_configs=proof["safe_reference_configs"])


def plan_command(args):
    limits = options(args); budget = t.Budget(limits["max_bytes"])
    root = g.project_root(args.project, args.codex_home)
    source, run_id = source_path(root, args.source)
    assessment = admin_path(args.assessment, root, args.codex_home)
    output = admin_path(args.output, root, args.codex_home, True)
    proof = assess(root, source, args.source, run_id, assessment, budget)
    first = snapshot(source, proof["family"], limits["max_files"], budget)
    completion_ns = proof["evidence"][proof["completion"]]["fingerprint"]["mtime_ns"]
    if any(v["fingerprint"]["mtime_ns"] > completion_ns for v in first["files"].values()):
        raise g.GuardError("Task payload changed after the terminal record; fresh lifecycle review is required")
    activities = [require_activity(source)]
    before = refs(root, source, proof, [assessment, output], budget)
    time.sleep(limits["idle_seconds"])
    t.same_snapshot(snapshot(source, proof["family"], limits["max_files"]), first)
    activities.append(require_activity(source))
    after = refs(root, source, proof, [assessment, output], budget)
    if not t.reference_same(before, after) or assess(root, source, args.source, run_id, assessment, budget) != proof:
        raise g.GuardError("Project references or retained evidence changed during planning")
    value = {"schema": POLICY, "tool_version": VERSION, "action": "delete-completed-agent-task-artifacts",
        "created_at": g.utc(), "project": str(root), "project_identity": g.root_identity(root), "codex_home": args.codex_home,
        "source": args.source, "source_volume": r.volume(source), "run_id": run_id, "family": proof["family"],
        "assessment_path": str(assessment), "proof": proof, "snapshot": first, "limits": limits,
        "reference_evidence": after, "activity_evidence": activities, "logical_bytes": sum(v["fingerprint"]["size"] for v in first["files"].values()),
        "planned_files": len(first["files"]), "minimum_age_hours": 0,
        "timely_basis": "Real run/source-bound terminal and writer-stop evidence, retained result/input, semantic value review and current checks; age is not disposal evidence.",
        "concurrency": CONCURRENCY}
    digest = r.atomic_json(output, value)
    print(json.dumps({"plan": str(output), "plan_sha256": digest, "planned_files": value["planned_files"], "logical_bytes": value["logical_bytes"]}))
    return value


def claim(root, source, plan, sha, receipt):
    folder = root / CLAIMS_DIR
    try: os.mkdir(folder, 0o700)
    except FileExistsError: g.ancestors(folder)
    path = folder / (t.digest({"project_identity": plan["project_identity"], "source": plan["source"]}) + ".json")
    if path.exists():
        raise g.GuardError("An apply claim already exists; reconcile the original plan/receipt, never blind retry")
    value = {"schema": POLICY, "source": plan["source"], "source_identity": g.root_identity(source), "plan_sha256": sha,
        "receipt": str(receipt), "started_at": g.utc(), "automatic_retry": False}
    return {"path": str(path), "sha256": r.atomic_json(path, value)}


def reserve_events(receipt):
    """Reserve durable logging before consuming the source's single apply claim."""
    stack = contextlib.ExitStack()
    event_root = Path(str(receipt) + ".in-progress")
    try:
        parent = stack.enter_context(r.anchor_directory(receipt.parent))
        if os.name == "nt":
            os.mkdir(event_root, 0o700)
        else:
            os.mkdir(event_root.name, 0o700, dir_fd=parent)
        created = g.root_identity(event_root)
        handle = stack.enter_context(r.anchor_directory(event_root))
        g.same_root(event_root, created)
        if os.name == "nt":
            events = g.new_file(event_root / "events.jsonl")
        else:
            fd = os.open("events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=handle)
            try:
                events = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
            except BaseException:
                os.close(fd)
                raise
        stack.callback(events.close)
        payload = {"at": g.utc(), "status": "event_log_initialized", "new_apply_claim_created": False}
        events.write(json.dumps({"event": payload, "sha256": t.digest(payload)}) + "\n")
        events.flush(); os.fsync(events.fileno())
        g.same_root(event_root, created)
        return stack, event_root, events
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        try: stack.close()
        except (OSError, ValueError): pass
        raise InitializationError(str(exc), new_apply_claim_created=False, receipt=str(receipt), event_directory=str(event_root)) from exc


def release(source, current, family, budget, checkpoint, value, held, root, root_id):
    value["status"] = "releasing"; checkpoint({"status": "release_started"})
    ordered = sorted(current["files"].items())
    for offset in range(0, len(ordered), 64):
        t.check_held(held); g.same_root(root, root_id)
        batch = ordered[offset:offset + 64]
        value["pending_batch"] = [rel for rel, _ in batch]
        checkpoint({"status": "batch_delete_pending", "members": [{"relative": rel, "fingerprint": rec["fingerprint"]} for rel, rec in batch]})
        for rel, rec in batch:
            value["current_file"] = rel; unit_member(rel, family)
            for prefix in ("", *["/".join(rel.split("/")[:i]) for i in range(1, len(rel.split("/")))]):
                path = source.joinpath(*prefix.split("/")) if prefix else source
                expected = current["directories"][prefix]["fingerprint"]
                g.same_root(path, {k: expected[k] for k in ("device", "inode")})
            t.file_hash(source.joinpath(*rel.split("/")), rec, budget, delete=True)
            value["deleted_files"] += 1; value["deleted_logical_bytes"] += rec["fingerprint"]["size"]
            value["items"].append({"relative": rel, "status": "deleted", "logical_bytes": rec["fingerprint"]["size"]})
            value["pending_batch"].remove(rel); value["current_file"] = None
            checkpoint({"status": "deleted", "relative": rel}, durable=False)
        checkpoint({"status": "batch_completed", "deleted_files": value["deleted_files"]})
    t.check_held(held)
    for rel in sorted(current["directories"], key=lambda s: s.count("/") + bool(s), reverse=True):
        p = source.joinpath(*rel.split("/")) if rel else source
        expected = current["directories"][rel]["fingerprint"]
        g.same_root(p, {k: expected[k] for k in ("device", "inode")}); g.ancestors(p)
        os.rmdir(p)  # New/unplanned members are never removed recursively.


def apply_command(args):
    if not args.confirm_idle:
        raise g.GuardError("--confirm-idle is mandatory on every platform")
    path = admin_path(args.plan, codex_home=getattr(args, "codex_home", None))
    plan, sha = g.read_json(path)
    if args.authorize_plan != sha or not re.fullmatch(r"[0-9a-f]{64}", args.authorize_plan or ""):
        raise g.GuardError("Exact plan SHA256 authorization missing/mismatched")
    if plan.get("schema") != POLICY or plan.get("tool_version") != VERSION or plan.get("action") != "delete-completed-agent-task-artifacts":
        raise g.GuardError("Unsupported task-artifact plan/action/version")
    root = g.project_root(plan["project"], plan.get("codex_home")); g.same_root(root, plan["project_identity"])
    source, run_id = source_path(root, plan["source"])
    admin_path(path, root, plan.get("codex_home"))
    receipt = admin_path(args.receipt, root, plan.get("codex_home"), True)
    limits = options(argparse.Namespace(**plan["limits"], confirm_idle=True)); budget = t.Budget(limits["max_bytes"])
    initialization, event_root, events = reserve_events(receipt)
    try:
        reservation = claim(root, source, plan, sha, receipt)
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        initialization.close()
        raise InitializationError(str(exc), new_apply_claim_created="not_established_or_existing_claim", receipt=str(receipt), event_directory=str(event_root)) from exc
    value = {"schema": POLICY, "tool_version": VERSION, "operation": plan["action"], "plan_sha256": sha,
        "started_at": g.utc(), "status": "validating", "deleted_files": 0, "deleted_logical_bytes": 0,
        "items": [], "pending_batch": [], "current_file": None, "apply_claim": reservation,
        "source_free_before_bytes": g.volume_free(source), "automatic_retry": False,
        "project_code_executed": False, "database_connected": False, "concurrency": CONCURRENCY}

    def checkpoint(event, durable=True):
        payload = {"at": g.utc(), **event}
        events.write(json.dumps({"event": payload, "sha256": t.digest(payload)}, ensure_ascii=False) + "\n")
        if durable: events.flush(); os.fsync(events.fileno())

    try:
        checkpoint({"status": "validating"})
        assessment = admin_path(plan["assessment_path"], root, plan.get("codex_home"))
        proof = assess(root, source, plan["source"], run_id, assessment, budget)
        if proof != plan["proof"] or plan["family"] != proof["family"] or plan["run_id"] != run_id:
            raise g.GuardError("Producer, completion, result or assessment changed")
        if r.volume(source) != plan["source_volume"]:
            raise g.GuardError("Source volume changed")
        current = snapshot(source, proof["family"], limits["max_files"], budget)
        t.same_snapshot(current, plan["snapshot"], hashes=True)
        if plan["logical_bytes"] != sum(v["fingerprint"]["size"] for v in current["files"].values()) or plan["planned_files"] != len(current["files"]):
            raise g.GuardError("Plan accounting does not match the exact task snapshot")
        require_activity(source)
        before = refs(root, source, proof, [assessment, path, receipt, event_root], budget)
        if not t.reference_same(before, plan["reference_evidence"]):
            raise g.GuardError("Project references/configuration changed")
        time.sleep(limits["idle_seconds"])
        t.same_snapshot(snapshot(source, proof["family"], limits["max_files"]), current)
        require_activity(source)
        if not t.reference_same(refs(root, source, proof, [assessment, path, receipt, event_root], budget), before):
            raise g.GuardError("Project references changed during final idle observation")
        if assess(root, source, plan["source"], run_id, assessment, budget) != proof:
            raise g.GuardError("Retained evidence changed immediately before deletion")
        held_bytes = proof["assessment_record"]["fingerprint"]["size"] + sum(v["fingerprint"]["size"] for v in proof["evidence"].values())
        if budget.used + plan["logical_bytes"] + 2 * held_bytes > budget.maximum:
            raise g.GuardError("Insufficient read budget for complete release checks")
        with t.retained_guards(root, assessment, proof, budget) as held:
            release(source, current, proof["family"], budget, checkpoint, value, held, root, plan["project_identity"])
        value["status"] = "completed"
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        value["status"] = "partial_or_uncertain" if value["status"] == "releasing" else "refused_before_delete"
        value["error"] = str(exc)
    finally:
        value.update(finished_at=g.utc(), payload_evidence_bytes_read=budget.used, source_free_after_bytes=g.volume_free(root))
        before, after = value["source_free_before_bytes"], value["source_free_after_bytes"]
        value["source_free_delta_bytes"] = after - before if before is not None and after is not None else None
        value["space_note"] = "Logical deletion and measured volume delta differ; concurrent writes, sharing/snapshots and allocation affect reclaim."
        value["recovery_note"] = "Never retry automatically. Reconcile this exact claim/receipt and durable pending batch after interruption."
        try:
            try: checkpoint({"status": value["status"], "deleted_files": value["deleted_files"]})
            finally: events.close()
            receipt_sha = r.atomic_json(receipt, value)
        finally:
            initialization.close()
    print(json.dumps({"receipt": str(receipt), "receipt_sha256": receipt_sha, "status": value["status"],
        "deleted_files": value["deleted_files"], "deleted_logical_bytes": value["deleted_logical_bytes"], "source_free_delta_bytes": value["source_free_delta_bytes"]}))
    if value["status"] != "completed":
        raise g.GuardError(value.get("error", "Incomplete task cleanup; inspect receipt"))
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    for name in ("project", "source", "assessment", "output"): p.add_argument("--" + name, required=True)
    p.add_argument("--codex-home"); p.add_argument("--confirm-idle", action="store_true")
    p.add_argument("--max-files", type=int, default=10000); p.add_argument("--max-bytes", type=int, default=1024**3)
    p.add_argument("--idle-seconds", type=float, default=1)
    p = sub.add_parser("apply")
    for name in ("plan", "authorize-plan", "receipt"): p.add_argument("--" + name, required=True)
    p.add_argument("--codex-home"); p.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args(argv)
    try: return plan_command(args) if args.command == "plan" else apply_command(args)
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc), "policy": POLICY, **getattr(exc, "details", {})}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    result = main(); sys.exit(result if isinstance(result, int) else 0)
