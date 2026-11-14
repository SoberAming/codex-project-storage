#!/usr/bin/env python3
"""Guarded project-exclusive npm _cacache retirement (Python 3.10+, stdlib).

Only an explicitly reviewed, refetchable project cache is eligible. This is a
native npm operation, not an exact-delete engine. No project command, install,
network request, default cache, shell, service stop, or database is invoked.
"""
from __future__ import annotations

import argparse
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
import uuid

_native_path = Path(__file__).absolute().with_name("native_cache_guard.py")
for _entry in (_native_path, *_native_path.parents):
    _s = os.lstat(_entry)
    if stat.S_ISLNK(_s.st_mode) or getattr(_s, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Implementation links/reparse points are refused")
_spec = importlib.util.spec_from_file_location("_npm_native_cache_guard", _native_path)
n = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(n)
g = n.guard
_relocation_path = _native_path.with_name("relocation_guard.py")
for _entry in (_relocation_path, *_relocation_path.parents):
    _s = os.lstat(_entry)
    if stat.S_ISLNK(_s.st_mode) or getattr(_s, "st_file_attributes", 0) & 0x400:
        raise RuntimeError("Metadata implementation links/reparse points are refused")
_relocation_spec = importlib.util.spec_from_file_location("_npm_metadata_guard", _relocation_path)
metadata_guard = importlib.util.module_from_spec(_relocation_spec)
_previous_guard_module = sys.modules.get("storage_guard")
sys.modules["storage_guard"] = g
try:
    _relocation_spec.loader.exec_module(metadata_guard)
finally:
    if _previous_guard_module is None:
        sys.modules.pop("storage_guard", None)
    else:
        sys.modules["storage_guard"] = _previous_guard_module

VERSION = "1.4.0"
SCHEMA = "project-npm-cache-plan-v1"
ASSESSMENT = "project-npm-cache-assessment-v1"
OPERATION = "detached-project-npm-cacache-clean"
MAX_MEMBERS = 100000
MAX_BYTES = 8 * 1024 ** 3
MAX_SECONDS = 240
MAX_INDEX = 4 * 1024 ** 2
MAX_EVIDENCE = 256 * 1024
CHILD_SECONDS = 60
# Reviewed upstream command source, normalized LF; a version string alone is
# insufficient. Bootstrap/config files are also pinned in each individual plan.
SUPPORTED = {"10.9.2": "c7aced5e5ab97d492529195f59db75e035a79f161a7939ed330a0eeff506184e"}
SOURCES = [
    "https://docs.npmjs.com/cli/v10/commands/npm-cache",
    "https://raw.githubusercontent.com/npm/cli/v10.9.2/lib/commands/cache.js",
    "https://raw.githubusercontent.com/npm/cacache/v19.0.1/lib/content/path.js",
    "https://raw.githubusercontent.com/npm/cacache/v19.0.1/lib/entry-index.js",
]


def fail(message):
    raise g.GuardError(message)


def private_io_path(value):
    """Metadata-only privacy gate, before opening any caller-selected bytes.

    Check logical/physical state locations and known directory identities, not
    the file's contents or its claimed JSON schema. Missing output descendants
    are checked too; resolving an explicitly known root uses path metadata only.
    """
    path = g.absolute(value)
    private_parts = {".codex", ".agents", ".git", "sessions", "archived_sessions",
                     "thread_history", "credentials", "secrets", "memories",
                     "state", "indexes", "indices"}
    for component in path.parts:
        name = component.casefold()
        if component == path.anchor:
            continue
        if (name in private_parts or ":" in component
                or name.startswith((".env", "id_rsa", "id_ed25519"))
                or any(token in name for token in ("credential", "password", "secret", "token"))
                or name in {"auth.json", "config.toml", "history.jsonl"}
                or re.search(r"\.(?:jsonl|sqlite3?|db)(?:-(?:wal|shm|journal))?$", name)
                or Path(name).suffix in {".pem", ".key", ".p12", ".pfx", ".kdbx"}):
            fail("Sensitive input/output name refused before content access")
    roots = [g.absolute(Path.home() / ".codex")]
    for variable in ("CODEX_HOME", "CODEX_SQLITE_HOME"):
        if os.environ.get(variable):
            roots.append(g.absolute(os.environ[variable]))
    physical_path = g.absolute(os.path.realpath(path))
    candidates = (path, *path.parents, physical_path, *physical_path.parents)
    for state_root in roots:
        physical_root = g.absolute(os.path.realpath(state_root))
        if any(g.below(candidate, known) for candidate in (path, physical_path)
               for known in (state_root, physical_root)):
            fail("Codex state input/output root refused before content access")
        for candidate in candidates:
            for known in (state_root, physical_root):
                try:
                    if os.path.samefile(candidate, known):
                        fail("Known Codex state identity alias refused before content access")
                except FileNotFoundError:
                    pass
    return path


def output_path(value, project):
    return n.output_path(private_io_path(value), project)


def write_report(path, value, *args, **kwargs):
    return n.write_bounded(private_io_path(path), value, *args, **kwargs)


def read_bytes(path, limit=MAX_EVIDENCE):
    path = private_io_path(path)
    record = n.file_record(path, limit)
    with g.guarded_file(path) as (fd, _):
        value = os.read(fd, limit + 1)
    if len(value) > limit or hashlib.sha256(value).hexdigest() != record["sha256"]:
        fail("Evidence changed or exceeded its bounded read limit")
    return value, record


def fresh_time(value, maximum, label):
    instant = dt.datetime.fromisoformat(value)
    if instant.tzinfo is None or not 0 <= (dt.datetime.now(dt.timezone.utc) - instant).total_seconds() <= maximum:
        fail(label + " is missing, future-dated, or stale")


def clean_env(node, private_home):
    # In particular no NODE_OPTIONS, NODE_PATH, NPM_CONFIG_*, proxy, preload,
    # DYLD_*, LD_*, or arbitrary inherited PATH entry reaches the native child.
    env = {"PATH": str(Path(node).parent), "HOME": str(private_home),
           "USERPROFILE": str(private_home), "NO_COLOR": "1", "LC_ALL": "C"}
    for name in ("SystemRoot", "WINDIR") if os.name == "nt" else ():
        if name in os.environ:
            env[name] = os.environ[name]
    return env


def run_native(argv, cwd, home, timeout=CHILD_SECONDS):
    proc = subprocess.Popen(argv, cwd=str(cwd), env=clean_env(argv[0], home), shell=False,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    captured = bytearray()
    count = [0]
    def drain():
        while True:
            block = proc.stdout.read(8192)
            if not block:
                break
            count[0] += len(block)
            captured.extend(block[:max(0, n.MAX_CAPTURE - len(captured))])
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.terminate()  # Only the child this guard launched; no process tree.
        try:
            code = proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            code = proc.wait(timeout=3)
    reader.join(timeout=3)
    if reader.is_alive():
        fail("Native output pipe remained open; result uncertain, do not retry")
    proc.stdout.close()
    return {"returncode": code, "timed_out": timed_out, "pid": proc.pid,
            "output": captured.decode("utf-8", errors="replace"), "output_bytes": count[0],
            "output_truncated": count[0] > n.MAX_CAPTURE}


def tool_path(value, project, script=False):
    path = private_io_path(value)
    # Conventional installation symlinks may be explicitly resolved by the
    # operator before supplying the argument; the executor never follows them.
    g.ancestors(path.parent)
    g.plain(path, False)
    if g.below(path, project):
        fail("Project-owned Node/npm implementation is refused")
    if script:
        if path.name != "npm-cli.js" or path.parent.name != "bin":
            fail("An explicitly selected installed npm bin/npm-cli.js is required")
    elif os.name == "nt" and path.suffix.casefold() != ".exe":
        fail("Windows Node must be a native executable, not a command wrapper")
    elif os.name != "nt":
        with g.guarded_file(path) as (fd, _):
            if os.read(fd, 2) == b"#!":
                fail("Native Node required; shell/script launcher refused")
    return path


def probe_tool(project, node_value, cli_value):
    node, cli = tool_path(node_value, project), tool_path(cli_value, project, True)
    package = cli.parent.parent
    raw, package_record = read_bytes(package / "package.json")
    info = json.loads(raw.decode("utf-8"))
    version = info.get("version")
    if info.get("name") != "npm" or version not in SUPPORTED:
        fail("npm version is outside the reviewed 10.9.2 contract; preserve and report unsupported version")
    source, _ = read_bytes(package / "lib" / "commands" / "cache.js")
    normalized = source.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
    if hashlib.sha256(normalized).hexdigest() != SUPPORTED[version]:
        fail("npm cache command differs from the reviewed official implementation")
    implementation = {}
    for rel in ("bin/npm-cli.js", "lib/cli.js", "lib/cli/entry.js", "lib/npm.js",
                "lib/commands/cache.js", "node_modules/@npmcli/config/lib/index.js",
                "node_modules/@npmcli/config/lib/definitions/definitions.js", "npmrc"):
        implementation[rel] = n.file_record(package.joinpath(*rel.split("/")), 2 * 1024 * 1024)
    node_record = n.file_record(node, 128 * 1024 * 1024)
    result = run_native([str(node), "--version"], node.parent, node.parent)
    if (result["returncode"] != 0 or result["timed_out"] or result["output_truncated"]
            or not re.fullmatch(r"v(?:18|20|22|24)\.\d+\.\d+\s*", result["output"])):
        fail("Native Node version probe failed or is outside the admitted major versions")
    if node_record != n.file_record(node, 128 * 1024 * 1024):
        fail("Node executable changed during probing")
    return {"node": str(node), "node_record": node_record, "node_version": result["output"].strip(),
            "npm_cli": str(cli), "npm_version": version, "package_record": package_record,
            "implementation": implementation,
            "trust_boundary": "Operator-selected trusted installed Node/npm outside project; core implementation bound, not an OS software-attestation system"}


def cache_scope(project, cache_rel):
    parts = n.strict_relative(cache_rel)
    # A project .npm cache is permitted only through this dedicated adapter;
    # dependency installations and all other protected path components remain
    # forbidden. Default user caches cannot be inside an independent project.
    for part in parts:
        if part.casefold() in g.PROTECTED - {".npm"}:
            fail("Protected directory in npm cache path")
    if n.protected_name([p for p in parts if p.casefold() != ".npm"]):
        fail("State, credential, database, or environment path is not a cache scope")
    if any(p.casefold() in {"pgdata", "database", "databases", "dbdata"} for p in parts):
        fail("Business database storage cannot be adopted as an npm cache")
    cache = n.scoped_path(project, cache_rel, True)
    if cache == project or cache_rel in {".npm", "npm-cache"} and project == Path.home():
        fail("Default/shared cache scope refused")
    source = cache / "_cacache"
    g.ancestors(source)
    g.plain(source, True)
    return cache, source


def evidence_file(project, relative, source):
    parts = n.strict_relative(relative)
    if n.protected_name([p for p in parts if p.casefold() != ".npm"]):
        fail("Protected material cannot serve as npm cache ownership evidence")
    path = n.scoped_path(project, relative, False)
    if g.below(path, source):
        fail("Ownership evidence must survive cache retirement")
    raw, record = read_bytes(path)
    return raw.decode("utf-8", errors="strict"), record


def qualify(project, cache_rel, source, assessment_path):
    assessment_path = private_io_path(assessment_path)
    if g.below(assessment_path, project):
        fail("Review assessment must be retained outside the project")
    raw, assessment_record = read_bytes(assessment_path)
    assessment = json.loads(raw.decode("utf-8"))
    required = {"schema", "project", "cache", "ownership", "producer", "existing_log", "review"}
    if not isinstance(assessment, dict) or set(assessment) != required:
        fail("Missing structured evidence; boolean cache/test claims are insufficient")
    if (assessment["schema"] != ASSESSMENT or g.key(assessment["project"]) != g.key(project)
            or assessment["cache"] != cache_rel or assessment["ownership"] != "project-exclusive-refetchable"):
        fail("Exact project-exclusive refetchable cache classification is required")
    producer = assessment["producer"]
    if not isinstance(producer, dict) or set(producer) != {"path", "excerpts", "explanation"}:
        fail("Retained real producer/configuration evidence is required")
    code, code_record = evidence_file(project, producer["path"], source)
    excerpts = producer["excerpts"]
    if (not isinstance(excerpts, list) or not 1 <= len(excerpts) <= 12
            or any(not isinstance(x, str) or len(x) < 8 or len(x) > 2048 or x not in code for x in excerpts)
            or not isinstance(producer["explanation"], str) or len(producer["explanation"].strip()) < 40):
        fail("Producer citations must match existing retained bytes and explain cache ownership")
    combined = "\n".join(excerpts).casefold()
    if "npm" not in combined or not ("--cache" in combined or "cache=" in combined or "cache-dir" in combined):
        fail("Producer citations do not identify npm and its explicit dedicated cache")
    log_rel = assessment["existing_log"]
    log, log_record = evidence_file(project, log_rel, source)
    # Debug logs are existing native execution evidence, not a newly fabricated
    # historical receipt. They must show the exact dedicated cache argv.
    normalized = log.replace("\\\\", "\\").replace("\\", "/").casefold()
    absolute_cache = str(source.parent).replace("\\", "/").casefold()
    if ("verbose argv" not in normalized or "--cache" not in normalized
            or absolute_cache not in normalized or "verbose exit" not in normalized):
        fail("Existing npm debug log lacks exact dedicated cache argv and termination evidence; do not manufacture historical evidence")
    review = assessment["review"]
    fields = {"reviewed_at", "reviewed_by", "checked_project_roots", "reference_findings",
              "refetch_findings", "activity_checked_at", "activity_findings", "external_references", "writers"}
    if not isinstance(review, dict) or set(review) != fields:
        fail("A finite reference, refetchability, and activity review is required")
    fresh_time(review["reviewed_at"], 7 * 86400, "Reference review")
    fresh_time(review["activity_checked_at"], 1800, "Activity review")
    roots = review["checked_project_roots"]
    if (not isinstance(roots, list) or not 1 <= len(roots) <= 128
            or not any(g.key(p) == g.key(project) for p in roots)
            or review["external_references"] != "none-found" or review["writers"] != "none-found"
            or not isinstance(review["reviewed_by"], str) or not review["reviewed_by"].strip()):
        fail("Shared, active, unreviewed, or unknown cache use is not eligible")
    for key in ("reference_findings", "refetch_findings", "activity_findings"):
        if not isinstance(review[key], str) or len(review[key].strip()) < 60:
            fail("Review must explain actual checks and limits, not assert boolean permission: " + key)
    return {"assessment": str(assessment_path), "assessment_record": assessment_record,
            "producer_path": producer["path"], "producer_record": code_record,
            "existing_log_path": log_rel, "existing_log_record": log_record,
            "review": review,
            "semantic_limit": "Agent/operator must truthfully establish ownership, no outside consumers and refetchability from retained real evidence; hashes bind evidence, they do not prove arbitrary code semantics"}


def layout(relative, directory):
    p = n.strict_relative(relative)
    if p[0] == "content-v2":
        if directory and len(p) == 1:
            return "content-directory"
        lengths = {"sha512": 128, "sha256": 64, "sha1": 40}
        if len(p) >= 2 and p[1] in lengths:
            if directory and len(p) <= 4 and all(re.fullmatch("[a-f0-9]{2}", x) for x in p[2:]):
                return "content-directory"
            if (not directory and len(p) == 5
                    and all(re.fullmatch("[a-f0-9]{2}", x) for x in p[2:4])
                    and re.fullmatch("[a-f0-9]{%d}" % (lengths[p[1]] - 4), p[4])):
                return "content"
    if p[0] == "index-v5":
        if directory and len(p) <= 3 and all(re.fullmatch("[a-f0-9]{2}", x) for x in p[1:]):
            return "index-directory"
        if (not directory and len(p) == 4 and all(re.fullmatch("[a-f0-9]{2}", x) for x in p[1:3])
                and re.fullmatch("[a-f0-9]{60}", p[3])):
            return "index"
    if relative == "tmp" and directory:
        return "empty-tmp-directory"
    if relative == "_lastverified" and not directory:
        return "verification-metadata"
    fail("Unknown/mixed cache member retained: " + relative)


def validate_index(path, relative, expected_sha):
    raw, record = read_bytes(path, MAX_INDEX)
    if record["sha256"] != expected_sha:
        fail("Cache index changed while qualifying")
    for line in raw.split(b"\n"):
        if not line:
            continue
        try:
            digest, payload = line.split(b"\t", 1)
            if hashlib.sha1(payload).hexdigest().encode() != digest:
                fail("Unrecognized/corrupt npm index entry retained")
            entry = json.loads(payload)
            if (not isinstance(entry, dict) or not {"key", "integrity", "time"} <= set(entry)
                    or set(entry) - {"key", "integrity", "time", "size", "metadata"}
                    or not isinstance(entry["key"], str) or not entry["key"]
                    or not isinstance(entry["time"], (int, float))):
                fail("Unrecognized npm index record retained")
            expected_bucket = hashlib.sha256(entry["key"].encode("utf-8")).hexdigest()
            if "".join(relative.split("/")[1:]) != expected_bucket:
                fail("npm index key does not match its content-addressed bucket")
            integrity = entry["integrity"]
            if integrity is not None and (not isinstance(integrity, str)
                    or not re.fullmatch(r"(?:sha512|sha256|sha1)-[A-Za-z0-9+/]+={0,2}", integrity)):
                fail("Unsupported npm integrity record retained")
        except (ValueError, TypeError, KeyError, UnicodeError):
            fail("Unrecognized/corrupt npm index record retained")


def snapshot(source):
    g.ancestors(source)
    root_id = g.root_identity(source)
    if not root_id["device"] or not root_id["inode"]:
        fail("Unknown cache root identity; retained")
    root_metadata = metadata_guard.metadata(source, True)
    if sys.platform == "darwin" and root_metadata.get("darwin_acl") is None:
        fail("Unknown/unsupported macOS root ACL metadata; retained")
    deadline = time.monotonic() + MAX_SECONDS
    members, total = [], 0
    def error(exc):
        raise exc
    for directory, dirs, files in os.walk(source, topdown=True, followlinks=False, onerror=error):
        g.ancestors(directory)
        dirs.sort()
        files.sort()
        for name in dirs + files:
            if len(members) >= MAX_MEMBERS or time.monotonic() > deadline:
                fail("Complete npm cache inventory exceeded its bounded budget; retained")
            path = Path(directory) / name
            rel = path.relative_to(source).as_posix()
            info = g.plain(path)
            if not info.st_dev or not info.st_ino:
                fail("Unknown cache member identity; retained")
            is_dir = stat.S_ISDIR(info.st_mode)
            if not is_dir and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                fail("Special/hardlinked cache member retained")
            kind = layout(rel, is_dir)
            extra = metadata_guard.metadata(path, is_dir)
            if sys.platform == "darwin" and extra.get("darwin_acl") is None:
                fail("Unknown/unsupported macOS cache ACL metadata; retained")
            record = {"path": rel, "type": "directory" if is_dir else "file", "kind": kind, "metadata": extra}
            if is_dir:
                record["identity"] = n.fingerprint(info)
            else:
                if total + info.st_size > MAX_BYTES:
                    fail("Complete npm cache content budget exceeded; retained")
                record.update(n.file_record(path, deadline=deadline))
                total += record["identity"]["size"]
                if kind == "content":
                    algo = rel.split("/")[1]
                    h = hashlib.new(algo)
                    with g.guarded_file(path) as (fd, _):
                        while True:
                            if time.monotonic() > deadline:
                                fail("Cache content-address validation exceeded its time budget")
                            block = os.read(fd, 1024 * 1024)
                            if not block:
                                break
                            h.update(block)
                        if n.fingerprint(os.fstat(fd)) != record["identity"]:
                            fail("Cache payload changed during address validation")
                    if h.hexdigest() != "".join(rel.split("/")[2:]):
                        fail("Cache payload does not match its content address; retain for review")
                elif kind == "index":
                    validate_index(path, rel, record["sha256"])
                elif kind == "verification-metadata":
                    raw, check = read_bytes(path, 64)
                    if check != {k: v for k, v in record.items() if k in {"identity", "sha256"}} or not re.fullmatch(rb"[0-9]+\s*", raw):
                        fail("Unknown verification metadata retained")
            members.append(record)
    # One additional metadata traversal, not one complete tree walk per file.
    seen = []
    for directory, dirs, files in os.walk(source, topdown=True, followlinks=False, onerror=error):
        if time.monotonic() > deadline:
            fail("Cache second-pass budget exceeded; retained")
        g.ancestors(directory)
        dirs.sort()
        files.sort()
        for name in dirs + files:
            if len(seen) >= MAX_MEMBERS:
                fail("Cache grew beyond member budget")
            path = Path(directory) / name
            info = g.plain(path)
            seen.append((path.relative_to(source).as_posix(), n.fingerprint(info),
                         metadata_guard.metadata(path, stat.S_ISDIR(info.st_mode))))
    if (seen != [(r["path"], r["identity"], r["metadata"]) for r in members]
            or root_id != g.root_identity(source) or root_metadata != metadata_guard.metadata(source, True)):
        fail("Cache changed during complete inspection")
    return {"root_identity": root_id, "root_metadata": root_metadata, "members": members, "logical_bytes": total,
            "member_count": len(members), "complete": True, "tree_passes": 2}


def inspect(project_value, cache_rel, assessment_path, node, cli):
    project = g.project_root(project_value)
    report = {"schema": SCHEMA, "version": VERSION, "operation": OPERATION, "created_at": g.utc(),
              "project": str(project), "project_identity": g.root_identity(project), "cache": cache_rel,
              "assessment_path": str(g.absolute(assessment_path)), "node_path": str(g.absolute(node)),
              "npm_cli_path": str(g.absolute(cli)), "status": "blocked", "reasons": [], "sources": SOURCES,
              "scope": "Only the admitted _cacache subtree; original _logs, _npx, producer, source, lockfiles and application state survive",
              "concurrency": "Requires explicit idle confirmation after all writers/consumers are reviewed. Cooperative locks and macOS advisory locks do not freeze unrelated native writers.",
              "atomicity": "Same-volume unique detach reduces original-path races; native recursive removal is not an exact manifest operation. A writer with an existing handle or access to the detached path can still race; unknown activity refuses execution.",
              "failure": "Detach itself releases zero bytes. Interrupted/native failed results retain exact detached location for review, never automatically retry/restore over a recreated cache."}
    try:
        cache, source = cache_scope(project, cache_rel)
        report["provenance"] = qualify(project, cache_rel, source, assessment_path)
        report["native_tool"] = probe_tool(project, node, cli)
        report["snapshot"] = snapshot(source)
        report["cache_identity"] = g.root_identity(cache)
        report["status"] = "executable"
    except (OSError, g.GuardError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        if g.fatal_io(exc):
            raise
        report["reasons"].append(str(exc))
    return report


def npm_command(tool, detached_cache):
    # Never accept argv from the plan. cache clean has no project hook or network
    # path; all options are fixed, package configuration is not inherited.
    # npm refuses loading one physical null path as both user and global config.
    # Two distinct guard-created empty config files avoid reading either real
    # configuration and work on Windows as well as POSIX.
    return [tool["node"], tool["npm_cli"], "--userconfig=" + str(detached_cache / ".storage-empty-user.npmrc"),
            "--globalconfig=" + str(detached_cache / ".storage-empty-global.npmrc"),
            "--cache=" + str(detached_cache), "--prefix=" + str(detached_cache),
            "--logs-max=0", "--loglevel=silent", "--update-notifier=false", "--audit=false",
            "--fund=false", "--ignore-scripts=true", "--offline=true", "--progress=false",
            "--timing=false", "--color=false", "cache", "clean", "--force"]


def comparable(report):
    return {k: v for k, v in report.items() if k != "created_at"}


def rename_snapshot_matches(before, after, destination):
    if before == after:
        return True
    # exFAT file IDs derive from the directory entry: moving the root to a
    # different parent deliberately changes that root's ID. Descendant IDs,
    # metadata, all content hashes, membership and volume must remain exact.
    # Other filesystems do not get this exception.
    if os.name != "nt":
        return False
    import ctypes
    volume_name, fs_name = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
    serial, maximum, flags = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(str(destination.anchor), volume_name, len(volume_name),
            ctypes.byref(serial), ctypes.byref(maximum), ctypes.byref(flags), fs_name, len(fs_name))
    if not ok or fs_name.value.casefold() != "exfat":
        return False
    if before["root_identity"]["device"] != after["root_identity"]["device"]:
        return False
    return {k: v for k, v in before.items() if k != "root_identity"} == {k: v for k, v in after.items() if k != "root_identity"}


def evidence_fd_record(fd, path):
    private_io_path(path)
    before = n.fingerprint(os.fstat(fd))
    if before["size"] > MAX_EVIDENCE:
        fail("Retained evidence exceeds its read limit")
    os.lseek(fd, 0, os.SEEK_SET)
    digest, count = hashlib.sha256(), 0
    while True:
        data = os.read(fd, 65536)
        if not data:
            break
        count += len(data)
        if count > MAX_EVIDENCE:
            fail("Retained evidence grew while guarded")
        digest.update(data)
    if before != n.fingerprint(os.fstat(fd)) or before != n.fingerprint(g.plain(path, False)):
        fail("Retained evidence changed while guarded")
    if os.name == "nt" and not g.only_default_stream(path):
        fail("Retained evidence gained an additional stream")
    return {"identity": before, "sha256": digest.hexdigest()}


@contextlib.contextmanager
def guarded_provenance(project, provenance):
    """Keep every policy-bearing evidence byte guarded through native return.

    Windows handles deny shared write/delete and anchor ancestors. POSIX flock
    is cooperative; post-checks detect observed drift but cannot undo deletion
    if a noncooperating writer ignored the prerequisite idle condition.
    """
    entries = [(private_io_path(provenance["assessment"]), provenance["assessment_record"]),
               (n.scoped_path(project, provenance["producer_path"], False), provenance["producer_record"]),
               (n.scoped_path(project, provenance["existing_log_path"], False), provenance["existing_log_record"])]
    seen, opened = {}, []
    with contextlib.ExitStack() as stack:
        for path, expected in entries:
            key = g.key(path)
            if key in seen:
                if seen[key] != expected:
                    fail("Conflicting retained evidence identity")
                continue
            seen[key] = expected
            fd, _ = stack.enter_context(g.guarded_file(path))
            if evidence_fd_record(fd, path) != expected:
                fail("Provenance changed before native start; detached data retained")
            opened.append((fd, path, expected))
        yield
        for fd, path, expected in opened:
            if evidence_fd_record(fd, path) != expected:
                fail("Provenance changed during native operation; result requires review, do not retry")


def apply(args):
    if not args.confirm_idle:
        fail("Require --confirm-idle after reviewing/stopping all cache writers and consumers; no producer is stopped by this tool")
    private_io_path(args.receipt)
    plan, digest = g.read_json(private_io_path(args.plan))
    if digest != args.authorize_plan:
        fail("Authorized plan hash differs from exact plan bytes")
    if plan.get("schema") != SCHEMA or plan.get("operation") != OPERATION or plan.get("status") != "executable":
        fail("Only an executable npm plan may be applied")
    project = g.project_root(plan["project"])
    output = output_path(args.receipt, project)
    cache = n.scoped_path(project, plan["cache"], True)
    # Stable per-cache claim; choosing a different receipt directory must not
    # create a replay bypass.
    claim = cache / (".storage-npm-used-" + digest)
    if os.path.lexists(claim):
        fail("Single-use plan already claimed; reconcile original receipt, do not retry")
    cache, source = cache_scope(project, plan["cache"])
    lock = cache / (".storage-npm-lock-" + hashlib.sha256(str(source).encode()).hexdigest()[:24])
    lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    lock_id = n.fingerprint(os.fstat(lock_fd))
    receipt = {"schema": SCHEMA, "operation": OPERATION, "plan_sha256": digest,
               "project": str(project), "original_source": str(source), "started_at": g.utc(),
               "status": "preflight", "automatic_retry": False, "exact_delete_manifest": False,
               "observed_removed_logical_bytes": 0, "native_result": None}
    receipt_id = None
    try:
        with n.anchored_cache(cache):
            current = inspect(project, plan["cache"], plan["assessment_path"], plan["node_path"], plan["npm_cli_path"])
            if comparable(current) != comparable(plan):
                fail("Cache content/membership, tool, root, assessment, or provenance changed; review and create a fresh plan")
            write_report(output, receipt)
            info = g.plain(output, False)
            receipt_id = {"device": info.st_dev, "inode": info.st_ino}
            with os.fdopen(os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600), "wb") as stream:
                stream.write((digest + "\n" + str(output) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            stage = cache / (".storage-npm-detached-" + uuid.uuid4().hex)
            stage.mkdir(mode=0o700)
            g.ancestors(stage)
            for name in (".storage-empty-user.npmrc", ".storage-empty-global.npmrc"):
                with open(stage / name, "xb") as config:
                    config.flush()
                    os.fsync(config.fileno())
            receipt["detached_cache"] = str(stage)
            receipt["detached_source"] = str(stage / "_cacache")
            receipt["stage_identity"] = g.root_identity(stage)
            receipt["status"] = "detach_pending_result_unknown"
            write_report(output, receipt, False, receipt_id)
            g.same_root(source, current["snapshot"]["root_identity"])
            os.rename(source, stage / "_cacache")  # Unique same-volume destination, no overwrite.
            receipt["status"] = "detached_no_space_released"
            write_report(output, receipt, False, receipt_id)
            detached_snapshot = snapshot(stage / "_cacache")
            receipt["detached_root_identity"] = detached_snapshot["root_identity"]
            if not rename_snapshot_matches(current["snapshot"], detached_snapshot, stage):
                fail("Detached payload differs; retained in exact reported location, do not retry")
            if g.root_identity(cache) != current["cache_identity"]:
                fail("Cache parent identity changed")
            # Recheck the trusted implementation immediately before mutation.
            if probe_tool(project, plan["node_path"], plan["npm_cli_path"]) != current["native_tool"]:
                fail("Node/npm implementation changed after detach; detached data retained")
            # The second tool probe and detached snapshot are potentially long.
            # An earlier matching producer record cannot authorize a later
            # native operation after that producer/review has changed.
            final_provenance = qualify(project, plan["cache"], source, plan["assessment_path"])
            if final_provenance != plan["provenance"]:
                fail("Provenance changed after detach; detached data retained")
            before_free = shutil.disk_usage(project).free
            receipt["status"] = "native_evidence_guard_pending"
            write_report(output, receipt, False, receipt_id)
            with guarded_provenance(project, final_provenance), n.anchored_cache(stage):
                receipt["status"] = "native_started_result_unknown"
                write_report(output, receipt, False, receipt_id)
                native = run_native(npm_command(current["native_tool"], stage), stage, stage)
                receipt["native_result"] = native
            if (native["returncode"] == 0 and not native["timed_out"] and not native["output_truncated"]
                    and not os.path.lexists(stage / "_cacache")):
                receipt["status"] = "native_completed_verified_detached_scope"
                receipt["observed_removed_logical_bytes"] = current["snapshot"]["logical_bytes"]
                receipt["observed_removed_file_count"] = sum(m["type"] == "file" for m in current["snapshot"]["members"])
            else:
                receipt["status"] = "native_failed_or_uncertain_no_retry"
            receipt["original_cache_recreated"] = os.path.lexists(source)
            receipt["source_volume_free_delta"] = shutil.disk_usage(project).free - before_free
            receipt["measurement_note"] = "Logical payload removed and observed free-space change are distinct; other disk activity can change free space. A recreated original cache is never touched."
            receipt["finished_at"] = g.utc()
            write_report(output, receipt, False, receipt_id)
    except BaseException as exc:
        if receipt_id is not None:
            receipt["status"] = "stopped_requires_review_no_retry"
            receipt["error"] = str(exc)
            receipt["finished_at"] = g.utc()
            write_report(output, receipt, False, receipt_id)
        raise
    finally:
        os.close(lock_fd)
        if os.path.lexists(lock):
            with g.guarded_file(lock, delete=True) as (fd, unlink):
                if n.fingerprint(os.fstat(fd)) != lock_id:
                    fail("Guard-owned lock changed; retained for review")
                unlink()
    print(json.dumps({"receipt": str(output), "status": receipt["status"],
                      "observed_removed_logical_bytes": receipt["observed_removed_logical_bytes"]}))
    return 0 if receipt["status"] == "native_completed_verified_detached_scope" else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("plan", help="Read-only qualification; creates only the explicitly selected report")
    p.add_argument("--project", required=True)
    p.add_argument("--cache", required=True, help="Existing project-relative npm cache root, not its _cacache child")
    p.add_argument("--assessment", required=True, help="Retained, truthful agent review outside the project")
    p.add_argument("--node", required=True, help="Trusted installed native Node executable; no shell launcher")
    p.add_argument("--npm-cli", required=True, help="Trusted installed bin/npm-cli.js; no project local npm")
    p.add_argument("--output", required=True)
    a = sub.add_parser("apply", help="Single-use authorized detach and native clean; requires idle confirmation")
    a.add_argument("--plan", required=True)
    a.add_argument("--authorize-plan", required=True)
    a.add_argument("--receipt", required=True)
    a.add_argument("--confirm-idle", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode == "plan":
            # Refuse sensitive output destinations before inspecting evidence.
            private_io_path(args.output)
            report = inspect(args.project, args.cache, args.assessment, args.node, args.npm_cli)
            output = output_path(args.output, g.absolute(report["project"]))
            digest = write_report(output, report)
            print(json.dumps({"plan": str(output), "plan_sha256": digest, "status": report["status"], "reasons": report["reasons"]}))
            return 0 if report["status"] == "executable" else 2
        return apply(args)
    except (OSError, g.GuardError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"status": "stopped", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
