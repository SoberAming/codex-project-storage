"""Portable release-tool behavior checks using new fictional fixtures only.

Requires --work-root. Fixtures are retained for inspection. No existing project,
cache purge, hosted workflow, network service, or remote publication is used.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--work-root", required=True)
opts, remaining = parser.parse_known_args()
BASE = Path(opts.work_root).absolute()
if not BASE.is_dir():
    parser.error("--work-root must name an existing independent test directory")
RUN = Path(tempfile.mkdtemp(prefix="release-tool-tests-", dir=BASE))
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


B = load("_release_builder_under_test", ROOT / "tools/build_release.py")
V = load("_repo_validator_under_test", ROOT / "tools/validate_repository.py")

TEST_LICENSE = '''MIT License

Copyright (c) 2026 Fictional Test Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReleaseToolTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.repo = self.area / "fictional-repo"
        self.repo.mkdir()
        for relative in B.RUNTIME_FILES:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == "LICENSE":
                target.write_text(TEST_LICENSE, encoding="utf-8")
            elif relative == "README.md":
                target.write_text("# Fictional release fixture\n\n[License](LICENSE)\n", encoding="utf-8")
            else:
                shutil.copyfile(ROOT / relative, target)
        self.version = json.loads((self.repo / "references/verification.json").read_text(encoding="utf-8"))["bundle_version"]
        (self.repo / "CHANGELOG.md").write_text("# Fixture changes\n\n## " + self.version + "\n", encoding="utf-8")
        self.out = self.area / "outside-output"

    def test_curated_archive_excludes_private_and_developer_files(self):
        extra = {".codex/auth.json": b"fictional private data", ".github/secret.yml": b"not a package resource",
                 "tests/arbitrary.py": b"not runtime", "tools/arbitrary.py": b"not runtime",
                 "private-reports/raw.json": b"not public", "scripts/__pycache__/x.pyc": b"not source"}
        for rel, data in extra.items():
            target = self.repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        before = {rel: sha(self.repo / rel) for rel in extra}
        result = B.build(self.repo, self.out)
        with zipfile.ZipFile(result["outputs"]["archive"]) as archive:
            names = set(archive.namelist())
            self.assertIn(B.PACKAGE + "/SKILL.md", names)
            self.assertIn(B.PACKAGE + "/LICENSE", names)
            self.assertFalse(any(B.PACKAGE + "/" + rel in names for rel in extra))
        self.assertEqual(before, {rel: sha(self.repo / rel) for rel in extra})
        self.assertFalse(result["published_to_github"])

    def test_manifest_hashes_match_archive_and_checksums(self):
        result = B.build(self.repo, self.out)
        manifest = json.loads(Path(result["outputs"]["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["archive_sha256"], sha(result["outputs"]["archive"]))
        with zipfile.ZipFile(result["outputs"]["archive"]) as archive:
            self.assertEqual(manifest["file_count"], len(archive.namelist()))
            for item in manifest["files"]:
                content = archive.read(B.PACKAGE + "/" + item["path"])
                self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())
                self.assertEqual(item["bytes"], len(content))
        lines = Path(result["outputs"]["checksums"]).read_text(encoding="ascii").splitlines()
        self.assertIn(sha(result["outputs"]["archive"]) + "  " + Path(result["outputs"]["archive"]).name, lines)
        self.assertIn(sha(result["outputs"]["manifest"]) + "  " + Path(result["outputs"]["manifest"]).name, lines)

    def test_archive_is_reproducible_for_same_curated_input(self):
        first = B.build(self.repo, self.out)
        second = B.build(self.repo, self.area / "another-output")
        self.assertEqual(sha(first["outputs"]["archive"]), sha(second["outputs"]["archive"]))
        self.assertEqual(sha(first["outputs"]["manifest"]), sha(second["outputs"]["manifest"]))

    def test_existing_outputs_are_never_overwritten(self):
        result = B.build(self.repo, self.out)
        original = {key: sha(path) for key, path in result["outputs"].items()}
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, self.out)
        self.assertEqual(original, {key: sha(path) for key, path in result["outputs"].items()})

    def test_in_repository_output_refused_without_creating_directory(self):
        target = self.repo / "new-output"
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, target)
        self.assertFalse(target.exists())

    def test_actual_output_alias_into_repository_is_refused_simulation(self):
        original = Path.resolve
        output = self.out
        def aliased(path, strict=False):
            if path == output:
                return self.repo / "simulated-real-output"
            return original(path, strict=strict)
        with mock.patch.object(Path, "resolve", aliased):
            with self.assertRaises(B.ReleaseError):
                B.build(self.repo, self.out)
        self.assertFalse(self.out.exists())

    def test_version_mismatch_refused_before_writes(self):
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, self.out, "999.0.0")
        self.assertFalse(self.out.exists())

    def test_changed_component_refused_before_writes(self):
        metadata_file = self.repo / "references/verification.json"
        original = metadata_file.read_bytes()
        metadata = json.loads(original)
        metadata["components"] = {}
        metadata_file.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, self.out)
        metadata_file.write_bytes(original)
        with (self.repo / "scripts/storage_guard.py").open("a", encoding="utf-8") as file:
            file.write("\n# fictional modification after verification\n")
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, self.out)
        self.assertFalse(self.out.exists())

    def test_unfinished_or_missing_license_cannot_build(self):
        license_file = self.repo / "LICENSE"
        license_file.write_text("MIT License\nCopyright (c) [year] [fullname]\nDRAFT", encoding="utf-8")
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, self.out)
        license_file.unlink()
        with self.assertRaises(OSError):
            B.build(self.repo, self.out)
        self.assertFalse(self.out.exists())

    def test_hardlinked_resource_refused_metadata_simulation(self):
        original = os.lstat
        target = self.repo / "README.md"
        def linked(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if Path(path) == target:
                return SimpleNamespace(st_mode=value.st_mode, st_nlink=2, st_size=value.st_size,
                                       st_file_attributes=getattr(value, "st_file_attributes", 0))
            return value
        with mock.patch.object(B.os, "lstat", side_effect=linked):
            with self.assertRaises(B.ReleaseError):
                B.build(self.repo, self.out)
        self.assertFalse(self.out.exists())

    def test_oversized_resource_refused_by_metadata_budget(self):
        with mock.patch.object(B, "MAX_FILE_BYTES", 4):
            with self.assertRaises(B.ReleaseError):
                B.build(self.repo, self.out)
        self.assertFalse(self.out.exists())

    def test_validator_without_yaml_is_partial_and_not_full_pass(self):
        with mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo)
        self.assertEqual(result["status"], "partial", result["errors"])
        self.assertFalse(result["yaml_parsed"])
        self.assertEqual(result["errors"], [])
        self.assertTrue(result["license_text"]["valid_text"])

    def test_validator_require_yaml_fails_if_parser_absent(self):
        with mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo, require_yaml=True)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(item["check"] == "yaml_parser_unavailable" for item in result["errors"]))

    def test_validator_secret_canary_is_reported_without_echo(self):
        canary = "ghp_" + "a" * 40
        (self.repo / "README.md").write_text("# Fixture\n" + canary, encoding="utf-8")
        with mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any(item["check"] == "github_token" for item in result["errors"]))
        self.assertNotIn(canary, json.dumps(result))

    def test_validator_private_filename_does_not_read_body(self):
        private = self.repo / "auth.json"
        private.write_text("fictional private body", encoding="utf-8")
        private_members = [private]
        for relative in (".codex/credentials/client.json", "secrets/cloud.json", "private-reports/client.json", "access-token.json"):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fictional private body", encoding="utf-8")
            private_members.append(path)
        original = Path.read_bytes
        def deny(path):
            if path in private_members:
                raise AssertionError("Private body must not be read")
            return original(path)
        with mock.patch.object(Path, "read_bytes", deny), mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo)
        self.assertTrue(any(item["check"] == "private_filename_no_content_read" for item in result["errors"]))
        self.assertTrue(any(item["check"] == "private_directory_no_content_read" for item in result["errors"]))

    def test_validator_missing_markdown_target_is_an_error(self):
        (self.repo / "README.md").write_text("[Missing](not-present.md)\n", encoding="utf-8")
        with mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo)
        self.assertTrue(any(item["check"] == "missing_or_escaping_markdown_target" for item in result["errors"]))
        with self.assertRaises(B.ReleaseError):
            B.build(self.repo, self.out)
        self.assertFalse(self.out.exists())

    def test_validator_invalid_json_and_frontmatter_are_errors(self):
        (self.repo / "extra.json").write_text("{broken", encoding="utf-8")
        (self.repo / "SKILL.md").write_text("# Missing frontmatter", encoding="utf-8")
        with mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo)
        checks = {item["check"] for item in result["errors"]}
        self.assertIn("invalid_json", checks)
        self.assertIn("frontmatter_required", checks)

    def test_validator_report_cannot_be_written_inside_repository(self):
        report = self.repo / "report.json"
        result = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "tools/validate_repository.py"),
                                 "--repo", str(self.repo), "--output", str(report)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report.exists())

    def test_validator_does_not_read_worktree_git_pointer(self):
        (self.repo / ".git").write_bytes(b"private administrative pointer, not UTF-8: \xff")
        with mock.patch.object(V, "yaml_loader", return_value=None):
            result = V.validate(self.repo)
        self.assertFalse(any(x.get("file") == ".git" for x in result["errors"]))

    def test_validator_report_is_outside_and_not_overwritten(self):
        report = self.area / "validation.json"
        argv = [sys.executable, "-I", "-B", str(ROOT / "tools/validate_repository.py"), "--repo", str(self.repo), "--output", str(report)]
        first = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        original = sha(report)
        second = subprocess.run(argv, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(original, sha(report))


if __name__ == "__main__":
    print("Isolated evidence directory:", RUN, flush=True)
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
