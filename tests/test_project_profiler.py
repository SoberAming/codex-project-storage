"""Portable behavioral tests; every fictional fixture/report stays in --work-root.

Run: python -I -B test_project_profiler.py --work-root ABS_TEST_PARENT
No project scripts, builds, installs or cleanup executors are invoked. Test
directories are retained under the supplied parent for inspection.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


parser = argparse.ArgumentParser(description=__doc__, add_help=False)
parser.add_argument("--work-root", required=True)
opts, remaining = parser.parse_known_args()
BASE = Path(os.path.abspath(os.path.expanduser(opts.work_root)))
if BASE.parent == BASE or BASE == Path.home().absolute() or any(p.lower() in {".codex", ".agents", "sessions", "credentials", "secrets"} for p in BASE.parts):
    parser.error("work-root must be a precise test directory outside protected state storage")
for ancestor in reversed((BASE, *BASE.parents)):
    try:
        attributes = os.lstat(ancestor)
    except FileNotFoundError:
        continue
    if stat.S_ISLNK(attributes.st_mode) or getattr(attributes, "st_file_attributes", 0) & 0x400:
        parser.error("work-root ancestors must not contain symlinks/reparse points")
BASE.mkdir(parents=True, exist_ok=True)
RUN = Path(tempfile.mkdtemp(prefix="project-profiler-tests-", dir=BASE))
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "project_profiler.py"
spec = importlib.util.spec_from_file_location("project_profiler_under_test", SCRIPT)
PROFILE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PROFILE)


class ProjectProfilerTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix=self._testMethodName + "-", dir=RUN))
        self.project = self.area / "project"
        self.reports = self.area / "reports"
        self.codex = self.area / "empty-codex-state"
        self.sqlite = self.area / "sqlite-state"
        for directory in (self.project, self.reports, self.codex, self.sqlite):
            directory.mkdir()
        self.env = dict(os.environ)
        self.env.pop("CODEX_SQLITE_HOME", None)
        self.env.pop("NPM_CONFIG_CACHE", None)
        self.env.update({"CODEX_HOME": str(self.codex), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
        for variable, name in {
            "npm_config_cache": "shared-npm", "PIP_CACHE_DIR": "shared-pip", "UV_CACHE_DIR": "shared-uv",
            "CARGO_HOME": "shared-cargo", "GRADLE_USER_HOME": "shared-gradle", "GOPATH": "shared-go",
            "GOCACHE": "shared-go-build", "GOMODCACHE": "shared-go-modules", "NUGET_PACKAGES": "shared-nuget",
            "PUB_CACHE": "shared-pub", "PLAYWRIGHT_BROWSERS_PATH": "shared-playwright",
            "CYPRESS_CACHE_FOLDER": "shared-cypress", "PNPM_HOME": "shared-pnpm-home",
        }.items():
            shared = self.area / name
            shared.mkdir()
            self.env[variable] = str(shared)

    def put(self, relative, content=b"fictional data", root=None):
        path = (root or self.project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        path.write_bytes(content)
        return path

    def cli(self, *arguments, output=None, ok=True, environment=None):
        output = output or self.reports / ("report-" + str(len(list(self.reports.iterdir()))) + ".json")
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(SCRIPT), "inspect", "--project", str(self.project),
             "--codex-home", str(self.codex), "--output", str(output), *map(str, arguments)],
            cwd=self.area, env=environment or self.env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.is_file())
            self.assertTrue(output.with_suffix(".md").is_file())
            return json.loads(output.read_text(encoding="utf-8")), output
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result, output

    def profiler(self):
        args = SimpleNamespace(max_files=100000, max_config_bytes=1048576)
        return PROFILE.Profiler(args, self.project, self.codex, [])

    def logical_size(self, root=None):
        return sum(path.stat().st_size for path in (root or self.project).rglob("*") if path.is_file())

    def scan_fixture(self, files):
        rows = []
        for path in files:
            attributes = os.lstat(path)
            allocation = PROFILE.allocated(path, attributes)
            if allocation is None:
                self.skipTest("filesystem allocation metadata is unavailable")
            rows.append({"path": path.relative_to(self.project).as_posix(), "identity": PROFILE.fingerprint(attributes),
                         "allocated_bytes": allocation})
        # Deliberately inconsistent historical aggregate totals must never be added.
        value = {"schema": "project-cache-exact-v1", "project": str(self.project),
                 "root_identity": PROFILE.identity(os.lstat(self.project)), "created_at": "2026-11-14T00:00:00+00:00",
                 "coverage": {"complete": True}, "largest_files": rows, "candidates": [],
                 "totals": {"logical_bytes": 999999999999},
                 "directory_totals": {"bogus": {"logical_bytes": 999999999999}}}
        source = self.reports / "prior-scan.json"
        source.write_text(json.dumps(value), encoding="utf-8")
        return source, rows

    def test_mixed_ecosystems_are_detected_without_running_project_code(self):
        marker = "NEVER_EXECUTE_PROJECT_SCRIPT"
        self.put("package.json", json.dumps({"packageManager": "pnpm@9.0.0", "dependencies": {
            "next": "1", "vite": "1", "remotion": "1", "@playwright/test": "1", "cypress": "1"},
            "scripts": {"clean": marker + " " + str(self.area / "executed-marker")}}))
        for relative, contents in {
            "pyproject.toml": '[tool.uv]\n[tool.poetry]\n[project]\ndependencies=["pandas"]\n',
            "Cargo.toml": '[package]\nname="fictional"\n', "go.mod": "module fictional.test/project\ngo 1.21\n",
            "pom.xml": "<project/>", "android/build.gradle": "plugins {}", "CMakeLists.txt": "project(fictional)",
            "app.csproj": "<Project/>", "pubspec.yaml": "dependencies:\n  flutter:\n    sdk: flutter\n",
            "ios/Fictional.xcodeproj/project.pbxproj": "PRIVATE_XCODE_BODY_NOT_NEEDED",
        }.items():
            self.put(relative, contents)
        report, output = self.cli()
        names = {item["name"] for item in report["ecosystems"]}
        expected = {"Node.js", "Node/pnpm", "Next.js", "Vite", "Remotion", "Playwright", "Cypress", "Python/uv",
                    "Python/Poetry", "Rust/Cargo", "Go", "Java/Maven", "Java/Gradle", "Android", "C/C++/CMake", ".NET", "Flutter", "Xcode/Apple"}
        self.assertTrue(expected <= names, expected - names)
        self.assertEqual(report["commands_executed"], [])
        self.assertFalse((self.area / "executed-marker").exists())
        rendered = output.read_text(encoding="utf-8") + output.with_suffix(".md").read_text(encoding="utf-8")
        self.assertNotIn(marker, rendered)
        self.assertNotIn("PRIVATE_XCODE_BODY_NOT_NEEDED", rendered)

    def test_protected_large_directories_are_measured_not_pruned(self):
        self.put("package.json", '{"dependencies":{"next":"1"}}')
        fixtures = {"node_modules/dependency.bin": 12001, ".venv/Lib/site-packages/library.bin": 11003,
                    "target/debug/program.bin": 10007, "build/deliverable.bin": 9001,
                    ".git/objects/example.pack": 8009, ".next/cache/webpack/cache.bin": 7001,
                    ".codex/sessions/fictional.jsonl": 6007}
        for relative, size in fixtures.items():
            self.put(relative, b"x" * size)
        report, _ = self.cli()
        self.assertEqual(report["project_measurement"]["logical_bytes"], self.logical_size())
        self.assertEqual(sum(node["measurement"]["logical_bytes"] for node in report["nodes"] if node["scope"] == "project"), self.logical_size())
        for category in ("dependencies", "build_outputs", "version_control", "state_and_history"):
            self.assertGreater(sum(node["measurement"]["logical_bytes"] for node in report["nodes"] if node["category"] == category), 0, category)
        self.assertTrue(all(node["ownership"] == "unknown" for node in report["nodes"]))
        self.assertTrue(all(node["protection"] == "protected" for node in report["nodes"]))
        self.assertIsNone(report["execution_boundary"]["releasable_bytes"])

    def test_dependency_and_vendor_manifests_do_not_become_project_stacks(self):
        self.put("package.json", '{"dependencies":{"vite":"1"}}')
        self.put("node_modules/foreign/package.json", '{"dependencies":{"nuxt":"1","cypress":"1"}}')
        self.put("vendor/foreign/Cargo.toml", '[package]\nname="foreign"\n')
        report, _ = self.cli()
        names = {item["name"] for item in report["ecosystems"]}
        self.assertIn("Vite", names)
        self.assertNotIn("Nuxt", names)
        self.assertNotIn("Cypress", names)
        self.assertNotIn("Rust/Cargo", names)
        self.assertEqual(report["project_measurement"]["logical_bytes"], self.logical_size())

    def test_no_manifest_project_still_measures_unknown_files(self):
        self.put("unclassified/payload.bin", b"unknown" * 137)
        report, _ = self.cli()
        self.assertEqual(report["ecosystems"], [])
        self.assertEqual(report["project_measurement"]["logical_bytes"], self.logical_size())
        self.assertTrue(report["nodes"])
        self.assertTrue(all(node["action_support"]["executor"] is None for node in report["nodes"]))

    def test_related_root_is_separate_unknown_ownership_and_no_release_promise(self):
        self.put("payload.bin", b"p" * 101)
        related = self.area / "specific-related-output"
        self.put("kept.bin", b"r" * 3007, root=related)
        report, _ = self.cli("--related-root", related)
        self.assertEqual(report["project_measurement"]["logical_bytes"], 101)
        self.assertEqual(report["related_root_measurement_excluding_project_hardlink_duplicates"]["logical_bytes"], 3007)
        self.assertEqual(len(report["related_roots"]), 1)
        self.assertEqual(report["related_roots"][0]["ownership"], "unknown")
        external_nodes = [node for node in report["nodes"] if node["scope"] != "project"]
        self.assertTrue(external_nodes)
        self.assertTrue(all(node["action_support"]["status"] == "evidence_only" for node in external_nodes))
        self.assertFalse(report["coverage"]["complete"])
        self.assertFalse(report["execution_boundary"]["profile_grants_action_authority"])
        self.assertIsNone(report["execution_boundary"]["releasable_bytes"])

    def test_file_budget_reports_partial_coverage(self):
        for number in range(8):
            self.put(f"payload-{number}.bin", b"x" * 17)
        report, _ = self.cli("--max-files", 2)
        self.assertEqual(report["project_measurement"]["files"], 2)
        self.assertLess(report["project_measurement"]["logical_bytes"], self.logical_size())
        self.assertTrue(report["coverage"]["limit_hit"])
        self.assertFalse(report["coverage"]["project_traversal_complete"])
        self.assertGreater(report["coverage"]["gap_count"], 0)
        self.assertTrue(report["gaps"])

    def test_configuration_byte_budget_does_not_inflate_claims(self):
        self.put("package.json", '{"dependencies":{"next":"1"}}')
        report, _ = self.cli("--max-config-bytes", 1)
        self.assertLessEqual(report["coverage"]["config_bytes_read"], 1)
        names = {item["name"] for item in report["ecosystems"]}
        self.assertIn("Node.js", names)
        self.assertNotIn("Next.js", names)
        self.assertTrue(report["gaps"])

    def test_report_inside_project_is_refused_without_creating_files(self):
        output = self.project / "forbidden-report.json"
        self.cli(output=output, ok=False)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".md").exists())
        self.assertEqual(list(self.project.iterdir()), [])

    def test_existing_json_or_markdown_is_not_overwritten(self):
        for suffix in (".json", ".md"):
            with self.subTest(suffix=suffix):
                output = self.reports / ("existing-" + suffix[1:] + ".json")
                existing = output.with_suffix(suffix)
                existing.write_bytes(b"retained exact report bytes")
                self.cli(output=output, ok=False)
                self.assertEqual(existing.read_bytes(), b"retained exact report bytes")
                other = output.with_suffix(".md" if suffix == ".json" else ".json")
                self.assertFalse(other.exists())

    def test_report_inside_related_root_is_refused_before_writing(self):
        related = self.area / "specific-related-output"
        related.mkdir()
        output = related / "forbidden-report.json"
        self.cli("--related-root", related, output=output, ok=False)
        self.assertEqual(list(related.iterdir()), [])

    def test_sensitive_scan_inputs_are_rejected_before_content_reader(self):
        examples = [self.area / "auth.json", self.area / ".env", self.area / "api-token.json",
                    self.area / "sessions" / "scan.json", self.codex / "scan.json", self.sqlite / "scan.json"]
        for path in examples:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"PRIVATE_BODY":"must never be read"}', encoding="utf-8")
        with mock.patch.dict(os.environ, dict(self.env, CODEX_SQLITE_HOME=str(self.sqlite)), clear=True):
            for path in examples:
                with self.subTest(path=path.name), mock.patch.object(PROFILE, "read_bounded", side_effect=AssertionError("sensitive body read")) as reader:
                    with self.assertRaises(PROFILE.ProfileError):
                        self.profiler().load_scan(path)
                    reader.assert_not_called()

    def test_hardlink_alias_is_refused_before_os_read(self):
        path = self.put("renamed-inventory.json", b"private body")
        real_plain = PROFILE.plain
        def nlink_two(candidate, directory=None):
            result = real_plain(candidate, directory)
            if PROFILE.key(candidate) == PROFILE.key(path):
                return SimpleNamespace(st_nlink=2, st_ino=result.st_ino)
            return result
        with mock.patch.object(PROFILE, "plain", side_effect=nlink_two), mock.patch.object(PROFILE.os, "read", side_effect=AssertionError("body read")) as reader:
            with self.assertRaises(PROFILE.ProfileError):
                PROFILE.read_bounded(path, 1024)
            reader.assert_not_called()

    def test_exact_allocation_records_are_reused_without_adding_old_totals(self):
        paths = [self.put("payload-a.bin", b"a" * 1234), self.put("payload-b.bin", b"b" * 2345)]
        source, rows = self.scan_fixture(paths)
        report, _ = self.cli("--scan-json", source)
        self.assertEqual(report["source_scan_reuse"]["matched_allocation_records_reused"], 2)
        self.assertFalse(report["source_scan_reuse"]["aggregate_totals_added"])
        self.assertEqual(report["project_measurement"]["logical_bytes"], 3579)
        self.assertEqual(report["project_measurement"]["allocated_bytes_known"], sum(row["allocated_bytes"] for row in rows))
        self.assertEqual(report["project_measurement"]["unique_files"], 2)

    def test_changed_file_does_not_reuse_stale_allocation_record(self):
        paths = [self.put("payload-a.bin", b"a" * 1234), self.put("payload-b.bin", b"b" * 2345)]
        source, _ = self.scan_fixture(paths)
        paths[0].write_bytes(b"changed payload now has a different length")
        report, _ = self.cli("--scan-json", source)
        self.assertEqual(report["source_scan_reuse"]["matched_allocation_records_reused"], 1)
        self.assertEqual(report["project_measurement"]["logical_bytes"], self.logical_size())

    def test_shared_cache_candidates_stay_unmeasured_and_unexecuted(self):
        self.put("package.json", '{"dependencies":{"playwright":"1"}}')
        self.put("pyproject.toml", "[tool.uv]\n")
        for variable in ("npm_config_cache", "PIP_CACHE_DIR", "UV_CACHE_DIR", "PLAYWRIGHT_BROWSERS_PATH"):
            self.put("cache-content.bin", b"c" * 9007, root=Path(self.env[variable]))
        report, _ = self.cli()
        candidates = [entry for entry in report["external_candidates"] if entry.get("path") in {
            str(Path(self.env[variable])) for variable in ("npm_config_cache", "PIP_CACHE_DIR", "UV_CACHE_DIR", "PLAYWRIGHT_BROWSERS_PATH")}]
        self.assertEqual(len(candidates), 4)
        for entry in candidates:
            self.assertEqual(entry["existence"], "present")
            self.assertEqual(entry["ownership"], "shared")
            self.assertIsNone(entry["size"])
            self.assertFalse(entry["recursive_scan"])
            self.assertEqual(entry["action_support"], "evidence_only")
        self.assertEqual(report["project_measurement"]["logical_bytes"], self.logical_size())
        self.assertEqual(report["related_root_measurement_excluding_project_hardlink_duplicates"]["logical_bytes"], 0)
        self.assertEqual(report["commands_executed"], [])
        self.assertTrue(all(not probe["executed"] for probe in report["native_cache_probes"]))

    def test_sensitive_and_dependency_bodies_are_not_configuration_inputs(self):
        self.put("package.json", '{"dependencies":{"vite":"1"}}')
        self.put(".env", "PRIVATE_ENV_BODY")
        self.put(".codex/sessions/package.json", "PRIVATE_SESSION_BODY")
        self.put("node_modules/private/package.json", "PRIVATE_DEPENDENCY_BODY")
        self.put("vendor/private/Cargo.toml", "PRIVATE_VENDOR_BODY")
        self.put(".git/config", "PRIVATE_GIT_CONFIG_BODY")
        observed = []
        original_reader = PROFILE.read_bounded
        def tracked(path, limit):
            observed.append(Path(path).relative_to(self.project).as_posix())
            return original_reader(path, limit)
        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(PROFILE, "read_bounded", side_effect=tracked):
            profiler = self.profiler()
            profiler.walk(self.project, "project")
            profiler.parse_configs()
        self.assertEqual(observed, ["package.json"])
        self.assertEqual(sum(node["measurement"]["logical_bytes"] for node in profiler.nodes.values()), self.logical_size())

    def test_managed_and_state_roots_are_refused_as_projects(self):
        for relative in (".git", ".venv", "node_modules", ".agents", ".codex", "sessions"):
            target = self.project / relative
            target.mkdir()
            with self.subTest(relative=relative):
                with mock.patch.dict(os.environ, self.env, clear=True), self.assertRaises(PROFILE.ProfileError):
                    PROFILE.selected_root(target, self.codex)


if __name__ == "__main__":
    print("Isolated profiler fixtures retained at: " + str(RUN), flush=True)
    unittest.main(argv=[sys.argv[0], *remaining])
