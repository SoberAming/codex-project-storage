#!/usr/bin/env python3
"""Exact retirement of positively reviewed synthetic, stopped PostgreSQL fixtures.

This is deliberately not a database cleaner. No database is connected, project
code run, process stopped, or broad recursive deletion performed. Semantic source
review remains the agent's job; real retained evidence, machine activity/reference
checks, complete membership, and byte/identity guards constrain that judgment.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid

def _load_guard(name, filename):
    path = Path(__file__).absolute().with_name(filename)
    for entry in (path, *path.parents):
        s = os.lstat(entry)
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Guard implementation cannot be loaded through links/reparse points")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


g = _load_guard("_retired_storage_guard", "storage_guard.py")
_previous_guard = sys.modules.get("storage_guard")
sys.modules["storage_guard"] = g
try:
    r = _load_guard("_retired_relocation_guard", "relocation_guard.py")
finally:
    if _previous_guard is None:
        del sys.modules["storage_guard"]
    else:
        sys.modules["storage_guard"] = _previous_guard

VERSION = "1.4.0"
POLICY = "retired-synthetic-pg-v1"
ASSESSMENT = "retired-synthetic-pg-assessment-v1"
SOURCE = re.compile(r"^\.runtime/([a-z][a-z0-9-]{0,63}-pg-([0-9a-f-]{36}))/data$")
CODE = {".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".ps1"}
TEXT = CODE | {".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".sql", ".ini", ".cfg", ".conf", ".env", ".html"}
CLAIMS_DIR = ".storage-retirement-claims"
PRIVATE_NAME = re.compile(r"(?:^|[._-])(?:auth|credentials?|secrets?|token|password|customers?|clients?|contacts?|business|exports?|backup|recovery)(?:[._-]|$)", re.I)
SAFE_CONFIG = re.compile(r"(?:package|tsconfig|jsconfig|project|runtime|test|pytest|settings|config)(?:[._-][a-z0-9_-]+)?\.(?:json|toml|yaml|yml|ini|cfg|conf)$", re.I)
ROOT_DIRS = {"base", "global", "pg_commit_ts", "pg_dynshmem", "pg_logical", "pg_multixact",
             "pg_notify", "pg_replslot", "pg_serial", "pg_snapshots", "pg_stat", "pg_stat_tmp",
             "pg_subtrans", "pg_tblspc", "pg_twophase", "pg_wal", "pg_xact"}
ROOT_FILES = {"PG_VERSION", "postgresql.conf", "postgresql.auto.conf", "pg_hba.conf", "pg_ident.conf", "postmaster.opts"}
RELATION = re.compile(r"[0-9]+(?:_(?:fsm|vm|init))?(?:\.[0-9]+)?$")
HEX = re.compile(r"[0-9A-Fa-f]+$")
WAL = re.compile(r"[0-9A-F]{24}(?:\.partial)?$")
PRODUCER_CLAIMS = {
    "fresh_initdb": ("initdb",), "unique_generated_directory": (".runtime", "randomUUID"),
    "loopback_only": ("127.0.0.1",), "stop_in_finally": ("finally", "pg_ctl", "stop"),
}
CONCURRENCY = ("Windows exclusive current-file/ancestor handles; project writers must remain stopped"
               if os.name == "nt" else "POSIX advisory flock and anchored descriptors; noncooperating writers can still race unlink")
MAX_EVIDENCE_FILES = 32


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class Budget:
    def __init__(self, maximum):
        self.maximum = integer(maximum, "max-bytes", 2**50)
        self.used = 0

    def add(self, count):
        self.used += count
        if self.used > self.maximum:
            raise g.GuardError("Content read budget exceeded; no automatic retry")


def integer(value, label, maximum=100000):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        raise g.GuardError(f"Invalid {label}")
    return value


def text(value, label):
    if not isinstance(value, str) or not 8 <= len(value.strip()) <= 16000:
        raise g.GuardError(f"Missing substantive {label}; booleans are not evidence")
    return value


def source_path(root, relative):
    match = SOURCE.fullmatch(relative or "")
    if not match:
        raise g.GuardError("Source must be exactly .runtime/<family>-pg-<UUID>/data; business .runtime/pgdata is never accepted")
    try:
        run_id = uuid.UUID(match[2])
        if run_id.version != 4 or str(run_id) != match[2]:
            raise ValueError()
    except ValueError:
        raise g.GuardError("Generated run identifier must be a canonical random UUIDv4")
    path = root.joinpath(*relative.split("/"))
    g.ancestors(path)
    return path, match[1], match[2]


def administrative_path(path, codex_home=None):
    """Reject known sensitive/state admin paths before any body reader runs."""
    path = g.absolute(path)
    protected = g.PRUNE | {"state", "index", "indexes", "indices"}
    if (any(part.lower() in protected for part in path.parts)
            or path.name.lower().startswith(".env") or PRIVATE_NAME.search(path.name)
            or re.search(r"\.(?:jsonl|sqlite3?|db)(?:-(?:wal|shm|journal))?$", path.name, re.I)):
        raise g.GuardError("Sensitive/state administrative input/output refused before reading")
    states = [Path.home() / ".codex"]
    states += [Path(value) for value in (os.environ.get("CODEX_HOME"), os.environ.get("CODEX_SQLITE_HOME"), codex_home) if value]

    def same(a, b):
        try:
            return os.path.samefile(a, b)
        except FileNotFoundError:
            return False

    for state in states:
        state = g.absolute(state)
        physical = g.absolute(os.path.realpath(state))  # identity/path metadata only
        for bound in (state, physical):
            if g.below(path, bound) or any(same(parent, bound) for parent in (path, *path.parents)):
                raise g.GuardError("Administrative input/output overlaps Codex state (including identity aliases); body not read")
    g.ancestors(path.parent)
    if path.exists():
        g.plain(path, False)
    return path


def outside(path, source, codex_home=None):
    path = administrative_path(path, codex_home)
    if g.below(path, source) or g.key(path) == g.key(source.parent):
        raise g.GuardError("Administrative files must remain outside the data unit")
    return path


def record(path, directory=False):
    s = g.plain(path, directory)
    if not s.st_ino or (not directory and s.st_nlink != 1):
        raise g.GuardError(f"Hardlink/unknown identity refused: {path}")
    return {"fingerprint": g.fingerprint(s), "metadata": r.metadata(path, directory)}


def file_hash(path, expected, budget, delete=False):
    # The SHA is a separate assertion; it is not part of filesystem metadata.
    meta = {k: v for k, v in expected.items() if k != "sha256"}
    with g.guarded_file(path, delete=delete) as (fd, unlink):
        if record(path) != meta or g.fingerprint(os.fstat(fd)) != meta["fingerprint"]:
            raise g.GuardError(f"File identity/metadata changed: {path}")
        h = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            budget.add(len(chunk)); h.update(chunk)
        if record(path) != meta or g.fingerprint(os.fstat(fd)) != meta["fingerprint"]:
            raise g.GuardError(f"File changed while reading: {path}")
        actual = h.hexdigest()
        if expected.get("sha256", actual) != actual:
            raise g.GuardError(f"Content changed: {path}")
        if delete:
            unlink()
        return actual


def check_held(entries, budget=None):
    for path, fd, expected in entries:
        meta = {k: v for k, v in expected.items() if k != "sha256"}
        if record(path) != meta or g.fingerprint(os.fstat(fd)) != meta["fingerprint"]:
            raise g.GuardError("Retained evidence identity/metadata changed during release")
        if budget is not None:
            os.lseek(fd, 0, os.SEEK_SET); h = hashlib.sha256()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                budget.add(len(chunk)); h.update(chunk)
            if h.hexdigest() != expected["sha256"]:
                raise g.GuardError("Retained evidence content changed during release")
            if record(path) != meta or g.fingerprint(os.fstat(fd)) != meta["fingerprint"]:
                raise g.GuardError("Retained evidence changed during final fd verification")


@contextlib.contextmanager
def retained_guards(root, assessment_path, proof, budget):
    if len(proof["evidence"]) > MAX_EVIDENCE_FILES:
        raise g.GuardError("Too many explicit retained evidence files for bounded release guards")
    paths = {str(root.joinpath(*rel.split("/"))): rec for rel, rec in proof["evidence"].items()}
    paths[str(assessment_path)] = {**proof["assessment_record"], "sha256": proof["assessment_sha256"]}
    with contextlib.ExitStack() as stack:
        entries = []
        for path, expected in sorted(paths.items()):
            p = Path(path)
            fd, _ = stack.enter_context(g.guarded_file(p))
            entries.append((p, fd, expected))
        check_held(entries, budget)
        yield entries
        check_held(entries, budget)


def layout(relative, directory=False):
    """A narrow ordinary initdb layout, not a claim about database contents."""
    if not relative:
        return directory
    parts = relative.split("/")
    first = parts[0]
    if len(parts) == 1:
        return first in (ROOT_DIRS if directory else ROOT_FILES)
    if first == "base":
        if len(parts) == 2 and directory:
            return parts[1].isdigit()
        return (not directory and len(parts) == 3 and parts[1].isdigit()
                and (parts[2] in {"PG_VERSION", "pg_filenode.map", "pg_internal.init"} or bool(RELATION.fullmatch(parts[2]))))
    if first == "global":
        return not directory and len(parts) == 2 and (parts[1] in {"pg_control", "pg_filenode.map", "pg_internal.init"} or bool(RELATION.fullmatch(parts[1])))
    if first == "pg_wal":
        if directory:
            return len(parts) == 2 and parts[1] in {"archive_status", "summaries"}
        if len(parts) == 2:
            return bool(WAL.fullmatch(parts[1]))
        if len(parts) == 3 and parts[1] == "archive_status":
            return bool(re.fullmatch(r"[0-9A-F]{24}\.(?:ready|done)", parts[2]))
        return len(parts) == 3 and parts[1] == "summaries" and bool(re.fullmatch(r"[0-9A-F]{16}-[0-9A-F]{16}-[0-9A-F]{8}\.summary", parts[2]))
    if first == "pg_multixact":
        if len(parts) == 2:
            return directory and parts[1] in {"offsets", "members"}
        return not directory and len(parts) == 3 and parts[1] in {"offsets", "members"} and bool(HEX.fullmatch(parts[2]))
    if first == "pg_logical":
        if len(parts) == 2:
            return (directory and parts[1] in {"mappings", "snapshots"}) or (not directory and parts[1] == "replorigin_checkpoint")
        return (not directory and len(parts) == 3 and parts[1] in {"mappings", "snapshots"}
                and bool(re.fullmatch(r"[0-9A-Fa-f]+(?:[-_][0-9A-Fa-f]+)*(?:\.[0-9A-Fa-f]+)?", parts[2])))
    if first in {"pg_commit_ts", "pg_notify", "pg_serial", "pg_subtrans", "pg_xact"}:
        return not directory and len(parts) == 2 and bool(HEX.fullmatch(parts[1]))
    if first in {"pg_stat", "pg_stat_tmp"}:
        return not directory and len(parts) == 2 and bool(re.fullmatch(r"(?:pgstat|global|db_[0-9]+)\.stat", parts[1]))
    # Replication slots, tablespaces, prepared transactions and unknown members
    # require a separate review, rather than silently broadening this policy.
    return False


def snapshot(source, max_files, budget=None, min_age=48.0):
    directories, files, stack = {}, {}, [(source, "")]
    while stack:
        folder, rel = stack.pop()
        if not layout(rel, True):
            raise g.GuardError(f"Unknown/mixed PG directory retained: {rel}")
        directories[rel] = record(folder, True)
        with os.scandir(folder) as entries:
            for entry in entries:
                sub = (rel + "/" if rel else "") + entry.name
                p = Path(entry.path); s = g.plain(p)
                if stat.S_ISDIR(s.st_mode):
                    stack.append((p, sub))
                elif stat.S_ISREG(s.st_mode):
                    if not layout(sub):
                        raise g.GuardError(f"Unknown/credential/recovery/mixed member retained: {sub}")
                    if time.time_ns() - s.st_mtime_ns < min_age * 3600 * 10**9:
                        raise g.GuardError(f"Runtime member is too recent (minimum {min_age} hours): {sub}")
                    rec = record(p)
                    if budget is not None:
                        rec["sha256"] = file_hash(p, rec, budget)
                    files[sub] = rec
                else:
                    raise g.GuardError(f"Special member refused: {sub}")
                if len(files) + len(stack) + len(directories) > max_files * 4 or len(files) > max_files:
                    raise g.GuardError("Runtime membership limit exceeded")
    for required in ("PG_VERSION", "global/pg_control"):
        if required not in files:
            raise g.GuardError(f"Not an independently initialized PG data unit; missing {required}")
    return {"directories": directories, "files": files}


def same_snapshot(current, expected, hashes=False):
    if set(current["files"]) != set(expected["files"]) or current["directories"] != expected["directories"]:
        raise g.GuardError("Complete runtime membership/directory identity changed")
    for rel, item in current["files"].items():
        old = expected["files"][rel]
        if not hashes:
            old = {k: v for k, v in old.items() if k != "sha256"}
        if item != old:
            raise g.GuardError(f"Runtime file changed since plan: {rel}")


def bounded_text(path, budget, limit=4 * 1024 * 1024):
    rec = record(path)
    if not 0 < rec["fingerprint"]["size"] <= limit:
        raise g.GuardError(f"Evidence/config text is empty or exceeds bound: {path}")
    with g.guarded_file(path) as (fd, _):
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            budget.add(len(chunk)); total += len(chunk); chunks.append(chunk)
            if total > limit:
                raise g.GuardError(f"Evidence/config grew beyond its text bound: {path}")
        raw = b"".join(chunks)
        if len(raw) != rec["fingerprint"]["size"] or record(path) != rec or g.fingerprint(os.fstat(fd)) != rec["fingerprint"]:
            raise g.GuardError(f"Evidence/config changed: {path}")
    try:
        body = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise g.GuardError(f"Evidence must be bounded UTF-8 text: {path}")
    rec["sha256"] = hashlib.sha256(raw).hexdigest()
    return body, rec


def quote(body, value, label, tokens=()):
    value = text(value, label)
    if value not in body or any(token.lower() not in value.lower() for token in tokens):
        raise g.GuardError(f"Missing real quoted {label}; a boolean/summary is insufficient")


def private_path(relative):
    parts = relative.split("/")
    return (r.credential(relative) or any(p.lower() in g.PROTECTED or p.lower().startswith(".env")
            or PRIVATE_NAME.search(p) for p in parts))


def assess(root, source, relative, assessment_path, budget):
    value, assessment_sha = g.read_json(assessment_path)
    if not isinstance(value, dict) or value.get("schema") != ASSESSMENT or value.get("source") != relative:
        raise g.GuardError("Missing exact-source retired-synthetic-pg assessment schema")
    review = value.get("review", {})
    for field in ("reviewer", "synthetic_data_reason", "rebuild_recipe", "unique_value_review", "reference_scope_reason"):
        text(review.get(field), "agent semantic review: " + field)
    if value.get("data_class") != "synthetic-rebuildable-only":
        raise g.GuardError("Only positively reviewed synthetic-rebuildable-only data can be retired")
    evidence, bodies = {}, {}

    def evidence_file(spec, label):
        if not isinstance(spec, dict):
            raise g.GuardError(f"Missing retained {label} evidence record")
        relative_e = r.relative(spec.get("path"))
        p = g.relative_file(root, relative_e)
        if g.below(p, source) or private_path(relative_e):
            raise g.GuardError(f"{label} evidence must be retained outside data/state/credentials")
        body, rec = bounded_text(p, budget)
        if not re.fullmatch(r"[0-9a-f]{64}", spec.get("sha256", "")) or spec["sha256"] != rec["sha256"]:
            raise g.GuardError(f"Retained {label} evidence hash missing/changed: {relative_e}")
        evidence[relative_e] = rec; bodies[relative_e] = body
        if len(evidence) > MAX_EVIDENCE_FILES:
            raise g.GuardError("Explicit retained evidence exceeds the 32-file guard limit")
        return relative_e, p, body

    producer = value.get("producer")
    producer_rel, producer_path, producer_body = evidence_file(producer, "producer")
    if producer_path.suffix.lower() not in CODE:
        raise g.GuardError("Producer must be real retained executable source, not a newly written declaration")
    claims = producer.get("claims", {})
    for name, tokens in PRODUCER_CLAIMS.items():
        quote(producer_body, claims.get(name), "producer " + name, tokens)
    family_prefix = SOURCE.fullmatch(relative)[1][:-37]
    if family_prefix not in claims["unique_generated_directory"]:
        raise g.GuardError("Producer quote does not bind this generated family prefix")

    inputs = value.get("inputs")
    if not isinstance(inputs, list) or not 1 <= len(inputs) <= 32:
        raise g.GuardError("Missing real retained synthetic generator/input evidence")
    input_links = []
    for item in inputs:
        rel_i, p_i, body_i = evidence_file(item, "synthetic input")
        if rel_i == producer_rel or any(rel_i == item_i[0] for item_i in input_links):
            raise g.GuardError("Synthetic input evidence must be distinct from the producer and other inputs")
        if item.get("kind") not in {"synthetic-generator", "synthetic-fixture"}:
            raise g.GuardError("Inputs must be explicitly reviewed synthetic generators/fixtures")
        quote(body_i, item.get("synthetic_quote"), "synthetic input content")
        text(item.get("reason"), "synthetic input reasoning")
        input_links.append((rel_i, item.get("referenced_by")))
    for rel_i, via in input_links:
        if via not in bodies or (rel_i not in bodies[via] and Path(rel_i).name not in bodies[via]):
            raise g.GuardError(f"Input has no actual retained producer/input reference: {rel_i}")
    # Require every input chain to reach the producer, not an unrelated cycle.
    links = dict(input_links)
    for rel_i in links:
        seen, current = set(), rel_i
        while current != producer_rel:
            if current in seen or current not in links:
                raise g.GuardError(f"Synthetic input chain does not reach producer: {rel_i}")
            seen.add(current); current = links[current]

    completion = value.get("completion")
    completion_rel, completion_path, completion_body = evidence_file(completion, "completion")
    if completion_rel == producer_rel or completion_rel in dict(input_links):
        raise g.GuardError("Historical completion must be independent from retained source/input evidence")
    run_id = SOURCE.fullmatch(relative)[2]
    if not g.below(completion_path, source.parent) and run_id not in completion_body:
        raise g.GuardError("Completion evidence is not bound to this exact historical run UUID")
    quote(completion_body, completion.get("stop_quote"), "completed shutdown")
    if not re.search(r"(?:stopped|shut\s*down|shutdown complete)", completion["stop_quote"], re.I):
        raise g.GuardError("Completion evidence lacks actual stopped/shutdown text")
    quote(completion_body, completion.get("terminal_quote"), "terminal run result")
    if not re.search(r"(?:passed|failed|finished|completed|stopped|shut\s*down)", completion["terminal_quote"], re.I):
        try:
            terminal = json.loads(completion["terminal_quote"])
        except (ValueError, TypeError):
            terminal = None
        if not isinstance(terminal, dict) or len(terminal) < 2:
            raise g.GuardError("Completion evidence lacks a terminal result/real test JSON; passed=true is not mandatory")
    historical_paths = [completion_rel]
    for item in value.get("historical_references", []):
        rel_h, _, body = evidence_file(item, "retained historical reference")
        quote(body, item.get("quote"), "historical-only reference")
        text(item.get("reason"), "historical-only reference reasoning")
        historical_paths.append(rel_h)
    safe_configs = []
    for item in value.get("reference_files", []):
        if (not isinstance(item, dict) or not isinstance(item.get("path"), str)
                or not SAFE_CONFIG.fullmatch(Path(item["path"]).name)
                or private_path(item["path"])):
            raise g.GuardError("Reference config must be an explicitly reviewed, non-sensitive project config; no credentials/customer documents")
        rel_c, _, _ = evidence_file(item, "safe reference config")
        text(item.get("reason"), "safe config scope and privacy review")
        safe_configs.append(rel_c)
    version, _ = bounded_text(source / "PG_VERSION", budget, 16)
    if not re.fullmatch(r"(?:1[3-9]|[2-9][0-9])\s*", version):
        raise g.GuardError("Only ordinary PostgreSQL 13+ initdb layouts are supported")
    for name in ("postgresql.conf", "postgresql.auto.conf", "pg_hba.conf", "pg_ident.conf", "postmaster.opts"):
        p = source / name
        if p.exists():
            body, _ = bounded_text(p, budget)
            active = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
            if re.search(r"(?:password|secret|token|primary_conninfo|restore_command|archive_command|recovery_target)\s*[=\s]", active, re.I):
                raise g.GuardError(f"Credential/recovery/external archive configuration retained: {name}")
    return {"assessment_sha256": assessment_sha, "assessment_record": record(assessment_path), "evidence": evidence, "review": review,
            "producer": producer_rel, "completion": completion_rel, "safe_reference_configs": sorted(safe_configs),
            "historical_reference_paths": sorted(set(historical_paths)),
            "semantic_boundary": "Agent reviewed source/data meaning; file hashes do not independently prove synthetic provenance"}


def system_directory():
    """Authoritative Windows API, never an executable path from environment."""
    if os.name != "nt":
        raise g.GuardError("Windows system directory requested on another platform")
    g.K32.GetSystemDirectoryW.argtypes = [g.wt.LPWSTR, g.wt.UINT]
    g.K32.GetSystemDirectoryW.restype = g.wt.UINT
    buffer = g.ctypes.create_unicode_buffer(32768)
    count = g.K32.GetSystemDirectoryW(buffer, len(buffer))
    if not count or count >= len(buffer):
        raise g.GuardError("Activity coverage unknown: cannot identify trusted Windows system directory")
    path = Path(buffer.value); g.ancestors(path)
    return path


def child_context():
    if os.name == "nt":
        system = system_directory()
        modules = system / "WindowsPowerShell/v1.0/Modules"
        g.ancestors(modules)
        # Explicit allowlist: PSModulePath, analysis-cache, policy, profiler,
        # CLR/DLL injection and startup variables from the caller do not survive.
        environment = {"SystemRoot": str(system.parent), "WINDIR": str(system.parent),
                       "PATH": str(system), "PSModulePath": str(modules)}
        return environment, str(system)
    return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C", "HOME": "/var/empty"}, "/"


def _run(command):
    environment, cwd = child_context()
    kwargs = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "strict", "timeout": 30,
              "env": environment, "cwd": cwd}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        return subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise g.GuardError(f"Activity coverage unknown ({type(exc).__name__}); no release allowed")


def confirmed_exited_windows(pid):
    """CIM can retain a just-exited row; ignore only an OS-confirmed exit."""
    g.K32.OpenProcess.argtypes = [g.wt.DWORD, g.wt.BOOL, g.wt.DWORD]
    g.K32.OpenProcess.restype = g.wt.HANDLE
    g.K32.WaitForSingleObject.argtypes = [g.wt.HANDLE, g.wt.DWORD]
    g.K32.WaitForSingleObject.restype = g.wt.DWORD
    g.ctypes.set_last_error(0)
    handle = g.K32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE; no write/terminate rights
    if not handle:
        return g.ctypes.get_last_error() in (87, 1168)  # no such process; access-denied stays unknown
    try:
        return g.K32.WaitForSingleObject(handle, 0) == 0  # signaled == exited, timeout == still active
    finally:
        g.K32.CloseHandle(handle)


def capture_activity(root, source):
    """Capture live OS facts; there is no CLI override accepting an idle JSON."""
    if os.name == "nt":
        system = system_directory()
        powershell = system / "WindowsPowerShell/v1.0/powershell.exe"
        g.ancestors(powershell.parent); g.plain(powershell, False)
        modules = powershell.parent / "Modules"
        cim = modules / "CimCmdlets/CimCmdlets.psd1"
        utility = modules / "Microsoft.PowerShell.Utility/Microsoft.PowerShell.Utility.psd1"
        for path in (cim, utility):
            g.ancestors(path.parent); g.plain(path, False)
        ps_cim, ps_utility = (str(p).replace("'", "''") for p in (cim, utility))
        result = _run([str(powershell), "-NoProfile", "-NonInteractive", "-Command",
                       "$ErrorActionPreference='Stop'; $PSModuleAutoLoadingPreference='None'; "
                       "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
                       f"Import-Module -Name '{ps_utility}' -ErrorAction Stop; Import-Module -Name '{ps_cim}' -ErrorAction Stop; "
                       "CimCmdlets\\Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | "
                       "Microsoft.PowerShell.Utility\\Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
                       "Microsoft.PowerShell.Utility\\ConvertTo-Json -Compress"])
        if result.returncode or result.stderr.strip():
            raise g.GuardError("Activity coverage unknown: Windows process inventory failed")
        try:
            values = json.loads(result.stdout)
            if isinstance(values, dict):
                values = [values]
            processes = [{"pid": int(v["ProcessId"]), "ppid": int(v["ParentProcessId"]),
                          "name": v["Name"], "args": v.get("CommandLine")} for v in values]
        except (ValueError, TypeError, KeyError):
            raise g.GuardError("Activity coverage unknown: invalid Windows process inventory")
        method = "Windows CIM process command lines + exclusive current-file handles"
    elif sys.platform == "darwin":
        result = _run(["/bin/ps", "-axo", "pid=,ppid=,args="])
        if result.returncode or result.stderr.strip():
            raise g.GuardError("Activity coverage unknown: macOS process inventory failed")
        processes = []
        for line in result.stdout.splitlines():
            fields = line.strip().split(None, 2)
            if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
                raise g.GuardError("Activity coverage unknown: incomplete macOS process inventory")
            processes.append({"pid": int(fields[0]), "ppid": int(fields[1]), "name": fields[2].split()[0], "args": fields[2]})
        opened = _run(["/usr/sbin/lsof", "-nP", "+D", str(source), "-Fpcn"])
        if opened.returncode not in (0, 1) or opened.stderr.strip():
            raise g.GuardError("Activity coverage unknown: macOS lsof visibility/permissions incomplete")
        if opened.stdout.strip():
            raise g.GuardError("Active open files found in the exact runtime unit")
        method = "macOS visible ps/lsof + advisory locks; other-user/noncooperating writes are not excluded"
    else:
        raise g.GuardError("Activity coverage unknown: runtime retirement currently supports Windows/macOS only")
    if not processes:
        raise g.GuardError("Activity coverage unknown: empty process inventory")
    parent = {v["pid"]: v["ppid"] for v in processes}
    ignored, current = set(), os.getpid()
    while current and current not in ignored:
        ignored.add(current); current = parent.get(current, 0)
    raw_evidence = []
    needles = {str(root).replace("\\", "/").casefold(), str(source).replace("\\", "/").casefold(), source.parent.name.casefold()}
    runtimes = re.compile(r"(?:postgres|pg_ctl|node|python|ruby|java|dotnet|php)(?:[0-9.]*)(?:\.exe)?$", re.I)
    for process in processes:
        if process["pid"] in ignored:
            continue
        name = Path(str(process["name"]).replace("\\", "/")).name
        args = process["args"]
        if args is None or not str(args).strip():
            if runtimes.fullmatch(name):
                if os.name == "nt" and confirmed_exited_windows(process["pid"]):
                    raw_evidence.append({"pid": process["pid"], "ppid": process["ppid"], "name": name,
                                         "status": "confirmed_exited_during_CIM_inventory"})
                    continue
                raise g.GuardError(f"Activity coverage unknown: inaccessible active runtime command line (pid {process['pid']}, {name})")
            continue
        normalized = str(args).replace("\\", "/").casefold()
        if any(needle in normalized for needle in needles):
            raise g.GuardError(f"Active project/runtime process found (pid {process['pid']}, {name}); stop it separately")
        if re.fullmatch(r"(?:postgres|pg_ctl)(?:\.exe)?", name, re.I):
            # PG children may omit -D; an unrelated server is not safely attributable.
            raise g.GuardError("PostgreSQL runtime present; exact writer attribution is incomplete. Keep unrelated projects running; this retirement remains refused without separate attribution")
        raw_evidence.append({"pid": process["pid"], "ppid": process["ppid"], "name": name,
                             "command_sha256": hashlib.sha256(str(args).encode()).hexdigest()})
    if (source / "postmaster.pid").exists():
        raise g.GuardError("postmaster.pid exists; live/unresolved database retained")
    return {"status": "clear", "captured_at": g.utc(), "method": method, "visible_processes": len(processes),
            "records": raw_evidence, "records_sha256": digest(raw_evidence), "limitations": CONCURRENCY}


def require_activity(root, source):
    value = capture_activity(root, source)
    if (not isinstance(value, dict) or value.get("status") != "clear"
            or not isinstance(value.get("records"), list) or value.get("visible_processes", 0) <= 0
            or value.get("records_sha256") != digest(value["records"])):
        raise g.GuardError("Activity coverage unknown; an idle boolean/declaration is insufficient")
    return value


def references(root, source, evidence_paths, excluded, budget, max_files=100000, max_bytes=128 * 1024 * 1024, safe_configs=()):
    """Code-only body inspection; credentials and user documents are metadata-only.

    Safe configs are exact, hash-bound, agent-reviewed assessment inputs. No
    user-authored idle/reference JSON can replace this current source inspection.
    """
    result, metadata_only, skipped, stack, visited, read = {}, {}, {}, [root], 0, 0
    allowed = {g.key(root.joinpath(*rel.split("/"))) for rel in evidence_paths}
    excluded_keys = {g.key(p) for p in excluded}
    needles = (str(source).replace("\\", "/").casefold(),
               str(source.relative_to(root)).replace("\\", "/").casefold(), source.parent.name.casefold())
    while stack:
        folder = stack.pop()
        with os.scandir(folder) as entries:
            for entry in entries:
                p = Path(entry.path)
                if g.key(p) in excluded_keys:
                    continue
                rel = p.relative_to(root).as_posix()
                if (entry.name.lower() in g.PROTECTED or (folder == root and entry.name in {".runtime", CLAIMS_DIR})
                        or private_path(rel)):
                    # Inspect only the entry itself; never follow or read it.
                    s = os.lstat(p)
                    skipped[rel] = {"identity": {"device": s.st_dev, "inode": s.st_ino},
                                    "reason": "protected/generated/credential/business scope; body not read"}
                    continue
                s = g.plain(p)
                visited += 1
                if visited > max_files:
                    raise g.GuardError("Reference inspection incomplete: file/entry budget exceeded")
                if stat.S_ISDIR(s.st_mode):
                    stack.append(p)
                elif stat.S_ISREG(s.st_mode):
                    if p.suffix.lower() not in CODE and rel not in safe_configs:
                        metadata_only[rel] = g.fingerprint(s)
                        continue
                    if s.st_size == 0:
                        result[p.relative_to(root).as_posix()] = {"empty": True, "fingerprint": g.fingerprint(s)}
                        continue
                    if s.st_size > 4 * 1024 * 1024 or read + s.st_size > max_bytes:
                        raise g.GuardError(f"Reference inspection incomplete: bounded text exceeded ({p.relative_to(root)})")
                    body, rec = bounded_text(p, budget); read += s.st_size
                    hit = any(needle in body.replace("\\\\", "/").replace("\\", "/").casefold() for needle in needles)
                    if hit and g.key(p) not in allowed:
                        raise g.GuardError(f"Unresolved exact runtime reference retained: {p.relative_to(root)}")
                    result[rel] = {"record": rec, "historical_evidence_reference": hit}
                else:
                    raise g.GuardError("Reference coverage unknown: special filesystem entry")
    return {"files": result, "files_sha256": digest(result), "metadata_only": metadata_only,
            "skipped_scopes": skipped, "bytes_read": read, "entries_inspected": visited,
            "coverage": "ordinary non-sensitive project code and exact declared safe configs only; .env/auth/credentials/customer documents are never read; generated runtime, state, assets, dependencies excluded. Agent must review the stated binding gaps; this is not a whole-project body search"}


def reference_same(a, b):
    # Safe source/config bodies and non-private file metadata form the watched
    # scope. Skipped scopes are disclosed, not falsely asserted fully audited.
    return a["files"] == b["files"] and a["metadata_only"] == b["metadata_only"]


def claim_apply(root, source, plan, plan_sha, receipt):
    folder = root / CLAIMS_DIR
    try:
        os.mkdir(folder, 0o700)
    except FileExistsError:
        g.ancestors(folder)
    key = digest({"project_identity": g.root_identity(root), "source": plan["source"]})
    path = folder / (key + ".json")
    if path.exists():
        previous, _ = g.read_json(path)
        if (previous.get("schema") != POLICY or previous.get("source") != plan["source"]
                or previous.get("project_identity") != g.root_identity(root)):
            raise g.GuardError("Unknown/changed source apply claim; manual reconciliation required")
        raise g.GuardError("An apply claim already exists for this exact source; changing receipt/plan does not authorize retry. Reconcile the original claimed plan and receipt")
    value = {"schema": POLICY, "tool_version": VERSION, "project_identity": g.root_identity(root),
             "source": plan["source"], "source_identity": g.root_identity(source), "plan_sha256": plan_sha,
             "snapshot_sha256": digest(plan["snapshot"]), "receipt": str(receipt),
             "started_at": g.utc(), "note": "Single attempt reservation; never auto-remove or retry after failed/uncertain execution"}
    sha = r.atomic_json(path, value)
    check, check_sha = g.read_json(path)
    if check != value or check_sha != sha:
        raise g.GuardError("Source apply claim verification failed; no release allowed")
    return {"path": str(path), "sha256": sha}


def options(args):
    maximum = integer(args.max_files, "max-files")
    if not 48 <= args.min_age_hours <= 36500 or not 1 <= args.idle_seconds <= 60:
        raise g.GuardError("Minimum age must be >=48 hours; idle interval must be 1..60 seconds")
    if not args.confirm_idle:
        raise g.GuardError("--confirm-idle is required: all project writers must remain stopped throughout this operation")
    return {"max_files": maximum, "max_bytes": integer(args.max_bytes, "max-bytes", 2**50),
            "min_age_hours": args.min_age_hours, "idle_seconds": args.idle_seconds}


def plan_command(args):
    limits = options(args); budget = Budget(limits["max_bytes"])
    root = g.project_root(args.project, args.codex_home)
    source, family, run_id = source_path(root, args.source)
    output, assessment_path = g.safe_output(outside(args.output, source, args.codex_home)), outside(args.assessment, source, args.codex_home)
    proof = assess(root, source, args.source, assessment_path, budget)
    first = snapshot(source, limits["max_files"], budget, limits["min_age_hours"])
    activity_before = require_activity(root, source)
    excluded = [output, assessment_path]
    ref_before = references(root, source, proof["historical_reference_paths"], excluded, budget, safe_configs=proof["safe_reference_configs"])
    time.sleep(limits["idle_seconds"])
    same_snapshot(snapshot(source, limits["max_files"], min_age=limits["min_age_hours"]), first)
    activity_after = require_activity(root, source)
    ref_after = references(root, source, proof["historical_reference_paths"], excluded, budget, safe_configs=proof["safe_reference_configs"])
    if not reference_same(ref_before, ref_after):
        raise g.GuardError("Reference/config inputs changed during idle observation")
    if assess(root, source, args.source, assessment_path, budget) != proof:
        raise g.GuardError("Retained evidence changed during planning")
    allocated = [g.allocated(source.joinpath(*rel.split("/")), g.plain(source.joinpath(*rel.split("/")), False)) for rel in first["files"]]
    value = {"schema": POLICY, "tool_version": VERSION, "action": "delete-retired-synthetic-pg-data",
             "project": str(root), "project_identity": g.root_identity(root), "codex_home": args.codex_home,
             "source": args.source, "family": family, "run_id": run_id,
             "assessment_path": str(assessment_path), "proof": proof, "snapshot": first, "limits": limits,
             "reference_evidence": ref_after, "activity_evidence": [activity_before, activity_after],
             "logical_bytes": sum(rec["fingerprint"]["size"] for rec in first["files"].values()),
             "allocated_bytes": sum(allocated) if all(x is not None for x in allocated) else None,
             "planned_files": len(first["files"]), "payload_evidence_bytes_read": budget.used,
             "created_at": g.utc(), "concurrency": CONCURRENCY,
             "preserved": "producer, all synthetic inputs, completion/reference evidence, siblings including logs/results; no DB backup required for proven disposable synthetic data"}
    sha = r.atomic_json(output, value)
    print(json.dumps({"plan": str(output), "plan_sha256": sha, "planned_files": value["planned_files"],
                      "logical_bytes": value["logical_bytes"], "allocated_bytes": value["allocated_bytes"]}))
    return value


def release_files(source, current, budget, checkpoint, value, held):
    # O(N) full scans at stage boundaries; O(1) identity/hash guard per file.
    # This is a cooperative idle contract, not a filesystem-wide freeze.
    checkpoint({"status": "release_started", "planned_files": len(current["files"])})
    value["status"] = "releasing"
    ordered = sorted(current["files"].items())
    for start in range(0, len(ordered), 64):
        check_held(held)
        batch = ordered[start:start + 64]
        value["pending_batch"] = [rel for rel, _ in batch]
        # Durable write-ahead membership before any item in this batch is touched.
        checkpoint({"status": "batch_delete_pending", "members": [
            {"relative": rel, "fingerprint": rec["fingerprint"]} for rel, rec in batch]})
        for rel, rec in batch:
            value["current_file"] = rel
            p = source.joinpath(*rel.split("/"))
            for parent_rel in ("", *["/".join(rel.split("/")[:i]) for i in range(1, len(rel.split("/")))]):
                parent_path = source.joinpath(*parent_rel.split("/")) if parent_rel else source
                if g.root_identity(parent_path) != {k: v for k, v in current["directories"][parent_rel]["fingerprint"].items() if k in {"device", "inode"}}:
                    raise g.GuardError("Ancestor directory identity changed during release")
            file_hash(p, rec, budget, delete=True)
            value["deleted_files"] += 1; value["deleted_logical_bytes"] += rec["fingerprint"]["size"]
            value["items"].append({"relative": rel, "status": "deleted", "logical_bytes": rec["fingerprint"]["size"]})
            value["pending_batch"].remove(rel); value["current_file"] = None
            checkpoint({"status": "deleted", "relative": rel}, durable=False)
        checkpoint({"status": "batch_completed", "deleted_files": value["deleted_files"]})
    check_held(held)
    # Unknown new members are never swept up. Empty directory removal only.
    for rel in sorted(current["directories"], key=lambda s: s.count("/") + bool(s), reverse=True):
        p = source.joinpath(*rel.split("/")) if rel else source
        expected = current["directories"][rel]["fingerprint"]
        if g.root_identity(p) != {k: expected[k] for k in ("device", "inode")}:
            raise g.GuardError("Directory changed before empty-directory removal")
        g.ancestors(p); os.rmdir(p)


def apply_command(args):
    if not args.confirm_idle:
        raise g.GuardError("--confirm-idle is mandatory even on Windows")
    plan_path = administrative_path(args.plan, getattr(args, "codex_home", None)); plan, sha = g.read_json(plan_path)
    if args.authorize_plan != sha or not re.fullmatch(r"[0-9a-f]{64}", args.authorize_plan or ""):
        raise g.GuardError("Exact plan SHA256 authorization missing/mismatched")
    if plan.get("schema") != POLICY or plan.get("tool_version") != VERSION or plan.get("action") != "delete-retired-synthetic-pg-data":
        raise g.GuardError("Unsupported retirement plan/action/version")
    root = g.project_root(plan["project"], plan.get("codex_home")); g.same_root(root, plan["project_identity"])
    source, _, _ = source_path(root, plan["source"])
    administrative_path(plan_path, plan.get("codex_home"))
    receipt = g.safe_output(outside(args.receipt, source, plan.get("codex_home")))
    claim = claim_apply(root, source, plan, sha, receipt)
    reservation = Path(str(receipt) + ".in-progress")
    g.ancestors(reservation.parent); os.mkdir(reservation, 0o700)
    events = g.new_file(reservation / "events.jsonl")
    value = {"schema": POLICY, "tool_version": VERSION, "operation": plan["action"], "plan_sha256": sha,
             "started_at": g.utc(), "status": "validating", "deleted_files": 0, "deleted_logical_bytes": 0,
             "items": [], "source_free_before_bytes": g.volume_free(source), "concurrency": CONCURRENCY,
             "apply_claim": claim,
             "automatic_retry": False, "database_connected": False, "project_code_executed": False}
    budget = Budget(plan["limits"]["max_bytes"])

    def checkpoint(event, durable=True):
        payload = {"at": g.utc(), **event}
        events.write(json.dumps({"event": payload, "sha256": digest(payload)}, ensure_ascii=False) + "\n")
        if durable:
            events.flush(); os.fsync(events.fileno())

    try:
        checkpoint({"status": "validating"})
        limits = plan["limits"]
        # Re-validate all policy choices; an edited plan cannot lower the floor.
        opts = argparse.Namespace(**limits, confirm_idle=True)
        options(opts)
        assessment_path = outside(plan["assessment_path"], source, plan.get("codex_home"))
        proof = assess(root, source, plan["source"], assessment_path, budget)
        if proof != plan["proof"]:
            raise g.GuardError("Producer/input/completion evidence or semantic assessment changed since plan")
        current = snapshot(source, limits["max_files"], budget, limits["min_age_hours"])
        same_snapshot(current, plan["snapshot"], hashes=True)
        require_activity(root, source)
        excluded = [plan_path, assessment_path, receipt, reservation]
        refs = references(root, source, proof["historical_reference_paths"], excluded, budget, safe_configs=proof["safe_reference_configs"])
        if not reference_same(refs, plan["reference_evidence"]):
            raise g.GuardError("Project reference/config evidence changed since plan")
        time.sleep(limits["idle_seconds"])
        same_snapshot(snapshot(source, limits["max_files"], min_age=limits["min_age_hours"]), current)
        require_activity(root, source)
        if not reference_same(references(root, source, proof["historical_reference_paths"], excluded, budget, safe_configs=proof["safe_reference_configs"]), refs):
            raise g.GuardError("References changed during final idle observation")
        if assess(root, source, plan["source"], assessment_path, budget) != proof:
            raise g.GuardError("Evidence changed immediately before deletion")
        remaining_size = sum(item["fingerprint"]["size"] for item in current["files"].values())
        held_bytes = proof["assessment_record"]["fingerprint"]["size"] + sum(
            item["fingerprint"]["size"] for item in proof["evidence"].values())
        if budget.used + remaining_size + 2 * held_bytes > budget.maximum:
            raise g.GuardError("Insufficient read budget for all per-file release checks; no files deleted")
        with retained_guards(root, assessment_path, proof, budget) as held:
            release_files(source, current, budget, checkpoint, value, held)
        value["status"] = "completed"
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        value["status"] = "partial_or_uncertain" if value["status"] == "releasing" else "refused_before_delete"
        value["error"] = str(exc)
    finally:
        value.update(finished_at=g.utc(), payload_evidence_bytes_read=budget.used,
                     source_free_after_bytes=g.volume_free(root))
        before, after = value["source_free_before_bytes"], value["source_free_after_bytes"]
        value["source_free_delta_bytes"] = after - before if before is not None and after is not None else None
        value["space_note"] = "Logical deleted bytes and volume free-space delta differ; other writes, snapshots, allocation and open handles can affect reclaim"
        value["recovery_note"] = "No automatic retry/rollback. If interrupted, reconcile the exact durable pending batch (at most 64 members); partially deleted data is not a valid database."
        try:
            checkpoint({"status": value["status"], "deleted_files": value["deleted_files"]})
        finally:
            events.close()
        receipt_sha = r.atomic_json(receipt, value)
    print(json.dumps({"receipt": str(receipt), "receipt_sha256": receipt_sha, "status": value["status"],
                      "deleted_files": value["deleted_files"], "deleted_logical_bytes": value["deleted_logical_bytes"],
                      "source_free_delta_bytes": value["source_free_delta_bytes"]}))
    if value["status"] != "completed":
        raise g.GuardError(value.get("error", "Retirement incomplete; inspect exact receipt"))
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("plan")
    p.add_argument("--project", required=True); p.add_argument("--source", required=True)
    p.add_argument("--assessment", required=True); p.add_argument("--output", required=True)
    p.add_argument("--codex-home"); p.add_argument("--confirm-idle", action="store_true")
    p.add_argument("--max-files", type=int, default=100000)
    p.add_argument("--max-bytes", type=int, default=16 * 1024**3)
    p.add_argument("--min-age-hours", type=float, default=48.0)
    p.add_argument("--idle-seconds", type=float, default=2.0)
    p = commands.add_parser("apply")
    p.add_argument("--plan", required=True); p.add_argument("--authorize-plan", required=True)
    p.add_argument("--receipt", required=True); p.add_argument("--confirm-idle", action="store_true")
    p.add_argument("--codex-home", help="Also protect an explicitly relocated state root before reading the plan")
    args = parser.parse_args(argv)
    try:
        return plan_command(args) if args.command == "plan" else apply_command(args)
    except (g.GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc), "policy": POLICY}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    result = main()
    sys.exit(result if isinstance(result, int) else 0)
