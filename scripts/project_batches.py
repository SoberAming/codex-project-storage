#!/usr/bin/env python3
"""Resumable, metadata-only project/task inventory. No cleanup or project code runs.

The ledger is created outside the project. File identities are attributed once
across batches; multiple-link files are retained individually, not by category.
Every directory is enumerated once into a durable work queue. Large single
directories have a separate bounded enumeration limit and fail explicitly.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time
import uuid


def sibling(name, filename):
    path = Path(__file__).absolute().with_name(filename)
    for parent in (path, *path.parents):
        if os.path.islink(parent) or getattr(os.lstat(parent), "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Linked guard code refused")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


P = sibling("_batch_profiler", "project_profiler.py")
G = sibling("_batch_boundaries", "storage_guard.py")
VERSION = "1.6.0"
SCHEMA = "project-storage-batches-v1"
TASK_CONTAINERS = {".tmp", ".runtime", "task-runs", "task_runs", "outputs", "releases"}
PRIVATE = P.STATE_DIRS | {".git"}
BUILD_PRUNE = PRIVATE | P.DEPENDENCY_DIRS | {
    "assets", "media", "public", "static", "data", "models", "prepared",
    "rollback", "recovery", "backups", "browser-data", "source-data"}


def relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise G.GuardError("A project-relative slash path is required")
    if value != "." and any(x in ("", ".", "..") or ":" in x for x in value.split("/")):
        raise G.GuardError("Unsafe relative path")
    return value


def private(rel):
    return any(x.lower() in PRIVATE for x in rel.split("/"))


def admin(path, root=None):
    path = G.protect_agent_state_path(path)
    if any(p.lower() in PRIVATE for p in path.parts):
        raise G.GuardError("Private/Agent-state ledger location refused")
    G.ancestors(path.parent, missing=True)
    if root is not None and (G.below(path, root) or G.below(root, path)):
        raise G.GuardError("Ledger must be outside and not contain the project")
    return path


def new_json(path, value):
    G.write_json(path, value)


def manifest_path(folder):
    return folder / "project-batches.json"


@contextlib.contextmanager
def ledger(value):
    folder = admin(value); G.ancestors(folder)
    manifest, _ = G.read_json(manifest_path(folder))
    if manifest.get("schema") != SCHEMA:
        raise G.GuardError("Not a project-batch ledger")
    G.same_root(folder, manifest["ledger_identity"])
    root = G.project_root(manifest["project"], manifest.get("codex_home"))
    G.same_root(root, manifest["project_identity"])
    database = folder / "inventory.sqlite"
    before = G.plain(database, False)
    if before.st_nlink != 1 or P.identity(before) != manifest["inventory_identity"]:
        raise G.GuardError("Ledger database identity/link changed")
    lock = folder / ".command-lock"
    with G.new_file(lock) as handle:
        handle.write(json.dumps({"pid": os.getpid(), "at": G.utc()}))
        handle.flush(); os.fsync(handle.fileno())
    lock_identity = P.identity(os.lstat(lock))
    db = None
    try:
        db = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA trusted_schema=OFF")
        if db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0] != SCHEMA:
            raise G.GuardError("Ledger schema mismatch")
        if P.identity(G.plain(database, False)) != manifest["inventory_identity"]:
            raise G.GuardError("Ledger replaced while opening")
        yield folder, root, manifest, db
    finally:
        if db is not None: db.close()
        if P.identity(os.lstat(lock)) == lock_identity: os.unlink(lock)


def discover(args):
    root = G.project_root(args.project, args.codex_home)
    folder = admin(args.output, root)
    if os.path.lexists(folder):
        raise G.GuardError("Ledger output must be new; use scan to resume")
    folder.mkdir(parents=True); G.ancestors(folder)
    units = []
    if args.unit:
        units = [relative(x) for x in args.unit]
        if len(set(units)) != len(units): raise G.GuardError("Duplicate unit")
        for a in units:
            if private(a): raise G.GuardError("State unit refused")
            for b in units:
                if a != b and (b.startswith(a + "/") or a == "."):
                    raise G.GuardError("Overlapping units refused")
    else:
        with P.anchored_directory(root) as anchor:
            with os.scandir(anchor) as entries:
                names = []
                for entry in entries:
                    if len(names) >= args.max_units:
                        raise G.GuardError("Discovery entry budget reached; select explicit units")
                    names.append(entry.name)
        for name in sorted(names):
            path = root / name
            s = os.lstat(path)
            if name.lower() in PRIVATE or getattr(s, "st_file_attributes", 0) & 0x400:
                continue
            if stat.S_ISDIR(s.st_mode) and name.lower() in TASK_CONTAINERS:
                with P.anchored_directory(path) as anchor:
                    with os.scandir(anchor) as children:
                        for entry in children:
                            if len(units) >= args.max_units:
                                raise G.GuardError("Task budget reached; select explicit units")
                            units.append(name + "/" + entry.name)
            else:
                units.append(name)
    if not units: raise G.GuardError("No ordinary units discovered")
    if len(units) > args.max_units: raise G.GuardError("Too many units")
    database = folder / "inventory.sqlite"
    fd = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd)
    db = sqlite3.connect(database)
    try:
        db.executescript("""
          PRAGMA journal_mode=DELETE;
          CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
          CREATE TABLE units(path TEXT PRIMARY KEY,status TEXT NOT NULL,error TEXT,finished TEXT);
          CREATE TABLE work(id INTEGER PRIMARY KEY,unit TEXT NOT NULL,path TEXT UNIQUE NOT NULL,
                            done INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE files(path TEXT PRIMARY KEY,unit TEXT NOT NULL,identity TEXT NOT NULL,
             size INTEGER NOT NULL,allocated INTEGER,links INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,
             category TEXT NOT NULL,artifact TEXT,protection TEXT NOT NULL);
          CREATE INDEX file_identity ON files(identity);
          CREATE INDEX file_artifact ON files(artifact);
          CREATE INDEX work_pending ON work(done,unit,id);
          CREATE TABLE excluded(path TEXT PRIMARY KEY,unit TEXT,reason TEXT,identity TEXT);
          CREATE TABLE directory_checkpoints(path TEXT PRIMARY KEY,unit TEXT,device TEXT,
                                              inode TEXT,mtime_ns INTEGER);
          CREATE TABLE batches(id INTEGER PRIMARY KEY,at TEXT,processed INTEGER,seconds REAL);
        """)
        db.execute("INSERT INTO metadata VALUES('schema',?)", (SCHEMA,))
        db.executemany("INSERT INTO units(path,status) VALUES(?,'pending')", [(x,) for x in units])
        db.executemany("INSERT INTO work(unit,path) VALUES(?,?)", [(x,x) for x in units])
        db.commit()
    finally:
        db.close()
    manifest = {"schema": SCHEMA, "tool_version": VERSION, "project": str(root),
        "project_identity": G.root_identity(root), "codex_home": args.codex_home,
        "ledger_identity": G.root_identity(folder), "inventory_identity": P.identity(os.lstat(database)),
        "created_at": G.utc(), "focus": args.focus, "unit_count": len(units),
        "scope_explicit_units": bool(args.unit),
        "directory_entry_limit": args.max_directory_entries,
        "project_payload_bytes_read": 0, "source_files_modified": 0,
        "snapshot_note": "Live metadata at per-unit observation times; no net-growth or disposal claim"}
    new_json(manifest_path(folder), manifest)
    result = {"ledger": str(folder), "units": len(units), "focus": args.focus, "read_only_project": True}
    print(json.dumps(result)); return result


def build_root(rel):
    parts = rel.split("/")
    for i, part in enumerate(parts):
        if part == ".next": return "/".join(parts[:i+1])
    return None


def excluded(db, unit, rel, reason, s):
    db.execute("INSERT OR REPLACE INTO excluded VALUES(?,?,?,?)",
               (rel, unit, reason, json.dumps(P.identity(s))))


def process(root, manifest, db, row):
    unit, rel = row["unit"], row["path"]; relative(rel)
    path = root if rel == "." else root.joinpath(*rel.split("/"))
    # The configured state/root boundary is revalidated when opening the ledger.
    # Private names are pruned below and links are never followed.
    G.ancestors(path.parent)
    parent_rel=path.parent.relative_to(root).as_posix() if path!=root else None
    if parent_rel is not None:
        checkpoint=db.execute("SELECT device,inode,mtime_ns FROM directory_checkpoints WHERE path=?",(parent_rel,)).fetchone()
        if checkpoint is not None:
            parent=os.lstat(path.parent)
            if (str(parent.st_dev),str(parent.st_ino),parent.st_mtime_ns)!=tuple(checkpoint):
                raise G.GuardError("Directory identity/membership changed between batches; unit retained")
    s = os.lstat(path)
    if private(rel) or getattr(s, "st_file_attributes", 0) & 0x400 or stat.S_ISLNK(s.st_mode):
        excluded(db, unit, rel, "private/state/link boundary; not followed or body-read", s); return
    artifact = build_root(rel)
    if stat.S_ISDIR(s.st_mode):
        if (manifest["focus"] == "builds" and not artifact and path.name.lower() in BUILD_PRUNE):
            excluded(db, unit, rel, "build-focused scan excludes this retained subtree; size unknown", s); return
        count = 0
        with P.anchored_directory(path) as anchor:
            before = P.fingerprint(os.lstat(path))
            with os.scandir(anchor) as entries:
                for entry in entries:
                    count += 1
                    if count > manifest["directory_entry_limit"]:
                        raise G.GuardError("Single-directory entry budget reached; select narrower known units")
                    child = entry.name if rel == "." else rel + "/" + entry.name
                    relative(child)
                    db.execute("INSERT OR IGNORE INTO work(unit,path) VALUES(?,?)", (unit,child))
            if P.fingerprint(os.lstat(path)) != before:
                raise G.GuardError("Directory changed during its name snapshot; explicit refresh needed")
            db.execute("INSERT OR REPLACE INTO directory_checkpoints VALUES(?,?,?,?,?)",
                       (rel,unit,str(s.st_dev),str(s.st_ino),s.st_mtime_ns))
        return
    if not stat.S_ISREG(s.st_mode):
        excluded(db, unit, rel, "special file retained", s); return
    if manifest["focus"] == "builds" and not artifact:
        return
    identity = str(s.st_dev) + ":" + str(s.st_ino) if s.st_ino else "unknown:" + rel
    category = "framework_cache_and_build" if artifact else P.file_class(path)[0]
    protection = ("retained_shared_identity" if s.st_nlink > 1 else
                  "retained_unknown_identity" if not s.st_ino else "review_required")
    allocation = P.allocated(path,s)
    db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?)",
        (rel,unit,identity,s.st_size,allocation,s.st_nlink,s.st_mtime_ns,category,artifact,protection))


def scan(args):
    if not 1 <= args.max_files <= 1000000 or not 1 <= args.max_seconds <= 300:
        raise G.GuardError("Invalid batch budget")
    start = time.monotonic(); processed = 0
    with ledger(args.ledger) as (folder, root, manifest, db):
        if args.unit:
            for x in args.unit:
                if not db.execute("SELECT 1 FROM units WHERE path=?", (x,)).fetchone():
                    raise G.GuardError("Unknown exact unit; discover explicit units in a new ledger")
        db.execute("BEGIN")
        while processed < args.max_files and time.monotonic()-start < args.max_seconds:
            sql = "SELECT w.* FROM work w JOIN units u ON u.path=w.unit WHERE w.done=0 AND u.status IN ('pending','scanning')"
            params = []
            if args.unit:
                sql += " AND w.unit IN (" + ",".join("?" for _ in args.unit) + ")"; params.extend(args.unit)
            row = db.execute(sql + " ORDER BY u.path,w.id LIMIT 1", params).fetchone()
            if row is None: break
            try:
                db.execute("SAVEPOINT entry")
                db.execute("UPDATE units SET status='scanning' WHERE path=?", (row["unit"],))
                process(root, manifest, db, row)
                db.execute("UPDATE work SET done=1 WHERE id=?", (row["id"],))
                if not db.execute("SELECT 1 FROM work WHERE unit=? AND done=0", (row["unit"],)).fetchone():
                    db.execute("UPDATE units SET status='complete',finished=? WHERE path=?", (G.utc(),row["unit"]))
                db.execute("RELEASE entry")
            except (OSError,G.GuardError,P.ProfileError) as exc:
                db.execute("ROLLBACK TO entry"); db.execute("RELEASE entry")
                db.execute("UPDATE units SET status='error',error=? WHERE path=?", (type(exc).__name__+": "+str(exc),row["unit"]))
                if P.fatal_io(exc):
                    db.commit()
                    raise
            processed += 1
            if processed % 256 == 0:
                db.commit(); db.execute("BEGIN")
        with db:
            db.execute("INSERT INTO batches(at,processed,seconds) VALUES(?,?,?)", (G.utc(),processed,time.monotonic()-start))
        counts = dict(db.execute("SELECT status,COUNT(*) FROM units GROUP BY status").fetchall())
        result = {"processed_entries":processed,"seconds":round(time.monotonic()-start,3),"units":counts,
            "pending_entries":db.execute("SELECT COUNT(*) FROM work w JOIN units u ON w.unit=u.path WHERE w.done=0 AND u.status!='error'").fetchone()[0],
            "project_payload_bytes_read":0,"source_files_modified":0}
        print(json.dumps(result)); return result


def report(args):
    with ledger(args.ledger) as (folder, root, manifest, db):
        tasks = [dict(x) for x in db.execute("SELECT * FROM units ORDER BY path")]
        units = [dict(x) for x in db.execute("""
          SELECT artifact AS path,COUNT(*) AS path_files,SUM(size) AS logical_at_paths,
          SUM(CASE WHEN links=1 AND protection='review_required' THEN size ELSE 0 END) AS independent_review_bytes,
          SUM(CASE WHEN links>1 THEN size ELSE 0 END) AS shared_retained_at_paths,
          SUM(CASE WHEN links>1 THEN 1 ELSE 0 END) AS shared_files,
          COUNT(DISTINCT unit) AS observation_unit_count FROM files WHERE artifact IS NOT NULL
          GROUP BY artifact ORDER BY independent_review_bytes DESC,path""")]
        by_task={x["path"]:x for x in tasks}
        for value in units:
            owners = [x[0] for x in db.execute("SELECT DISTINCT unit FROM files WHERE artifact=? ORDER BY unit",(value["path"],))]
            value["observation_units"] = owners
            value["metadata_complete"] = all(by_task[x]["status"]=="complete" for x in owners)
            value["approved_release_bytes"] = 0
        unique = db.execute("SELECT SUM(n),COUNT(*) FROM (SELECT MAX(size) n FROM files GROUP BY identity)").fetchone()
        conflict = db.execute("SELECT COUNT(*) FROM (SELECT identity FROM files GROUP BY identity HAVING MIN(size)!=MAX(size))").fetchone()[0]
        units_complete=all(t["status"]=="complete" for t in tasks)
        result = {"schema":SCHEMA,"tool_version":VERSION,"project":str(root),"at":G.utc(),
            "focus":manifest["focus"],"units":tasks,"build_units":units,"build_units_truncated":False,
            "observed_unique_logical_bytes":unique[0] or 0,"observed_unique_identities":unique[1],
            "identity_size_conflicts":conflict,"file_paths":db.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "excluded":[dict(x) for x in db.execute("SELECT path,unit,reason FROM excluded ORDER BY path")],
            "batches":[dict(x) for x in db.execute("SELECT * FROM batches ORDER BY id")],
            "coverage":{"selected_units_complete":units_complete,
                "project_complete":units_complete and manifest["focus"]=="metadata" and not manifest["scope_explicit_units"],
                "scope":"explicit discovered units and declared focus; excluded sizes unknown; no global reference/lifecycle claim",
                "all_paths_preserved_in_ledger":True,"anonymous_overflow_buckets":False},
            "approved_release_bytes":0,"executed_release_bytes":0,"project_payload_bytes_read":0}
        output = admin(args.output, root)
        if G.below(output, folder): raise G.GuardError("Export report outside ledger to avoid self observation")
        new_json(output,result)
        print(json.dumps({"report":str(output),"build_units":len(units),"complete_units":sum(t["status"]=="complete" for t in tasks),
                          "pending_units":sum(t["status"] in ("pending","scanning") for t in tasks),
                          "project_complete":result["coverage"]["project_complete"],
                          "selected_units_complete":units_complete,"read_only_project":True}))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version",action="version",version=VERSION)
    sub = parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("discover")
    p.add_argument("--project",required=True); p.add_argument("--output",required=True)
    p.add_argument("--codex-home"); p.add_argument("--unit",action="append",default=[])
    p.add_argument("--focus",choices=("metadata","builds"),default="metadata")
    p.add_argument("--max-units",type=int,default=20000); p.add_argument("--max-directory-entries",type=int,default=200000)
    p=sub.add_parser("scan")
    p.add_argument("--ledger",required=True); p.add_argument("--unit",action="append",default=[])
    p.add_argument("--max-files",type=int,default=10000); p.add_argument("--max-seconds",type=float,default=30)
    p=sub.add_parser("report")
    p.add_argument("--ledger",required=True); p.add_argument("--output",required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="discover":
            if not 1<=args.max_units<=100000 or not 1<=args.max_directory_entries<=1000000: raise G.GuardError("Invalid discovery budget")
            discover(args)
        elif args.command=="scan": scan(args)
        else: report(args)
        return 0
    except (OSError,G.GuardError,sqlite3.Error,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({"status":"refused","error":str(exc),"project_modified":False,"no_automatic_retry":True}),file=sys.stderr)
        return 2


if __name__=="__main__": sys.exit(main())
