#!/usr/bin/env python3
"""Read-only project-volume diagnosis and migration-location discovery.

Python 3.10+, standard library only. Reads path/volume metadata; never walks a
project or a disk, reads file contents, creates target directories, or moves or
deletes anything. Only a new JSON report and its same-stem Markdown companion
are written, outside the selected project, into an existing report directory.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import stat
import sys

VERSION = "2.0.0"
GIB = 1024 ** 3
MAX_MOUNTS = 512


def _load_guard():
    # A private module instance lets this read-only tool extend the ordinary
    # directory check for verified Windows volume mount roots without changing
    # storage_guard.py, its deletion policy, or another importer's module state.
    path = Path(__file__).with_name("storage_guard.py")
    spec = importlib.util.spec_from_file_location("_volume_advisor_guard", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import adjacent storage_guard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()
GuardError = guard.GuardError
_ordinary_plain = guard.plain


class WindowsVolumes:
    """Bounded metadata-only Win32 volume APIs, including directory mounts."""

    DRIVE_NAMES = {0: "unknown", 1: "no_root", 2: "removable", 3: "fixed",
                   4: "network", 5: "optical", 6: "ramdisk"}

    def __init__(self):
        import ctypes
        from ctypes import wintypes as wt
        self.c = ctypes
        self.wt = wt
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "GetLogicalDriveStringsW": ([wt.DWORD, wt.LPWSTR], wt.DWORD),
            "GetDriveTypeW": ([wt.LPCWSTR], wt.UINT),
            "GetVolumePathNameW": ([wt.LPCWSTR, wt.LPWSTR, wt.DWORD], wt.BOOL),
            "GetVolumeNameForVolumeMountPointW": ([wt.LPCWSTR, wt.LPWSTR, wt.DWORD], wt.BOOL),
            "GetVolumeInformationW": ([wt.LPCWSTR, wt.LPWSTR, wt.DWORD,
                ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.DWORD),
                ctypes.POINTER(wt.DWORD), wt.LPWSTR, wt.DWORD], wt.BOOL),
            "FindFirstVolumeW": ([wt.LPWSTR, wt.DWORD], wt.HANDLE),
            "FindNextVolumeW": ([wt.HANDLE, wt.LPWSTR, wt.DWORD], wt.BOOL),
            "FindVolumeClose": ([wt.HANDLE], wt.BOOL),
            "GetVolumePathNamesForVolumeNameW": ([wt.LPCWSTR, wt.LPWSTR,
                wt.DWORD, ctypes.POINTER(wt.DWORD)], wt.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.k, name)
            fn.argtypes = args
            fn.restype = result

    @staticmethod
    def slash(path):
        return str(path).rstrip("\\/") + "\\"

    def error(self, name):
        return f"{name} failed (Windows error {self.c.get_last_error()})"

    def drive_type(self, path):
        return self.DRIVE_NAMES.get(int(self.k.GetDriveTypeW(self.slash(path))), "unknown")

    def mount_guid(self, path):
        buf = self.c.create_unicode_buffer(1024)
        if self.k.GetVolumeNameForVolumeMountPointW(self.slash(path), buf, len(buf)):
            return buf.value.lower()
        return None

    def is_volume_mount(self, path):
        # A junction to an ordinary directory is not accepted. The mount path
        # itself must be a mount root recognized by both volume APIs.
        if not self.mount_guid(path):
            return False
        buf = self.c.create_unicode_buffer(32768)
        if not self.k.GetVolumePathNameW(str(path), buf, len(buf)):
            return False
        return guard.key(self.slash(buf.value)) == guard.key(self.slash(path))

    def info(self, path):
        limits = []
        root_buf = self.c.create_unicode_buffer(32768)
        if not self.k.GetVolumePathNameW(str(path), root_buf, len(root_buf)):
            return {"mount_path": None, "volume_id": None, "filesystem": "unknown",
                    "drive_type": "unknown", "limits": [self.error("GetVolumePathNameW")]}
        mount = root_buf.value
        guid = self.mount_guid(mount)
        if guid is None:
            limits.append(self.error("GetVolumeNameForVolumeMountPointW"))
        serial, max_component, flags = self.wt.DWORD(), self.wt.DWORD(), self.wt.DWORD()
        fs = self.c.create_unicode_buffer(256)
        ok = self.k.GetVolumeInformationW(mount, None, 0, self.c.byref(serial),
            self.c.byref(max_component), self.c.byref(flags), fs, len(fs))
        if not ok:
            limits.append(self.error("GetVolumeInformationW"))
        return {"mount_path": mount, "volume_id": ("windows-volume:" + guid) if guid else None,
                "windows_volume_guid": guid, "windows_volume_serial": int(serial.value) if ok else None,
                "filesystem": fs.value if ok and fs.value else "unknown",
                "drive_type": self.drive_type(mount), "limits": limits}

    def discover(self):
        paths, limits = [], []
        needed = int(self.k.GetLogicalDriveStringsW(0, None))
        if 0 < needed <= 32768:
            buf = self.c.create_unicode_buffer(needed + 1)
            used = int(self.k.GetLogicalDriveStringsW(len(buf), buf))
            if used and used < len(buf):
                paths.extend(x for x in buf[:used].split("\0") if x)
            else:
                limits.append(self.error("GetLogicalDriveStringsW"))
        else:
            limits.append("Logical drive enumeration unavailable or exceeded its metadata bound")
        buf = self.c.create_unicode_buffer(1024)
        handle = self.k.FindFirstVolumeW(buf, len(buf))
        invalid = self.c.c_void_p(-1).value
        if handle in (None, invalid):
            limits.append(self.error("FindFirstVolumeW"))
            return paths, limits
        try:
            for index in range(MAX_MOUNTS):
                volume = buf.value
                required = self.wt.DWORD()
                self.k.GetVolumePathNamesForVolumeNameW(volume, None, 0, self.c.byref(required))
                if 0 < required.value <= 65536:
                    names = self.c.create_unicode_buffer(required.value + 1)
                    if self.k.GetVolumePathNamesForVolumeNameW(volume, names, len(names), self.c.byref(required)):
                        paths.extend(x for x in names[:required.value].split("\0") if x)
                    else:
                        limits.append(self.error("GetVolumePathNamesForVolumeNameW"))
                elif required.value > 65536:
                    limits.append("A volume's mount paths exceeded the metadata bound")
                if not self.k.FindNextVolumeW(handle, buf, len(buf)):
                    if self.c.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                        limits.append(self.error("FindNextVolumeW"))
                    break
            else:
                limits.append(f"Volume discovery stopped at the {MAX_MOUNTS}-volume bound")
        finally:
            self.k.FindVolumeClose(handle)
        return paths, limits


WIN = WindowsVolumes() if os.name == "nt" else None


class DarwinVolumes:
    """Cached mount metadata; MNT_NOWAIT avoids querying network servers.

    ABI/flag references (not a claim of macOS runtime acceptance):
    https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/mount.h
    https://developer.apple.com/library/archive/qa/nw09/_index.html
    """

    def __init__(self):
        import ctypes as c
        import platform
        self.mounts, self.limits = [], []

        class StatFS64(c.Structure):
            _fields_ = [("bsize", c.c_uint32), ("iosize", c.c_int32),
                ("blocks", c.c_uint64), ("bfree", c.c_uint64),
                ("bavail", c.c_uint64), ("files", c.c_uint64),
                ("ffree", c.c_uint64), ("fsid", c.c_int32 * 2),
                ("owner", c.c_uint32), ("type", c.c_uint32),
                ("flags", c.c_uint32), ("subtype", c.c_uint32),
                ("fstypename", c.c_char * 16), ("mntonname", c.c_char * 1024),
                ("mntfromname", c.c_char * 1024), ("flags_ext", c.c_uint32),
                ("reserved", c.c_uint32 * 7)]
        try:
            if c.sizeof(StatFS64) != 2168:
                raise RuntimeError("Unsupported Darwin statfs ABI size")
            libc = c.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
            fn = getattr(libc, "getfsstat$INODE64", None) or getattr(libc, "getfsstat64", None)
            if fn is None and platform.machine().lower() in {"arm64", "aarch64"}:
                fn = getattr(libc, "getfsstat", None)
            if fn is None:
                raise RuntimeError("A verified 64-bit getfsstat entry point is unavailable")
            fn.argtypes = [c.POINTER(StatFS64), c.c_int, c.c_int]
            fn.restype = c.c_int
            array = (StatFS64 * MAX_MOUNTS)()
            count = fn(array, c.sizeof(array), 2)  # MNT_NOWAIT
            if count < 0:
                raise OSError(c.get_errno(), "getfsstat metadata call failed")
            if count >= MAX_MOUNTS:
                self.limits.append("Darwin mount metadata reached its bounded capacity; later mounts may be omitted")
            for item in array[:min(count, MAX_MOUNTS)]:
                mount = os.fsdecode(bytes(item.mntonname))
                if mount.startswith("/"):
                    self.mounts.append({"mount_path": mount,
                        "filesystem": os.fsdecode(bytes(item.fstypename)) or "unknown",
                        "locality": "local" if item.flags & 0x1000 else "network",
                        "read_only_mount": bool(item.flags & 1),
                        "darwin_fsid": [int(x) for x in item.fsid]})
        except (OSError, RuntimeError, AttributeError) as exc:
            self.limits.append(f"Darwin cached mount metadata unavailable: {exc}")

    def covering(self, path):
        matches = [m for m in self.mounts if guard.below(path, m["mount_path"])]
        return max(matches, key=lambda m: len(m["mount_path"])) if matches else None

    def verified_for_device(self, path, device):
        ordered = sorted(self.mounts, key=lambda m: not guard.below(path, m["mount_path"]))
        for item in ordered:
            if item["locality"] != "local":
                continue
            try:
                guard.ancestors(item["mount_path"])
                if checked_plain(item["mount_path"], True).st_dev == device:
                    return dict(item)
            except (OSError, GuardError):
                pass
        return None


DARWIN = DarwinVolumes() if sys.platform == "darwin" else None


def checked_plain(path, directory=None):
    try:
        return _ordinary_plain(path, directory)
    except GuardError:
        if WIN is None or directory is False:
            raise
        info = os.lstat(path)
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode)
                or not getattr(info, "st_file_attributes", 0) & 0x400
                or not WIN.is_volume_mount(path)):
            raise
        return info


# Keep guard.project_root's home/CODEX_HOME/protected-path/worktree checks.
# Only a real Win32 volume mount root may extend its ordinary-path check.
guard.plain = checked_plain


def checked_location(path):
    """Validate every existing ancestor; never resolve links or create paths."""
    absolute = guard.absolute(path)
    nearest = None
    missing_seen = False
    for entry in reversed((absolute, *absolute.parents)):
        try:
            checked_plain(entry, True)
        except FileNotFoundError:
            missing_seen = True
        else:
            if missing_seen:
                raise GuardError(f"Path changed while checking ancestors: {entry}")
            nearest = entry
    if nearest is None:
        raise GuardError("No existing ordinary parent directory was found")
    return absolute, nearest, nearest == absolute


def mount_from_device(path, device):
    """Walk ancestor metadata only, stopping at the filesystem boundary."""
    current = Path(path)
    while current.parent != current:
        parent = current.parent
        try:
            checked_plain(parent, True)
            if os.stat(parent, follow_symlinks=False).st_dev != device:
                break
        except (OSError, GuardError):
            break
        current = parent
    return str(current)


def volume_info(path):
    info = checked_plain(path, True)
    device = int(info.st_dev)
    result = {"metadata_path": str(path), "st_dev": device,
              "volume_id": None, "mount_path": None, "filesystem": "unknown",
              "drive_type": "unknown", "disk_type": "unknown",
              "attachment": "unknown", "locality": "unknown", "total_bytes": None, "used_bytes": None,
              "free_bytes": None, "limits": []}
    if WIN:
        result.update(WIN.info(path))
        result["locality"] = "network" if result["drive_type"] == "network" else (
            "local" if result["drive_type"] in {"fixed", "removable", "ramdisk", "optical"} else "unknown")
    else:
        result["volume_id"] = "posix-st_dev:" + str(device)
        result["mount_path"] = mount_from_device(path, device)
        if DARWIN:
            verified = DARWIN.verified_for_device(path, device)
            if verified:
                result.update(verified)
            else:
                result["limits"].append("Darwin filesystem/locality metadata could not be matched to actual st_dev")
        result["limits"].append("Filesystem name, physical device, SSD/HDD and internal/external attachment were not verified")
    try:
        if DARWIN and result["locality"] != "local":
            raise OSError("Unverified/network Darwin volume excluded from free-space probing")
        usage = shutil.disk_usage(path)
        result.update(total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free)
    except OSError as exc:
        result["limits"].append(f"Free-space metadata unavailable: {exc}")
    if WIN:
        result["limits"].append("Win32 drive type does not establish SSD/HDD or internal/external attachment")
        if result["drive_type"] in {"unknown", "no_root"}:
            result["limits"].append("Actual volume type/locality is unverified; no durable-target or physical-medium qualification is inferred")
    return result


def same_volume(left, right):
    a, b = left.get("volume_id"), right.get("volume_id")
    if a and b:
        return a == b
    return None


def discover_locations(source_volume):
    if WIN:
        return WIN.discover()
    paths, limits = [], []
    if sys.platform == "darwin":
        limits.extend(DARWIN.limits)
        volumes = Path("/Volumes")
        try:
            guard.ancestors(volumes)
            # Exactly one directory level, bounded. No file-tree or disk scan.
            with os.scandir(volumes) as entries:
                for index, entry in enumerate(entries):
                    if index >= MAX_MOUNTS:
                        limits.append(f"/Volumes discovery stopped at {MAX_MOUNTS} entries")
                        break
                    try:
                        mounted = DARWIN.covering(entry.path)
                        if not mounted or mounted["locality"] != "local":
                            limits.append(f"/Volumes entry excluded: {entry.path}: network/locality unknown")
                            continue
                        checked_plain(entry.path, True)
                        if os.path.ismount(entry.path):
                            paths.append(entry.path)
                    except (OSError, GuardError) as exc:
                        limits.append(f"/Volumes entry excluded: {entry.path}: {exc}")
        except (OSError, GuardError) as exc:
            limits.append(f"/Volumes metadata discovery unavailable: {exc}")
        limits.append("macOS implementation has not been validated on a real macOS host in this delivery")
        limits.append("/Volumes directories are not presumed to be external disks; only actual mount points are discovered")
    else:
        limits.append("Automatic mounted-volume discovery is implemented for Windows and macOS only; add explicit --target paths on this platform")
    if source_volume.get("mount_path"):
        paths.append(source_volume["mount_path"])
    return paths, limits


def target_record(path, origins, source_volume):
    record = {"requested_path": str(guard.absolute(path)), "origins": sorted(origins),
              "status": "excluded", "eligible_different_volume_location": False,
              "same_volume_as_project": None, "migration_ready": False,
              "limits": [], "target_directory_created": False}
    if WIN:
        absolute = guard.absolute(path)
        # Do not probe network shares, optical media, or unavailable drive roots.
        # A directory-mounted local volume is checked again at its actual root.
        if str(absolute).startswith("\\\\"):
            record["limits"].append("UNC/network paths are excluded; reachability and credentials were not probed")
            return record
        preliminary = WIN.drive_type(absolute.anchor)
        if preliminary in {"network", "optical", "no_root", "unknown"}:
            record["limits"].append(f"Drive root excluded: {preliminary}; no directory traversal or write probe")
            return record
    if DARWIN:
        mounted = DARWIN.covering(guard.absolute(path))
        if not mounted or mounted["locality"] != "local":
            record["limits"].append("Network or unknown-locality Darwin location excluded; no write or network reachability probe")
            return record
    try:
        absolute, nearest, exists = checked_location(path)
        record.update(path=str(absolute), exists=exists, nearest_existing_parent=str(nearest),
                      canonical_path=os.path.realpath(nearest) if exists else None,
                      canonical_nearest_existing_parent=os.path.realpath(nearest),
                      nearest_parent_identity=guard.root_identity(nearest))
        metadata = volume_info(nearest)
        record["volume"] = metadata
        relation = same_volume(source_volume, metadata)
        record["same_volume_as_project"] = relation
        if metadata["locality"] != "local":
            record["limits"].append("Actual volume locality is unknown or network; excluded")
        elif metadata["drive_type"] == "ramdisk":
            record["limits"].append("Known RAM disk is non-durable; excluded as a target for retained project data")
        elif DARWIN and metadata.get("read_only_mount"):
            record["limits"].append("Read-only Darwin mount excluded from migration candidates")
        elif WIN and metadata["drive_type"] not in {"fixed", "removable"}:
            record["limits"].append(f"Actual mounted volume type is not a verified fixed/removable location; excluded: {metadata['drive_type']}")
        elif metadata["free_bytes"] is None:
            record["limits"].append("Capacity unavailable; target qualification is unknown")
        elif relation is None:
            record["limits"].append("Volume relationship could not be verified; not a migration candidate")
        else:
            record["status"] = "same_volume" if relation else "different_volume_candidate"
            record["eligible_different_volume_location"] = not relation and metadata["free_bytes"] > 0
            if relation:
                record["limits"].append("Moving data here cannot free space on the project's source volume")
            elif metadata["free_bytes"] <= 0:
                record["status"] = "different_volume_no_free_space"
        if not exists:
            record["limits"].append("Target does not exist; volume identity is bound only to the nearest existing parent; no directory was created")
        record["limits"].append("Write permission, migration object size, references, application behavior and rollback have not been tested")
    except (OSError, GuardError, ValueError) as exc:
        record["limits"].append(f"Location rejected or inaccessible: {exc}")
    return record


def inspect_project(args):
    goal = args.goal_free_gib
    if goal is not None and (not math.isfinite(goal) or goal < 0 or goal > (2 ** 63 - 1) / GIB):
        raise GuardError("--goal-free-gib must be finite, nonnegative, and fit a signed 64-bit byte count")
    project = guard.project_root(args.project, args.codex_home)
    project_identity = guard.root_identity(project)
    source = volume_info(project)
    if source.get("mount_path") and os.path.samefile(project, source["mount_path"]):
        raise GuardError("Project must be a specific directory, not a mounted filesystem root")
    canonical = os.path.realpath(project)
    discovered, discovery_limits = ([], ["Automatic discovery disabled by --no-discover"]) if args.no_discover else discover_locations(source)
    # The source mount is always present as a same-volume comparison location.
    if source.get("mount_path"):
        discovered.append(source["mount_path"])
    unique = {}
    for path, origin in [(x, "mounted_volume_discovery") for x in discovered] + [(x, "explicit_target") for x in args.target]:
        key = guard.key(path)
        if key not in unique:
            unique[key] = [path, set()]
        unique[key][1].add(origin)
    records = [target_record(path, origins, source) for path, origins in unique.values()]
    goal_bytes = int(goal * GIB) if goal is not None else None
    free = source["free_bytes"]
    gap = max(0, goal_bytes - free) if free is not None and goal_bytes is not None else None
    different = [r for r in records if r["eligible_different_volume_location"]]
    same = [r for r in records if r["same_volume_as_project"] is True]
    unknown = list(discovery_limits) + list(source["limits"])
    for record in records:
        if record["status"] == "excluded":
            unknown.extend(f"{record['requested_path']}: {x}" for x in record["limits"])
    unknown += ["No recursive project/disk inventory or file-content reading was performed",
                "Unknown project outputs, build directories, media and recovery data are not assumed deletable",
                "Free-space values are point-in-time metadata and may change independently of this task",
                "Different mount paths do not prove different volumes; volume identities determine the relationship",
                "Different volumes may share physical storage; physical-device independence was not established",
                "No write probe was performed; every candidate still needs an exact approved migration plan"]
    if goal is None:
        recommendation = "No free-space goal was specified. Review the current free-space snapshot, project growth and exact inventory before choosing any changes. "
        if different:
            recommendation += "Different-volume locations are metadata candidates only; no migration size or permission has been qualified."
            options = ["review_current_capacity_and_growth", "review_optional_different_volume_locations"]
        else:
            recommendation += "No qualified different-volume location was found; supply or attach a target if migration is desired."
            options = ["review_current_capacity_and_growth", "add_or_attach_different_volume_target"]
    elif not different:
        recommendation = "No qualified different-volume location was found. Review proven disposable project cache, or supply/attach an additional target; do not force a same-volume migration."
        options = ["review_verified_deletion_candidates", "add_or_attach_different_volume_target"]
    elif gap == 0:
        recommendation = "The current free-space goal is already met. Review project growth before choosing any deletion or migration."
        options = ["retain_current_layout", "review_growth_and_optional_migration"]
    else:
        recommendation = "Use an exact project inventory to offer migration, proven deletion, or a combination; compare required bytes with a chosen different-volume location before authorization."
        options = ["migration_plan", "verified_deletion_plan", "combined_plan"]
    # Confirm project identity again before delivering the snapshot.
    guard.same_root(project, project_identity)
    return {"schema": "project-volume-advisor-v2", "tool_version": VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": sys.platform, "read_only": True, "goal_user_specified": goal is not None,
        "project": {"requested_path": str(args.project), "path": str(project),
                    "canonical_path": canonical, "identity": project_identity},
        "source_volume": source, "target_locations": records,
        "decision_basis": {"source_volume_free": free, "source_volume_free_bytes": free,
            "goal_user_specified": goal is not None, "goal_free_gib": goal, "goal_free_bytes": goal_bytes,
            "goal_gap": gap, "goal_gap_bytes": gap,
            "different_volume_target_candidates": [{"path": r["path"], "volume_id": r["volume"]["volume_id"],
                "free_bytes": r["volume"]["free_bytes"], "exists": r["exists"], "migration_ready": False} for r in different],
            "same_volume_locations": [r["path"] for r in same],
            "unknown_limits": list(dict.fromkeys(unknown))},
        "recommendation": recommendation, "user_decision_options": options,
        "writes": "Only the explicitly named new JSON report and same-stem Markdown companion; no project or target writes"}


def gib(value):
    return "unknown" if value is None else f"{value / GIB:.2f} GiB"


def markdown(report):
    basis = report["decision_basis"]
    goal_text = (f"目标 {gib(basis['goal_free_bytes'])}；缺口 {gib(basis['goal_gap'])}。"
                 if basis["goal_user_specified"] else "未指定空闲目标；不计算缺口。")
    lines = ["# 项目所在磁盘诊断 / Project volume review", "",
        f"项目：`{report['project']['canonical_path']}`", "",
        f"源卷：`{report['source_volume']['volume_id'] or 'unknown'}`  ",
        f"总量 {gib(report['source_volume']['total_bytes'])}；空闲 {gib(basis['source_volume_free'])}；" + goal_text, "",
        "| 位置 | 卷关系 | 空闲 | 磁盘介质/内外置 | 状态 |",
        "| --- | --- | --- | --- | --- |"]
    for item in report["target_locations"]:
        volume = item.get("volume", {})
        relation = {True: "同卷，迁入不能释放源卷", False: "不同卷", None: "unknown"}[item["same_volume_as_project"]]
        path = item["requested_path"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{path}` | {relation} | {gib(volume.get('free_bytes'))} | unknown / unknown | {item['status']} |")
    lines += ["", "建议 / Recommendation", "", report["recommendation"], "",
        "候选仅通过位置与容量元数据检查；迁移对象大小、权限、引用关系与回退尚待核实。未知项目产物不视为可删除。", "",
        "限制 / Limits", ""]
    lines.extend("- " + text.replace("\n", " ") for text in basis["unknown_limits"])
    lines += ["", "仅写本报告及同名 Markdown；未扫描文件树、未创建目标目录、未删除或迁移。", ""]
    return "\n".join(lines)


def report_paths(output, project):
    path = guard.absolute(output)
    if path.suffix.lower() != ".json":
        raise GuardError("--output must name a new .json file")
    companion = path.with_suffix(".md")
    for item in (path, companion):
        # No implicit mkdir: report-parent paths must already exist and be safe.
        guard.ancestors(item.parent)
        inside_project = guard.below(item, project)
        if not inside_project:
            # Mount aliases can reach the same directory without a lexical
            # prefix match. Compare actual directory identities as well.
            for ancestor in (item.parent, *item.parent.parents):
                if os.path.samefile(ancestor, project):
                    inside_project = True
                    break
        if inside_project:
            raise GuardError("Reports must be outside the project; the project is read-only")
        if os.path.lexists(item):
            raise GuardError(f"Output already exists; choose a new name: {item}")
    return path, companion


def run(args):
    # Preflight destinations before any discovery; inspect_project validates the
    # source independently so API callers cannot bypass project-root protection.
    project = guard.project_root(args.project, args.codex_home)
    json_path, md_path = report_paths(args.output, project)
    report = inspect_project(args)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    rendered = markdown(report)
    # O_EXCL refuses overwrite, including a destination appearing after preflight.
    # A concurrent failure can leave a partial report, never a project mutation.
    with contextlib.ExitStack() as stack:
        handles = []
        for path in (json_path, md_path):
            guard.ancestors(path.parent)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            handles.append(stack.enter_context(os.fdopen(fd, "w", encoding="utf-8", newline="\n")))
        for handle, content in zip(handles, (encoded, rendered)):
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    print(json.dumps({"report": str(json_path), "markdown": str(md_path),
        "source_volume_free_bytes": report["decision_basis"]["source_volume_free"],
        "goal_gap_bytes": report["decision_basis"]["goal_gap"],
        "different_volume_candidates": len(report["decision_basis"]["different_volume_target_candidates"]),
        "read_only": True}, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inspect project-volume metadata and candidate target locations; no migration or deletion")
    inspect.add_argument("--project", required=True)
    inspect.add_argument("--output", required=True, help="New .json report outside the project; parent directory must exist")
    inspect.add_argument("--target", action="append", default=[], help="Explicit target path; repeatable, may be nonexistent")
    inspect.add_argument("--goal-free-gib", type=float, default=None, help="Optional explicit free-space goal in GiB; no goal is assumed when omitted")
    inspect.add_argument("--codex-home")
    inspect.add_argument("--no-discover", action="store_true", help="Only inspect explicit targets and the source-volume comparison location")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (GuardError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "read_only": True,
            "no_automatic_retry": True}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
