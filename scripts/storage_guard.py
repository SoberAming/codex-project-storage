#!/usr/bin/env python3
"""Read-only project storage inventory, exact cache plans, and guarded deletion.

Python 3.10+, standard library only. No recursive delete, process termination,
privilege changes, migration, compression, or global Codex cache cleanup.
Cache minimum age defaults to 48 hours; dependency/tool-managed data is retained.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import hashlib
import json
import importlib.util
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time

VERSION = "1.3.0"
POLICY = "project-cache-exact-v1"
MIN_AGE = 48.0
CACHE_MAX_BYTES = 64 * 1024 * 1024
PRUNE = {".codex", ".agents", ".git", "sessions", "archived_sessions",
         "thread_history", "credentials", "secrets"}
MANAGED_DIRS = {"node_modules", ".venv", "venv", "site-packages", "__pypackages__",
                ".uv-cache", ".pnpm-store", ".npm", ".yarn", ".tox", ".nox", ".conda"}
PROTECTED = PRUNE | {"state", "index", "indexes", "indices", "backup", "backups",
    "recovery", "restore", "releases", "release", "dist", "build", "out",
    "assets", "media", "public", "static", "prepared", "rollback", "worktrees",
    "素材", "备份", "恢复", "发布"} | MANAGED_DIRS
CACHE_SCAN_PRUNE = PROTECTED
SOURCE_EXT = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".html", ".css", ".scss", ".sass", ".less", ".c", ".h", ".cpp", ".cc",
    ".hpp", ".rs", ".go", ".java", ".kt", ".swift", ".m", ".mm", ".rb",
    ".php", ".sh", ".ps1", ".bat", ".cmd", ".sql", ".toml", ".yaml", ".yml",
    ".json", ".md", ".txt", ".doc", ".docx", ".pdf", ".pptx", ".xlsx",
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".mp4", ".mov", ".mp3",
    ".wav", ".zip", ".7z", ".tar", ".gz", ".bak"}
PYC = re.compile(r"^(.+)\.cpython-[0-9]{2,3}(?:\.opt-[12])?\.pyc$")
PACK = re.compile(r"^(?:\.next/cache/webpack|node_modules/\.cache/webpack)/"
                  r"[A-Za-z0-9_-]+/[0-9]+\.pack(?:\.gz)?(?:\.old)?$")
LOCKS = (".next/lock", ".next/dev/lock", ".next/cache/webpack/.lock",
         "node_modules/.cache/webpack/.lock")


class GuardError(Exception):
    pass


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def volume_free(root):
    try:
        return shutil.disk_usage(root).free
    except OSError:
        return None


def plain(path, directory=None):
    s = os.lstat(path)
    if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
        raise GuardError(f"Link/reparse entry refused: {path}")
    if directory is True and not stat.S_ISDIR(s.st_mode):
        raise GuardError(f"Expected ordinary directory: {path}")
    if directory is False and not stat.S_ISREG(s.st_mode):
        raise GuardError(f"Expected ordinary file: {path}")
    return s


def absolute(path):
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def key(path):
    return os.path.normcase(str(absolute(path)))


def below(path, root):
    try:
        return os.path.commonpath((key(path), key(root))) == key(root)
    except ValueError:
        return False


def ancestors(path, missing=False):
    path = absolute(path)
    for p in reversed((path, *path.parents)):
        try:
            plain(p, directory=True)
        except FileNotFoundError:
            if not missing:
                raise


def project_root(path, codex_home=None):
    root = absolute(path)
    ancestors(root)
    home = absolute(Path.home())
    codex = absolute(codex_home or os.environ.get("CODEX_HOME", home / ".codex"))
    # Do not resolve a relocated Codex home through a junction/symlink implicitly.
    try:
        ancestors(codex)
    except FileNotFoundError:
        pass
    def same(a, b):
        try:
            return os.path.samefile(a, b)
        except FileNotFoundError:
            return False
    def contains_state(state):
        # A missing configured state path is still protected if it can appear
        # inside the selected project later. Resolve only path/identity metadata
        # for an explicit relocated state root; never walk its contents.
        if below(state, root):
            return True
        physical = absolute(os.path.realpath(state))
        return (below(physical, root) or any(same(root, p)
            for p in (state, *state.parents, physical, *physical.parents)))
    sqlite_value = os.environ.get("CODEX_SQLITE_HOME")
    if sqlite_value:
        sqlite = absolute(sqlite_value)
        # This configured state root may have a plain name or an explicit
        # relocation link. Inspect only identities; never walk or read its data.
        # Existing project ancestors must already be ordinary directories.
        if (below(root, sqlite) or contains_state(sqlite)
                or any(same(p, sqlite) for p in (root, *root.parents))):
            raise GuardError("Selected project overlaps CODEX_SQLITE_HOME; select an independent project")
    if contains_state(codex):
        raise GuardError("Selected project contains CODEX_HOME state; select an independent project")
    if root.parent == root or same(root, home) or same(root, codex):
        raise GuardError("Project must be a specific project directory, not a drive/root, home, or CODEX_HOME")
    codex_ancestor = next((p for p in root.parents if same(p, codex)), None)
    worktree = False
    if codex_ancestor:
        parts = root.relative_to(codex_ancestor).parts
        if len(parts) >= 3 and parts[0].lower() == "worktrees":
            repo = codex_ancestor.joinpath(*parts[:3])
            git_stat = plain(repo / ".git")
            worktree = stat.S_ISREG(git_stat.st_mode) or stat.S_ISDIR(git_stat.st_mode)
        if not worktree or any(p.lower() in PRUNE for p in parts):
            raise GuardError("Only an explicit worktrees/<id>/<repo> with ordinary .git may be selected inside CODEX_HOME")
    if any(p.lower() in MANAGED_DIRS for p in root.parts):
        raise GuardError("A dependency/environment/cache subtree cannot be selected as a standalone project")
    if (below(root, codex) and not worktree) or (not worktree and any(p.lower() in PRUNE for p in root.parts)):
        raise GuardError("Project cannot be inside Codex, Git, agent, session, or credential storage")
    return root


def relative_file(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise GuardError("Invalid relative file path")
    parts = relative.split("/")
    if any(p in {"", ".", ".."} or ":" in p for p in parts):
        raise GuardError("Traversal/alternate stream path refused")
    path = root.joinpath(*parts)
    if not below(path, root) or key(path) == key(root):
        raise GuardError("File escaped the project")
    ancestors(path.parent)
    plain(path, directory=False)
    return path


def fingerprint(s):
    return {"device": s.st_dev, "inode": s.st_ino, "size": s.st_size,
            "mtime_ns": s.st_mtime_ns, "links": s.st_nlink}


def root_identity(root):
    s = plain(root, True)
    return {"device": s.st_dev, "inode": s.st_ino}


def same_root(root, identity):
    if root_identity(root) != identity:
        raise GuardError("Project directory identity changed")


def fatal_io(exc):
    return (getattr(exc, "errno", None) in {errno.EIO, getattr(errno, "EBADMSG", -1)}
            or getattr(exc, "winerror", None) in {23, 30, 1117, 1392})


def protected_reason(relative):
    parts = relative.lower().split("/")
    if (any(p in MANAGED_DIRS for p in parts[:-1])
            or any(a == ".cache" and b in {"uv", "pip"} for a, b in zip(parts[:-2], parts[1:-1]))):
        return "dependency/tool-managed data; retained for its native manager"
    if any(p in PROTECTED for p in parts[:-1]):
        return "protected directory or data boundary"
    name = parts[-1]
    if (name in {"auth.json", "config.toml", "history.jsonl", "package-lock.json"}
            or name.startswith((".env", "id_rsa", "id_ed25519"))
            or any(x in name for x in ("credential", "secret", "token", "password"))):
        return "credential/configuration/history boundary"
    if re.search(r"\.(?:jsonl|sqlite3?|db)(?:-(?:wal|shm|journal))?$", name):
        return "session/index/database file (including WAL/SHM)"
    # .pack.gz is an explicit reconstructible webpack format, not a general archive.
    if Path(name).suffix in SOURCE_EXT and not PACK.fullmatch(relative):
        return "source, document, media, archive, or recovery material"
    return None


def managed_marker_reason(root, relative):
    """Metadata only, checked afresh by scan, plan, and immediately before delete."""
    if root.name.lower() in MANAGED_DIRS or (root.parent.name.lower() == ".cache" and root.name.lower() in {"uv", "pip"}):
        return "selected root is dependency/tool-managed data; retained for its native manager"
    directory = root.joinpath(*relative.split("/")[:-1])
    while True:
        for name in ("pyvenv.cfg", "CACHEDIR.TAG"):
            try:
                os.lstat(directory / name)  # Any marker type, including a dangling link, is a boundary.
                return f"dependency/tool-managed marker {name} present; retained"
            except FileNotFoundError:
                pass
            except OSError as exc:
                if fatal_io(exc):
                    raise
                return f"dependency/tool-managed marker {name} unverifiable; retained"
        if directory == root:
            return None
        directory = directory.parent


def activity(root):
    found = []
    for rel in LOCKS:
        p = root.joinpath(*rel.split("/"))
        try:
            ancestors(p.parent)
            plain(p, False)
            found.append(rel)
        except FileNotFoundError:
            pass
        except (OSError, GuardError) as exc:
            if fatal_io(exc):
                raise
            found.append(rel + " (unverifiable)")
    return found


def classify(root, relative, s, min_age, now=None):
    """Recompute policy from paths and current filesystem; never trust a plan kind."""
    why = protected_reason(relative)
    if why:
        return None, why
    parts = relative.split("/")
    evidence = None
    match = PYC.fullmatch(parts[-1]) if len(parts) > 1 and parts[-2] == "__pycache__" else None
    if match:
        marker_reason = managed_marker_reason(root, relative)
        if marker_reason:
            return None, marker_reason
        source_rel = "/".join(parts[:-2] + [match.group(1) + ".py"])
        try:
            source = relative_file(root, source_rel)
            evidence = {"kind": "cpython_bytecode", "source": source_rel,
                        "source_identity": fingerprint(plain(source, False))}
        except (OSError, GuardError) as exc:
            if fatal_io(exc):
                raise
            return None, "bytecode source is absent, linked, or unverifiable"
    elif PACK.fullmatch(relative):
        return None, "webpack-shaped cache retained for review; package.json presence alone is insufficient provenance"
    if evidence is None:
        if ".pytest_cache" in parts:
            return None, "pytest cache retained for review; no executable rule"
        return None, "unknown/mixed data; no executable cache rule"
    if s.st_nlink != 1 or not s.st_ino:
        return None, "hardlink or unavailable file identity; retained"
    if s.st_size > CACHE_MAX_BYTES:
        return None, "cache exceeds the 64 MiB single-file read limit; retained for review"
    age = ((time.time() if now is None else now) * 1e9 - s.st_mtime_ns) / 3.6e12
    if age < min_age:
        return None, "recent/future-dated cache; retained"
    if activity(root):
        return None, "build lock present or unverifiable; retained for review"
    expected_tag = getattr(sys.implementation, "cache_tag", None)
    if sys.implementation.name != "cpython" or not expected_tag or f".{expected_tag}." not in parts[-1]:
        return None, "bytecode belongs to another Python runtime; retained for review"
    if os.name == "nt":
        try:
            if not only_default_stream(root.joinpath(*parts)):
                return None, "file has additional data streams; retained for review"
        except OSError as exc:
            if fatal_io(exc):
                raise
            return None, "cannot verify absence of alternate data streams; retained for review"
    return evidence, None


def validate_cache_fd(fd):
    # Only selected cache bytes are inspected. Never deserialize/execute marshal data.
    os.lseek(fd, 0, os.SEEK_SET)
    header = os.read(fd, 17)
    if (len(header) < 17 or header[:4] != importlib.util.MAGIC_NUMBER
            or int.from_bytes(header[4:8], "little") not in {0, 1, 3}
            or header[16] & 0x7f != ord("c")):
        raise GuardError("Not a verified CPython bytecode cache for this Python runtime")


def safe_output(path, directory=False):
    p = absolute(path)
    ancestors(p if directory and p.exists() else p.parent, missing=True)
    if not directory and os.path.lexists(p):
        raise GuardError(f"Output already exists; choose a new path: {p}")
    p.mkdir(parents=True, exist_ok=True) if directory else p.parent.mkdir(parents=True, exist_ok=True)
    ancestors(p if directory else p.parent)
    return p


def new_file(path):
    p = safe_output(path)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    return os.fdopen(fd, "w", encoding="utf-8", newline="\n")


def write_json(path, value):
    with new_file(path) as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def read_json(path):
    p = absolute(path)
    ancestors(p.parent)
    plain(p, False)
    if p.stat().st_size > 128 * 1024 * 1024:
        raise GuardError("Report/plan is larger than the 128 MiB safety limit")
    with guarded_file(p) as (fd, _):
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            if sum(map(len, chunks)) > 128 * 1024 * 1024:
                raise GuardError("Report/plan grew beyond the safety limit")
        data = b"".join(chunks)
    def reject_constant(value):
        raise GuardError(f"Nonfinite JSON number refused: {value}")
    return json.loads(data, parse_constant=reject_constant), hashlib.sha256(data).hexdigest()


if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes as wt
    K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    class FileInfo(ctypes.Structure):
        _fields_ = [("attrs", wt.DWORD), ("created", wt.FILETIME), ("accessed", wt.FILETIME),
            ("written", wt.FILETIME), ("volume", wt.DWORD), ("size_hi", wt.DWORD),
            ("size_lo", wt.DWORD), ("links", wt.DWORD), ("index_hi", wt.DWORD), ("index_lo", wt.DWORD)]
    class StandardInfo(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_longlong), ("length", ctypes.c_longlong),
                    ("links", wt.DWORD), ("pending", wt.BOOLEAN), ("directory", wt.BOOLEAN)]
    K32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
    K32.CreateFileW.restype = wt.HANDLE
    K32.CloseHandle.argtypes = [wt.HANDLE]
    K32.GetFileInformationByHandle.argtypes = [wt.HANDLE, ctypes.POINTER(FileInfo)]
    K32.GetFileInformationByHandleEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD]
    K32.GetFinalPathNameByHandleW.argtypes = [wt.HANDLE, wt.LPWSTR, wt.DWORD, wt.DWORD]
    K32.SetFileInformationByHandle.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD]
    class StreamInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_longlong), ("name", wt.WCHAR * 296)]
    K32.FindFirstStreamW.argtypes = [wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(StreamInfo), wt.DWORD]
    K32.FindFirstStreamW.restype = wt.HANDLE
    K32.FindNextStreamW.argtypes = [wt.HANDLE, ctypes.POINTER(StreamInfo)]
    K32.FindClose.argtypes = [wt.HANDLE]
    K32.GetVolumePathNameW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD]
    K32.GetVolumeInformationW.argtypes = [wt.LPCWSTR, wt.LPWSTR, wt.DWORD, wt.LPDWORD,
        wt.LPDWORD, wt.LPDWORD, wt.LPWSTR, wt.DWORD]

    def only_default_stream(path):
        volume = ctypes.create_unicode_buffer(32768)
        flags = wt.DWORD()
        if not K32.GetVolumePathNameW(str(path), volume, len(volume)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not K32.GetVolumeInformationW(volume, None, 0, None, None, ctypes.byref(flags), None, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if not flags.value & 0x40000:  # FILE_NAMED_STREAMS: capability, not a guessed filesystem name
            return True
        info = StreamInfo()
        h = K32.FindFirstStreamW(str(path), 0, ctypes.byref(info), 0)
        if h == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            while True:
                if info.name != "::$DATA":
                    return False
                if not K32.FindNextStreamW(h, ctypes.byref(info)):
                    if ctypes.get_last_error() != 38:  # ERROR_HANDLE_EOF
                        raise ctypes.WinError(ctypes.get_last_error())
                    return True
        finally:
            K32.FindClose(h)

    def win_open(path, access, share, directory=False):
        flags = 0x00200000 | (0x02000000 if directory else 0)  # OPEN_REPARSE_POINT / BACKUP_SEMANTICS
        h = K32.CreateFileW(str(path), access, share, None, 3, flags, None)
        if h == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info = FileInfo()
            if not K32.GetFileInformationByHandle(h, ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.attrs & 0x400 or bool(info.attrs & 0x10) != directory:
                raise GuardError("Opened link, reparse point, or wrong file type")
            buf = ctypes.create_unicode_buffer(32768)
            length = K32.GetFinalPathNameByHandleW(h, buf, len(buf), 0)
            if not length or length >= len(buf):
                raise GuardError("Cannot verify opened file's final path")
            final = buf.value
            if final.startswith("\\\\?\\UNC\\"):
                final = "\\\\" + final[8:]
            elif final.startswith("\\\\?\\"):
                final = final[4:]
            if key(final) != key(path):
                raise GuardError("Opened file resolves to a different path")
            return h
        except BaseException:
            K32.CloseHandle(h)
            raise


def allocated(path, s):
    if hasattr(s, "st_blocks"):
        return s.st_blocks * 512
    if os.name == "nt":
        h = win_open(path, 0, 7)
        try:
            info = StandardInfo()
            if not K32.GetFileInformationByHandleEx(h, 1, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            return info.allocation
        finally:
            K32.CloseHandle(h)
    return None


@contextlib.contextmanager
def guarded_file(path, delete=False):
    """Open without links; keep all ancestors anchored while inspecting/deleting."""
    path = absolute(path)
    ancestors(path.parent)
    plain(path, False)
    handles, fd = [], None
    try:
        if os.name == "nt":
            for p in reversed((path.parent, *path.parent.parents)):
                handles.append(win_open(p, 0x80, 3, directory=True))  # no shared DELETE on ancestors
            h = win_open(path, 0x80000000 | (0x10000 if delete else 0), 0)
            try:
                fd = msvcrt.open_osfhandle(h, os.O_RDONLY | os.O_BINARY)
            except BaseException:
                K32.CloseHandle(h)
                raise
            def unlink():
                disposition = wt.BOOL(True)
                if not K32.SetFileInformationByHandle(h, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
                    raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            handle = os.open(path.anchor, flags)
            handles.append(handle)
            for part in path.parent.parts[1:]:
                handle = os.open(part, flags, dir_fd=handle)
                handles.append(handle)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=handles[-1])
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def unlink():
                if fingerprint(os.stat(path.name, dir_fd=handles[-1], follow_symlinks=False)) != fingerprint(os.fstat(fd)):
                    raise GuardError("File changed between opening and unlink")
                ancestors(path.parent)
                if fingerprint(plain(path, False)) != fingerprint(os.fstat(fd)):
                    raise GuardError("File path changed before unlink")
                os.unlink(path.name, dir_fd=handles[-1])
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            raise GuardError("Not a single-link ordinary file")
        yield fd, unlink
    finally:
        if fd is not None:
            os.close(fd)
        for h in reversed(handles):
            K32.CloseHandle(h) if os.name == "nt" else os.close(h)


def hash_fd(fd):
    if os.fstat(fd).st_size > CACHE_MAX_BYTES:
        raise GuardError("Cache exceeds the 64 MiB single-file read limit")
    digest = hashlib.sha256()
    total = 0
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > CACHE_MAX_BYTES:
            raise GuardError("Cache grew beyond the 64 MiB single-file read limit")
        digest.update(chunk)
    return digest.hexdigest()


def codex_metadata(path):
    result = {"path": str(absolute(path)), "scope": "top-level metadata only; directory totals unknown",
              "cross_project": True, "cleanup_candidates": False, "entries": []}
    try:
        ancestors(path)
        with os.scandir(path) as entries:
            for n, entry in enumerate(entries):
                if n >= 200:
                    result["truncated"] = True
                    break
                if any(x in entry.name.lower() for x in ("auth", "secret", "credential", "token")):
                    continue
                s = plain(entry.path)
                result["entries"].append({"name": entry.name,
                    "type": "directory" if stat.S_ISDIR(s.st_mode) else "file",
                    "logical_bytes": None if stat.S_ISDIR(s.st_mode) else s.st_size})
    except (OSError, GuardError) as exc:
        result["error"] = str(exc)
    return result


def scan(args):
    root = project_root(args.project, args.codex_home)
    out = safe_output(args.output, directory=True)
    if key(out) == key(root) or below(root, out):
        raise GuardError("Scan output must be outside the project or a dedicated subdirectory")
    if args.max_files < 1 or not math.isfinite(args.min_age_hours) or args.min_age_hours < MIN_AGE:
        raise GuardError("max-files must be positive and min-age-hours must be at least 48")
    # Check both report targets before doing the inventory.
    for name in ("scan.json", "scan.md"):
        safe_output(out / name)
    report = {"schema": POLICY, "tool_version": VERSION, "created_at": utc(), "project": str(root),
        "root_identity": root_identity(root), "min_age_hours": args.min_age_hours,
        "volume_free_bytes": volume_free(root),
        "activity": {"state": "unverified", "known_lock_markers": activity(root),
                     "note": "No running-process inspection; absence of a marker does not prove idle"},
        "totals": {"files": 0, "unique_files": 0, "hardlink_duplicates": 0, "logical_bytes": 0,
                   "allocated_bytes_known": 0, "allocation_unknown_files": 0},
        "coverage": {"complete": True, "read_limit_hit": False, "aborted_io": False,
                     "max_files": args.max_files, "pruned_subtrees": [], "excluded_output": str(out),
                     "scope": "metadata of ordinary files outside protected pruned subtrees and output"},
        "directory_totals_scope": "complete top-level subtrees in reported coverage; each hardlink identity belongs to its lexicographically smallest scanned relative path",
        "directory_totals": {}, "top_directories": [], "largest_files": [], "candidates": [], "retained": {}, "review_examples": [], "errors": []}
    seen, dirs, stack, visited = {}, {}, [root], 0
    now = time.time()
    stop = False
    while stack and not stop:
        directory = stack.pop()
        try:
            ancestors(directory)
            with os.scandir(directory) as entries:
                for entry in entries:
                    visited += 1
                    if report["totals"]["files"] >= args.max_files or visited > args.max_files * 4:
                        report["coverage"].update(complete=False, read_limit_hit=True)
                        stop = True
                        break
                    path = Path(entry.path)
                    rel = path.relative_to(root).as_posix()
                    if below(path, out):
                        if rel not in report["coverage"]["pruned_subtrees"]:
                            report["coverage"]["pruned_subtrees"].append(rel)
                        continue
                    try:
                        s = plain(path)
                        if stat.S_ISDIR(s.st_mode):
                            if entry.name.lower() in CACHE_SCAN_PRUNE:
                                report["coverage"]["pruned_subtrees"].append(rel)
                            else:
                                if directory == root:
                                    dirs.setdefault(rel, {"path": rel, "files": 0, "logical_bytes": 0,
                                        "allocated_bytes_known": 0, "allocation_unknown_files": 0})
                                stack.append(path)
                            continue
                        if not stat.S_ISREG(s.st_mode):
                            raise GuardError("Special filesystem entry retained")
                        report["totals"]["files"] += 1
                        ident = (s.st_dev, s.st_ino) if s.st_ino else ("unknown", str(path))
                        top = rel.split("/")[0] if "/" in rel else "(root files)"
                        d = dirs.setdefault(top, {"path": top, "files": 0, "logical_bytes": 0,
                            "allocated_bytes_known": 0, "allocation_unknown_files": 0})
                        if ident in seen:
                            report["totals"]["hardlink_duplicates"] += 1
                            previous = seen[ident]
                            if rel < previous["path"]:
                                old_d = dirs[previous["top"]]
                                for field, amount in (("files", 1), ("logical_bytes", previous["size"]),
                                    ("allocated_bytes_known", previous["allocated"] or 0),
                                    ("allocation_unknown_files", int(previous["allocated"] is None))):
                                    old_d[field] -= amount
                                    d[field] += amount
                                previous.update(path=rel, top=top)
                            continue
                        seen[ident] = {"path": rel, "top": top, "size": s.st_size, "allocated": None}
                        report["totals"]["unique_files"] += 1
                        d["files"] += 1
                        d["logical_bytes"] += s.st_size
                        report["totals"]["logical_bytes"] += s.st_size
                        try:
                            amount = allocated(path, s)
                            if amount is None:
                                report["totals"]["allocation_unknown_files"] += 1
                                d["allocation_unknown_files"] += 1
                            else:
                                report["totals"]["allocated_bytes_known"] += amount
                                d["allocated_bytes_known"] += amount
                            seen[ident]["allocated"] = amount
                        except OSError as exc:
                            report["totals"]["allocation_unknown_files"] += 1
                            d["allocation_unknown_files"] += 1
                            raise exc
                        evidence, why = classify(root, rel, s, args.min_age_hours, now)
                        if evidence:
                            report["candidates"].append({"id": "", "path": rel, "identity": fingerprint(s),
                                "allocated_bytes": amount, "evidence": evidence,
                                "status": "eligible_pending_selected_cache_header_validation"})
                        else:
                            report["retained"][why] = report["retained"].get(why, 0) + 1
                            if len(report["review_examples"]) < 60 and ("cache" in rel.lower() or why.startswith("hardlink")):
                                report["review_examples"].append({"path": rel, "reason": why})
                        largest = report["largest_files"]
                        if len(largest) < 30 or s.st_size > largest[-1]["identity"]["size"]:
                            largest.append({"path": rel, "identity": fingerprint(s), "allocated_bytes": amount,
                                "reason": why or "candidate pending selected-cache header validation"})
                            largest.sort(key=lambda x: x["identity"]["size"], reverse=True)
                            del largest[30:]
                    except (OSError, GuardError) as exc:
                        report["errors"].append({"path": rel, "error": str(exc)})
                        report["coverage"]["complete"] = False
                        if fatal_io(exc):
                            report["coverage"]["aborted_io"] = True
                            stop = True
                            break
        except (OSError, GuardError) as exc:
            report["errors"].append({"path": str(directory), "error": str(exc)})
            report["coverage"]["complete"] = False
            if fatal_io(exc):
                report["coverage"]["aborted_io"] = True
                break
    report["coverage"]["pruned_subtrees"].sort()
    report["coverage"]["signature"] = hashlib.sha256(json.dumps({"policy": POLICY,
        "pruned": report["coverage"]["pruned_subtrees"], "output": str(out) if below(out, root) else None,
        "max_files": args.max_files}, sort_keys=True).encode()).hexdigest()
    report["directory_totals"] = {name: dirs[name] for name in sorted(dirs)}
    report["top_directories"] = sorted(dirs.values(), key=lambda d: (-d["logical_bytes"], d["path"]))[:30]
    report["candidates"].sort(key=lambda c: c["path"])
    for i, candidate in enumerate(report["candidates"], 1):
        candidate["id"] = f"C{i:06d}"
    report["baseline"] = {"comparable": False, "reason": "no baseline supplied"}
    if args.baseline:
        old, _ = read_json(args.baseline)
        comparable = (old.get("schema") == POLICY and key(old.get("project", "")) == key(root)
            and old.get("root_identity") == report["root_identity"]
            and old.get("coverage", {}).get("complete") is True and report["coverage"]["complete"]
            and old.get("coverage", {}).get("signature") == report["coverage"]["signature"])
        report["baseline"] = {"comparable": comparable,
            "reason": "same root identity and complete matching traversal coverage" if comparable else "root/coverage changed or partial scan; no net-growth claim"}
        if comparable:
            report["baseline"]["logical_bytes_delta"] = report["totals"]["logical_bytes"] - old["totals"]["logical_bytes"]
            if not report["totals"]["allocation_unknown_files"] and not old["totals"]["allocation_unknown_files"]:
                report["baseline"]["allocated_bytes_delta"] = report["totals"]["allocated_bytes_known"] - old["totals"]["allocated_bytes_known"]
            previous = old.get("directory_totals")
            if isinstance(previous, dict):
                changes = []
                empty = {"files": 0, "logical_bytes": 0, "allocated_bytes_known": 0, "allocation_unknown_files": 0}
                for name in sorted(previous.keys() | dirs.keys()):
                    before, after = previous.get(name, empty), dirs.get(name, empty)
                    delta = {"path": name, "logical_bytes_delta": after["logical_bytes"] - before["logical_bytes"],
                        "files_delta": after["files"] - before["files"], "allocated_bytes_delta": None}
                    if before.get("allocation_unknown_files") == 0 and after.get("allocation_unknown_files") == 0:
                        delta["allocated_bytes_delta"] = after["allocated_bytes_known"] - before["allocated_bytes_known"]
                    changes.append(delta)
                report["baseline"]["directory_deltas"] = sorted(changes, key=lambda x: (-x["logical_bytes_delta"], x["path"]))
            else:
                report["baseline"]["directory_delta_reason"] = "baseline has no complete directory_totals field; directory changes are unavailable, not zero"
    codex = absolute(args.codex_home or os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    report["codex_home"] = codex_metadata(codex)
    write_json(out / "scan.json", report)
    lines = ["# Project storage inventory", "", f"Project: `{root}`", "",
        f"Traversal complete: {report['coverage']['complete']} (protected pruned subtrees are excluded)",
        f"Ordinary unique files: {report['totals']['unique_files']}; logical bytes: {report['totals']['logical_bytes']}",
        f"Known allocated bytes: {report['totals']['allocated_bytes_known']}; unknown allocation files: {report['totals']['allocation_unknown_files']}",
        f"Volume free bytes at scan: {report['volume_free_bytes']} (other writes can affect snapshots)",
        f"Hardlink duplicates not double-counted: {report['totals']['hardlink_duplicates']}",
        "", "Project activity is unverified. No whole directory is eligible for removal.",
        "Candidates require selected-file CPython header validation before a plan can be created. No deletion occurred.", "",
        "| ID | File | Logical bytes | Evidence |", "|---|---|---:|---|"]
    for c in report["candidates"][:100]:
        lines.append(f"| {c['id']} | `{c['path'].replace('|', '?')}` | {c['identity']['size']} | {c['evidence']['kind']} |")
    if len(report["candidates"]) > 100:
        lines += ["", "Only the first 100 candidates are shown here; scan.json contains the complete list."]
    lines += ["", "## Largest top-level directories", "", "| Directory | Files | Logical bytes | Known allocated bytes |",
              "|---|---:|---:|---:|"]
    for d in report["top_directories"]:
        lines.append(f"| `{d['path'].replace('|', '?')}` | {d['files']} | {d['logical_bytes']} | {d['allocated_bytes_known']} |")
    lines += ["", "Directory rows include descendant files, excluding documented pruned subtrees; hardlinks are attributed once to their lexicographically smallest scanned relative path.",
        "", "## Baseline change", "", report["baseline"]["reason"]]
    baseline = report["baseline"]
    if baseline["comparable"]:
        lines += [f"Logical bytes net change: {baseline['logical_bytes_delta']:+d}",
                  f"Allocated bytes net change: {baseline.get('allocated_bytes_delta', 'unavailable (unknown allocation)')}"]
        if "directory_deltas" in baseline:
            growth = [x for x in baseline["directory_deltas"] if x["logical_bytes_delta"] > 0][:30]
            reduction = [x for x in reversed(baseline["directory_deltas"]) if x["logical_bytes_delta"] < 0][:30]
            lines += ["", "| Growth directory | Logical delta | Allocated delta | Reduction directory | Logical delta | Allocated delta |",
                      "|---|---:|---:|---|---:|---:|"]
            for i in range(max(len(growth), len(reduction))):
                cells = []
                for entries in (growth, reduction):
                    x = entries[i] if i < len(entries) else None
                    cells += [f"`{x['path'].replace('|', '?')}`", f"{x['logical_bytes_delta']:+d}", str(x["allocated_bytes_delta"]) if x["allocated_bytes_delta"] is not None else "unavailable"] if x else ["", "", ""]
                lines.append("| " + " | ".join(cells) + " |")
            if not growth and not reduction:
                lines += ["", "No top-level logical growth or reduction in matching complete snapshots."]
        else:
            lines += [baseline["directory_delta_reason"]]
    lines += ["", "## Largest files (metadata only)", "", "| File | Logical bytes | Allocated bytes | Retention/review reason |",
              "|---|---:|---:|---|"]
    for x in report["largest_files"]:
        lines.append(f"| `{x['path'].replace('|', '?')}` | {x['identity']['size']} | {x['allocated_bytes']} | {x['reason']} |")
    lines += ["", "## Retained reasons", ""] + [f"- {reason}: {count}" for reason, count in report["retained"].items()]
    lines += ["", "## Coverage", "", f"Errors: {len(report['errors'])}; read limit hit: {report['coverage']['read_limit_hit']}",
              "Excluded subtrees: " + ", ".join(report["coverage"]["pruned_subtrees"]),
              "", "Codex home metadata is cross-project and shallow. It is never a cleanup candidate.",
              "Allocation is filesystem metadata, not a promise that deleting a file returns that many free bytes."]
    with new_file(out / "scan.md") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({"scan": str(out / "scan.json"), "summary": str(out / "scan.md"),
        "candidates": len(report["candidates"]), "complete": report["coverage"]["complete"]}))


def plan(args):
    report, digest = read_json(args.scan)
    if report.get("schema") != POLICY:
        raise GuardError("Unsupported scan policy/schema")
    root = project_root(report["project"], report.get("codex_home", {}).get("path"))
    same_root(root, report["root_identity"])
    if not report["coverage"]["complete"]:
        raise GuardError("Partial/error-limited scans cannot produce an executable plan")
    min_age = float(report["min_age_hours"])
    if not math.isfinite(min_age) or min_age < MIN_AGE:
        raise GuardError("Minimum age below policy floor")
    ids = [s for group in args.ids for s in group.split(",") if s]
    if not ids or len(set(ids)) != len(ids):
        raise GuardError("Choose explicit unique candidate IDs")
    choices = {c["id"]: c for c in report["candidates"]}
    result = {"schema": POLICY, "tool_version": VERSION, "created_at": utc(),
        "project": str(root), "root_identity": report["root_identity"], "min_age_hours": min_age,
        "codex_home": report.get("codex_home", {}).get("path"),
        "source_scan_sha256": digest, "items": [],
        "operation": "exact-cache-file-delete", "concurrency": "Windows exclusive file and ancestor handles; POSIX advisory flock and anchored parent descriptors"}
    for cid in ids:
        if cid not in choices:
            raise GuardError(f"Unknown candidate: {cid}")
        c = choices[cid]
        p = relative_file(root, c["path"])
        with guarded_file(p) as (fd, _):
            s = os.fstat(fd)
            if fingerprint(s) != c["identity"]:
                raise GuardError(f"Candidate changed after scan: {c['path']}")
            evidence, why = classify(root, c["path"], s, min_age)
            if not evidence:
                raise GuardError(f"Candidate is no longer eligible: {c['path']}: {why}")
            validate_cache_fd(fd)
            sha = hash_fd(fd)
            if fingerprint(os.fstat(fd)) != fingerprint(s):
                raise GuardError("Candidate changed while hashing")
            result["items"].append({"id": cid, "path": c["path"], "identity": fingerprint(s),
                                     "sha256": sha, "evidence": evidence})
    if len({i["path"] for i in result["items"]}) != len(result["items"]):
        raise GuardError("Duplicate selected paths")
    write_json(args.output, result)
    _, plan_sha = read_json(args.output)
    print(json.dumps({"plan": str(absolute(args.output)), "plan_sha256": plan_sha,
                      "files": len(result["items"]), "logical_bytes": sum(i["identity"]["size"] for i in result["items"])}))


def apply(args):
    if os.name != "nt" and not args.confirm_idle:
        raise GuardError("POSIX apply requires --confirm-idle after confirming no build/render/cache writer is running; advisory locks are not a system-wide guarantee")
    plan_data, digest = read_json(args.plan)
    if args.authorize_plan.lower() != digest:
        raise GuardError("Authorization must exactly match the SHA256 of the plan file")
    if plan_data.get("schema") != POLICY or plan_data.get("operation") != "exact-cache-file-delete":
        raise GuardError("Unsupported plan policy/operation")
    root = project_root(plan_data["project"], plan_data.get("codex_home"))
    same_root(root, plan_data["root_identity"])
    min_age = float(plan_data["min_age_hours"])
    if not math.isfinite(min_age) or min_age < MIN_AGE:
        raise GuardError("Minimum age below policy floor")
    items = plan_data["items"]
    if not items or len({i["path"] for i in items}) != len(items):
        raise GuardError("Plan must contain explicit unique files")
    receipt_path = absolute(args.receipt)
    if any(key(receipt_path) == key(root.joinpath(*i["path"].split("/"))) for i in items):
        raise GuardError("Receipt cannot overwrite a selected file")
    receipt = {"schema": POLICY, "started_at": utc(), "plan_sha256": digest, "project": str(root),
        "status": "running", "planned_files": len(items), "deleted_files": 0, "deleted_logical_bytes": 0,
        "volume_free_before_bytes": volume_free(root),
        "physical_space_reclaimed": "not measured; logical deletions are not a free-space guarantee",
        "concurrency": "exclusive Windows handles" if os.name == "nt" else "POSIX advisory flock; noncooperating writers can still race unlink",
        "items": []}
    with new_file(receipt_path) as f:
        def save():
            f.seek(0)
            json.dump(receipt, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        save()
        for item in items:
            record = {"path": item["path"], "status": "checking"}
            receipt["items"].append(record)
            save()
            try:
                same_root(root, plan_data["root_identity"])
                p = relative_file(root, item["path"])
                with guarded_file(p, delete=True) as (fd, unlink):
                    s = os.fstat(fd)
                    if fingerprint(s) != item["identity"]:
                        raise GuardError("File identity/size/mtime changed since planning")
                    evidence, why = classify(root, item["path"], s, min_age)
                    if not evidence:
                        raise GuardError(f"Current protection/evidence check refused deletion: {why}")
                    if evidence != item.get("evidence"):
                        raise GuardError("Cache provenance changed since planning")
                    validate_cache_fd(fd)
                    if hash_fd(fd) != item["sha256"] or fingerprint(os.fstat(fd)) != item["identity"]:
                        raise GuardError("File hash/identity changed since planning")
                    record["status"] = "delete_pending"
                    save()
                    # Keep receipt I/O outside the final validation-to-delete interval.
                    same_root(root, plan_data["root_identity"])
                    ancestors(p.parent)
                    final_evidence, why = classify(root, item["path"], os.fstat(fd), min_age)
                    if final_evidence != evidence or why:
                        raise GuardError("Evidence changed immediately before deletion")
                    unlink()
                record["status"] = "deleted"
                record["logical_bytes"] = s.st_size
                receipt["deleted_files"] += 1
                receipt["deleted_logical_bytes"] += s.st_size
            except (OSError, GuardError) as exc:
                record.update(status="skipped", error=str(exc))
                if fatal_io(exc):
                    record["status"] = "io_error"
                    receipt["status"] = "aborted_io_error"
                else:
                    receipt["status"] = "aborted_validation" if isinstance(exc, GuardError) else "aborted_os_error"
                save()
                break
            save()
        if receipt["status"] == "running":
            receipt["status"] = "completed" if all(i["status"] == "deleted" for i in receipt["items"]) else "completed_with_skips"
        receipt["finished_at"] = utc()
        receipt["not_attempted_files"] = len(items) - len(receipt["items"])
        receipt["volume_free_after_bytes"] = volume_free(root)
        before, after = receipt["volume_free_before_bytes"], receipt["volume_free_after_bytes"]
        receipt["volume_free_delta_bytes"] = after - before if before is not None and after is not None else None
        receipt["volume_free_note"] = "Snapshot difference includes unrelated writes/deletes on the volume; it is not attributable solely to this operation"
        save()
    print(json.dumps({"receipt": str(receipt_path), "status": receipt["status"],
        "deleted_files": receipt["deleted_files"], "deleted_logical_bytes": receipt["deleted_logical_bytes"]}))
    return 3 if receipt["status"] != "completed" else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="Read metadata only; never remove project files")
    s.add_argument("--project", required=True)
    s.add_argument("--output", required=True, help="New report directory; if nested, excluded from inventory")
    s.add_argument("--baseline")
    s.add_argument("--codex-home")
    s.add_argument("--min-age-hours", type=float, default=MIN_AGE, help="Minimum cache age in hours (default: 48; cannot be lower)")
    s.add_argument("--max-files", type=int, default=250000)
    s.set_defaults(run=scan)
    p = sub.add_parser("plan", help="Hash explicit selected cache files and freeze exact identities")
    p.add_argument("--scan", required=True)
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--output", required=True)
    p.set_defaults(run=plan)
    a = sub.add_parser("apply", help="Delete only revalidated exact files from an explicitly authorized plan")
    a.add_argument("--plan", required=True)
    a.add_argument("--receipt", required=True)
    a.add_argument("--authorize-plan", required=True, metavar="SHA256")
    a.add_argument("--confirm-idle", action="store_true", help="Required on POSIX after confirming no build/render/cache writers are active")
    a.set_defaults(run=apply)
    args = parser.parse_args()
    try:
        return args.run(args) or 0
    except (GuardError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "no_automatic_retry": True}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
