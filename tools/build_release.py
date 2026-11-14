#!/usr/bin/env python3
"""Build a curated, reproducible skill ZIP without publishing or overwriting.

Only explicitly named public skill resources and documentation are included.
The output directory must be outside the repository. No project command runs.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import unquote
import zipfile

PACKAGE = "codex-project-storage"
RUNTIME_FILES = (
    "SKILL.md", "agents/openai.yaml",
    "scripts/storage_guard.py", "scripts/volume_advisor.py",
    "scripts/relocation_guard.py", "scripts/generated_artifact_guard.py",
    "scripts/native_cache_guard.py", "scripts/project_profiler.py",
    "scripts/retired_runtime_guard.py", "scripts/npm_cache_guard.py",
    "scripts/agent_artifact_guard.py", "references/agent-artifacts.md",
    "scripts/project_batches.py", "scripts/build_artifact_guard.py",
    "references/batched-inventory.md", "references/historical-builds.md",
    "references/storage-map.md", "references/operations.md",
    "references/mature-patterns.md", "references/relocation.md",
    "references/verification.json", "references/project-types.md",
    "references/generated-artifacts.md", "references/native-cache.md",
    "references/retired-runtime.md", "references/npm-cache.md",
    "docs/COMPATIBILITY.md",
    "references/codex-state.md", "LICENSE", "README.md",
)
PUBLIC_DOCS = (
    "README.en.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md",
    "SUPPORT.md", "CODE_OF_CONDUCT.md", "ACKNOWLEDGEMENTS.md",
    "THIRD_PARTY_NOTICES.md", "docs/INSTALLATION.md", "docs/QUICKSTART.md",
    "docs/ARCHITECTURE.md", "docs/SAFETY.md",
    "docs/RELEASING.md", "docs/GITHUB-PUBLISHING.zh-CN.md",
    "docs/RELEASE_NOTES_v1.3.0.md", "docs/RELEASE_NOTES_v1.4.0.md", "docs/ROADMAP.md",
    "docs/RELEASE_NOTES_v1.5.0.md",
    "docs/RELEASE_NOTES_v1.6.0.md",
)
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_BUNDLE_BYTES = 16 * 1024 * 1024


class ReleaseError(Exception):
    pass


def absolute(value):
    return Path(os.path.abspath(os.path.expanduser(str(value))))


def below(path, root):
    try:
        return os.path.commonpath((os.path.normcase(str(path)), os.path.normcase(str(root)))) == os.path.normcase(str(root))
    except ValueError:
        return False


def ordinary_ancestors(path, allow_missing=False):
    for parent in reversed((path, *path.parents)):
        try:
            value = os.lstat(parent)
        except FileNotFoundError:
            if allow_missing:
                continue
            raise ReleaseError("Required directory is missing")
        if not stat.S_ISDIR(value.st_mode) or stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
            raise ReleaseError("Linked, reparse, or non-directory ancestor refused")


def read_public(root, relative):
    path = root.joinpath(*relative.split("/"))
    ordinary_ancestors(path.parent)
    before = os.lstat(path)
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_nlink != 1
            or before.st_size > MAX_FILE_BYTES):
        raise ReleaseError("Public resource is linked, non-ordinary, or exceeds the file budget: " + relative)
    with path.open("rb") as handle:
        current = os.fstat(handle.fileno())
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ReleaseError("Public resource changed before reading: " + relative)
        data = handle.read(MAX_FILE_BYTES + 1)
        after = os.fstat(handle.fileno())
    if (len(data) != before.st_size or len(data) > MAX_FILE_BYTES
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)):
        raise ReleaseError("Public resource changed during reading: " + relative)
    return data


def license_state(data):
    text = data.decode("utf-8-sig")
    if re.search(r"\[(?:year|fullname|name|copyright holder)\]|\b(?:TODO|TBD|DRAFT)\b|待确认|许可证草案", text, re.I):
        return {"valid_text": False, "identifier": None, "reason": "Unfinished license text"}
    if (text.lstrip().startswith("MIT License") and re.search(r"Copyright\s+\(c\)\s+\d{4}\s+\S", text)
            and "Permission is hereby granted" in text and "THE SOFTWARE IS PROVIDED" in text):
        return {"valid_text": True, "identifier": "MIT", "reason": "Recognizable license text; this does not confirm author consent or ownership"}
    if ("Apache License" in text and "Version 2.0" in text and "TERMS AND CONDITIONS FOR USE" in text
            and "END OF TERMS AND CONDITIONS" in text):
        return {"valid_text": True, "identifier": "Apache-2.0", "reason": "Recognizable license text; this does not confirm author consent or ownership"}
    return {"valid_text": False, "identifier": None, "reason": "Missing or unrecognized complete license text"}


def snapshot(root, version=None):
    ordinary_ancestors(root)
    payloads, total = {}, 0
    def add(relative):
        nonlocal total
        data = read_public(root, relative)
        total += len(data)
        if total > MAX_BUNDLE_BYTES:
            raise ReleaseError("Curated bundle exceeds the total read budget")
        payloads[relative] = data
    for rel in RUNTIME_FILES:
        add(rel)
    for rel in PUBLIC_DOCS:
        path = root.joinpath(*rel.split("/"))
        if os.path.lexists(path):
            add(rel)
    metadata = json.loads(payloads["references/verification.json"].decode("utf-8-sig"))
    recorded = metadata.get("bundle_version")
    if not isinstance(recorded, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", recorded):
        raise ReleaseError("Invalid bundle version")
    if version is not None and version != recorded:
        raise ReleaseError("Requested version differs from verification metadata")
    components = metadata.get("components")
    expected = {Path(rel).name for rel in RUNTIME_FILES if rel.startswith("scripts/")}
    if not isinstance(components, dict) or set(components) != expected:
        raise ReleaseError("Verification metadata must fingerprint all runtime components")
    for name, component in components.items():
        key = "scripts/" + name
        if not isinstance(component, dict) or key not in payloads or hashlib.sha256(payloads[key]).hexdigest() != component.get("sha256"):
            raise ReleaseError("Component fingerprint differs from verification metadata: " + name)
    license_info = license_state(payloads["LICENSE"])
    if not license_info["valid_text"]:
        raise ReleaseError(license_info["reason"])
    return recorded, payloads, license_info


def check_packaged_links(payloads):
    # The install ZIP must not leave public README/document links pointing to
    # developer files deliberately excluded from the runtime distribution.
    for relative, data in payloads.items():
        if not relative.endswith(".md"):
            continue
        text = data.decode("utf-8-sig")
        for match in re.finditer(r"\]\(([^)]+)\)", text):
            raw = match.group(1).strip()
            if raw.startswith("<") and ">" in raw:
                raw = raw[1:raw.index(">")]
            elif ' "' in raw:
                raw = raw.split(' "', 1)[0]
            target = unquote(raw.split("#", 1)[0])
            if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("//"):
                continue
            components = [] if target.startswith("/") else relative.split("/")[:-1]
            for part in target.split("/"):
                if part in {"", "."}:
                    continue
                if part == "..":
                    if not components:
                        raise ReleaseError("Packaged Markdown link escapes package: " + relative)
                    components.pop()
                else:
                    components.append(part)
            resolved = "/".join(components)
            if resolved not in payloads and not any(p.startswith(resolved.rstrip("/") + "/") for p in payloads):
                raise ReleaseError("Packaged Markdown target is not in the curated distribution: " + relative + " -> " + target)


def exclusive_write(path, data):
    # Exclusive creation is deliberate: no replacement, shell move, or cleanup.
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def build(repo, output_dir, version=None):
    root, out = absolute(repo), absolute(output_dir)
    ordinary_ancestors(root)
    ordinary_ancestors(out, allow_missing=True)
    if below(out, root) or below(out.resolve(strict=False), root.resolve(strict=True)):
        raise ReleaseError("Build output must be outside the repository")
    actual_version, payloads, license_info = snapshot(root, version)
    check_packaged_links(payloads)
    stem = PACKAGE + "-" + actual_version
    targets = {"archive": out / (stem + ".zip"), "manifest": out / (stem + ".manifest.json"), "checksums": out / "SHA256SUMS"}
    if any(os.path.lexists(path) for path in targets.values()):
        raise ReleaseError("Output already exists; use a new output directory")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(PACKAGE + "/" + relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    archive_bytes = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as check:
        if check.testzip() is not None or len(check.namelist()) != len(payloads):
            raise ReleaseError("Archive self-check failed")
        if any(hashlib.sha256(check.read(PACKAGE + "/" + rel)).digest() != hashlib.sha256(data).digest() for rel, data in payloads.items()):
            raise ReleaseError("Archive content check failed")
    manifest = {
        "schema": "codex-project-storage-distribution-v1", "package": PACKAGE,
        "version": actual_version, "archive": targets["archive"].name,
        "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "file_count": len(payloads), "uncompressed_bytes": sum(map(len, payloads.values())),
        "license": license_info["identifier"], "license_text_validation_is_not_author_consent": True,
        "files": [{"path": rel, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for rel, data in sorted(payloads.items())],
        "excluded_by_design": [".git", ".github", "tests", "tools", "private run reports", "credentials", "__pycache__"],
        "published_to_github": False,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    sums = (hashlib.sha256(archive_bytes).hexdigest() + "  " + targets["archive"].name + "\n"
            + hashlib.sha256(manifest_bytes).hexdigest() + "  " + targets["manifest"].name + "\n").encode("ascii")
    out.mkdir(parents=True, exist_ok=True)
    ordinary_ancestors(out)
    for name, data in (("archive", archive_bytes), ("manifest", manifest_bytes), ("checksums", sums)):
        exclusive_write(targets[name], data)
    return {"status": "built_verified", "version": actual_version, "outputs": {k: str(v) for k, v in targets.items()},
            "file_count": len(payloads), "archive_sha256": manifest["archive_sha256"], "published_to_github": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        result = build(args.repo, args.output_dir, args.version)
    except (ReleaseError, OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "refused_or_failed", "error": str(exc), "note": "No retry or automatic overwrite. Partial output, if any, is not a qualified release."}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
