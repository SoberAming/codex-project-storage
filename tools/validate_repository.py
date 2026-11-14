#!/usr/bin/env python3
"""Read-only public repository checks; never run project code or cleanup.

PyYAML enables actual YAML parsing. Without it, status is partial; CI passes
--require-yaml. These checks do not certify legal ownership, GitHub execution,
platform acceptance, global references, or absence of all sensitive content.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import unquote

SENSITIVE_NAMES = {"auth.json", "history.jsonl", "session_index.jsonl", "id_rsa", "id_ed25519"}
PRIVATE_DIRS = {".codex", ".agents", ".claude", ".kimi", ".kimi-code", ".workbuddy", ".codebuddy", "sessions", "archived_sessions", "thread_history",
                "credentials", "secrets", "private-reports", "qa-runs", "test-runs",
                ".ssh", ".aws", ".azure", ".gnupg"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache"}
MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES = 500, 4 * 1024 * 1024, 16 * 1024 * 1024


def load_builder():
    path = Path(__file__).with_name("build_release.py")
    spec = importlib.util.spec_from_file_location("_release_validation_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def yaml_loader():
    try:
        import yaml
    except ImportError:
        return None
    return yaml.safe_load


def collect(root, errors):
    files, total = {}, 0
    def unreadable(exc):
        errors.append({"check": "directory_unreadable", "errno": getattr(exc, "errno", None)})
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=unreadable):
        kept = []
        for name in sorted(dirs):
            path = Path(directory) / name
            info = os.lstat(path)
            if name.lower() in PRIVATE_DIRS:
                errors.append({"file": path.relative_to(root).as_posix(), "check": "private_directory_no_content_read"})
            elif stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                errors.append({"file": path.relative_to(root).as_posix(), "check": "linked_directory"})
            elif name not in SKIP_DIRS:
                kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            info = os.lstat(path)
            if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_nlink != 1):
                errors.append({"file": relative, "check": "nonordinary_or_linked_file"})
                continue
            if len(files) >= MAX_FILES or info.st_size > MAX_FILE_BYTES or total + info.st_size > MAX_TOTAL_BYTES:
                errors.append({"file": relative, "check": "read_budget_exceeded"})
                continue
            if (name.lower() in SENSITIVE_NAMES or name.startswith(".env")
                    or re.search(r"(?:credential|secret|token|password)", name, re.I)):
                errors.append({"file": relative, "check": "private_filename_no_content_read"})
                continue
            if path.suffix.lower() not in {".md", ".py", ".yaml", ".yml", ".json", ".txt"} and name not in {"LICENSE", ".gitignore", ".gitattributes", "SHA256SUMS"}:
                errors.append({"file": relative, "check": "unreviewed_public_file_type"})
                continue
            data = path.read_bytes()
            if len(data) != info.st_size:
                errors.append({"file": relative, "check": "size_changed_during_read"})
                continue
            total += len(data)
            try:
                files[relative] = (data.decode("utf-8-sig"), data)
            except UnicodeError:
                errors.append({"file": relative, "check": "non_utf8_public_text"})
    return files, total


def privacy_checks(relative, text, errors):
    # Report locations and categories only; do not print matched secret text.
    patterns = {
        "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "github_token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
        "openai_style_key": r"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b",
        "aws_access_key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    }
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text):
            errors.append({"file": relative, "line": text.count("\n", 0, match.start()) + 1, "check": kind})
    for match in re.finditer(r"(?:[A-Za-z]:[\\/]Users[\\/]|/Users/)([A-Za-z0-9._-]+)", text):
        if match.group(1).upper() not in {"USER", "USERNAME", "YOUR_USER", "EXAMPLE", "REDACTED"}:
            errors.append({"file": relative, "line": text.count("\n", 0, match.start()) + 1, "check": "concrete_personal_home_path"})


def markdown_links(root, relative, text, errors):
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        raw = match.group(1).strip()
        if raw.startswith("<") and ">" in raw:
            raw = raw[1:raw.index(">")]
        elif ' "' in raw:
            raw = raw.split(' "', 1)[0]
        target = unquote(raw.split("#", 1)[0])
        if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("//"):
            continue
        path = root / target.lstrip("/") if target.startswith("/") else (root / relative).parent / target
        resolved = path.resolve(strict=False)
        if not load_builder().below(resolved, root.resolve(strict=True)) or not path.exists():
            errors.append({"file": relative, "line": text.count("\n", 0, match.start()) + 1, "check": "missing_or_escaping_markdown_target", "target": target})


def workflow_checks(relative, parsed, errors):
    if not isinstance(parsed, dict):
        errors.append({"file": relative, "check": "workflow_mapping_required"})
        return
    permissions = parsed.get("permissions")
    if permissions != {"contents": "read"}:
        errors.append({"file": relative, "check": "workflow_must_have_read_only_contents_permission"})
    events = parsed.get("on", parsed.get(True))  # PyYAML YAML1.1 treats 'on' as true.
    if not events:
        errors.append({"file": relative, "check": "workflow_trigger_required"})
    if isinstance(events, dict) and any(k in events for k in ("pull_request_target", "workflow_run")):
        errors.append({"file": relative, "check": "privileged_cross_context_trigger_refused"})
    for job in parsed.get("jobs", {}).values():
        if isinstance(job, dict):
            for step in job.get("steps", []):
                use = step.get("uses") if isinstance(step, dict) else None
                if use and not use.startswith("./") and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[a-f0-9]{40}", use):
                    errors.append({"file": relative, "check": "external_action_must_pin_full_commit"})


def validate(repo, require_yaml=False):
    builder = load_builder()
    root = builder.absolute(repo)
    builder.ordinary_ancestors(root)
    errors, warnings = [], []
    parse_yaml = yaml_loader()
    if parse_yaml is None:
        (errors if require_yaml else warnings).append({"check": "yaml_parser_unavailable", "detail": "Install requirements-dev.txt; YAML not fully parsed"})
    files, total = collect(root, errors)
    for relative, (text, data) in files.items():
        privacy_checks(relative, text, errors)
        if relative.endswith(".py"):
            try:
                ast.parse(text, filename=relative, feature_version=(3, 10))
            except SyntaxError as exc:
                errors.append({"file": relative, "line": exc.lineno, "check": "python_3_10_syntax"})
        elif relative.endswith(".json"):
            try:
                json.loads(text)
            except ValueError:
                errors.append({"file": relative, "check": "invalid_json"})
        elif relative.endswith((".yaml", ".yml")) and parse_yaml:
            try:
                parsed = parse_yaml(text)
                if relative.startswith(".github/workflows/"):
                    workflow_checks(relative, parsed, errors)
            except Exception:
                errors.append({"file": relative, "check": "invalid_yaml"})
        if relative.endswith(".md"):
            markdown_links(root, relative, text, errors)
    front = files.get("SKILL.md", ("", b""))[0]
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", front, re.S)
    if not match:
        errors.append({"file": "SKILL.md", "check": "frontmatter_required"})
    elif parse_yaml:
        try:
            metadata = parse_yaml(match.group(1))
            if (not isinstance(metadata, dict) or metadata.get("name") != builder.PACKAGE
                    or not isinstance(metadata.get("description"), str) or not metadata["description"].strip()):
                raise ValueError()
        except Exception:
            errors.append({"file": "SKILL.md", "check": "invalid_skill_frontmatter"})
    else:
        if not re.search(r"(?m)^name:\s*codex-project-storage\s*$", match.group(1)) or not re.search(r"(?m)^description:\s*\S", match.group(1)):
            errors.append({"file": "SKILL.md", "check": "invalid_basic_frontmatter"})
    license_info = {"valid_text": False, "identifier": None}
    version = None
    try:
        version, payloads, license_info = builder.snapshot(root)
        for name, component in json.loads(payloads["references/verification.json"].decode("utf-8-sig")).get("components", {}).items():
            tree = ast.parse(payloads["scripts/" + name].decode("utf-8-sig"))
            found = [n.value.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets) and isinstance(n.value, ast.Constant)]
            if found != [component.get("version")]:
                errors.append({"file": "scripts/" + name, "check": "component_version_mismatch"})
        changelog = files.get("CHANGELOG.md", ("", b""))[0]
        if not re.search(r"(?m)^##\s+\[?v?" + re.escape(version) + r"(?:\]|\s|$)", changelog):
            errors.append({"file": "CHANGELOG.md", "check": "bundle_version_section_missing"})
    except (builder.ReleaseError, OSError, ValueError, UnicodeError) as exc:
        errors.append({"check": "release_snapshot", "detail": str(exc)})
    if parse_yaml and "agents/openai.yaml" in files:
        try:
            ui = parse_yaml(files["agents/openai.yaml"][0])["interface"]
            if not (25 <= len(ui["short_description"]) <= 64 and "$codex-project-storage" in ui["default_prompt"]):
                raise ValueError()
        except Exception:
            errors.append({"file": "agents/openai.yaml", "check": "invalid_interface_metadata"})
    return {"schema": "codex-project-storage-repository-check-v1", "status": "failed" if errors else "partial" if warnings else "passed",
            "bundle_version": version, "files_checked": len(files), "text_bytes_read": total,
            "yaml_parsed": bool(parse_yaml), "license_text": license_info,
            "errors": errors, "warnings": warnings,
            "limits": ["No project code executed", "No complete secret-scanner, legal, ownership, runtime, hosted-CI or platform certification", "Relative Markdown file existence checked; anchors and remote links not fetched"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--require-yaml", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    builder = load_builder()
    try:
        root = builder.absolute(args.repo)
        output = builder.absolute(args.output) if args.output else None
        if output:
            builder.ordinary_ancestors(output.parent, allow_missing=True)
            if builder.below(output, root) or builder.below(output.resolve(strict=False), root.resolve(strict=True)):
                raise builder.ReleaseError("Report output must be outside the repository")
            if os.path.lexists(output):
                raise builder.ReleaseError("Report output already exists")
        result = validate(root, args.require_yaml)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            builder.exclusive_write(output, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except (builder.ReleaseError, OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
