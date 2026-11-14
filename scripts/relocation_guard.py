#!/usr/bin/env python3
"""Exact, assessed artifact relocation. Python 3.10+; standard library only.

Copy keeps the source. Acceptance is a separate business decision. Release never
recursively deletes directories, changes references, creates links, or repairs I/O.
POSIX locking is advisory and requires --confirm-idle. macOS is not device-tested.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

import storage_guard as g

VERSION = "1.3.0"
POLICY = "assessed-artifact-relocation-v1"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".mkv",
              ".webm", ".wav", ".mp3", ".m4a", ".zip", ".7z", ".tar", ".gz"}
BLOCKED = g.PROTECTED | {"src", "source", "sources", "config", "configs", "input", "inputs",
    "raw", "original", "originals", "original-assets", "archive", "archives", "snapshots",
    "rollback", "素材", "原始素材", "原件", "原图", "原视频"}
EVIDENCE_BLOCKED = g.PRUNE | {"state", "index", "indexes", "indices"}
MAX_EVIDENCE = 64 * 1024 * 1024
ADMIN_READ_BYTES = 0
DARWIN = None


def darwin_metadata(path):
    """Apple libc APIs: no xattr body reads and no permission changes. Untested on device."""
    global DARWIN
    before = g.plain(path)
    if not (stat.S_ISREG(before.st_mode) or stat.S_ISDIR(before.st_mode)):
        raise g.GuardError("macOS ACL inspection requires an ordinary file or directory")
    if DARWIN is None:
        DARWIN = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        DARWIN.listxattr.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        DARWIN.listxattr.restype = ctypes.c_ssize_t
        DARWIN.acl_get_link_np.argtypes = [ctypes.c_char_p, ctypes.c_uint]
        DARWIN.acl_get_link_np.restype = ctypes.c_void_p
        DARWIN.acl_size.argtypes = [ctypes.c_void_p]
        DARWIN.acl_size.restype = ctypes.c_ssize_t
        DARWIN.acl_copy_ext.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t]
        DARWIN.acl_copy_ext.restype = ctypes.c_ssize_t
        DARWIN.acl_free.argtypes = [ctypes.c_void_p]
    encoded = os.fsencode(path)
    size = DARWIN.listxattr(encoded, None, 0, 0x0001 | 0x0020)  # NOFOLLOW | SHOWCOMPRESSION
    if size < 0:
        raise OSError(ctypes.get_errno(), "Cannot verify macOS xattrs/resource forks", str(path))
    if size:
        raise g.GuardError(f"macOS xattrs/resource forks/compression metadata refused: {path}")
    ctypes.set_errno(0)
    acl = DARWIN.acl_get_link_np(encoded, 0x100)  # ACL_TYPE_EXTENDED; no following the leaf
    if not acl:
        code = ctypes.get_errno()
        if code == errno.ENOENT:
            # Apple filesec_get_property(FILESEC_ACL) also returns ENOENT when
            # a present object has no ACL property. Never hide disappearance
            # or replacement under the same error code.
            after = g.plain(path)
            if (stat.S_IFMT(after.st_mode) != stat.S_IFMT(before.st_mode)
                    or g.fingerprint(after) != g.fingerprint(before)):
                raise g.GuardError("Object changed during macOS ACL inspection")
            return ""  # Verified absence, distinct from unknown/unsupported None.
        if code in {errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}:
            return None  # Portable export can adopt this; preserve will refuse unverified ACLs.
        raise OSError(code, "Cannot inspect macOS ACL", str(path))
    try:
        size = DARWIN.acl_size(acl)
        if not 0 <= size <= 1024 * 1024:
            raise g.GuardError("Cannot bound native macOS ACL")
        buf = ctypes.create_string_buffer(size)
        if DARWIN.acl_copy_ext(buf, acl, size) < 0:
            raise OSError(ctypes.get_errno(), "Cannot capture macOS ACL", str(path))
        return base64.b64encode(buf.raw).decode("ascii")
    finally:
        DARWIN.acl_free(acl)


def integer(value, label, maximum=2**60):
    if type(value) is not int or not 0 <= value <= maximum:
        raise g.GuardError(f"{label} must be a finite nonnegative integer <= {maximum}")
    return value


def relative(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or any(x in {"", ".", ".."} or ":" in x for x in value.split("/"))):
        raise g.GuardError("Expected a precise non-root project-relative path")
    return value


def identity(path, directory=True):
    s = g.plain(path, directory)
    return {"device": s.st_dev, "inode": s.st_ino}


def volume(path):
    s = g.plain(path, True)
    result = {"device": s.st_dev}
    if os.name == "nt":
        buf = g.ctypes.create_unicode_buffer(32768)
        serial, flags = g.wt.DWORD(), g.wt.DWORD()
        if (not g.K32.GetVolumePathNameW(str(path), buf, len(buf))
                or not g.K32.GetVolumeInformationW(buf, None, 0, g.ctypes.byref(serial), None,
                                                  g.ctypes.byref(flags), None, 0)):
            raise g.ctypes.WinError(g.ctypes.get_last_error())
        result.update(serial=serial.value, persistent_acls=bool(flags.value & 8))
    return result


def credential(relative_path):
    parts = relative_path.lower().replace("\\", "/").split("/")
    name = parts[-1]
    return (any(p in EVIDENCE_BLOCKED for p in parts[:-1]) or name.startswith((".env", "id_rsa", "id_ed25519"))
            or any(x in name for x in ("auth", "credential", "secret", "token", "password"))
            or bool(re.search(r"\.(?:jsonl|sqlite3?|db)(?:-(?:wal|shm|journal))?$", name)))


def source_policy(root, relative_path, directory=False):
    parts = relative_path.lower().split("/")
    directory_parts = parts if directory else parts[:-1]
    if (any(p in BLOCKED for p in directory_parts)
            or any(a == ".cache" and b in {"uv", "pip"} for a, b in zip(directory_parts, directory_parts[1:]))
            or credential(relative_path)):
        raise g.GuardError(f"Hard-protected source boundary: {relative_path}")
    marker = g.managed_marker_reason(root, relative_path + "/_file" if directory else relative_path)
    if marker:
        raise g.GuardError(marker)
    if not directory:
        name = parts[-1]
        if Path(name).suffix not in EXTENSIONS or re.search(r"(^|[_. -])(raw|original|backup|recovery|master)([_. -]|$)", name):
            raise g.GuardError(f"Not an allowed noncritical artifact format/name: {relative_path}")


if os.name == "nt":
    ADV = g.ctypes.WinDLL("advapi32", use_last_error=True)
    ADV.GetFileSecurityW.argtypes = [g.wt.LPCWSTR, g.wt.DWORD, g.wt.LPVOID, g.wt.DWORD, g.wt.LPDWORD]
    g.K32.SetFileTime.argtypes = [g.wt.HANDLE, g.wt.LPVOID, g.wt.LPVOID, g.wt.LPVOID]


def metadata(path, directory=False):
    s = g.plain(path, directory)
    if not directory and (s.st_nlink != 1 or not s.st_ino):
        raise g.GuardError(f"Hardlink/unknown file identity refused: {path}")
    result = {"mode": stat.S_IMODE(s.st_mode)}
    if os.name == "nt":
        attrs = s.st_file_attributes
        # Refuse encryption, sparse/compressed, offline/cloud and unknown attributes.
        if attrs & ~(0x27 | 0x10 | 0x80) or (not directory and attrs & 1):
            raise g.GuardError(f"Unsupported/readonly/encrypted/offline Windows metadata: {path}")
        try:
            if not g.only_default_stream(path):
                raise g.GuardError(f"Additional Windows data streams refused: {path}")
        except OSError as exc:
            if not (directory and getattr(exc, "winerror", None) == 38):
                raise  # Directories can have no streams (ERROR_HANDLE_EOF); named streams are never ignored.
        h = g.win_open(path, 0, 7, directory)
        try:
            info = g.FileInfo()
            if not g.K32.GetFileInformationByHandle(h, g.ctypes.byref(info)):
                raise g.ctypes.WinError(g.ctypes.get_last_error())
            result["created_100ns"] = info.created.dwLowDateTime | (info.created.dwHighDateTime << 32)
        finally:
            g.K32.CloseHandle(h)
        result["attributes"] = attrs & 0x27
        if volume(path if directory else path.parent).get("persistent_acls"):
            needed = g.wt.DWORD()
            ADV.GetFileSecurityW(str(path), 7, None, 0, g.ctypes.byref(needed))
            if not needed.value or needed.value > 1024 * 1024:
                raise g.GuardError("Cannot bound/read source security descriptor")
            buf = g.ctypes.create_string_buffer(needed.value)
            if not ADV.GetFileSecurityW(str(path), 7, buf, len(buf), g.ctypes.byref(needed)):
                raise g.ctypes.WinError(g.ctypes.get_last_error())
            result["security_descriptor"] = base64.b64encode(buf.raw[:needed.value]).decode("ascii")
        else:
            result["security_descriptor"] = None
    else:
        if sys.platform == "darwin":
            result["darwin_acl"] = darwin_metadata(path)
        elif not hasattr(os, "listxattr"):
            raise g.GuardError("Cannot verify xattrs/resource forks on this platform; execution unsupported")
        elif os.listxattr(path, follow_symlinks=False):
            raise g.GuardError(f"Extended attributes/resource forks refused: {path}")
        if getattr(s, "st_flags", 0):
            raise g.GuardError(f"Unsupported filesystem flags: {path}")
        result.update(uid=s.st_uid, gid=s.st_gid)
        if hasattr(s, "st_birthtime"):
            result["birthtime_ns"] = getattr(s, "st_birthtime_ns", int(s.st_birthtime * 1e9))
    return result


def outside_output(path, source, target):
    p = g.absolute(path)
    if any(g.below(p, tree) for tree in (source, target)):
        raise g.GuardError("Assessment/plan/receipts must be outside both data trees")
    return g.safe_output(p)


def audit_input(path, source, target):
    path = g.absolute(path)
    if any(g.below(path, tree) for tree in (source, target)):
        raise g.GuardError("Audit inputs must remain outside both data trees")
    return path


def read_json(path):
    global ADMIN_READ_BYTES
    value, digest = g.read_json(path)
    ADMIN_READ_BYTES += g.plain(g.absolute(path), False).st_size
    return value, digest


def read_assessment(path, root, source, target):
    path = g.absolute(path)
    rel = path.relative_to(root).as_posix() if g.below(path, root) else path.as_posix()
    if credential(rel) or any(g.below(path, tree) for tree in (source, target)):
        raise g.GuardError("Assessment cannot be credential/state data or inside either data tree")
    if g.plain(path, False).st_size > 1024 * 1024:
        raise g.GuardError("Assessment exceeds 1 MiB")
    return read_json(path)


@contextlib.contextmanager
def anchor_directory(path):
    """Keep Windows ancestors nonrenamable; POSIX descriptors remain advisory."""
    path = g.absolute(path)
    g.ancestors(path)
    handles = []
    try:
        if os.name == "nt":
            for parent in reversed((path, *path.parents)):
                handles.append(g.win_open(parent, 0x80, 3, True))
        else:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            handles.append(os.open(path.anchor, flags))
            for part in path.parts[1:]:
                handles.append(os.open(part, flags, dir_fd=handles[-1]))
        yield handles[-1]
    finally:
        for handle in reversed(handles):
            g.K32.CloseHandle(handle) if os.name == "nt" else os.close(handle)


def atomic_json(path, value):
    path = g.safe_output(path)
    temp = path.parent / ("." + path.name + ".pending-" + uuid.uuid4().hex)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > 128 * 1024 * 1024:
        raise g.GuardError("Administrative JSON output exceeds 128 MiB")
    with g.new_file(temp) as f:
        f.write(encoded)
        f.flush()
        os.fsync(f.fileno())
    if os.name == "nt":
        os.rename(temp, path)  # Windows rename is atomic and fails if destination exists.
    else:
        os.link(temp, path, follow_symlinks=False)  # atomic exclusive publish
        os.unlink(temp)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Budget:
    def __init__(self, limit, required):
        self.limit, self.used = integer(limit, "max-bytes"), 0
        if required > self.limit:
            raise g.GuardError(f"Stage requires {required} payload/evidence bytes read; budget is {self.limit}")

    def read(self, fd, count):
        if self.used + count > self.limit:
            raise g.GuardError("Actual payload/evidence read budget exhausted")
        data = os.read(fd, count)
        self.used += len(data)
        return data


def digest_fd(fd, size, budget, writer=None):
    integer(size, "file size")
    os.lseek(fd, 0, os.SEEK_SET)
    digest, remaining = hashlib.sha256(), size
    while remaining:
        data = budget.read(fd, min(1024 * 1024, remaining))
        if not data:
            raise g.GuardError("Unexpected EOF")
        digest.update(data)
        remaining -= len(data)
        if writer is not None:
            view = memoryview(data)
            while view:
                n = os.write(writer, view)
                if n <= 0:
                    raise g.GuardError("Incomplete target write")
                view = view[n:]
    return digest.hexdigest()


def collect(tree, project=None, source_relative=None, max_files=10000):
    """No content reads; full membership includes the root and empty directories."""
    g.ancestors(tree)
    dirs, files, stack = {}, {}, [(tree, "")]
    while stack:
        folder, rel = stack.pop()
        g.ancestors(folder)
        if project is not None:
            source_policy(project, source_relative + ("/" + rel if rel else ""), True)
        s = g.plain(folder, True)
        dirs[rel] = {"identity": identity(folder), "mtime_ns": s.st_mtime_ns,
                     "metadata": metadata(folder, True)}
        with os.scandir(folder) as entries:
            for entry in entries:
                sub = (rel + "/" if rel else "") + entry.name
                relative(sub)
                path = Path(entry.path)
                s = g.plain(path)
                if stat.S_ISDIR(s.st_mode):
                    stack.append((path, sub))
                elif stat.S_ISREG(s.st_mode):
                    if len(files) >= max_files:
                        raise g.GuardError("Directory snapshot file limit exceeded")
                    if project is not None:
                        source_policy(project, source_relative + "/" + sub)
                    elif Path(entry.name.lower()).suffix not in EXTENSIONS or credential(sub):
                        raise g.GuardError("Retained tree contains unknown/protected data")
                    files[sub] = {"identity": g.fingerprint(s), "metadata": metadata(path)}
                else:
                    raise g.GuardError(f"Special/link entry refused: {path}")
        if len(dirs) + len(stack) > max_files * 4:
            raise g.GuardError("Directory snapshot directory limit exceeded")
    return {"directories": dict(sorted(dirs.items())), "files": dict(sorted(files.items()))}


def verify_hashes(tree, snapshot, budget):
    for rel, record in snapshot["files"].items():
        path = tree.joinpath(*rel.split("/"))
        with g.guarded_file(path) as (fd, _):
            if g.fingerprint(os.fstat(fd)) != record["identity"]:
                raise g.GuardError(f"File changed while opening: {path}")
            digest = digest_fd(fd, record["identity"]["size"], budget)
            if g.fingerprint(os.fstat(fd)) != record["identity"] or metadata(path) != record["metadata"]:
                raise g.GuardError(f"File changed while hashing: {path}")
            if "sha256" in record and digest != record["sha256"]:
                raise g.GuardError(f"File hash changed: {path}")
            record["sha256"] = digest


def compare_source(current, expected):
    stripped = {"directories": expected["directories"], "files": {
        rel: {k: v for k, v in record.items() if k != "sha256"} for rel, record in expected["files"].items()}}
    if stripped != current:
        raise g.GuardError("Source membership, directory identity, timestamps, or metadata changed")


def same_copy(source, target, policy):
    if source["directories"].keys() != target["directories"].keys() or source["files"].keys() != target["files"].keys():
        raise g.GuardError("Retained copy has different complete membership")
    mismatches = []
    if policy == "preserve" and any(record["metadata"].get("darwin_acl", "verified") is None
        for tree in (source, target) for kind in ("files", "directories") for record in tree[kind].values()):
        raise g.GuardError("Cannot prove equivalent macOS ACLs under preserve policy")
    for rel, original in source["files"].items():
        kept = target["files"][rel]
        if original["identity"]["size"] != kept["identity"]["size"] or original["sha256"] != kept["sha256"]:
            raise g.GuardError(f"Retained bytes do not match: {rel}")
        if original["identity"]["mtime_ns"] != kept["identity"]["mtime_ns"]:
            mismatches.append({"path": rel, "field": "mtime_ns", "source": original["identity"]["mtime_ns"], "target": kept["identity"]["mtime_ns"]})
        if (original["identity"]["device"], original["identity"]["inode"]) == (kept["identity"]["device"], kept["identity"]["inode"]):
            raise g.GuardError("Retained file is not an independent object")
        if original["metadata"] != kept["metadata"]:
            mismatches.append({"path": rel, "field": "permission_or_creation_metadata"})
    for rel, original in source["directories"].items():
        if original["metadata"] != target["directories"][rel]["metadata"]:
            mismatches.append({"path": (rel or ".") + "/", "field": "directory_permission_or_creation_metadata"})
        if original["mtime_ns"] != target["directories"][rel]["mtime_ns"]:
            mismatches.append({"path": (rel or ".") + "/", "field": "directory_mtime_ns",
                               "source": original["mtime_ns"], "target": target["directories"][rel]["mtime_ns"]})
    if mismatches and policy == "preserve":
        raise g.GuardError("Preserve metadata cannot be proven equivalent; source kept: " + ", ".join(x["path"] for x in mismatches[:10]))
    return mismatches


def copy_shape(source, target):
    """Reject changed membership/size before reading any retained payload bytes."""
    if any(source[k].keys() != target[k].keys() for k in ("files", "directories")):
        raise g.GuardError("Retained copy has different complete membership")
    if any(record["identity"]["size"] != target["files"][rel]["identity"]["size"]
           for rel, record in source["files"].items()):
        raise g.GuardError("Retained file size mismatch; no retained payload hash attempted")


def target_location(root, source, value, action):
    if not isinstance(value, str) or not os.path.isabs(value):
        raise g.GuardError("Target must be an explicit absolute directory")
    target = g.absolute(value)
    g.ancestors(target.parent)
    if any(p.lower() in EVIDENCE_BLOCKED for p in target.parts):
        raise g.GuardError("Target cannot be global/session/credential storage")
    if any(g.below(a, b) or g.below(b, a) for a, b in ((target, root), (target, source))):
        raise g.GuardError("Retained tree must be outside the project, with no parent/child overlap")
    root_id = identity(root)
    if any(identity(p) == root_id for p in (target.parent, *target.parent.parents)):
        raise g.GuardError("Target is an alias within the project")
    if action == "migrate":
        if os.path.lexists(target):
            raise g.GuardError("Migration target must not exist; never overwrite a partial copy")
        if volume(source) == volume(target.parent):
            raise g.GuardError("Migration must use another actual volume; same-volume copy frees no net space")
    else:
        g.ancestors(target)
        target_id = identity(target)
        if any(identity(p) == target_id for p in (root, *root.parents)):
            raise g.GuardError("Target is an ancestor/alias of the project")
    return target


def evidence_records(root, assessment_path, assessment, source, target):
    if (assessment.get("source") != source.relative_to(root).as_posix()
            or assessment.get("classification") not in {"generated-artifacts", "completed-exports"}
            or not isinstance(assessment.get("purpose"), str) or not assessment["purpose"].strip()
            or any(assessment.get(k) is not True for k in ("references_checked", "no_live_references", "writers_idle"))
            or assessment.get("original_assets") is not False):
        raise g.GuardError("Assessment is missing exact source, verified purpose/references/idle state, or excludes original assets")
    producer = assessment.get("producer_evidence")
    if (not isinstance(producer, dict) or not isinstance(producer.get("description"), str)
            or not producer["description"].strip() or not isinstance(producer.get("paths"), list)
            or not 1 <= len(producer["paths"]) <= 64):
        raise g.GuardError("producer_evidence requires description and 1..64 exact project-relative paths")
    paths = [g.absolute(assessment_path)]
    for rel in producer["paths"]:
        relative(rel)
        if credential(rel):
            raise g.GuardError("Credentials/session/index data cannot be evidence")
        paths.append(g.relative_file(root, rel))
    if len(set(map(g.key, paths))) != len(paths):
        raise g.GuardError("Duplicate evidence paths")
    records = []
    for path in paths:
        if any(g.below(path, tree) for tree in (source, target)):
            raise g.GuardError("Assessment and provenance evidence must be outside both data trees")
        g.ancestors(path.parent)
        s = g.plain(path, False)
        if s.st_nlink != 1:
            raise g.GuardError("Evidence hardlinks refused")
        records.append({"path": str(path), "identity": g.fingerprint(s)})
    if sum(x["identity"]["size"] for x in records) > MAX_EVIDENCE:
        raise g.GuardError("Total assessment/provenance evidence exceeds 64 MiB")
    return records


def check_evidence(records, budget, hash_content=True):
    for record in records:
        path = g.absolute(record["path"])
        g.ancestors(path.parent)
        with g.guarded_file(path) as (fd, _):
            if g.fingerprint(os.fstat(fd)) != record["identity"]:
                raise g.GuardError("Purpose/provenance evidence identity changed")
            if hash_content:
                digest = digest_fd(fd, record["identity"]["size"], budget)
                if record.get("sha256", digest) != digest:
                    raise g.GuardError("Purpose/provenance evidence content changed")
                record["sha256"] = digest
            if g.fingerprint(os.fstat(fd)) != record["identity"]:
                raise g.GuardError("Evidence changed while reading")


def limits(plan):
    data = plan["limits"]
    count = integer(data["max_files"], "max-files", 100000)
    maximum = integer(data["max_bytes"], "max-bytes")
    integer(data["reserve_bytes"], "reserve-bytes")
    if not count or not maximum:
        raise g.GuardError("File/read limits must be positive")
    snapshot = plan["source_snapshot"]
    if not 1 <= len(snapshot["files"]) <= count or len(snapshot["directories"]) > count * 4:
        raise g.GuardError("Invalid manifest counts")
    total = sum(integer(x["identity"]["size"], "manifest size") for x in snapshot["files"].values())
    evidence = sum(integer(x["identity"]["size"], "evidence size") for x in plan["evidence"])
    if evidence > MAX_EVIDENCE:
        raise g.GuardError("Evidence read limit exceeded")
    return count, total, evidence, maximum


def load_plan(args, phase):
    data, digest = read_json(args.plan)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.authorize_plan) or args.authorize_plan.lower() != digest:
        raise g.GuardError("Explicit authorization must match exact plan SHA256")
    if (data.get("schema") != POLICY or data.get("action") not in {"migrate", "deduplicate"}
            or data.get("metadata_policy") not in {"preserve", "portable-export"}):
        raise g.GuardError("Unsupported independent relocation policy")
    if os.name != "nt" and not args.confirm_idle:
        raise g.GuardError("POSIX execution requires --confirm-idle; advisory locks cannot stop noncooperating writers")
    root = g.project_root(data["project"], data.get("codex_home"))
    g.same_root(root, data["project_identity"])
    source = root.joinpath(*relative(data["source"]).split("/"))
    g.ancestors(source)
    source_policy(root, data["source"], True)
    target = g.absolute(data["target"])
    audit_input(args.plan, source, target)
    g.ancestors(target.parent)
    if identity(target.parent) != data["target_parent_identity"] or volume(source) != data["source_volume"] or volume(target.parent) != data["target_volume"]:
        raise g.GuardError("Source/target volume or target parent identity changed")
    if identity(source) != data["source_snapshot"]["directories"][""]["identity"]:
        raise g.GuardError("Source root identity changed")
    # Recompute containment even if a plan was edited and reauthorized.
    if any(g.below(a, b) or g.below(b, a) for a, b in ((target, root), (target, source))):
        raise g.GuardError("Retained tree overlaps the project")
    if any(identity(p) == identity(root) for p in (target.parent, *target.parent.parents)):
        raise g.GuardError("Retained path is an identity alias within the project")
    if os.path.lexists(target) and any(identity(p) == identity(target) for p in (root, *root.parents)):
        raise g.GuardError("Retained path is an identity alias above the project")
    if any(p.lower() in EVIDENCE_BLOCKED for p in target.parts):
        raise g.GuardError("Protected retained path")
    if data["action"] == "migrate" and data["source_volume"] == data["target_volume"]:
        raise g.GuardError("Migration must remain cross-volume")
    count, total, evidence, maximum = limits(data)
    cost = {"copy": 3, "accept": 2, "release": 4}[phase] * total + evidence
    budget = Budget(maximum, cost)
    assessment, _ = read_assessment(data["assessment_path"], root, source, target)
    fresh_evidence = evidence_records(root, data["assessment_path"], assessment, source, target)
    if assessment != data["assessment"] or fresh_evidence != [{k: v for k, v in x.items() if k != "sha256"} for x in data["evidence"]]:
        raise g.GuardError("Assessment/provenance membership or identity changed")
    return data, digest, root, source, target, count, budget


class Journal:
    """Linear, fsynced events; checksum detects a torn final line. No replay."""
    def __init__(self, path, source, target, plan_sha, operation):
        self.path = outside_output(path, source, target)
        self.folder = Path(str(self.path) + ".in-progress")
        g.ancestors(self.folder.parent)
        os.mkdir(self.folder, 0o700)  # exclusive reservation; do not reuse interrupted operations
        self.events = g.new_file(self.folder / "events.jsonl")
        self.serial = 0
        self.value = {"schema": POLICY, "tool_version": VERSION, "operation": operation,
            "plan_sha256": plan_sha, "started_at": g.utc(), "status": "running", "items": [],
            "source_free_before_bytes": g.volume_free(source), "checkpoint_directory": str(self.folder),
            "concurrency": "exclusive Windows handles" if os.name == "nt" else "POSIX advisory locking; idle confirmation required",
            "note": "No automatic retry. A delete_pending checkpoint is an uncertain outcome, reconcile that exact file."}
        self.save()

    def save(self):
        self.serial += 1
        event = {"sequence": self.serial, "plan_sha256": self.value["plan_sha256"],
            "operation": self.value["operation"], "status": self.value["status"],
            "last_item": self.value["items"][-1] if self.value["items"] else None,
            "attempted_files": len(self.value["items"]), "deleted_files": self.value.get("deleted_files", 0),
            "error": self.value.get("error")}
        encoded = json.dumps(event, ensure_ascii=False, sort_keys=True)
        self.events.write(json.dumps({"event": event, "sha256": hashlib.sha256(encoded.encode()).hexdigest()}, ensure_ascii=False) + "\n")
        self.events.flush()
        os.fsync(self.events.fileno())

    def finish(self, source, budget):
        self.value.update(finished_at=g.utc(), payload_evidence_bytes_read=budget.used,
                          administrative_json_bytes_read=ADMIN_READ_BYTES,
                          source_free_after_bytes=g.volume_free(source))
        before, after = self.value["source_free_before_bytes"], self.value["source_free_after_bytes"]
        self.value["source_free_delta_bytes"] = after - before if before is not None and after is not None else None
        self.value["space_note"] = "Free-space difference includes unrelated volume writes/deletes; logical bytes do not guarantee physical reclaim"
        try:
            self.save()
            sha = atomic_json(self.path, self.value)
        finally:
            self.events.close()
        print(json.dumps({"receipt": str(self.path), "receipt_sha256": sha, "status": self.value["status"]}))


def stage_error(journal, exc):
    journal.value.update(status="aborted_io_error" if g.fatal_io(exc) else "aborted_validation_or_os_error", error=str(exc))


def current_source(plan, root, source, count, budget=None):
    current = collect(source, root, plan["source"], count)
    compare_source(current, plan["source_snapshot"])
    if budget is not None:
        for rel, record in current["files"].items():
            record["sha256"] = plan["source_snapshot"]["files"][rel]["sha256"]
        verify_hashes(source, current, budget)
    return current


def retained(plan, target, count, budget, expected=None):
    snap = collect(target, max_files=count)
    copy_shape(plan["source_snapshot"], snap)
    if expected is not None:
        compare_source(snap, expected)
        for rel, record in snap["files"].items():
            record["sha256"] = expected["files"][rel]["sha256"]
    verify_hashes(target, snap, budget)
    mismatches = same_copy(plan["source_snapshot"], snap, plan["metadata_policy"])
    return snap, mismatches


def release_membership(plan, root, source, target, count, target_snapshot, deleted):
    """Recheck names and directory identities; current files get strict dual guards.

    This is still bounded repeated enumeration, not an indexed large-tree service.
    Other files' content/metadata changes are caught before their own release.
    """
    for tree, expected, removed in ((source, plan["source_snapshot"], deleted), (target, target_snapshot, set())):
        directories, files, stack = {}, set(), [(tree, "")]
        while stack:
            folder, rel = stack.pop()
            directories[rel] = identity(folder)
            with os.scandir(folder) as entries:
                for entry in entries:
                    sub = (rel + "/" if rel else "") + entry.name
                    relative(sub)
                    if entry.is_symlink():
                        raise g.GuardError("Link appeared during release")
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((Path(entry.path), sub))
                    elif entry.is_file(follow_symlinks=False):
                        files.add(sub)
                    else:
                        raise g.GuardError("Special entry appeared during release")
                    if len(files) > count or len(directories) + len(stack) > count * 4:
                        raise g.GuardError("Membership limit exceeded during release")
        if (directories != {rel: rec["identity"] for rel, rec in expected["directories"].items()}
                or files != expected["files"].keys() - removed):
            raise g.GuardError("Complete membership/directory identity changed during release")


def plan_command(args):
    root = g.project_root(args.project, args.codex_home)
    rel = relative(args.source)
    source = root.joinpath(*rel.split("/"))
    g.ancestors(source)
    source_policy(root, rel, True)
    target = target_location(root, source, args.target, args.action)
    output = outside_output(args.output, source, target)
    count = integer(args.max_files, "max-files", 100000)
    maximum = integer(args.max_bytes, "max-bytes")
    reserve = integer(args.reserve_bytes, "reserve-bytes")
    if not count or not maximum:
        raise g.GuardError("Limits must be positive")
    assessment_path = g.absolute(args.assessment)
    assessment, _ = read_assessment(assessment_path, root, source, target)
    evidence = evidence_records(root, assessment_path, assessment, source, target)
    snapshot = collect(source, root, rel, count)
    if not snapshot["files"]:
        raise g.GuardError("No releasable artifact files")
    target_snapshot = collect(target, max_files=count) if args.action == "deduplicate" else None
    if target_snapshot is not None:
        copy_shape(snapshot, target_snapshot)
    total = sum(x["identity"]["size"] for x in snapshot["files"].values())
    evidence_bytes = sum(x["identity"]["size"] for x in evidence)
    # max-bytes is the payload/evidence READ budget per stage, not a size-only cap.
    budget = Budget(maximum, (2 if args.action == "deduplicate" else 1) * total + evidence_bytes)
    Budget(maximum, 4 * total + evidence_bytes)  # release must fit before making a plan
    check_evidence(evidence, budget)
    verify_hashes(source, snapshot, budget)
    compare_source(collect(source, root, rel, count), snapshot)
    data = {"schema": POLICY, "tool_version": VERSION, "created_at": g.utc(), "project": str(root),
        "project_identity": identity(root), "codex_home": args.codex_home, "source": rel, "target": str(target),
        "action": args.action, "metadata_policy": args.metadata_policy, "assessment_path": str(assessment_path),
        "assessment": assessment, "evidence": evidence, "source_snapshot": snapshot,
        "source_volume": volume(source), "target_volume": volume(target.parent),
        "target_parent_identity": identity(target.parent), "limits": {"max_files": count, "max_bytes": maximum, "reserve_bytes": reserve},
        "logical_bytes": total, "metadata_contract": "Default bytes verified. Source identity/mtime always exact. Preserve requires equivalent recorded permissions/creation/mtime. Portable export explicitly accepts destination permissions and its initial represented timestamps; all subsequent target timestamps must remain exact. ADS/xattrs/unknown flags always refused. Volatile access/change times excluded.",
        "read_budget_note": "max-bytes bounds payload/evidence reads per stage; bounded administrative JSON reads are reported separately",
        "release_read_bytes_required": 4 * total + evidence_bytes}
    if args.action == "migrate":
        free = g.volume_free(target.parent)
        if free is None or free < total + reserve:
            raise g.GuardError("Cannot prove sufficient target free space plus reserve")
    else:
        verify_hashes(target, target_snapshot, budget)
        mismatches = same_copy(snapshot, target_snapshot, args.metadata_policy)
        data["initial_target_snapshot"] = target_snapshot
        data["initial_metadata_differences"] = mismatches
    sha = atomic_json(output, data)
    print(json.dumps({"plan": str(output), "plan_sha256": sha, "action": args.action,
                      "metadata_policy": args.metadata_policy, "files": len(snapshot["files"]), "logical_bytes": total}))


def set_times(path, record, directory=False, descriptor=None, native_handle=None):
    stamp = record["mtime_ns"] if directory else record["identity"]["mtime_ns"]
    if os.name == "nt":
        created = record["metadata"]["created_100ns"]
        filetime = g.wt.FILETIME(created & 0xffffffff, created >> 32)
        written = stamp // 100 + 116444736000000000
        modified = g.wt.FILETIME(written & 0xffffffff, written >> 32)
        h = native_handle if native_handle is not None else g.msvcrt.get_osfhandle(descriptor)
        if h is None:
            raise g.GuardError("Timestamp writes require the anchored created object")
        if not g.K32.SetFileTime(h, g.ctypes.byref(filetime), None, g.ctypes.byref(modified)):
            raise g.ctypes.WinError(g.ctypes.get_last_error())
    else:
        if descriptor is None:
            descriptor = native_handle
        if descriptor is None:
            raise g.GuardError("Timestamp writes require the anchored created object")
        os.utime(descriptor, ns=(stamp, stamp))


def copy_payload(plan, root, source, target, journal, budget):
    """Anchor every new directory. Exhausting handles stops safely with source kept."""
    with contextlib.ExitStack() as locks:
        parent = locks.enter_context(anchor_directory(target.parent))
        if identity(target.parent) != plan["target_parent_identity"] or volume(target.parent) != plan["target_volume"]:
            raise g.GuardError("Target parent changed before creating copy")
        handles, created = {}, {}
        for rel, record in sorted(plan["source_snapshot"]["directories"].items(), key=lambda x: (x[0].count("/"), x[0])):
            path = target.joinpath(*rel.split("/")) if rel else target
            parent_rel = rel.rpartition("/")[0]
            parent_handle = handles[parent_rel] if rel else parent
            if os.name == "nt":
                os.mkdir(path, record["metadata"]["mode"])
                handle = g.win_open(path, 0x180, 3, True)
                locks.callback(g.K32.CloseHandle, handle)
            else:
                os.mkdir(path.name, record["metadata"]["mode"], dir_fd=parent_handle)
                handle = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_handle)
                locks.callback(os.close, handle)
            handles[rel], created[rel] = handle, identity(path)
        journal.value["target_identity"] = created[""]
        journal.save()
        for rel, record in plan["source_snapshot"]["files"].items():
            item = {"path": rel, "status": "copy_pending"}
            journal.value["items"].append(item)
            journal.save()
            src, dst = source.joinpath(*rel.split("/")), target.joinpath(*rel.split("/"))
            g.same_root(root, plan["project_identity"])
            for directory_rel, directory_id in created.items():
                folder = target.joinpath(*directory_rel.split("/")) if directory_rel else target
                if identity(folder) != directory_id:
                    raise g.GuardError("New target directory identity changed")
            with g.guarded_file(src) as (fd, _):
                if g.fingerprint(os.fstat(fd)) != record["identity"] or metadata(src) != record["metadata"]:
                    raise g.GuardError("Source changed before copy")
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                out = os.open(dst, flags, record["metadata"]["mode"]) if os.name == "nt" else os.open(
                    dst.name, flags, record["metadata"]["mode"], dir_fd=handles[rel.rpartition("/")[0]])
                try:
                    digest = digest_fd(fd, record["identity"]["size"], budget, out)
                    set_times(dst, record, descriptor=out)
                    os.fsync(out)
                finally:
                    os.close(out)
                if digest != record["sha256"] or g.fingerprint(os.fstat(fd)) != record["identity"]:
                    raise g.GuardError("Source bytes changed during copy")
            item.update(status="copied_not_accepted", target_identity=g.fingerprint(g.plain(dst, False)))
            journal.save()
        for rel, record in sorted(plan["source_snapshot"]["directories"].items(), key=lambda x: len(x[0]), reverse=True):
            folder = target.joinpath(*rel.split("/")) if rel else target
            if identity(folder) != created[rel]:
                raise g.GuardError("Target directory changed before metadata finalization")
            set_times(folder, record, True, native_handle=handles[rel])
        target_snap, differences = retained(plan, target, plan["limits"]["max_files"], budget)
        for rel, directory_id in created.items():
            if target_snap["directories"][rel]["identity"] != directory_id:
                raise g.GuardError("Target directory changed during final verification")
        current_source(plan, root, source, plan["limits"]["max_files"], budget)
        return target_snap, differences


def copy_command(args):
    plan, sha, root, source, target, count, budget = load_plan(args, "copy")
    if plan["action"] != "migrate":
        raise g.GuardError("deduplicate uses an existing copy; no copy command")
    journal = Journal(args.receipt, source, target, sha, "copy")
    try:
        check_evidence(plan["evidence"], budget)
        current_source(plan, root, source, count)
        target_location(root, source, str(target), "migrate")
        total = sum(x["identity"]["size"] for x in plan["source_snapshot"]["files"].values())
        if g.volume_free(target.parent) is None or g.volume_free(target.parent) < total + plan["limits"]["reserve_bytes"]:
            raise g.GuardError("Insufficient target space plus reserve")
        target_snap, differences = copy_payload(plan, root, source, target, journal, budget)
        journal.value.update(status="completed", target_snapshot=target_snap,
                             metadata_differences=differences, source_retained=True)
    except (OSError, g.GuardError, ValueError, KeyError, TypeError) as exc:
        stage_error(journal, exc)
    journal.value["not_attempted_files"] = len(plan["source_snapshot"]["files"]) - len(journal.value["items"])
    journal.finish(source, budget)
    return 0 if journal.value["status"] == "completed" else 3


def accept_command(args):
    if not args.confirm_accepted:
        raise g.GuardError("Acceptance requires the already chosen business outcome and explicit --confirm-accepted")
    plan, sha, root, source, target, count, budget = load_plan(args, "accept")
    journal = Journal(args.output, source, target, sha, "accept")
    try:
        expected, copy_sha = plan.get("initial_target_snapshot"), None
        if plan["action"] == "migrate":
            if not args.copy_receipt:
                raise g.GuardError("Migration acceptance requires a completed copy receipt")
            receipt, copy_sha = read_json(audit_input(args.copy_receipt, source, target))
            if (receipt.get("schema") != POLICY or receipt.get("operation") != "copy"
                    or receipt.get("status") != "completed" or receipt.get("plan_sha256") != sha):
                raise g.GuardError("Copy receipt is incomplete or belongs to another plan")
            expected = receipt["target_snapshot"]
        elif args.copy_receipt:
            raise g.GuardError("deduplicate must not use a migration copy receipt")
        check_evidence(plan["evidence"], budget)
        current_source(plan, root, source, count, budget)
        target_snap, differences = retained(plan, target, count, budget, expected)
        journal.value.update(status="accepted", accepted=True, target_snapshot=target_snap,
            metadata_differences=differences, metadata_policy=plan["metadata_policy"], copy_receipt_sha256=copy_sha,
            permission_effect="Destination permissions and initially recorded timestamps are adopted; other users may read portable exports and nanosecond/creation metadata may differ" if plan["metadata_policy"] == "portable-export" else "Recorded metadata equivalence verified",
            acceptance_note="Acceptance transfers retention responsibility to this independent destination; later device loss/disconnection cannot be guaranteed against")
    except (OSError, g.GuardError, ValueError, KeyError, TypeError) as exc:
        stage_error(journal, exc)
    journal.finish(source, budget)
    return 0 if journal.value["status"] == "accepted" else 3


def release_command(args):
    plan, sha, root, source, target, count, budget = load_plan(args, "release")
    journal = Journal(args.receipt, source, target, sha, "release")
    try:
        accepted, accept_sha = read_json(audit_input(args.accept, source, target))
        if (accepted.get("schema") != POLICY or accepted.get("operation") != "accept" or accepted.get("status") != "accepted"
                or accepted.get("accepted") is not True or accepted.get("plan_sha256") != sha
                or accepted.get("metadata_policy") != plan["metadata_policy"]):
            raise g.GuardError("Release requires accepted evidence for this exact plan and metadata policy")
        journal.value["accept_sha256"] = accept_sha
        check_evidence(plan["evidence"], budget)
        current_source(plan, root, source, count, budget)
        target_snap, differences = retained(plan, target, count, budget, accepted["target_snapshot"])
        journal.value.update(planned_files=len(plan["source_snapshot"]["files"]), deleted_files=0,
                             deleted_logical_bytes=0, metadata_differences=differences)
        deleted = set()
        for rel, record in plan["source_snapshot"]["files"].items():
            item = {"path": rel, "status": "checking"}
            journal.value["items"].append(item)
            journal.save()
            src, dst = source.joinpath(*rel.split("/")), target.joinpath(*rel.split("/"))
            with g.guarded_file(src, delete=True) as (src_fd, unlink), g.guarded_file(dst) as (dst_fd, _):
                if (g.fingerprint(os.fstat(src_fd)) != record["identity"]
                        or g.fingerprint(os.fstat(dst_fd)) != target_snap["files"][rel]["identity"]):
                    raise g.GuardError("Source or retained identity changed during release")
                if (digest_fd(src_fd, record["identity"]["size"], budget) != record["sha256"]
                        or digest_fd(dst_fd, record["identity"]["size"], budget) != record["sha256"]):
                    raise g.GuardError("Source or retained hash changed during release")
                item["status"] = "delete_pending"
                journal.save()
                g.same_root(root, plan["project_identity"])
                if identity(source) != plan["source_snapshot"]["directories"][""]["identity"] or volume(target) != plan["target_volume"]:
                    raise g.GuardError("Data root or volume changed immediately before release")
                release_membership(plan, root, source, target, count, target_snap, deleted)
                source_policy(root, plan["source"] + "/" + rel)
                check_evidence(plan["evidence"], budget, hash_content=False)
                if (g.fingerprint(os.fstat(src_fd)) != record["identity"] or metadata(src) != record["metadata"]
                        or g.fingerprint(os.fstat(dst_fd)) != target_snap["files"][rel]["identity"]
                        or metadata(dst) != target_snap["files"][rel]["metadata"]):
                    raise g.GuardError("File metadata changed immediately before release")
                unlink()
            item["status"] = "deleted"
            deleted.add(rel)
            journal.value["deleted_files"] += 1
            journal.value["deleted_logical_bytes"] += record["identity"]["size"]
            journal.save()
        release_membership(plan, root, source, target, count, target_snap, deleted)
        journal.value.update(status="completed", directories_retained=True)
    except (OSError, g.GuardError, ValueError, KeyError, TypeError) as exc:
        stage_error(journal, exc)
    journal.value["not_attempted_files"] = len(plan["source_snapshot"]["files"]) - len(journal.value["items"])
    journal.finish(source, budget)
    return 0 if journal.value["status"] == "completed" else 3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="Assess a precise inactive artifact directory; hash only after full metadata protection checks")
    for name in ("project", "source", "target", "assessment", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--action", choices=("migrate", "deduplicate"), required=True)
    p.add_argument("--metadata-policy", choices=("preserve", "portable-export"), default="preserve")
    p.add_argument("--max-files", type=int, default=10000)
    p.add_argument("--max-bytes", type=int, default=107374182400, help="Payload/evidence bytes READ budget per stage; release requires 4x artifact bytes plus evidence")
    p.add_argument("--reserve-bytes", type=int, default=1073741824)
    p.add_argument("--codex-home")
    p.set_defaults(run=plan_command)
    for command, run in (("copy", copy_command), ("accept", accept_command), ("release", release_command)):
        s = sub.add_parser(command)
        s.add_argument("--plan", required=True)
        s.add_argument("--authorize-plan", required=True, metavar="SHA256")
        s.add_argument("--confirm-idle", action="store_true", help="Required on POSIX; advisory locking is not a system-wide guarantee")
        if command == "accept":
            s.add_argument("--copy-receipt")
            s.add_argument("--output", required=True)
            s.add_argument("--confirm-accepted", action="store_true")
        else:
            s.add_argument("--receipt", required=True)
        if command == "release":
            s.add_argument("--accept", required=True)
        s.set_defaults(run=run)
    args = parser.parse_args()
    try:
        return args.run(args) or 0
    except (OSError, g.GuardError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "no_automatic_retry": True}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
