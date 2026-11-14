#!/usr/bin/env python3
"""Narrow native pip-cache adapter; uv/npm are deliberately advice-only.

This is a scoped native operation, NOT an exact-delete manifest.  No rmtree,
shell, install, download, prune, project hook, privilege change, or process
enumeration is used.  See references/native-cache.md for the evidence contract.
Python 3.10+, stdlib only; shares path/handle guards with storage_guard.py.
"""
from __future__ import annotations

import argparse
import configparser
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import threading
import time

_guard_path = Path(__file__).absolute().with_name("storage_guard.py")
for _entry in (_guard_path, *_guard_path.parents):
    _s = os.lstat(_entry)
    if stat.S_ISLNK(_s.st_mode) or getattr(_s, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Guard implementation cannot be loaded through a link/reparse point")
_guard_spec = importlib.util.spec_from_file_location("_native_storage_guard", _guard_path)
guard = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(guard)

VERSION = "1.3.0"
SCHEMA = "project-native-cache-v1"
OPERATION = "native-pip-cache-purge"
BINDING = ".storage-cache/pip-binding.json"
TAG = b"Signature: 8a477f597d28d172789f06886806bc55"
SUPPORTED_PIP = {"25.0.1", "26.1.1"}
MAX_JSON = 32 * 1024 * 1024
MAX_EVIDENCE = 64 * 1024
MAX_MEMBERS = 100000
MAX_CAPTURE = 64 * 1024
SNAPSHOT_SECONDS = 180
CHILD_SECONDS = 60
SOURCES = [
    "https://pip.pypa.io/en/stable/cli/pip_cache/",
    "https://pip.pypa.io/en/stable/cli/pip/",
    "https://pip.pypa.io/en/stable/topics/configuration/",
    "https://raw.githubusercontent.com/pypa/pip/25.0.1/src/pip/_internal/commands/cache.py",
    "https://raw.githubusercontent.com/pypa/pip/26.1.1/src/pip/_internal/commands/cache.py",
    "https://raw.githubusercontent.com/pypa/pip/26.1.1/src/pip/_internal/cache.py",
    "https://raw.githubusercontent.com/pypa/pip/26.1.1/src/pip/_internal/network/cache.py",
    "https://docs.astral.sh/uv/concepts/cache/",
    "https://docs.npmjs.com/cli/v11/commands/npm-cache",
]


class NativeError(guard.GuardError):
    pass


def fail(message):
    raise NativeError(message)


def strict_relative(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or value.startswith("/") or len(value) > 1024):
        fail("Expected a forward-slash project-relative path")
    parts = value.split("/")
    if any(p in {"", ".", ".."} or ":" in p or p.endswith((" ", ".")) for p in parts):
        fail("Traversal, alternate stream, or ambiguous path refused")
    return parts


def scoped_path(project, relative, directory=None):
    path = project.joinpath(*strict_relative(relative))
    if not guard.below(path, project) or guard.key(path) == guard.key(project):
        fail("Cache/evidence escaped the project")
    guard.ancestors(path.parent)
    guard.plain(path, directory)
    return path


def evidence_path(project, relative):
    parts = strict_relative(relative)
    why = protected_name(parts)
    if why:
        fail("Protected material cannot be declared as provenance evidence")
    return scoped_path(project, relative, False)


def fingerprint(s):
    result = guard.fingerprint(s)
    # Windows CRT fstat may report zero creation time and synthesized permission
    # bits on exFAT; these are not comparable to lstat. Content is hashed fully.
    if os.name != "nt":
        result["ctime_ns"] = s.st_ctime_ns
    result["type"] = stat.S_IFMT(s.st_mode)
    return result


def file_record(path, limit=None, deadline=None):
    """Hash ordinary, single-link bytes under anchored ancestors, in bounded RAM."""
    with guard.guarded_file(path) as (fd, _):
        before = fingerprint(os.fstat(fd))
        if limit is not None and before["size"] > limit:
            fail("Evidence/executable exceeds its read limit")
        if os.name == "nt" and not guard.only_default_stream(path):
            fail("Alternate data stream refused")
        h = hashlib.sha256()
        total = 0
        while True:
            if deadline is not None and time.monotonic() > deadline:
                fail("Complete snapshot time budget exceeded; retained")
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if limit is not None and total > limit:
                fail("Evidence grew beyond its read limit")
            h.update(block)
        if before != fingerprint(os.fstat(fd)) or before != fingerprint(guard.plain(path, False)):
            fail("File changed during inspection")
        return {"identity": before, "sha256": h.hexdigest()}


def read_small(path):
    record = file_record(path, MAX_EVIDENCE)
    with guard.guarded_file(path) as (fd, _):
        data = os.read(fd, MAX_EVIDENCE + 1)
    if len(data) > MAX_EVIDENCE or hashlib.sha256(data).hexdigest() != record["sha256"]:
        fail("Evidence changed during reading")
    return data, record


def load_small_json(path):
    data, record = read_small(path)
    return json.loads(data.decode("utf-8"), parse_constant=lambda _: fail("Nonfinite JSON refused")), record


def protected_name(parts):
    # This check is independent of plan kind and cannot be waived by a tag.
    low = [p.casefold() for p in parts]
    if any(p in guard.PROTECTED for p in low):
        return "Protected directory/name in native-cache scope"
    for name in low:
        if (name.startswith((".env", "id_rsa", "id_ed25519"))
                or any(x in name for x in ("credential", "secret", "token", "password"))
                or name in {"auth.json", "config.toml", "history.jsonl", "pyvenv.cfg"}
                or re.search(r"\.(?:jsonl|sqlite3?|db)(?:-(?:wal|shm|journal))?$", name)):
            return "Session, index, database, authentication, or environment material in cache"
    return None


def pip_layout(relative, directory):
    """Vetted producer layout only. Metadata exceptions are exact, never generic."""
    parts = strict_relative(relative)
    why = protected_name(parts)
    if why:
        fail(why + ": " + relative)
    if not directory and relative == "CACHEDIR.TAG":
        return "root-marker"
    if parts[0] in {"http", "http-v2"}:
        nested = parts[1:]
        if directory and len(nested) <= 5 and all(re.fullmatch("[0-9a-f]", p) for p in nested):
            return "http-directory"
        if not directory and len(nested) == 6:
            name = nested[-1].removesuffix(".body")
            if (re.fullmatch("[0-9a-f]{56}", name)
                    and list(name[:5]) == nested[:5]):
                return "http-payload"
    if parts[0] == "wheels":
        nested = parts[1:]
        lengths = [2, 2, 2, 50]
        if directory and len(nested) <= 4 and all(re.fullmatch("[0-9a-f]{%d}" % lengths[i], p)
                                                 for i, p in enumerate(nested)):
            return "wheel-directory"
        if not directory and len(nested) == 5:
            if all(re.fullmatch("[0-9a-f]{%d}" % lengths[i], p) for i, p in enumerate(nested[:4])):
                name = nested[-1]
                if name == "origin.json":
                    return "wheel-origin-metadata"
                # Wheel archives are producer artifacts; general archives remain forbidden.
                if re.fullmatch(r"[A-Za-z0-9_.]+-[A-Za-z0-9_.]+(?:-[0-9][A-Za-z0-9_.]*)?-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+\.whl", name):
                    return "wheel-payload"
    fail("Unknown or mixed data in pip cache; retained: " + relative)


def snapshot(cache):
    guard.ancestors(cache)
    initial = guard.root_identity(cache)
    deadline = time.monotonic() + SNAPSHOT_SECONDS
    members = []
    total = 0
    def walk_error(exc):
        raise exc

    for directory, dirs, files in os.walk(cache, topdown=True, followlinks=False, onerror=walk_error):
        if time.monotonic() > deadline:
            fail("Complete snapshot time budget exceeded; retained")
        guard.ancestors(directory)
        dirs.sort()
        files.sort()
        for name in dirs + files:
            path = Path(directory) / name
            relative = path.relative_to(cache).as_posix()
            s = guard.plain(path)
            is_dir = stat.S_ISDIR(s.st_mode)
            if not is_dir and not stat.S_ISREG(s.st_mode):
                fail("Special cache entry refused")
            kind = pip_layout(relative, is_dir)
            if len(members) >= MAX_MEMBERS or time.monotonic() > deadline:
                fail("Complete snapshot exceeded its bounded budget; retained")
            record = {"path": relative, "type": "directory" if is_dir else "file", "kind": kind}
            if is_dir:
                record["identity"] = fingerprint(s)
            else:
                record.update(file_record(path, deadline=deadline))
                total += record["identity"]["size"]
            members.append(record)
    if initial != guard.root_identity(cache):
        fail("Cache root changed during inspection")
    # A second metadata pass catches membership drift that happened after hashing.
    seen = []
    for directory, dirs, files in os.walk(cache, topdown=True, followlinks=False, onerror=walk_error):
        if time.monotonic() > deadline:
            fail("Complete snapshot time budget exceeded; retained")
        guard.ancestors(directory)
        dirs.sort()
        files.sort()
        for name in dirs + files:
            if len(seen) >= MAX_MEMBERS or time.monotonic() > deadline:
                fail("Complete snapshot exceeded its bounded budget; retained")
            path = Path(directory) / name
            seen.append((path.relative_to(cache).as_posix(), fingerprint(guard.plain(path))))
    if seen != [(r["path"], r["identity"]) for r in members]:
        fail("Cache members changed during inspection")
    return {"root_identity": initial, "members": members, "logical_bytes": total,
            "member_count": len(members), "complete": True}


def clean_env(executable):
    # Do not inherit PIP_*, PYTHONPATH/PYTHONHOME, LD_PRELOAD, DYLD_*, or proxies.
    env = {"PATH": str(Path(executable).parent), "PIP_CONFIG_FILE": os.devnull,
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
           "NO_COLOR": "1", "LC_ALL": "C"}
    for name in ("SystemRoot", "WINDIR", "COMSPEC") if os.name == "nt" else ():
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def run_native(argv, cwd, timeout=CHILD_SECONDS):
    """Bounded pipe capture. On timeout terminate only this launched child PID."""
    env = clean_env(argv[0])
    proc = subprocess.Popen(argv, cwd=str(cwd), env=env, shell=False, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    captured = bytearray()
    count = [0]

    def drain():
        while True:
            block = proc.stdout.read(8192)
            if not block:
                break
            count[0] += len(block)
            remaining = MAX_CAPTURE - len(captured)
            if remaining > 0:
                captured.extend(block[:remaining])

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.terminate()  # Never kill an unrelated producer or process tree.
        try:
            code = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()  # This child only, no taskkill/pkill/process enumeration.
            code = proc.wait(timeout=3)
    reader.join(timeout=3)
    if reader.is_alive():
        # A descendant holding stdout is an uncertain native result, not retryable.
        fail("Native output pipe did not close; do not retry")
    proc.stdout.close()
    return {"returncode": code, "timed_out": timed_out, "pid": proc.pid,
            "output": captured.decode("utf-8", errors="replace"),
            "output_bytes": count[0], "output_truncated": count[0] > MAX_CAPTURE}


def checked_run(argv, cwd):
    result = run_native(argv, cwd)
    if result["timed_out"] or result["returncode"] != 0 or result["output_truncated"]:
        fail("Read-only native probe failed, timed out, or exceeded output budget")
    return result["output"]


def pip_prefix(executable, cache=None):
    argv = [str(executable), "-I", "-B", "-m", "pip", "--isolated",
            "--disable-pip-version-check", "--no-input", "--no-color", "--log", os.devnull]
    if cache is not None:
        argv += ["--cache-dir", str(cache)]
    return argv


def executable_path(tool, project):
    # The public CLI offers no --executable escape hatch.
    # Use the runtime that is already executing this trusted guard. Resolving its
    # launcher once permits conventional macOS Python symlinks, while the actual
    # executable and every ancestor must be plain on every subsequent use.
    exe = guard.absolute(os.path.realpath(sys.executable))
    guard.ancestors(exe.parent)
    guard.plain(exe, False)
    if guard.below(exe, project) or exe.suffix.lower() in {".bat", ".cmd", ".ps1", ".py", ".sh"}:
        fail("Project-owned tool or shell/script launcher refused")
    if os.name == "nt" and exe.suffix.lower() != ".exe":
        fail("Windows adapter requires a native executable")
    if os.name != "nt":
        with guard.guarded_file(exe) as (fd, _):
            if os.read(fd, 2) == b"#!":
                fail("Script launcher refused; only native Python executables are supported")
    return exe


def probe_pip(project, cache):
    exe = executable_path("pip", project)
    record = file_record(exe, 32 * 1024 * 1024)
    prefix = pip_prefix(exe)
    version_text = checked_run(prefix + ["--version"], exe.parent).strip()
    match = re.fullmatch(r"pip ([0-9]+\.[0-9]+(?:\.[0-9]+)?) from (.+) \(python ([0-9]+\.[0-9]+)\)", version_text)
    if not match or match[1] not in SUPPORTED_PIP:
        fail("pip version is outside reviewed 25.0.1 / 26.1.1 contracts")
    package = guard.absolute(match[2])
    guard.ancestors(package)
    if package.name != "pip" or guard.below(package, project):
        fail("pip package must be installed outside the selected project")
    # Keep a fingerprint of the implementation that defines purge and scoping.
    implementation = {}
    for rel in ("_internal/commands/cache.py", "_internal/configuration.py", "_internal/utils/filesystem.py",
                "_internal/cli/base_command.py", "_internal/cli/cmdoptions.py"):
        implementation[rel] = file_record(package.joinpath(*rel.split("/")), 2 * 1024 * 1024)
    help_text = checked_run(prefix + ["cache", "--help"], exe.parent)
    for token in ("--isolated", "--cache-dir", "--disable-pip-version-check", "--no-input", "--no-color", "--log", "purge"):
        if token not in help_text:
            fail("Installed pip help lacks required scoped command contract: " + token)
    resolved = checked_run(pip_prefix(exe, cache) + ["cache", "dir"], exe.parent).strip()
    if guard.key(resolved) != guard.key(cache):
        fail("pip did not resolve exactly the approved cache directory")
    if record != file_record(exe, 32 * 1024 * 1024):
        fail("Executable changed during read-only probes")
    return {"executable": str(exe), "executable_record": record, "version": match[1],
            "version_text": version_text, "package": str(package), "implementation": implementation,
            "help_sha256": hashlib.sha256(help_text.encode()).hexdigest(), "resolved_cache": str(cache)}


def check_binding(project, cache, cache_rel, tool):
    path = scoped_path(project, BINDING, False)
    binding, record = load_small_json(path)
    required = {"schema", "project", "tool", "cache", "ownership", "audit", "producer_config", "producer_receipt"}
    if not isinstance(binding, dict) or set(binding) != required:
        fail("Binding has unknown/missing fields; a path alone is not ownership evidence")
    if (binding["schema"] != "project-native-cache-binding-v1" or binding["tool"] != "pip"
            or binding["ownership"] != "project-exclusive" or binding["cache"] != cache_rel
            or guard.key(binding["project"]) != guard.key(project)):
        fail("Binding does not establish this exact project-exclusive pip cache")
    audit = binding["audit"]
    if (not isinstance(audit, dict) or set(audit) != {"reviewed_at", "reviewed_by", "checked_project_roots", "external_references", "evidence"}
            or audit["external_references"] != "none-found" or not isinstance(audit["reviewed_by"], str)
            or not audit["reviewed_by"].strip() or not isinstance(audit["evidence"], str)
            or len(audit["evidence"].strip()) < 20):
        fail("Explicit ownership/reference audit is missing")
    reviewed = dt.datetime.fromisoformat(audit["reviewed_at"])
    if reviewed.tzinfo is None or not 0 <= (dt.datetime.now(dt.timezone.utc) - reviewed).total_seconds() <= 7 * 86400:
        fail("Project-exclusive reference audit must be timezone-aware and no older than seven days")
    roots = audit["checked_project_roots"]
    if (not isinstance(roots, list) or not roots or len(roots) > 128
            or not any(guard.key(p) == guard.key(project) for p in roots)):
        fail("Audit must identify its finite checked project scope")
    # Never scan other projects merely because their names appear in evidence.
    config = evidence_path(project, binding["producer_config"])
    if guard.below(config, cache):
        fail("Producer configuration cannot live inside its purge scope")
    raw_config, config_record = read_small(config)
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string(raw_config.decode("utf-8-sig"))
    if (parser.defaults() or parser.sections() != ["global"]
            or set(parser["global"]) != {"cache-dir"}
            or not os.path.isabs(parser["global"]["cache-dir"])
            or guard.key(parser["global"]["cache-dir"]) != guard.key(cache)):
        fail("Producer INI must contain only [global] cache-dir = this absolute cache")
    producer = evidence_path(project, binding["producer_receipt"])
    if guard.below(producer, cache):
        fail("Producer receipt cannot live inside its purge scope")
    evidence, producer_record = load_small_json(producer)
    fields = {"schema", "project", "cwd", "executable", "executable_sha256", "config", "config_sha256",
              "config_loading", "resolved_cache", "argv", "operation", "returncode"}
    if not isinstance(evidence, dict) or set(evidence) != fields:
        fail("A bounded, existing native producer receipt is required")
    if (evidence["schema"] != "pip-cache-producer-v1" or evidence["returncode"] != 0
            or evidence["operation"] not in {"install", "download", "wheel"}
            or evidence["config"] != binding["producer_config"]
            or evidence["config_sha256"] != config_record["sha256"]
            or evidence["config_loading"] != "PIP_CONFIG_FILE"
            or evidence["executable"] != tool["executable"]
            or evidence["executable_sha256"] != tool["executable_record"]["sha256"]
            or any(guard.key(evidence[k]) != guard.key(project) for k in ("project", "cwd"))
            or guard.key(evidence["resolved_cache"]) != guard.key(cache)):
        fail("Historical producer/config evidence does not match the current binding")
    argv = evidence["argv"]
    producer_prefix = pip_prefix(tool["executable"], cache) + [evidence["operation"], "-r"]
    if not isinstance(argv, list) or len(argv) != len(producer_prefix) + 1 or argv[:-1] != producer_prefix:
        fail("Unsupported historical producer argv; no shell recipes are accepted")
    # A supported recipe is python -I -B -m pip --cache-dir ABS install -r requirements.txt.
    # Historical argv is evidence only and never executed by this guard.
    requirements = evidence_path(project, argv[-1])
    if guard.below(requirements, cache):
        fail("Producer input is inside the proposed purge scope")
    return {"binding": record, "config_path": binding["producer_config"], "config": config_record,
            "producer_receipt_path": binding["producer_receipt"], "producer_receipt": producer_record,
            "requirements_path": argv[-1], "requirements": file_record(requirements, 2 * 1024 * 1024),
            "ownership_basis": "operator-audited finite reference scope plus existing producer/config record",
            "audit": {"reviewed_at": audit["reviewed_at"], "checked_project_count": len(roots)}}


def inspect(project_value, tool_name, cache_rel):
    project = guard.project_root(project_value)
    result = {"schema": SCHEMA, "created_at": guard.utc(), "project": str(project),
              "project_identity": guard.root_identity(project), "tool": tool_name, "cache": cache_rel,
              "operation": OPERATION if tool_name == "pip" else "native-cache-advice",
              "status": "advice_only", "reasons": [], "sources": SOURCES,
              "scope_contract": "Native manager may remove cache payloads and its own reviewed metadata. Snapshot is a drift guard, not an exact deletion manifest.",
              "concurrency": "Requires explicit idle confirmation on all platforms; cooperative guard lock does not exclude unrelated writers.",
              "native_atomicity": "Root and ancestors are anchored; manager descendants are not held exclusive. A noncooperating writer can race a native operation. Idle confirmation is a prerequisite, not an inferred filesystem fact.",
              "estimated_reclaim": "No guaranteed deletion-byte estimate or exact file-deletion claim"}
    try:
        cache = scoped_path(project, cache_rel, True)
        why = protected_name(strict_relative(cache_rel))
        if why:
            fail(why)
        result["cache_absolute"] = str(cache)
        if tool_name != "pip":
            fail("uv/npm remain advice-only: uv can affect centralized/symlinked environments; npm clean requires force")
        # Tag is necessary but insufficient. Never create/repair it during planning.
        tag_data, tag_record = read_small(cache / "CACHEDIR.TAG")
        if not tag_data.startswith(TAG):
            fail("A valid existing CACHEDIR.TAG is required")
        tool = probe_pip(project, cache)
        result["native_tool"] = tool
        result["provenance"] = check_binding(project, cache, cache_rel, tool)
        result["tag"] = tag_record
        result["snapshot"] = snapshot(cache)
        result["command"] = pip_prefix(tool["executable"], cache) + ["cache", "purge"]
        result["status"] = "executable"
    except (OSError, guard.GuardError, ValueError, TypeError, KeyError, configparser.Error) as exc:
        if guard.fatal_io(exc):
            raise
        # ConfigParser's error text can quote secret-bearing source lines.
        result["reasons"].append("Producer INI parse failed (" + type(exc).__name__ + ")"
                                 if isinstance(exc, configparser.Error) else str(exc))
    return result


def output_path(value, project):
    path = guard.absolute(value)
    if guard.below(path, project):
        fail("Plans/receipts must be outside the selected project")
    guard.ancestors(path.parent, missing=True)
    if os.path.lexists(path):
        fail("Output already exists; never overwrite a plan/receipt")
    return path


def write_bounded(path, value, create=True, expected_identity=None):
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > MAX_JSON:
        fail("Bounded report budget exceeded")
    guard.ancestors(path.parent, missing=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    guard.ancestors(path.parent)
    if shutil.disk_usage(path.parent).free < len(data) + 1024 * 1024:
        fail("Insufficient report-volume reserve")
    # Updates are anchored and opened without following a reparse point. Never
    # truncate a path before checking its current type/link count.
    with contextlib.ExitStack() as stack:
        if os.name == "nt":
            for parent in reversed((path.parent, *path.parent.parents)):
                h = guard.win_open(parent, 0x80, 3, directory=True)
                stack.callback(guard.K32.CloseHandle, h)
        if create:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags, 0o600)
        elif os.name == "nt":
            import msvcrt
            h = guard.win_open(path, 0x40000000, 0)
            try:
                fd = msvcrt.open_osfhandle(h, os.O_WRONLY | os.O_BINARY)
            except BaseException:
                guard.K32.CloseHandle(h)
                raise
        else:
            fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "wb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                fail("Report target is not a single-link ordinary file")
            if not create:
                if expected_identity != {"device": opened.st_dev, "inode": opened.st_ino}:
                    fail("Receipt identity changed before update")
                stream.truncate(0)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def stable_view(plan):
    # Recompute every admissibility decision; ignore no policy-bearing plan field.
    return {k: v for k, v in plan.items() if k != "created_at"}


@contextlib.contextmanager
def anchored_cache(cache):
    handles = []
    try:
        guard.ancestors(cache)
        for path in reversed((cache, *cache.parents)):
            if os.name == "nt":
                # Root/ancestors cannot be replaced; manager may mutate descendants.
                handles.append(guard.win_open(path, 0x80, 3, directory=True))
            else:
                handles.append(os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        yield
    finally:
        for handle in reversed(handles):
            guard.K32.CloseHandle(handle) if os.name == "nt" else os.close(handle)


def apply(args):
    if not args.confirm_idle:
        fail("Native pip purge requires --confirm-idle after stopping/confirming all cache writers and consumers; no lock marker is proof of idle")
    plan_path = guard.absolute(args.plan)
    plan, digest = guard.read_json(plan_path)
    if digest != args.authorize_plan:
        fail("Authorized plan SHA256 does not match the exact plan bytes")
    if plan.get("schema") != SCHEMA or plan.get("operation") != OPERATION or plan.get("tool") != "pip" or plan.get("status") != "executable":
        fail("Only an executable native-pip plan is applicable")
    project = guard.project_root(plan["project"])
    receipt_path = output_path(args.receipt, project)
    cache = scoped_path(project, plan["cache"], True)
    claim = project / (".native-cache-used-" + digest)
    lock = project / (".native-cache-lock-" + hashlib.sha256(str(cache).encode()).hexdigest()[:24])
    if os.path.lexists(claim):
        fail("This exact native plan was already claimed; do not retry or replay")
    lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    lock_identity = None
    lock_payload = (str(os.getpid()) + ":" + os.urandom(16).hex()).encode("ascii")
    receipt = {"schema": SCHEMA, "plan_sha256": digest, "project": str(project), "cache": str(cache),
               "operation": OPERATION, "started_at": guard.utc(), "status": "preflight",
               "native_result": None, "automatic_retry": False, "exact_delete_manifest": False}
    receipt_identity = None
    try:
        os.write(lock_fd, lock_payload)
        os.fsync(lock_fd)
        lock_stat = os.fstat(lock_fd)
        lock_identity = {"device": lock_stat.st_dev, "inode": lock_stat.st_ino}
        with anchored_cache(cache):
            current = inspect(project, "pip", plan["cache"])
            if stable_view(current) != stable_view(plan):
                fail("Native plan evidence, executable, cache content/members, identity, or policy changed; create a new plan only after review")
            write_bounded(receipt_path, receipt)
            receipt_stat = guard.plain(receipt_path, False)
            receipt_identity = {"device": receipt_stat.st_dev, "inode": receipt_stat.st_ino}
            # Single-use claim is created only after successful preflight, before mutation.
            claim_fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(claim_fd, "wb") as stream:
                stream.write((digest + "\n" + str(receipt_path) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            receipt["status"] = "native_started_result_unknown"
            write_bounded(receipt_path, receipt, create=False, expected_identity=receipt_identity)
            before_free = shutil.disk_usage(project).free
            # No argv is accepted from a plan: derive the only supported operation.
            command = pip_prefix(current["native_tool"]["executable"], cache) + ["cache", "purge"]
            result = run_native(command, Path(command[0]).parent)
            receipt["native_result"] = result
            receipt["status"] = "native_completed_pending_verification" if result["returncode"] == 0 and not result["timed_out"] else "native_failed_or_timed_out_no_retry"
            try:
                after = snapshot(cache)
                old_files = {m["path"]: m for m in current["snapshot"]["members"] if m["type"] == "file"}
                new_files = {m["path"]: m for m in after["members"] if m["type"] == "file"}
                changed = [p for p in new_files if p not in old_files or new_files[p] != old_files[p]]
                unexpected_removed = [p for p in set(old_files) - set(new_files)
                                      if old_files[p]["kind"] not in {"http-payload", "wheel-payload", "wheel-origin-metadata"}]
                receipt["verification"] = {"after_snapshot": after, "new_or_changed_files": changed,
                    "unexpected_removed_files": unexpected_removed,
                    "observed_removed_file_count": len(set(old_files) - set(new_files)),
                    "observed_removed_logical_bytes": sum(old_files[p]["identity"]["size"] for p in set(old_files) - set(new_files)),
                    "source_volume_free_delta": shutil.disk_usage(project).free - before_free,
                    "note": "Observed logical bytes and free delta are distinct; other disk activity may affect free space."}
                if result["returncode"] == 0 and not result["timed_out"] and not changed and not unexpected_removed:
                    receipt["status"] = "native_completed_verified_scope"
            except (OSError, guard.GuardError, ValueError) as exc:
                receipt["verification_error"] = str(exc)
                receipt["status"] = "native_result_requires_review_no_retry"
            receipt["finished_at"] = guard.utc()
            write_bounded(receipt_path, receipt, create=False, expected_identity=receipt_identity)
    except BaseException as exc:
        if receipt_identity is not None and receipt_path.exists():
            receipt["error"] = str(exc)
            receipt["finished_at"] = guard.utc()
            receipt["status"] = "stopped_requires_review_no_retry"
            write_bounded(receipt_path, receipt, create=False, expected_identity=receipt_identity)
        raise
    finally:
        os.close(lock_fd)
        # Only unlink the exact guard-owned lock, not any producer lock.
        if os.path.lexists(lock):
            with guard.guarded_file(lock, delete=True) as (fd, unlink):
                opened = os.fstat(fd)
                if (lock_identity != {"device": opened.st_dev, "inode": opened.st_ino}
                        or os.read(fd, 128) != lock_payload):
                    fail("Guard lock identity changed; it was left for review")
                unlink()
    print(json.dumps({"receipt": str(receipt_path), "status": receipt["status"]}))
    return 0 if receipt["status"] == "native_completed_verified_scope" else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("plan", help="Read-only native probes and complete scoped-cache admission")
    p.add_argument("--project", required=True)
    p.add_argument("--tool", required=True, choices=("pip", "uv", "npm"))
    p.add_argument("--cache", required=True, help="Forward-slash project-relative existing cache")
    p.add_argument("--output", required=True)
    a = sub.add_parser("apply", help="Single-use native pip purge for exact authorized plan bytes")
    a.add_argument("--plan", required=True)
    a.add_argument("--receipt", required=True)
    a.add_argument("--authorize-plan", required=True)
    a.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode == "plan":
            report = inspect(args.project, args.tool, args.cache)
            path = output_path(args.output, guard.absolute(report["project"]))
            digest = write_bounded(path, report)
            print(json.dumps({"plan": str(path), "plan_sha256": digest, "status": report["status"], "reasons": report["reasons"]}))
        else:
            return apply(args)
    except (OSError, guard.GuardError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "stopped", "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
