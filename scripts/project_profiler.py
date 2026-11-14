#!/usr/bin/env python3
"""Bounded, read-only, multi-ecosystem project storage attribution.

Python 3.10+ / standard library. Does not run project code or any tool command.
Only specifically allowlisted tool manifests/configuration are read as content;
all other project and related-root observations are filesystem metadata only.
Classification never grants deletion, migration, or native cleanup authority.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

VERSION = "1.5.0"
SCHEMA = "project-storage-profile-v1"
MAX_CONFIG_FILES = 256
MAX_CONFIG_FILE_BYTES = 256 * 1024
MAX_REPORT_BYTES = 128 * 1024 * 1024
MAX_DEPTH = 64
MAX_ATTRIBUTION_NODES = 4096
STATE_DIRS = {".codex", ".agents", ".claude", ".kimi", ".kimi-code", ".workbuddy", ".codebuddy",
              "sessions", "archived_sessions", "thread_history",
              "credentials", "secrets", "state", "index", "indexes", "indices"}
SOURCE_DIRS = {"src", "source", "sources"}
RETAIN_DIRS = {"original", "originals", "inputs", "素材", "原件",
              "final", "finals", "deliverables", "delivery", "approved", "published", "成片", "交付", "定稿",
              "backup", "backups", "recovery", "rollback", "releases", "release", "备份", "发布",
              "acceptance", "evidence", "audit", "baselines", "baseline", "golden", "__snapshots__",
              "__image_snapshots__", "验收", "证据", "基准", "pgdata"}
RESIDUE_DIRS = {"scratch", ".scratch", "tmp", ".tmp", "temp", ".temp", "task-temp", "task_tmp",
                "task-scratch", "run-scratch", "staging", "download-fragments", "partial-downloads",
                "test-results", "test-output", "test-outputs", "playwright-report", "traces", "trace",
                "screenshots", "captures", "recordings", "previews", "preview", "decoded-frames"}
RETAIN_FILE = re.compile(r"(?:^|[_. -])(?:final|deliverable|approved|published|release|master|backup|recovery|baseline|evidence|原件|成片|交付|定稿)(?:[_. -]|$)", re.I)
RESIDUE_CATEGORIES = {"agent_task_residue_clue", "task_download_fragment_clue", "task_scratch_file_clue", "isolated_runtime_clue",
                      "python_bytecode", "tool_managed_cache", "unverified_cache_name", "framework_cache_and_build", "build_outputs"}
PROTECTED_PARTITIONS = {"dependencies", "version_control", "state_and_history", "browser_profile",
                        "retained_project_material", "media_and_assets", "data_and_models",
                        "tool_managed_cache", "browser_downloads", "framework_cache_and_build",
                        "build_outputs", "unverified_cache_name"}
DEPENDENCY_DIRS = {"node_modules", ".venv", "venv", "env", "site-packages", "__pypackages__",
                   ".tox", ".nox", ".conda", "pods", ".dart_tool"}
MANIFEST_NAMES = {"package.json", "pyproject.toml", "requirements.txt", "pipfile", "uv.lock",
    "poetry.lock", "cargo.toml", "cargo.lock", "go.mod", "go.work", "pom.xml", "build.gradle",
    "build.gradle.kts", "settings.gradle", "settings.gradle.kts", "gradle.properties",
    "cmakelists.txt", "cmakepresets.json", "pubspec.yaml", "pubspec.lock", "podfile",
    "package.swift", "project.pbxproj", "global.json", "directory.build.props",
    "directory.build.targets", "nuget.config", ".npmrc", ".yarnrc.yml", ".yarnrc",
    ".cargo/config", "config.toml", "pip.conf", "pip.ini", "uv.toml", "poetry.toml",
    "pytest.ini", "tox.ini", "pnpm-workspace.yaml", "lerna.json", "turbo.json", "nx.json",
    "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb", "pyvenv.cfg"}
CONFIG_STEMS = {"next.config", "vite.config", "remotion.config", "playwright.config", "cypress.config"}
TEXT_MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "pipfile", "cargo.toml",
    "go.mod", "go.work", "pom.xml", "build.gradle", "build.gradle.kts", "gradle.properties",
    "cmakepresets.json", "pubspec.yaml", "directory.build.props", "nuget.config", ".npmrc",
    ".yarnrc.yml", ".yarnrc", "pip.conf", "pip.ini", "uv.toml", "poetry.toml", "turbo.json",
    "nx.json"}
MEDIA_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".wav", ".mp3", ".flac", ".aiff",
             ".png", ".jpg", ".jpeg", ".webp", ".psd", ".ai", ".blend", ".aep"}
DATA_EXT = {".parquet", ".arrow", ".feather", ".h5", ".hdf5", ".npy", ".npz", ".csv", ".tsv"}
DATABASE_EXT = {".db", ".sqlite", ".sqlite3", ".jsonl"}
SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".rs", ".go", ".java", ".kt",
              ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".dart", ".md", ".docx",
              ".pdf", ".pptx", ".xlsx", ".toml", ".yaml", ".yml", ".json"}
SENSITIVE = re.compile(r"(?:token|password|passwd|secret|credential|authorization|api[_-]?key)", re.I)
TOKEN = re.compile(r"(?:\b(?:sk|pk)-[A-Za-z0-9_-]{16,}|\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}|\bBearer\s+\S+)", re.I)


class ProfileError(Exception):
    pass


def shared_state_guard():
    """Load only the adjacent reviewed helper; never resolve through sys.path."""
    path = Path(__file__).absolute().with_name("storage_guard.py")
    for entry in (path, *path.parents):
        s = os.lstat(entry)
        if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
            raise ProfileError("state guard implementation cannot be loaded through links")
    spec = importlib.util.spec_from_file_location("_project_profiler_state_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_state_guard = None


def protect_state(path, codex_home=None, include_containing=False):
    global _state_guard
    if _state_guard is None:
        _state_guard = shared_state_guard()
    try:
        _state_guard.protect_agent_state_path(path, codex_home, include_containing=include_containing)
    except _state_guard.GuardError as exc:
        raise ProfileError(str(exc)) from exc


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def absolute(path):
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def key(path):
    return os.path.normcase(str(absolute(path)))


def below(path, root):
    try:
        return os.path.commonpath((key(path), key(root))) == key(root)
    except ValueError:
        return False


def scrub(value):
    value = TOKEN.sub("[REDACTED]", str(value))
    value = re.sub(r"(?i)(?:https?|ssh)://[^\s/]*@", "[REDACTED_URL_USERINFO]/", value)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "?", value)


def plain(path, directory=None):
    s = os.lstat(path)
    if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
        raise ProfileError("link/reparse entry; not followed")
    if directory is True and not stat.S_ISDIR(s.st_mode):
        raise ProfileError("ordinary directory required")
    if directory is False and not stat.S_ISREG(s.st_mode):
        raise ProfileError("ordinary file required")
    return s


def ancestors(path):
    for p in reversed((absolute(path), *absolute(path).parents)):
        plain(p, True)


def identity(s):
    return {"device": s.st_dev, "inode": s.st_ino}


def fingerprint(s):
    return {"device": s.st_dev, "inode": s.st_ino, "size": s.st_size,
            "mtime_ns": s.st_mtime_ns, "links": s.st_nlink}


def fatal_io(exc):
    return (getattr(exc, "errno", None) in {errno.EIO, getattr(errno, "EBADMSG", -1)}
            or getattr(exc, "winerror", None) in {23, 30, 1117, 1392})


if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes as wt
    K32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class WinInfo(ctypes.Structure):
        _fields_ = [("attrs", wt.DWORD), ("created", wt.FILETIME), ("accessed", wt.FILETIME),
            ("written", wt.FILETIME), ("volume", wt.DWORD), ("size_hi", wt.DWORD),
            ("size_lo", wt.DWORD), ("links", wt.DWORD), ("index_hi", wt.DWORD), ("index_lo", wt.DWORD)]

    class StandardInfo(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_longlong), ("length", ctypes.c_longlong),
                    ("links", wt.DWORD), ("pending", wt.BOOLEAN), ("directory", wt.BOOLEAN)]

    K32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, wt.LPVOID, wt.DWORD, wt.DWORD, wt.HANDLE]
    K32.CreateFileW.restype = wt.HANDLE
    K32.CloseHandle.argtypes = [wt.HANDLE]
    K32.GetFileInformationByHandle.argtypes = [wt.HANDLE, ctypes.POINTER(WinInfo)]
    K32.GetFileInformationByHandleEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD]
    K32.GetFinalPathNameByHandleW.argtypes = [wt.HANDLE, wt.LPWSTR, wt.DWORD, wt.DWORD]

    def win_open(path, directory=False, content=False, anchored=False):
        access = 0x80000000 if content else 0x80
        h = K32.CreateFileW(str(path), access, 3 if anchored else 7, None, 3,
                           0x00200000 | (0x02000000 if directory else 0), None)
        if h == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info = WinInfo()
            if not K32.GetFileInformationByHandle(h, ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.attrs & 0x400 or bool(info.attrs & 0x10) != directory:
                raise ProfileError("opened link/reparse or unexpected type")
            buf = ctypes.create_unicode_buffer(32768)
            n = K32.GetFinalPathNameByHandleW(h, buf, len(buf), 0)
            if not n or n >= len(buf):
                raise ProfileError("opened final path could not be verified")
            final = buf.value
            if final.startswith("\\\\?\\UNC\\"):
                final = "\\\\" + final[8:]
            elif final.startswith("\\\\?\\"):
                final = final[4:]
            if key(final) != key(path):
                raise ProfileError("opened entry resolves to another path")
            return h
        except BaseException:
            K32.CloseHandle(h)
            raise


@contextlib.contextmanager
def anchored_directory(path):
    """Keep every ancestor ordinary/anchored; never recurse through a link."""
    path = absolute(path)
    handles = []
    try:
        if os.name == "nt":
            for p in reversed((path, *path.parents)):
                handles.append(win_open(p, directory=True, anchored=True))
            yield str(path)
        else:
            fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(fd)
            for part in path.parts[1:]:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                handles.append(fd)
            yield fd
    finally:
        for handle in reversed(handles):
            K32.CloseHandle(handle) if os.name == "nt" else os.close(handle)


def read_bounded(path, limit):
    path = absolute(path)
    try:
        protect_state(path)
    except ProfileError:
        git_project = (path.parent if path.name.lower() == ".git" else
            path.parent.parent if path.name.lower() == "commondir" and path.parent.name.lower() == ".git" else None)
        if git_project is not None:
            # These two pre-existing, bounded pointer formats are project
            # metadata. Validate their owning project against all Agent-state
            # roots; never exempt arbitrary .git files or follow the pointer.
            try:
                _state_guard.project_root(git_project)
            except _state_guard.GuardError as exc:
                raise ProfileError(str(exc)) from exc
        else:
            validate_worktree_manifest(path)
    fd = None
    with anchored_directory(path.parent) as parent:
        before = plain(path, False)
        if before.st_nlink != 1 or not before.st_ino:
            raise ProfileError("content read requires an ordinary single-link file with available identity")
        if getattr(before, "st_file_attributes", 0) & 0x1000:
            raise ProfileError("offline file content is not read")
        if before.st_size > limit:
            raise ProfileError("content exceeds bounded read allowance")
        try:
            if os.name == "nt":
                h = win_open(path, content=True)
                try:
                    fd = msvcrt.open_osfhandle(h, os.O_RDONLY | os.O_BINARY)
                except BaseException:
                    K32.CloseHandle(h)
                    raise
            else:
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            current = os.fstat(fd)
            if fingerprint(current) != fingerprint(before) or not stat.S_ISREG(current.st_mode):
                raise ProfileError("file identity changed before bounded read")
            data = bytearray()
            while len(data) <= limit:
                chunk = os.read(fd, min(65536, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > limit or fingerprint(os.fstat(fd)) != fingerprint(before):
                raise ProfileError("file changed or exceeded bounded read allowance")
            return bytes(data)
        finally:
            if fd is not None:
                os.close(fd)


def validate_worktree_manifest(path):
    # The existing explicit Codex worktree payload exception permits only
    # allowlisted project manifests, never arbitrary state/report bodies.
    codex = absolute(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    if not below(path, codex):
        raise ProfileError("content path crosses an Agent-state boundary")
    parts = path.relative_to(codex).parts
    if len(parts) < 4 or parts[0].lower() != "worktrees":
        raise ProfileError("content path crosses an Agent-state boundary")
    project = codex.joinpath(*parts[:3])
    if not manifest_kind(path) or blocked_manifest(path.relative_to(project)) or not content_allowed(path):
        raise ProfileError("worktree content is not an allowlisted project manifest")
    try:
        _state_guard.project_root(project, codex)
    except _state_guard.GuardError as exc:
        raise ProfileError(str(exc)) from exc


def allocated(path, s):
    if hasattr(s, "st_blocks"):
        return s.st_blocks * 512
    if os.name == "nt":
        h = win_open(path)
        try:
            info = StandardInfo()
            if not K32.GetFileInformationByHandleEx(h, 1, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(info.allocation)
        finally:
            K32.CloseHandle(h)
    return None


def selected_root(path, codex, related=False):
    root = absolute(path)
    ancestors(root)
    home = absolute(Path.home())
    def actual_id(path):
        try:
            # Identity only: detects case-insensitive aliases and relocated homes;
            # this does not enumerate or read the target's contents.
            s = os.stat(path)
            return (s.st_dev, s.st_ino) if s.st_ino else None
        except FileNotFoundError:
            return None
    rid, hid, cid = actual_id(root), actual_id(home), actual_id(codex)
    sqlite_value = os.environ.get("CODEX_SQLITE_HOME")
    if sqlite_value:
        sqlite_root = absolute(sqlite_value)
        sid = actual_id(sqlite_root)
        sqlite_ancestor_ids = {actual_id(p) for p in sqlite_root.parents}
        sqlite_ancestor_ids.discard(None)
        inside_state_alias = sid is not None and any(actual_id(p) == sid for p in root.parents)
        if (below(root, sqlite_root) or below(sqlite_root, root) or inside_state_alias
                or rid is not None and (rid == sid or rid in sqlite_ancestor_ids)):
            raise ProfileError("CODEX_SQLITE_HOME state storage and its parent cannot be selected for recursive profiling")
    protected_parent_ids = {actual_id(p) for base in (home, codex) for p in base.parents}
    protected_parent_ids.discard(None)
    if (root.parent == root or key(root) in {key(home), key(codex)} or below(home, root) or below(codex, root)
            or rid is not None and (rid in {hid, cid} or rid in protected_parent_ids)):
        raise ProfileError("select a precise directory, not a drive/root, home, CODEX_HOME, or their parent")
    codex_alias_ancestor = next((p for p in root.parents if cid is not None and actual_id(p) == cid), None)
    within_codex = below(root, codex) or codex_alias_ancestor is not None
    allowed_worktree = False
    if within_codex:
        parts = root.relative_to(codex_alias_ancestor or codex).parts
        allowed_worktree = (not related and len(parts) >= 3 and parts[0].lower() == "worktrees"
                            and not any(p.lower() in STATE_DIRS for p in parts))
        if not allowed_worktree:
            raise ProfileError("Codex state/related roots cannot be recursively profiled")
        plain((codex_alias_ancestor or codex).joinpath(*parts[:3]) / ".git")
    if not allowed_worktree:
        protect_state(root, codex, include_containing=True)
    else:
        # Keep the explicit metadata worktree exception, while still checking
        # every other configured host/state root through the shared guard.
        global _state_guard
        if _state_guard is None:
            _state_guard = shared_state_guard()
        try:
            _state_guard.project_root(root, codex)
        except _state_guard.GuardError as exc:
            raise ProfileError(str(exc)) from exc
    if related:
        if any(p.lower() in STATE_DIRS for p in root.parts):
            raise ProfileError("session/credential/agent roots cannot be selected as related roots")
    else:
        protected_parts = STATE_DIRS | {".git"}
        if allowed_worktree:
            # The verified Codex ancestor is expected; only inspect the worktree suffix.
            checked_parts = root.relative_to(codex_alias_ancestor or codex).parts
        else:
            checked_parts = root.parts
        if any(p.lower() in protected_parts for p in checked_parts):
            raise ProfileError("project root cannot be inside Git, agent, session, index or state storage")
        if any(p.lower() in DEPENDENCY_DIRS | {".npm", ".pnpm-store", ".uv-cache", ".yarn", ".gradle", ".m2", ".nuget", ".pub-cache"} for p in checked_parts):
            raise ProfileError("project root cannot be a dependency environment or tool-managed storage root; select the owning project")
    return root


def new_output(path):
    path = absolute(path)
    ancestors(path.parent)
    if path.exists() or path.is_symlink():
        raise ProfileError("report target already exists; choose a new output name")
    return path


def output_outside_observation(path, roots):
    protect_state(path)
    # All existing ancestors have already passed the no-link checks. Also catch
    # root aliases when an output ancestor has an observed root's device/FileID.
    protected_ids = set()
    for root in roots:
        if below(path, root):
            raise ProfileError("report outputs must be outside project, related roots and CODEX_HOME")
        try:
            # Identity only also protects an explicitly relocated CODEX_HOME;
            # project/related roots themselves passed no-link validation earlier.
            s = os.stat(root)
            protected_ids.add((s.st_dev, s.st_ino))
        except FileNotFoundError:
            continue
    for parent in path.parents:
        s = plain(parent, True)
        if s.st_ino and (s.st_dev, s.st_ino) in protected_ids:
            raise ProfileError("report output ancestor aliases an observed/protected root")


def write_new(path, value, json_value=False):
    with anchored_directory(path.parent) as parent:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path if os.name == "nt" else path.name, flags, 0o600,
                     **({} if os.name == "nt" else {"dir_fd": parent}))
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            if json_value:
                json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.write("\n")
            else:
                f.write(value)


def empty_measurement():
    return {"files": 0, "unique_files": 0, "hardlink_duplicates": 0, "logical_bytes": 0,
            "allocated_bytes_known": 0, "allocation_unknown_files": 0, "identity_unknown_files": 0}


def add_measurement(dst, size, allocation, unknown_identity=False, sign=1):
    dst["unique_files"] += sign
    dst["logical_bytes"] += size * sign
    dst["allocated_bytes_known"] += (allocation or 0) * sign
    dst["allocation_unknown_files"] += int(allocation is None) * sign
    dst["identity_unknown_files"] += int(unknown_identity) * sign


def manifest_kind(path):
    name = path.name.lower()
    if name == ".git" or name == "commondir" and path.parent.name.lower() == ".git":
        return name
    if name == "config.toml" and path.parent.name.lower() != ".cargo":
        return None
    if name in MANIFEST_NAMES or path.suffix.lower() in {".csproj", ".fsproj", ".vbproj", ".sln", ".xcodeproj"}:
        return name
    if any(name.startswith(stem + ".") and Path(name).suffix in {".js", ".cjs", ".mjs", ".ts", ".cts", ".mts", ".json"} for stem in CONFIG_STEMS):
        return name
    return None


def content_allowed(path):
    name = path.name.lower()
    return (name in {".git", "commondir"} or name in TEXT_MANIFESTS or name == "config.toml" and path.parent.name.lower() == ".cargo"
            or any(name.startswith(stem + ".") for stem in CONFIG_STEMS)
            or path.suffix.lower() in {".csproj", ".fsproj", ".vbproj"})


def blocked_manifest(relative):
    parts = [x.lower() for x in relative.parts[:-1]]
    if relative.as_posix().lower() == ".git/commondir":
        return False
    return (len(parts) > 6 or any(x in STATE_DIRS | DEPENDENCY_DIRS | {".git", "target", "dist", "build", ".next", ".gradle", ".cache",
        "vendor", "vendored", "third_party", "third-party", "external", "_deps", "deps", "generated", ".pnpm", ".yarn", ".nuget", "cmakefiles"} for x in parts))


def classify_directory(relative):
    parts = relative.parts
    name = parts[-1].lower()
    lower = [x.lower() for x in parts]
    if (name == "data" and len(parts) >= 3 and parts[-3].lower() == ".runtime"
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*-pg-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", parts[-2])):
        return ("isolated_runtime_clue", "isolated PostgreSQL test producer (path clue only)",
                "possible generated test data; contents, producer and current role are unverified",
                "protected_pending_lifecycle_review",
                "review real producer, synthetic inputs, per-run completion, retained results and current references; only a separately qualified retired_runtime_guard plan can authorize disposal")
    if name == ".git":
        return "version_control", "Git", "repository objects, worktree metadata and recovery history", "protected", "retain; inspect repository/worktree relationships and native object statistics"
    if name in STATE_DIRS:
        return "state_and_history", "Agent/application state boundary clue (owner unverified)", "session, index, application state or sensitive boundary", "protected", "retain; application-specific backup and recovery procedure required"
    if name in RETAIN_DIRS:
        return "retained_project_material", "unknown/project workflow", "source, input, deliverable, evidence, business database or recovery boundary", "protected", "retain; task-generated origin would not remove independent project/retention value"
    if name in {"node_modules", "site-packages", "__pypackages__", ".venv", "venv", ".tox", ".nox", ".conda", "pods", ".dart_tool"}:
        producer = "Node package manager" if name == "node_modules" else "Python environment manager" if name in {"site-packages", "__pypackages__", ".venv", "venv", ".tox", ".nox", ".conda"} else "CocoaPods" if name == "pods" else "Dart/Flutter"
        return "dependencies", producer, "installed dependencies/environment; may contain local edits or native builds", "protected", "recreate only with verified manifests, lockfiles, toolchain and local-edit preservation"
    if name in {".npm", ".pnpm-store", ".yarn", ".uv-cache", ".gradle", ".m2", ".nuget", ".pub-cache"}:
        return "tool_managed_cache", "package/build manager inferred from directory name", "tool-managed cache or dependency state", "protected", "use a verified native manager procedure; cache names alone do not authorize removal"
    if name in {"ms-playwright", ".playwright", ".local-browsers", "cypress-cache"}:
        return "browser_downloads", "Playwright/Cypress (path clue)", "downloaded browser/runtime binaries; binding not proven", "protected", "verify installed tool version and executable path before native re-download or cleanup planning"
    if name in {"user-data", "user_data", "browser-profile", "browser-profiles", "chromium-profile", "profiles"}:
        return "browser_profile", "browser/application (unverified)", "persistent browser identity, cookies, extensions and state", "protected", "retain; use application-specific export/restore and active-profile checks"
    if name == "__pycache__":
        return "python_bytecode", "CPython (format/source still require validation)", "bytecode-shaped files; descendants are not automatically eligible", "retained_pending_exact_rule", "rebuild from corresponding source using the matching interpreter; storage_guard revalidates exact selected files"
    if name in {".next", ".turbo", ".vite", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".parcel-cache", ".svelte-kit", ".angular"}:
        producer = {".next": "Next.js", ".turbo": "Turborepo", ".vite": "Vite", ".pytest_cache": "pytest",
                    ".mypy_cache": "mypy", ".ruff_cache": "Ruff", ".parcel-cache": "Parcel", ".svelte-kit": "SvelteKit", ".angular": "Angular"}[name]
        return "framework_cache_and_build", producer + " (path clue; manifest/runtime verification required)", "framework build, development state or cache; may mix outputs", "protected", "verify current manifest/configuration, runtime use and native lifecycle; no generic directory deletion"
    if name == "target":
        return "build_outputs", "Cargo/Maven or custom producer (verify manifest)", "compiled outputs, downloaded intermediates or custom data", "protected", "verify producing manifest, toolchain and exact build recipe; retain until scoped native plan"
    if name in {"build", "dist", "out", "bin", "obj", "cmake-build-debug", "cmake-build-release", "deriveddata"}:
        return "build_outputs", "build system (requires nearby manifest/configuration)", "build/output directory; may include deliverables or irreplaceable generated assets", "protected", "verify producing task, retained source and deliverable use; no generic clean command"
    if name in {"cache", ".cache", "caches"}:
        return "unverified_cache_name", "unknown", "directory name suggests cache; provenance and recoverability unknown", "protected", "establish writer, contents and native policy; name/age/Git-ignore is insufficient"
    if name in {"media", "assets", "public", "static", "素材"}:
        return "media_and_assets", "unknown/source or media pipeline", "source assets or produced media; value and references unknown", "protected", "preserve originals; inspect producer/input/output relationships and retained delivery copies"
    if name in RESIDUE_DIRS:
        if any(part in SOURCE_DIRS for part in lower[:-1]):
            return "retained_project_material", "source-tree boundary", "scratch-shaped name inside a source tree; current role unknown", "protected", "retain source-tree material; a temporary name is not proof of a detached task output"
        return ("agent_task_residue_clue", "task/tool producer unverified (directory metadata clue only)",
                "possible scratch, capture, trace, preview, failed download or test-run output; completion and value unknown",
                "protected_pending_task_review", "establish exact initiating task and actual producer, retained inputs/results, completion, current references and readers/writers; only a separate exact supported cleanup plan can authorize deletion")
    if len(parts) >= 2 and lower[-2] in {".runtime", ".runs", "task-runs"}:
        return ("agent_task_residue_clue", "per-run directory clue; initiating Agent and tool unverified",
                "possible individual runtime/task output; may still contain current valuable data",
                "protected_pending_task_review", "review this exact run and its descendants separately; do not treat the mixed runtime parent as disposable")
    if name in {"exports", "export", "outputs", "renders", "render", "artifacts", "archive", "archives", "backup", "backups", "recovery", "releases", "rollback", "备份", "发布"}:
        return "outputs_archives_recovery", "unknown/export, render or release task", "potential outputs, archives, backups or recovery material; inactivity unverified", "protected", "verify producer, inactivity, references and independent usable copy before relocation_guard routing"
    if name in {"data", "datasets", "checkpoints", "models"}:
        return "data_and_models", "unknown/data pipeline", "dataset, model, checkpoint or user data; recoverability unknown", "protected", "verify licenses, provenance, expensive processing and original/download availability"
    return None


def file_class(path):
    name, ext = path.name.lower(), path.suffix.lower()
    if name == ".git":
        return "version_control", "Git worktree pointer", "repository location pointer; target is not recursively followed", "protected", "verify worktree/common-directory relationships and preserve repository history"
    if ext in DATABASE_EXT or re.search(r"\.(?:db|sqlite3?)-(?:wal|shm|journal)$", name):
        return "database_and_records", "application/data store", "database, records or session-like storage; metadata only", "protected", "application-consistent backup/export and recovery checks required"
    if (name.startswith(".env") or SENSITIVE.search(name) or name in {"auth.json", "history.jsonl"}
            or RETAIN_FILE.search(name)):
        return "sensitive_metadata", "application/project", "sensitive, final, baseline or recovery-shaped file; content not read", "protected", "retain; no generic storage action"
    if ext in {".part", ".partial", ".crdownload", ".download"}:
        return "task_download_fragment_clue", "download tool unverified", "possible partial download; actual writer, resume value and completion unknown", "protected_pending_task_review", "verify task failure/completion, source availability, references and no active download before separately supported cleanup"
    if ext in {".tmp", ".temp"}:
        return "task_scratch_file_clue", "task/tool producer unverified", "temporary-shaped file; current purpose and producer unknown", "protected_pending_task_review", "verify exact task, retained results, current references and no active writer before separately supported cleanup"
    if ext in MEDIA_EXT:
        return "media_files", "unknown/media task", "source or generated media; extension does not establish replaceability", "protected", "preserve until source/output relationship and references are proven"
    if ext in DATA_EXT:
        return "data_files", "unknown/data task", "data table/array; source versus export is unverified", "protected", "verify upstream inputs, transformations, cost and downstream consumers"
    if ext in {".zip", ".7z", ".tar", ".gz", ".bak", ".iso"}:
        return "archives_and_backups", "unknown", "archive, package or backup; retention value unknown", "protected", "verify contents through a separate bounded review and independent usable retained copy"
    if name.startswith(".env") or SENSITIVE.search(name) or name in {"auth.json", "history.jsonl"}:
        return "sensitive_metadata", "application", "sensitive/configuration metadata; content not read", "protected", "retain; no generic storage action"
    return "source_and_other", "unknown", "source, documents, configuration or unclassified ordinary files", "protected", "retain; establish precise provenance before any action"


def route(category, external=False):
    if external:
        return {"status": "evidence_only", "executor": None, "reason": "explicit related-root measurement does not prove project ownership or authorize action"}
    if category == "python_bytecode":
        return {"status": "exact_rule_available_after_validation", "executor": "storage_guard.py scan/plan/apply", "reason": "only exact CPython files accepted by the existing source, age, header, identity and activity rules"}
    if category in {"agent_task_residue_clue", "task_download_fragment_clue", "task_scratch_file_clue"}:
        return {"status": "conditional_task_lifecycle_review", "executor": None,
                "executors_to_evaluate": ["agent_artifact_guard.py"],
                "reason": "names and partial-download extensions are clues only; separately prove task provenance, completion/failure, retained valuable results, no references or writers, and executor-supported payloads before any exact authorized plan"}
    if category in {"outputs_archives_recovery", "media_files", "media_and_assets"}:
        return {"status": "conditional_evidence_route", "executor": None,
            "executors_to_evaluate": ["generated_artifact_guard.py", "relocation_guard.py"],
            "reason": "generated_artifact_guard only supports separately assessed decoded-frames/render-preview/deterministic-transform intermediates with retained local inputs and producer, 48h age and verified absence of references; never originals, finished/unique AI results or unknown build outputs. relocation_guard only supports its separately verified inactive media/archive artifacts. No eligibility or releasable bytes follows from this category"}
    if category == "archives_and_backups":
        return {"status": "conditional_evidence_route", "executor": "relocation_guard.py", "reason": "only its supported inactive media/archive artifacts; requires provenance, inactivity, references, retained-copy/use acceptance and exact plans; a profile is not a plan"}
    if category == "isolated_runtime_clue":
        return {"status": "conditional_lifecycle_review", "executor": None,
                "executors_to_evaluate": ["retired_runtime_guard.py"],
                "reason": "a generated-looking PG path is not proof of disposable data; independently verify synthetic provenance, retained inputs/results, per-run completion, reference and activity evidence; business databases and recovery stores remain protected"}
    if category in {"tool_managed_cache", "unverified_cache_name"}:
        return {"status": "conditional_native_review", "executor": None,
                "executors_to_evaluate": ["native_cache_guard.py", "npm_cache_guard.py"],
                "reason": "verify actual producer and project exclusivity; only the independently qualified pip/npm adapters may execute; all other/shared/mixed caches remain advice only"}
    if category in {"dependencies", "tool_managed_cache", "framework_cache_and_build", "browser_downloads", "unverified_cache_name"}:
        return {"status": "native_advice_only", "executor": None, "reason": "current executors do not support this directory; verify manager scope before a separate proposal"}
    return {"status": "protected_or_unproven", "executor": None, "reason": "no supported general action; preserve data and obtain specific evidence"}


def review_priorities(nodes, project_totals):
    """Rank existing, mutually exclusive metadata partitions without a new read.

    This is an evidence queue, never an eligibility or free-space estimate.
    A tiny supported cache must not conceal a much larger unexplained runtime.
    """
    groups = {}
    total = project_totals["logical_bytes"]
    for node in nodes:
        if node["scope"] != "project":
            continue
        category = node["category"]
        group = groups.setdefault(category, {"category": category, "logical_bytes": 0,
            "partition_count": 0, "representative_paths": [], "release_authorized": False})
        group["logical_bytes"] += node["measurement"]["logical_bytes"]
        group["partition_count"] += 1
        if len(group["representative_paths"]) < 5:
            group["representative_paths"].append(node["path"])
    ordered = sorted(groups.values(), key=lambda x: (-x["logical_bytes"], x["category"]))
    checks = {
        "isolated_runtime_clue": "establish each run's producer, synthetic inputs, completion and inactivity; retain logs/results; qualified disposable data may be retired, otherwise state the precise missing evidence and retention route",
        "database_and_records": "distinguish current business/state/recovery data from positively proven disposable synthetic test stores; never infer disposal from a test-like name",
        "tool_managed_cache": "verify effective cache path, producer/version, exclusive ownership and offline-use cost; evaluate the dedicated pip/npm adapter without running project hooks",
        "unverified_cache_name": "identify the actual writer and layout first; evaluate a supported native adapter only after exclusive ownership is proven",
        "state_and_history": "explain the application owner and retention requirements; no direct session/index/database deletion",
        "sensitive_metadata": "retain; explain purpose without reading secrets",
        "dependencies": "establish shared references, lockfiles, local edits and recreate cost; retain until a separate supported lifecycle exists",
    }
    selected = []
    cumulative = 0
    for group in ordered:
        group["share_of_observed_project"] = group["logical_bytes"] / total if total else 0.0
        group["next_read_only_check"] = checks.get(group["category"],
            "establish actual producer, original/generated role, current consumers and business retention value; select an independently supported operation or give a concrete protection reason")
        # Keep the queue small but account for at least 80% of observed bytes.
        # With <=5 classes, retain all so even a small project is explained.
        if len(selected) < 5 or cumulative < total * .8:
            selected.append(group)
            cumulative += group["logical_bytes"]
    pyc = groups.get("python_bytecode", {}).get("logical_bytes", 0)
    return {"schema": "project-storage-review-priorities-v1",
        "basis": "existing exclusive metadata partitions; no additional traversal or body read",
        "groups": selected, "covered_logical_bytes": cumulative,
        "covered_share_of_observed_project": cumulative / total if total else 0.0,
        "observed_project_logical_bytes": total,
        "bytecode_shaped_occupancy_bytes": pyc,
        "small_cache_only_plan_risk": bool(total >= 1024 * 1024 and 0 < pyc < total * .01),
        "requires_semantic_review_before_final_recommendation": bool(total),
        "approved_release_bytes": 0, "executed_release_bytes": 0,
        "interpretation": "occupancy and review priority only; no group has been established as removable. Explain major groups before presenting a small-cache-only result. Exact plans, user authorization and receipts determine promised and actual release separately.",
        "scope_limit": "if verified project-only release cannot meet the user's goal, state the shortfall and propose a bounded related-root or volume attribution audit; do not expand deletion scope or attribute unrelated volume growth to this project"}


def agent_residue_review(nodes):
    """Reuse exclusive observations as a task-lifecycle evidence work queue.

    The queue never classifies a file as waste, proves its initiating Agent, or
    grants an operation. Related roots remain visibly separate from the project.
    """
    items, project_bytes, related_bytes = [], 0, 0
    missing = ["real initiating task/run and actual tool producer",
        "retained producer, required inputs and valuable results",
        "that run's completion/failure evidence and retention purpose",
        "current references, readers/writers and shared ownership",
        "exact executor payload/version eligibility and user-selected scope"]
    for node in nodes:
        if node["category"] not in RESIDUE_CATEGORIES or not node["measurement"]["logical_bytes"]:
            continue
        amount = node["measurement"]["logical_bytes"]
        if node["scope"] == "project":
            project_bytes += amount
        else:
            related_bytes += amount
        checks = list(missing)
        if node["hardlink_cross_boundary"]:
            checks.append("hardlink ownership/physical-space ambiguity; do not claim ordinary independent payload")
        items.append({"node_id": node["id"], "scope": node["scope"], "path": node["path"],
            "category": node["category"], "measurement": dict(node["measurement"]),
            "initiating_agent": {"name": None, "status": "not_established_by_metadata"},
            "actual_producer_clue": node["producer"], "producer_verified": False,
            "lifecycle_status": "unverified_retain", "disposal_authorized": False,
            "hardlink_cross_boundary": node["hardlink_cross_boundary"],
            "evidence_required": checks, "action_support": dict(node["action_support"]),
            "next_step": "inspect this exact producing task and retained evidence without running it; preserve until a supported exact plan qualifies"})
    items.sort(key=lambda x: (-x["measurement"]["logical_bytes"], x["scope"], x["path"], x["category"]))
    return {"schema": "agent-task-residue-review-v1", "operation": "read_only_candidate_triage",
        "basis": "existing exclusive metadata partitions; no additional traversal or body reads",
        "candidate_partition_count": len(items), "items": items[:100], "items_truncated": len(items) > 100,
        "project_candidate_logical_bytes": project_bytes, "related_candidate_logical_bytes": related_bytes,
        "approved_release_bytes": 0, "executed_release_bytes": 0,
        "protection": "source, inputs, originals, current deliverables, state/session/index, unknown/business databases, evidence and recovery boundaries are retained; isolated test-store clues still need independent lifecycle evidence",
        "interpretation": "candidate occupancy only; Agent/tool names, directory names, ages and sizes never establish invalidity. Track real run provenance and lifecycle before cleanup. No cross-host runtime compatibility is established by this report.",
        "scope_limit": "related roots are explicit observation scope only; no whole Agent home or whole-disk cleanup, and no project ownership inferred from their measurements"}


class Profiler:
    def __init__(self, args, root, codex, excluded):
        self.args, self.root, self.codex, self.excluded = args, root, codex, set(map(key, excluded))
        self.nodes, self.seen, self.manifests = {}, {}, []
        self.entries = self.files = 0
        self.config_bytes = 0
        self.ecosystems, self.bindings, self.errors, self.gaps = {}, [], [], []
        self.gap_count = 0
        self.node_overflow_reported = False
        self.reused, self.reuse_source, self.reuse_candidates = {}, None, 0
        self.reuse_hits = 0
        self.limit_hit = self.aborted_io = False
        self.external_candidates = []

    def gap(self, path, reason, scope="project"):
        self.gap_count += 1
        if len(self.gaps) < 200:
            self.gaps.append({"scope": scope, "path": scrub(path), "reason": reason})

    def error(self, path, exc, scope="project"):
        if len(self.errors) < 100:
            self.errors.append({"scope": scope, "path": scrub(path), "error_type": type(exc).__name__,
                                "errno": getattr(exc, "errno", None), "winerror": getattr(exc, "winerror", None)})
        self.gap(path, "metadata/read error; error details intentionally omit configuration values", scope)
        if fatal_io(exc):
            self.aborted_io = True

    def node(self, scope, rel, definition, evidence=None):
        category, producer, purpose, protection, recovery = definition
        nk = (scope, rel, category)
        if nk not in self.nodes and len(self.nodes) >= MAX_ATTRIBUTION_NODES:
            if not self.node_overflow_reported:
                self.gap("(additional attribution partitions)", "node detail budget reached; further files remain measured in explicit per-class overflow partitions", scope)
                self.node_overflow_reported = True
            rel = "(additional directories grouped by class)"
            nk = (scope, rel, category)
        if nk not in self.nodes:
            self.nodes[nk] = {"id": "", "scope": scope, "path": scrub(rel), "category": category,
                "producer": producer, "purpose": purpose, "ownership": "unknown",
                "location_scope": "within_selected_project" if scope == "project" else "explicit_related_root",
                "ownership_basis": "located inside selected project; location does not prove exclusive runtime/project ownership" if scope == "project" else "user-specified related root; no exclusive project binding established",
                "protection": protection, "rebuild_or_retrieve": recovery, "action_support": route(category, scope != "project"),
                "evidence": evidence or [{"kind": "path_and_filesystem_metadata", "conclusion": "classification clue only; no deletion permission"}],
                "measurement": empty_measurement(), "measurement_basis": "exclusive attribution partition; child buckets are not included again", "hardlink_cross_boundary": False}
            if category == "python_bytecode" and any(p.lower() in DEPENDENCY_DIRS | STATE_DIRS | {".git", "dist", "build", "out", "assets", "media", "public", "static", "prepared", "backup", "backups", "recovery", "release", "releases", "rollback", "worktrees"} for p in Path(rel).parts[:-1]):
                self.nodes[nk]["action_support"] = {"status": "protected_or_unproven", "executor": None,
                    "reason": "bytecode is inside a protected/tool-managed ancestor; existing storage_guard policy remains controlling"}
        return nk

    def load_scan(self, path):
        if not path:
            return
        source = absolute(path)
        name = source.name.lower()
        if (source.suffix.lower() != ".json" or name.startswith((".env", "auth.", "history.")) or SENSITIVE.search(name)
                or any(p.lower() in STATE_DIRS for p in source.parts[:-1])):
            raise ProfileError("scan-json must be an ordinary JSON inventory outside sensitive/state paths")
        # Validate known sensitive boundaries before reading any report body. A
        # renamed hardlink is additionally refused by read_bounded's link rule.
        protected = [self.codex]
        if os.environ.get("CODEX_SQLITE_HOME"):
            protected.append(absolute(os.environ["CODEX_SQLITE_HOME"]))
        protected_ids = set()
        for state_root in protected:
            if below(source, state_root):
                raise ProfileError("scan-json cannot be read from Codex/SQLite state storage")
            try:
                s = os.stat(state_root)
                if s.st_ino:
                    protected_ids.add((s.st_dev, s.st_ino))
            except FileNotFoundError:
                pass
        ancestors(source.parent)
        for parent in source.parents:
            s = plain(parent, True)
            if s.st_ino and (s.st_dev, s.st_ino) in protected_ids:
                raise ProfileError("scan-json ancestor aliases Codex/SQLite state storage")
        data = read_bounded(path, MAX_REPORT_BYTES)
        old = json.loads(data)
        if (old.get("schema") != "project-cache-exact-v1" or key(old.get("project", "")) != key(self.root)
                or old.get("root_identity") != identity(plain(self.root, True))):
            raise ProfileError("scan-json schema, project or current root identity does not match")
        for row in old.get("largest_files", []) + old.get("candidates", []):
            rel, fp, amount = row.get("path"), row.get("identity"), row.get("allocated_bytes")
            if (isinstance(rel, str) and isinstance(fp, dict) and (amount is None or isinstance(amount, int) and amount >= 0)
                    and not rel.startswith(("/", "\\")) and not any(x in {"", ".", ".."} or ":" in x for x in rel.replace("\\", "/").split("/"))):
                self.reused[rel] = (fp, amount)
        self.reuse_source = {"path": scrub(absolute(path)), "sha256": hashlib.sha256(data).hexdigest(),
            "created_at": old.get("created_at") if isinstance(old.get("created_at"), str) and re.fullmatch(r"[0-9T:.+Z-]{10,40}", old["created_at"]) else "unknown",
            "coverage_complete_in_source": old.get("coverage", {}).get("complete") is True,
            "eligible_allocation_records": len(self.reused), "matched_allocation_records_reused": 0,
            "aggregate_totals_added": False,
            "note": "fresh metadata traversal is required for protected subtrees and cross-boundary FileID deduplication; only unchanged exact-file allocation records are reused; source directory/candidate totals are not added or treated as current authorization"}
        self.reuse_candidates = len(old.get("candidates", []))

    def walk(self, root, scope):
        start_gaps = self.gap_count
        stack = [(root, None, 0)]
        root_fp = identity(plain(root, True))
        while stack and not self.limit_hit and not self.aborted_io:
            directory, inherited, depth = stack.pop()
            rel_dir = directory.relative_to(root)
            definition = classify_directory(rel_dir) if rel_dir.parts else None
            locked = inherited and self.nodes[inherited]["category"] in PROTECTED_PARTITIONS
            if definition and not locked:
                inherited = self.node(scope, rel_dir.as_posix(), definition)
            locked = inherited and self.nodes[inherited]["category"] in PROTECTED_PARTITIONS
            if depth > MAX_DEPTH:
                self.gap(rel_dir.as_posix(), "maximum directory depth reached", scope)
                continue
            try:
                with anchored_directory(directory) as anchor:
                    with os.scandir(anchor) as entries:
                        # Bounded iteration avoids materializing a huge single directory.
                        for entry in entries:
                            self.entries += 1
                            if self.entries > self.args.max_files * 4 or self.files >= self.args.max_files:
                                self.limit_hit = True
                                self.gap(rel_dir.as_posix(), "global file/entry budget reached; unvisited descendants remain unknown", scope)
                                break
                            path = directory / entry.name
                            rel = path.relative_to(root)
                            if key(path) in self.excluded:
                                continue
                            try:
                                # Windows DirEntry.stat historically returns zero st_ino/st_dev/
                                # st_nlink. lstat is required for real FileID-based deduplication.
                                s = os.lstat(path) if os.name == "nt" else entry.stat(follow_symlinks=False)
                                if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                                    self.gap(rel.as_posix(), "link/reparse entry not followed or measured", scope)
                                    continue
                                if stat.S_ISDIR(s.st_mode):
                                    stack.append((path, inherited, depth + 1))
                                    continue
                                if not stat.S_ISREG(s.st_mode):
                                    self.gap(rel.as_posix(), "special filesystem entry not measured", scope)
                                    continue
                                self.files += 1
                                if scope == "project" and manifest_kind(path) and not blocked_manifest(rel):
                                    if len(self.manifests) < MAX_CONFIG_FILES * 4:
                                        self.manifests.append((path, s.st_size))
                                    else:
                                        self.gap(rel.as_posix(), "manifest discovery budget reached")
                                # The nearest named boundary takes precedence; otherwise use extension metadata.
                                definition = file_class(path)
                                if (definition[0] in {"task_download_fragment_clue", "task_scratch_file_clue"}
                                        and any(part.lower() in SOURCE_DIRS for part in rel.parts[:-1])):
                                    definition = ("retained_project_material", "source-tree boundary", "temporary-shaped source-tree file; role unknown", "protected", "retain pending source-specific review")
                                # Critical files inside scratch-like roots stay separately
                                # protected. A parent task label cannot absorb live source,
                                # database/session, input/config or final-shaped material.
                                critical = (definition[0] in {"sensitive_metadata", "database_and_records", "version_control"}
                                    or path.suffix.lower() in SOURCE_EXT | DATA_EXT | {".sql", ".ipynb", ".pem", ".key"})
                                if inherited and self.nodes[inherited]["category"] == "agent_task_residue_clue" and critical:
                                    nk = self.node(scope, rel_dir.as_posix() if rel_dir.parts else ".", definition)
                                elif definition[0] in {"task_download_fragment_clue", "task_scratch_file_clue"} and not locked:
                                    nk = self.node(scope, rel.as_posix(), definition)
                                else:
                                    nk = inherited or self.node(scope, rel_dir.as_posix() if rel_dir.parts else ".", definition)
                                node = self.nodes[nk]
                                node["measurement"]["files"] += 1
                                file_id = (s.st_dev, s.st_ino) if s.st_ino else ("unknown", key(path))
                                if file_id in self.seen:
                                    prior = self.seen[file_id]
                                    node["measurement"]["hardlink_duplicates"] += 1
                                    if prior["node"] != nk:
                                        node["hardlink_cross_boundary"] = self.nodes[prior["node"]]["hardlink_cross_boundary"] = True
                                    if prior["fingerprint"] != fingerprint(s):
                                        self.gap(rel.as_posix(), "same FileID changed during metadata snapshot", scope)
                                    continue
                                allocation = None
                                cached = self.reused.get(rel.as_posix()) if scope == "project" else None
                                if cached and cached[0] == fingerprint(s) and cached[1] is not None:
                                    allocation = cached[1]
                                    self.reuse_hits += 1
                                else:
                                    try:
                                        allocation = allocated(path, s)
                                    except (OSError, ProfileError) as exc:
                                        self.error(rel.as_posix(), exc, scope)
                                add_measurement(node["measurement"], s.st_size, allocation, not bool(s.st_ino))
                                self.seen[file_id] = {"node": nk, "fingerprint": fingerprint(s)}
                                if not s.st_ino:
                                    self.gap(rel.as_posix(), "FileID unavailable; cross-path hardlink deduplication unknown", scope)
                                if s.st_nlink > 1:
                                    node["hardlink_cross_boundary"] = True
                                if self.aborted_io:
                                    break
                            except (OSError, ProfileError) as exc:
                                self.error(rel.as_posix(), exc, scope)
                                if self.aborted_io:
                                    break
            except (OSError, ProfileError) as exc:
                self.error(rel_dir.as_posix(), exc, scope)
        try:
            if identity(plain(root, True)) != root_fp:
                self.gap(str(root), "selected root identity changed during observation", scope)
        except (OSError, ProfileError) as exc:
            self.error(str(root), exc, scope)
        return {"scope": scope, "path": scrub(root), "traversal_complete": self.gap_count == start_gaps and not self.limit_hit and not self.aborted_io,
                "ownership": "unknown", "authorization": "observation only"}

    def signal(self, ecosystem, evidence, confidence="manifest"):
        item = self.ecosystems.setdefault(ecosystem, {"name": ecosystem, "confidence": confidence, "evidence": []})
        if evidence not in item["evidence"] and len(item["evidence"]) < 15:
            item["evidence"].append(scrub(evidence))

    def binding(self, value, path, field, producer):
        # Literal paths only. Never expand shell variables, evaluate expressions, URLs or secrets.
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            return
        value = value.strip().strip('"\'')
        if (SENSITIVE.search(value) or TOKEN.search(value) or "://" in value or "${" in value
                or re.search(r"[\x00-\x1f`$%*?<>|;]", value) or value in {"0", "false", "true"}):
            self.bindings.append({"config": scrub(path.relative_to(self.root)), "field": field,
                "producer": producer, "status": "literal_path_not_accepted", "reason": "expression, URL, sensitive value, glob or non-path setting; value omitted"})
            return
        candidate = absolute(path.parent / value) if not os.path.isabs(value) else absolute(value)
        record = {"config": scrub(path.relative_to(self.root)), "field": field, "producer": producer,
                  "path": scrub(candidate), "scope": "project" if below(candidate, self.root) else "external",
                  "binding_strength": "literal configured path; active configuration and runtime use unverified",
                  "ownership": "unknown", "action_support": "evidence_only"}
        self.bindings.append(record)
        if record["scope"] == "external":
            self.external(candidate, producer, "explicit configuration field " + field, "unknown")

    def parse_configs(self):
        read_count = 0
        for path, size in sorted(self.manifests, key=lambda x: (len(x[0].relative_to(self.root).parts), str(x[0]))):
            rel, name = path.relative_to(self.root).as_posix(), path.name.lower()
            self.detect_marker(path, rel)
            if not content_allowed(path):
                continue
            if read_count >= MAX_CONFIG_FILES or self.config_bytes + size > self.args.max_config_bytes or size > MAX_CONFIG_FILE_BYTES:
                self.gap(rel, "allowlisted configuration content budget reached; metadata marker still recorded")
                continue
            try:
                data = read_bounded(path, min(4096 if name in {".git", "commondir"} else MAX_CONFIG_FILE_BYTES,
                                              self.args.max_config_bytes - self.config_bytes))
                self.config_bytes += len(data)
                read_count += 1
                text = data.decode("utf-8-sig", errors="replace")
                self.parse_config(path, text)
            except (OSError, ProfileError, ValueError, RecursionError) as exc:
                self.error(rel, exc)
                if self.aborted_io:
                    break
        self.config_count = read_count

    def detect_marker(self, path, rel):
        name = path.name.lower()
        mapping = {"package.json": "Node.js", "pyproject.toml": "Python", "requirements.txt": "Python/pip",
            "pipfile": "Python/Pipenv", "uv.lock": "Python/uv", "uv.toml": "Python/uv",
            "poetry.lock": "Python/Poetry", "poetry.toml": "Python/Poetry", "cargo.toml": "Rust/Cargo",
            "cargo.lock": "Rust/Cargo", "go.mod": "Go", "go.work": "Go", "pom.xml": "Java/Maven",
            "build.gradle": "Java/Gradle", "build.gradle.kts": "Java/Gradle", "settings.gradle": "Java/Gradle",
            "settings.gradle.kts": "Java/Gradle", "cmakelists.txt": "C/C++/CMake",
            "cmakepresets.json": "C/C++/CMake", "pubspec.yaml": "Dart/Flutter",
            "package.swift": "Swift/Apple", "project.pbxproj": "Xcode/Apple", "podfile": "Apple/CocoaPods",
            "global.json": ".NET", "directory.build.props": ".NET", "package-lock.json": "Node/npm",
            "pnpm-lock.yaml": "Node/pnpm", "yarn.lock": "Node/Yarn", "bun.lock": "Node/Bun",
            "bun.lockb": "Node/Bun", "pyvenv.cfg": "Python environment"}
        if name in mapping:
            self.signal(mapping[name], rel)
        if path.suffix.lower() in {".csproj", ".fsproj", ".vbproj", ".sln"}:
            self.signal(".NET", rel)
        if "android" in [x.lower() for x in path.relative_to(self.root).parts] and "gradle" in name:
            self.signal("Android", rel)
        for stem, ecosystem in {"next.config": "Next.js", "vite.config": "Vite", "remotion.config": "Remotion",
                               "playwright.config": "Playwright", "cypress.config": "Cypress"}.items():
            if name.startswith(stem + "."):
                self.signal(ecosystem, rel + " (presence only; code not executed)")

    def parse_config(self, path, text):
        name, rel = path.name.lower(), path.relative_to(self.root).as_posix()
        if name in {".git", "commondir"}:
            # Only the small path pointer is parsed. No target, common-directory or Git config is read.
            value = text.strip()
            if name == ".git":
                match = re.fullmatch(r"gitdir:\s*([^\r\n]+)", value)
                if match:
                    self.binding(match[1], path, "gitdir", "Git worktree pointer; not followed")
            elif len(value) <= 4096 and "\n" not in value and "\r" not in value:
                self.binding(value, path, "commondir", "Git common-directory pointer; not followed")
            return
        if name == "package.json":
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError("package manifest must be an object")
            packages = set()
            for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                if isinstance(obj.get(field), dict):
                    packages.update(obj[field])
            known = {"next": "Next.js", "vite": "Vite", "remotion": "Remotion", "@remotion/cli": "Remotion",
                "@playwright/test": "Playwright", "playwright": "Playwright", "playwright-core": "Playwright",
                "cypress": "Cypress", "@angular/core": "Angular", "nuxt": "Nuxt", "@sveltejs/kit": "SvelteKit"}
            for package, ecosystem in known.items():
                if package in packages:
                    self.signal(ecosystem, rel + ": recognized dependency " + package)
            manager = obj.get("packageManager", "")
            if isinstance(manager, str):
                match = re.match(r"^(npm|pnpm|yarn|bun)@", manager)
                if match:
                    self.signal("Node/" + match[1], rel + ": packageManager")
            return
        if name in {"pyproject.toml", "uv.toml", "poetry.toml", "requirements.txt", "pipfile"}:
            if re.search(r"(?m)^\s*\[tool\.uv(?:\]|\.)", text) or name == "uv.toml":
                self.signal("Python/uv", rel + ": recognized tool section")
            if re.search(r"(?m)^\s*\[tool\.poetry(?:\]|\.)", text) or name == "poetry.toml":
                self.signal("Python/Poetry", rel + ": recognized tool section")
            if re.search(r"(?i)(?:^|[\s\[\"'])playwright(?:[\s\]\"'=<>~!]|$)", text):
                self.signal("Playwright", rel + ": recognized Python dependency")
            if re.search(r"(?i)(?:^|[\s\[\"'])(?:pandas|polars|duckdb|pyarrow|datasets)(?:[\s\]\"'=<>~!]|$)", text):
                self.signal("Data processing", rel + ": recognized data dependency")
        if name == "pubspec.yaml" and re.search(r"(?m)^\s*flutter\s*:", text):
            self.signal("Flutter", rel + ": Flutter dependency/section")
        if name in {"go.mod", "go.work"}:
            for match in re.finditer(r"(?m)^\s*(?:replace\s+)?[^\r\n]*?=>\s*(\.{1,2}[\\/][^\s]+|[A-Za-z]:[\\/][^\s]+|/[^\s]+)\s*(?://.*)?$", text):
                self.binding(match[1], path, "replace local module", "Go local replacement; not recursively followed")
        path_fields = {
            ".npmrc": ("Node/npm", {"cache", "prefix", "userconfig"}),
            ".yarnrc.yml": ("Node/Yarn", {"cacheFolder", "globalFolder", "installStatePath"}),
            ".yarnrc": ("Node/Yarn", {"cache-folder"}),
            "config.toml": ("Rust/Cargo", {"target-dir"}),
            "gradle.properties": ("Gradle", {"org.gradle.projectcachedir", "gradle.user.home"}),
            "pip.conf": ("Python/pip", {"cache-dir"}), "pip.ini": ("Python/pip", {"cache-dir"}),
            "uv.toml": ("Python/uv", {"cache-dir"}), "poetry.toml": ("Python/Poetry", {"cache-dir"}),
            "pyproject.toml": ("Python (section binding requires review)", {"cache-dir"}),
        }
        if name in path_fields:
            producer, fields = path_fields[name]
            # Only literal assignment fields; comments, authentication and arbitrary keys are ignored.
            for line in text.splitlines():
                match = re.match(r"\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(.+?)\s*$", line)
                if match and match[1] in fields:
                    value = match[2]
                    if value.startswith(('"', "'")):
                        q = value[0]
                        end = value.find(q, 1)
                        if end < 0 or value[end + 1:].strip() not in {"", "#"} and not value[end + 1:].lstrip().startswith("#"):
                            continue
                        value = value[1:end]
                    elif "#" in value:
                        value = value.split("#", 1)[0].strip()
                    self.binding(value, path, match[1], producer)
        # Parse common tool JSON without executing JS; only known path keys are visited.
        if name in {"cmakepresets.json", "turbo.json", "nx.json"}:
            obj = json.loads(text)
            fields = {"binaryDir", "cacheDir", "cacheDirectory"}
            def visit(value, depth=0):
                if depth > 12:
                    return
                if isinstance(value, dict):
                    for k, v in value.items():
                        if k in fields and isinstance(v, str):
                            self.binding(v, path, k, "CMake" if name == "cmakepresets.json" else "Node build orchestrator")
                        elif isinstance(v, (dict, list)):
                            visit(v, depth + 1)
                elif isinstance(value, list):
                    for v in value[:100]:
                        visit(v, depth + 1)
            visit(obj)
        if any(name.startswith(stem + ".") for stem in CONFIG_STEMS):
            fields = {"cacheDir", "outDir", "distDir", "outputDir", "downloadsPath", "userDataDir",
                      "videosFolder", "screenshotsFolder", "downloadsFolder"}
            # A literal is only a path clue; comments/branches may be inactive, so no active binding claim.
            for match in re.finditer(r"\b([A-Za-z][A-Za-z0-9]*)\s*:\s*(['\"])([^\r\n]*?)\2\s*(?=[,}\r\n])", text):
                if match[1] in fields:
                    self.binding(match[3], path, match[1], "tool config literal (inactive branches/comments possible)")
        if path.suffix.lower() in {".csproj", ".fsproj", ".vbproj"} or name in {"directory.build.props", "nuget.config"}:
            for match in re.finditer(r"<(BaseIntermediateOutputPath|IntermediateOutputPath|BaseOutputPath|OutputPath|RestorePackagesPath)>\s*([^<]+)\s*</\1>", text):
                self.binding(match[2], path, match[1], ".NET/MSBuild")
            for match in re.finditer(r"<add\s+key=['\"]globalPackagesFolder['\"]\s+value=['\"]([^'\"]+)['\"]", text):
                self.binding(match[1], path, "globalPackagesFolder", ".NET/NuGet")

    def external(self, path, producer, source, ownership="shared"):
        path = absolute(path)
        record = {"path": scrub(path), "producer": producer, "source": source, "ownership": ownership,
                  "recursive_scan": False, "size": None, "size_status": "unknown_not_recursively_scanned",
                  "protection": "protected", "action_support": "evidence_only", "existence": "unknown"}
        try:
            s = os.lstat(path)
            record["existence"] = "present"
            record["entry_type"] = "link_or_reparse" if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400 else "directory" if stat.S_ISDIR(s.st_mode) else "file" if stat.S_ISREG(s.st_mode) else "special"
        except FileNotFoundError:
            record["existence"] = "absent"
        except OSError as exc:
            record["existence"] = "unverifiable"
            record["error_type"] = type(exc).__name__
        if not any(x["path"] == record["path"] and x["producer"] == producer for x in self.external_candidates):
            self.external_candidates.append(record)

    def external_defaults(self):
        home, env = Path.home(), os.environ
        def candidate(variable, default, producer):
            value = env.get(variable)
            # These variables denote path candidates, never shell-expanded values.
            if value and (SENSITIVE.search(value) or TOKEN.search(value) or "://" in value or re.search(r"[\x00-\x1f`$%<>|;]", value)):
                self.external_candidates.append({"producer": producer, "source": "environment " + variable,
                    "status": "value_omitted_unaccepted_path", "ownership": "shared", "recursive_scan": False,
                    "size": None, "action_support": "evidence_only"})
                return
            self.external(value or default, producer, "environment " + variable if value else "platform default candidate; active manager configuration unverified")
        names = set(self.ecosystems)
        if any(x.startswith("Node") or x in {"Next.js", "Vite", "Remotion", "Cypress", "Playwright"} for x in names):
            default = Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "npm-cache" if os.name == "nt" else home / ".npm"
            candidate("npm_config_cache", env.get("NPM_CONFIG_CACHE", str(default)), "Node/npm")
            if "Node/pnpm" in names:
                candidate("PNPM_HOME", Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "pnpm" if os.name == "nt" else home / ".local/share/pnpm", "Node/pnpm home (store path requires manager query)")
        if any(x.startswith("Python") for x in names):
            pip_default = Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "pip/Cache" if os.name == "nt" else home / "Library/Caches/pip" if sys.platform == "darwin" else Path(env.get("XDG_CACHE_HOME", home / ".cache")) / "pip"
            candidate("PIP_CACHE_DIR", pip_default, "Python/pip")
            if "Python/uv" in names:
                candidate("UV_CACHE_DIR", Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "uv/cache" if os.name == "nt" else home / "Library/Caches/uv" if sys.platform == "darwin" else Path(env.get("XDG_CACHE_HOME", home / ".cache")) / "uv", "Python/uv")
        if "Rust/Cargo" in names:
            candidate("CARGO_HOME", home / ".cargo", "Rust/Cargo home (registries/git/toolchain state)")
            if env.get("CARGO_TARGET_DIR"):
                candidate("CARGO_TARGET_DIR", self.root / "target", "Rust/Cargo target override")
        if "Java/Gradle" in names:
            candidate("GRADLE_USER_HOME", home / ".gradle", "Gradle user home")
        if "Java/Maven" in names:
            self.external(home / ".m2/repository", "Maven", "default repository candidate; settings.xml not read")
        if "Go" in names:
            candidate("GOPATH", home / "go", "Go workspace/module storage; exact GOMODCACHE unverified")
            if env.get("GOMODCACHE"):
                candidate("GOMODCACHE", home / "go/pkg/mod", "Go module cache")
            default = Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "go-build" if os.name == "nt" else home / "Library/Caches/go-build" if sys.platform == "darwin" else Path(env.get("XDG_CACHE_HOME", home / ".cache")) / "go-build"
            candidate("GOCACHE", default, "Go build cache")
        if ".NET" in names:
            candidate("NUGET_PACKAGES", home / ".nuget/packages", "NuGet global packages")
        if names & {"Flutter", "Dart/Flutter"}:
            candidate("PUB_CACHE", Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "Pub/Cache" if os.name == "nt" else home / ".pub-cache", "Dart/Flutter package cache")
        if "Playwright" in names:
            value = env.get("PLAYWRIGHT_BROWSERS_PATH")
            if value == "0":
                self.external_candidates.append({"producer": "Playwright", "source": "environment PLAYWRIGHT_BROWSERS_PATH=0",
                    "path": None, "ownership": "unknown", "recursive_scan": False, "size": None,
                    "action_support": "evidence_only", "note": "package-local hermetic browsers; determine exact installed package path"})
            else:
                default = Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "ms-playwright" if os.name == "nt" else home / "Library/Caches/ms-playwright" if sys.platform == "darwin" else Path(env.get("XDG_CACHE_HOME", home / ".cache")) / "ms-playwright"
                candidate("PLAYWRIGHT_BROWSERS_PATH", default, "Playwright browser downloads")
        if "Cypress" in names:
            default = Path(env.get("LOCALAPPDATA", home / "AppData/Local")) / "Cypress/Cache" if os.name == "nt" else home / "Library/Caches/Cypress" if sys.platform == "darwin" else Path(env.get("XDG_CACHE_HOME", home / ".cache")) / "Cypress"
            candidate("CYPRESS_CACHE_FOLDER", default, "Cypress downloaded binaries")
        self.external(self.codex, "Codex cross-project state", "--codex-home / CODEX_HOME / default; existence only")
        if env.get("CODEX_SQLITE_HOME"):
            candidate("CODEX_SQLITE_HOME", self.codex, "Codex cross-project SQLite state override; config sqlite_home may take precedence")

    def bind_node_producers(self):
        """Attach nearby allowlisted manifests, without inferring active runtime use."""
        candidates = []
        for name, item in self.ecosystems.items():
            for evidence in item["evidence"]:
                rel = evidence.split(":", 1)[0].split(" (", 1)[0]
                candidates.append((name, Path(rel).parent, rel))
        for node in self.nodes.values():
            if node["scope"] != "project":
                continue
            p = Path(node["path"])
            nearby = []
            for name, parent, manifest in candidates:
                if parent == Path(".") or p == parent or parent in p.parents:
                    nearby.append((len(parent.parts), name, manifest))
            if not nearby:
                continue
            depth = max(x[0] for x in nearby)
            matches = sorted({(name, manifest) for d, name, manifest in nearby if d == depth})[:12]
            node["producer_candidates_from_nearby_manifests"] = [{"ecosystem": name, "manifest": manifest,
                "status": "nearby manifest clue; does not establish active producer or exclusive ownership"} for name, manifest in matches]
            node["evidence"].append({"kind": "nearby_allowlisted_manifest", "manifests": [manifest for _, manifest in matches],
                                     "conclusion": "cross-check exact producing task and runtime configuration"})
            if (node["category"] in {"tool_managed_cache", "unverified_cache_name"}
                    and any(name.startswith("Python") for name, _ in matches)):
                node["native_adapter_hint"] = {"executor_to_evaluate": "native_cache_guard.py",
                    "status": "further_verification_required", "reason": "only a cache that the native adapter independently verifies as project-exclusive pip data may qualify; shared/default pip caches remain advice only, and cache naming does not prove a pip producer"}

    def codex_shallow_metadata(self):
        result = {"path": scrub(self.codex), "scope": "top-level metadata only", "ownership": "shared",
                  "protection": "protected_shared", "recursive_scan": False, "directory_size": None,
                  "content_read": False, "entries": [], "size_status": "directory_total_unknown"}
        try:
            with anchored_directory(self.codex) as anchor:
                with os.scandir(anchor) as entries:
                    for i, entry in enumerate(entries):
                        if i >= 200:
                            result["truncated"] = True
                            break
                        if SENSITIVE.search(entry.name) or "auth" in entry.name.lower():
                            continue
                        s = entry.stat(follow_symlinks=False)
                        linked = stat.S_ISLNK(s.st_mode) or bool(getattr(s, "st_file_attributes", 0) & 0x400)
                        result["entries"].append({"name": scrub(entry.name), "entry_type": "link_or_reparse" if linked else "directory" if stat.S_ISDIR(s.st_mode) else "file",
                            "logical_file_bytes": s.st_size if stat.S_ISREG(s.st_mode) and not linked else None,
                            "directory_bytes": None, "action_support": "protected_shared"})
        except FileNotFoundError:
            result["existence"] = "absent"
        except (OSError, ProfileError) as exc:
            result["error_type"] = type(exc).__name__
        return result


def probes(ecosystems):
    names = {x["name"] for x in ecosystems}
    result = []
    choices = [
        (any(x.startswith("Node") or x in {"Next.js", "Vite", "Remotion"} for x in names), "Node/npm", ["npm", "config", "get", "cache"], "read configured npm cache path"),
        ("Node/pnpm" in names, "Node/pnpm", ["pnpm", "store", "path"], "read configured pnpm store path"),
        (any(x.startswith("Python") for x in names), "Python/pip", ["TRUSTED_PYTHON", "-I", "-m", "pip", "cache", "info"], "query pip cache statistics in a trusted interpreter; isolated mode avoids project imports"),
        ("Python/uv" in names, "Python/uv", ["uv", "cache", "dir"], "read uv cache path"),
        ("Go" in names, "Go", ["go", "env", "GOCACHE", "GOMODCACHE", "GOPATH"], "read effective Go cache paths; toolchain auto-download must be disabled first"),
        (".NET" in names, ".NET/NuGet", ["dotnet", "nuget", "locals", "all", "--list"], "list NuGet cache locations; pre-provisioned trusted SDK required"),
        ("Cypress" in names, "Cypress", ["TRUSTED_INSTALLED_CYPRESS", "cache", "path"], "query existing Cypress cache path; no package runner or installation"),
        (True, "Git (only if repository exists)", ["git", "count-objects", "-v"], "query existing repository object statistics; run only in a verified repository"),
    ]
    for condition, producer, argv, purpose in choices:
        if condition:
            result.append({"producer": producer, "suggested_argv": argv, "purpose": purpose,
                "executed": False, "operation": "inspection_suggestion_only", "requires": "verify trusted installed executable, exact project scope and local policy first; do not use npx/corepack/install/build/clean commands; first-run/config/plugin side effects remain unverified"})
    for name in sorted(names & {"Rust/Cargo", "Java/Gradle", "Java/Maven", "Playwright", "C/C++/CMake", "Xcode/Apple", "Flutter"}):
        result.append({"producer": name, "suggested_argv": None, "executed": False,
            "purpose": "inspect known manifest/configuration and installed tool version; establish exact output/cache path without a build, install, dependency resolution or clean",
            "operation": "manual_evidence_check", "reason": "no universal side-effect-free project cache census is assumed"})
    return result


def markdown(report):
    def cell(x):
        return scrub(x).replace("|", "\\|").replace("\n", " ")
    cov = report["coverage"]
    lines = ["# Project storage profile", "", f"Project: `{cell(report['project'])}`", "",
        f"Observation: {report['created_at']}",
        f"Project metadata traversal complete: **{cov['project_traversal_complete']}**. Overall evidence complete: **False**.",
        "This is a bounded snapshot, not a comprehensive audit. Large occupancy does not establish its writer, growth, inactivity or reclaimable space.",
        "No project command, install, build, hook, cleanup or migration was executed. No releasable-byte promise is produced.", "",
        "## Project ecosystems", ""]
    for item in report["ecosystems"]:
        lines.append(f"- **{cell(item['name'])}**: " + "; ".join(cell(x) for x in item["evidence"]))
    if not report["ecosystems"]:
        lines.append("No supported tool manifest was established within the bounded scope.")
    totals = report["project_measurement"]
    lines += ["", "## Main measured sources", "",
        f"Unique observed project files: {totals['unique_files']}; logical bytes: {totals['logical_bytes']}; known allocated bytes: {totals['allocated_bytes_known']}; unknown allocation files: {totals['allocation_unknown_files']}.",
        "Rows are exclusive attribution partitions. Nested categories and reused scan totals are not counted twice. Hardlinks are attributed to their first observed path; this is not ownership or a release estimate.", "",
        "| Path | Class / producer | Logical bytes | Known allocation | Protection / route |",
        "|---|---|---:|---:|---|"]
    project_nodes = [x for x in report["nodes"] if x["scope"] == "project"]
    for node in project_nodes[:100]:
        if node["scope"] == "project":
            m = node["measurement"]
            lines.append(f"| `{cell(node['path'])}` | {cell(node['category'])} / {cell(node['producer'])} | {m['logical_bytes']} | {m['allocated_bytes_known']} ({m['allocation_unknown_files']} unknown files) | {cell(node['protection'])}; {cell(node['action_support']['status'])} |")
    if len(project_nodes) > 100:
        lines += ["", f"Only the largest 100 of {len(project_nodes)} project attribution partitions appear here; JSON contains all bounded rows."]
    residues = report["agent_residue_review"]
    lines += ["", "## Agent task residue review queue", "",
        "Prioritize possible task leftovers before proposing valuable-document migration. Each row is an exclusive measured partition requiring real task/tool/lifecycle evidence, never a disposable directory or free-space promise. Initiating Agent is not established by metadata.", "",
        "| Scope / path | Candidate clue | Logical bytes | Next action |",
        "|---|---|---:|---|"]
    for item in residues["items"]:
        lines.append(f"| {cell(item['scope'])} / `{cell(item['path'])}` | {cell(item['category'])}; actual producer unverified | {item['measurement']['logical_bytes']} | retain; establish real run, producer, completion, valuable results, references and idle status |")
    if not residues["items"]:
        lines.append("No supported residue clue was observed in this bounded snapshot. This does not prove that no leftovers exist.")
    if residues["items_truncated"]:
        lines.append(f"Only the largest 100 of {residues['candidate_partition_count']} candidate partitions are shown; omitted partitions are still included in the separately scoped observed amounts.")
    lines += ["", f"Project candidate occupancy: {residues['project_candidate_logical_bytes']} logical bytes; explicit related roots: {residues['related_candidate_logical_bytes']} logical bytes. Approved release: 0; actual release: 0.",
        "Protected source/input/final/state/database/evidence/recovery material is retained. A mixed `.runtime`/`outputs` root cannot be deleted from this report. Name, age, location and lack of a search hit do not establish invalidity."]
    priorities = report["review_priorities"]
    lines += ["", "## Priorities for meaningful optimization", "",
        "These are measured bytes requiring an explanation, not removable-byte promises. A cache-shaped file is not yet eligible. Real plans and receipts must report promised and actual release separately.", "",
        "| Measured class | Logical bytes | Share of observed project | Next evidence |",
        "|---|---:|---:|---|"]
    for group in priorities["groups"]:
        lines.append(f"| {cell(group['category'])} | {group['logical_bytes']} | {group['share_of_observed_project']:.1%} | {cell(group['next_read_only_check'])} |")
    if priorities["small_cache_only_plan_risk"]:
        lines += ["", "**Small-cache-only result risk:** bytecode-shaped occupancy is less than 1% of this observed project. Explain the major groups, including any lifecycle/capability gaps, before finishing with a small bytecode plan. This warning does not imply any other data can be removed."]
    lines += ["", priorities["scope_limit"]]
    lines += ["", "## External roots and shared candidates", "",
        "External observations are listed separately. An explicit related root is observation scope only; it does not prove project exclusivity. Default/config candidates are not recursively scanned.", ""]
    for root in report["related_roots"]:
        lines.append(f"- `{cell(root['path'])}`: {cell(root.get('status', 'measured'))}; ownership unknown; traversal complete {root.get('traversal_complete', False)}.")
    for item in report["external_candidates"]:
        lines.append(f"- {cell(item['producer'])}: `{cell(item.get('path', '(exact path not established)'))}`; {cell(item.get('existence', item.get('status', 'unknown')))}; size unknown; {cell(item['source'])}.")
    lines += ["", "## Configuration path clues", ""]
    for item in report["configured_path_clues"]:
        lines.append(f"- `{cell(item['config'])}` / {cell(item['field'])}: `{cell(item.get('path', '(value omitted)'))}`; {cell(item.get('binding_strength', item.get('reason', 'unverified')))}.")
    lines += ["", "## Available action routes", ""]
    lines += ["- `storage_guard.py`: only exact selected CPython bytecode that passes its existing validations; a profile category cannot add eligible files.",
        "- `generated_artifact_guard.py`: only separately assessed decoded frames, render previews or deterministic media intermediates with retained local inputs/producer, age and reference checks; originals, finished outputs, unique AI results and unknown build outputs remain protected.",
        "- `relocation_guard.py`: only its supported inactive media/archive artifact cases after its separate provenance, reference, identity, copy and use acceptance checks.",
        "- `native_cache_guard.py`: only its independently verified project-exclusive pip adapter; shared pip defaults remain advice only. This profile does not establish adapter eligibility.",
        "- `npm_cache_guard.py`: separately qualified project-exclusive npm cache only; native cleaning uses a fixed trusted tool and an isolated cache namespace, not project hooks. Default/shared caches remain advice only.",
        "- `retired_runtime_guard.py`: only positively qualified disposable synthetic PG test data; retain sibling logs, results, inputs and producers. Names, UUIDs and no PID file do not prove safety; business databases remain protected.",
        "- `agent_artifact_guard.py`: only separately assessed supported scratch payloads from completed/failed tasks, with retained producer, inputs/results, lifecycle and idle/reference evidence. No mixed runtime root, source, session/index, database, final or recovery deletion.",
        "- Dependencies, framework caches, browser downloads, build systems and shared caches: native inspection/advice only; no generic executable deletion rule.",
        "", "## Native inspection suggestions (not executed)", ""]
    for item in report["native_cache_probes"]:
        label = " ".join(item["suggested_argv"]) if item["suggested_argv"] else "manual metadata/configuration check"
        lines.append(f"- {cell(item['producer'])}: `{cell(label)}` — {cell(item['purpose'])}.")
    lines += ["", "Use a verified installed executable and inspect its configuration and side effects before any optional probe. No package runners, downloads, builds or clean commands are suggested.",
        "", "## Coverage and limits", "",
        f"Files observed: {cov['files_observed']}; entries observed: {cov['entries_observed']}; file/entry limit hit: {cov['limit_hit']}; hardware I/O abort: {cov['aborted_io']}.",
        f"Allowlisted config files read: {cov['config_files_read']}; config content bytes: {cov['config_bytes_read']}; total config allowance: {cov['max_config_bytes']}.",
        "Ordinary file metadata inside protected directories is measured. No environment/authentication/session/customer document body is intentionally read. Symlinks/reparse points are not followed. Directory metadata, alternate streams, filesystem overhead, dedup/compression sharing and files outside the selected roots are not a complete physical-space census.",
        "", "## Valuable next evidence", ""]
    lines.extend("- " + cell(x) for x in report["next_evidence_checks"])
    if report["source_scan_reuse"]:
        reuse = report["source_scan_reuse"]
        lines += ["", f"Existing scan reuse: {reuse['matched_allocation_records_reused']} exact unchanged allocation records; aggregate scan totals were not added. {cell(reuse['note'])}"]
    lines += ["", "## Observed gaps", ""]
    lines.extend(f"- [{cell(x['scope'])}] `{cell(x['path'])}`: {cell(x['reason'])}" for x in report["gaps"])
    if not report["gaps"]:
        lines.append("No traversal gap was observed within the stated bounds; ownership, activity, references and external-root totals remain unverified.")
    return "\n".join(lines) + "\n"


def inspect(args):
    if not 1 <= args.max_files <= 10_000_000 or not 1 <= args.max_config_bytes <= 64 * 1024 * 1024:
        raise ProfileError("max-files must be 1..10000000 and max-config-bytes 1..67108864")
    codex = absolute(args.codex_home or os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    root = selected_root(args.project, codex)
    output = new_output(args.output)
    if output.suffix.lower() != ".json":
        raise ProfileError("output must name a new .json report file")
    md = new_output(output.with_suffix(".md"))
    selected = []
    for value in args.related_root:
        related = selected_root(value, codex, related=True)
        if below(root, related):
            raise ProfileError("related-root cannot be the project or a parent containing the project")
        if any(below(related, x) or below(x, related) for x in selected):
            raise ProfileError("related-root scopes must not overlap one another")
        selected.append(related)
    protected_state_roots = [codex]
    if os.environ.get("CODEX_SQLITE_HOME"):
        protected_state_roots.append(absolute(os.environ["CODEX_SQLITE_HOME"]))
    for target in (output, md):
        output_outside_observation(target, [root, *protected_state_roots, *selected])
    profiler = Profiler(args, root, codex, [output, md])
    profiler.load_scan(args.scan_json)
    project_scope = profiler.walk(root, "project")
    related_results = []
    for i, related in enumerate(selected, 1):
        if below(related, root):
            related_results.append({"path": scrub(related), "status": "already_within_project_metadata_scope",
                "traversal_complete": project_scope["traversal_complete"], "ownership": "unknown", "authorization": "observation only"})
        elif profiler.limit_hit or profiler.aborted_io:
            related_results.append({"path": scrub(related), "status": "not_scanned_global_budget_or_io_abort", "ownership": "unknown"})
            profiler.gap(str(related), "explicit related root not reached due to shared scan budget or hardware I/O abort", "related_" + str(i))
        else:
            related_results.append(profiler.walk(related, "related_" + str(i)))
    if not profiler.aborted_io:
        profiler.parse_configs()
    else:
        profiler.config_count = 0
    profiler.bind_node_producers()
    if not profiler.aborted_io:
        profiler.external_defaults()
        codex_metadata = profiler.codex_shallow_metadata()
    else:
        codex_metadata = {"path": scrub(codex), "status": "not_observed_after_hardware_io_abort",
                          "ownership": "shared", "protection": "protected_shared", "directory_size": None,
                          "recursive_scan": False, "content_read": False}
    nodes = sorted(profiler.nodes.values(), key=lambda x: (x["scope"] != "project", -x["measurement"]["logical_bytes"], x["path"], x["category"]))
    project_totals = empty_measurement()
    external_totals = empty_measurement()
    for i, node in enumerate(nodes, 1):
        node["id"] = f"P{i:06d}"
        for field in project_totals:
            (project_totals if node["scope"] == "project" else external_totals)[field] += node["measurement"][field]
    if profiler.reuse_source:
        profiler.reuse_source["matched_allocation_records_reused"] = profiler.reuse_hits
    ecosystems = sorted(profiler.ecosystems.values(), key=lambda x: x["name"])
    if any(n["category"] in {"media_files", "media_and_assets", "outputs_archives_recovery"} for n in nodes if n["scope"] == "project"):
        ecosystems.append({"name": "Media/export workflow clue", "confidence": "metadata_clue_only",
                           "evidence": ["media/export directory names or media file extensions; source/output role and producer unverified"]})
    if any(n["category"] in {"data_files", "data_and_models"} for n in nodes if n["scope"] == "project"):
        ecosystems.append({"name": "Data workflow clue", "confidence": "metadata_clue_only",
                           "evidence": ["dataset/model paths or data file extensions; source/output role unverified"]})
    report = {"schema": SCHEMA, "tool_version": VERSION, "created_at": utc(), "project": scrub(root),
        "root_identity": identity(plain(root, True)), "operation": "read_only_profile", "commands_executed": [],
        "ecosystems": ecosystems, "nodes": nodes, "project_measurement": project_totals,
        "review_priorities": review_priorities(nodes, project_totals),
        "agent_residue_review": agent_residue_review(nodes),
        "related_root_measurement_excluding_project_hardlink_duplicates": external_totals,
        "measurement_notes": ["all category rows are exclusive partitions, not overlapping subtree totals",
            "hardlinks are deduplicated by device/FileID across all explicitly measured roots and attributed to first observed path; project is measured first",
            "outside-root hardlinks and filesystem sharing are unknown; occupancy is not reclaimable space",
            "known allocation is filesystem metadata or identity-matching source-scan allocation; directory overhead and alternate streams are not exhaustively measured",
            "one snapshot does not identify growth, current writer, references or inactivity"],
        "configured_path_clues": profiler.bindings, "external_candidates": profiler.external_candidates,
        "codex_home_metadata": codex_metadata,
        "related_roots": related_results, "source_scan_reuse": profiler.reuse_source,
        "native_cache_probes": probes(ecosystems), "errors": profiler.errors, "gaps": profiler.gaps,
        "coverage": {"complete": False, "project_traversal_complete": project_scope["traversal_complete"],
            "scope": "bounded ordinary-file metadata of selected project and explicit non-overlapping related roots; allowlisted project tool metadata only",
            "files_observed": profiler.files, "entries_observed": profiler.entries, "max_files": args.max_files,
            "max_entries": args.max_files * 4, "max_depth": MAX_DEPTH, "limit_hit": profiler.limit_hit,
            "max_detailed_attribution_nodes": MAX_ATTRIBUTION_NODES,
            "aborted_io": profiler.aborted_io, "config_files_read": profiler.config_count,
            "gap_count": profiler.gap_count, "gaps_list_truncated": profiler.gap_count > len(profiler.gaps),
            "config_bytes_read": profiler.config_bytes, "max_config_bytes": args.max_config_bytes,
            "max_single_config_bytes": MAX_CONFIG_FILE_BYTES, "max_config_files": MAX_CONFIG_FILES,
            "reason_not_comprehensive": "external/shared sizes, active configuration, runtime writers, references, ownership and recoverability are not fully established; see gaps"},
        "next_evidence_checks": [
            "Prioritize Agent/task leftover clues: map each exact producing task to its actual tool, retained inputs/results, real completion/failure and current references/writers. Keep unknowns; never fabricate historical lifecycle evidence.",
            "Start with the largest measured partitions; confirm their producing task, exact inputs/outputs, current readers/writers and business retention value.",
            "For dependencies/build caches, verify installed manager, effective cache/output path, lockfiles, local changes and re-creation cost; prepare a separate native proposal without assuming deletion support.",
            "For media/data/archives, distinguish original inputs, current deliverables and inactive outputs; prove inactivity and an independent usable retained copy before any supported exact relocation/redundancy plan.",
            "Resolve each skipped link/reparse point or inaccessible subtree through its explicit target/owner; do not follow or expand scope automatically.",
            "If growth matters, capture a later matching complete same-scope metadata snapshot; current size alone does not identify the write source.",
            "Treat CODEX_HOME, browser profiles, shared package stores, Git history, databases and session/index state as protected; a large size is not a cleanup rule."],
        "execution_boundary": {"profile_grants_action_authority": False, "profile_rules_may_expand_deletion_policy": False,
            "supported_executors": ["storage_guard.py exact validated CPython bytecode",
                "generated_artifact_guard.py separately assessed supported media intermediates",
                "relocation_guard.py separately validated inactive supported media/archive artifacts",
                "native_cache_guard.py independently verified project-exclusive pip adapter only",
                "npm_cache_guard.py independently verified project-exclusive npm adapter only",
                "retired_runtime_guard.py independently qualified synthetic stopped PG fixtures only",
                "agent_artifact_guard.py separately assessed supported disposable task scratch payloads only"],
            "releasable_bytes": None, "releasable_bytes_reason": "a storage profile is evidence, not an executable or authorized cleanup plan"}}
    # Serialize redacted values only; no raw configuration content is retained in this report.
    write_new(output, report, json_value=True)
    write_new(md, markdown(report))
    print(json.dumps({"report": str(output), "summary": str(md), "ecosystems": len(ecosystems),
                      "nodes": len(nodes), "project_traversal_complete": project_scope["traversal_complete"],
                      "comprehensive_audit": False}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect", help="Read bounded filesystem/tool metadata; no project commands or storage actions")
    p.add_argument("--project", required=True, help="specific ordinary project directory")
    p.add_argument("--output", required=True, help="new .json file; sibling .md is also created; parent must exist")
    p.add_argument("--max-files", type=int, default=100000, help="global regular-file budget across explicit roots (default 100000)")
    p.add_argument("--max-config-bytes", type=int, default=1048576, help="total allowlisted configuration content budget (default 1 MiB)")
    p.add_argument("--related-root", action="append", default=[], help="explicit exact related directory, separate evidence only; repeatable")
    p.add_argument("--codex-home", help="Codex home path, observed for existence only; never recursively scanned")
    p.add_argument("--scan-json", help="reuse exact unchanged allocation records from a matching storage_guard scan.json")
    p.set_defaults(run=inspect)
    args = parser.parse_args()
    try:
        return args.run(args)
    except (OSError, ProfileError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"error": scrub(str(exc)) if isinstance(exc, ProfileError) else type(exc).__name__,
                          "no_automatic_retry": True, "project_actions_executed": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
