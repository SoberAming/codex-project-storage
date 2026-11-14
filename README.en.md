# Codex Project Storage

[![CI](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml/badge.svg)](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml)

[中文](README.md) · English

Understand why a Codex project's disk is filling up, then choose what to delete, move, or retain. The agent investigates technical details; the user chooses the outcome.

This skill works from the **volume that actually contains the selected project**. It does not assume a system drive, a second partition, an external-drive letter, or a fixed destination.

## What it helps with

- Growing dependencies, environments, build outputs, worktrees, screenshots, recordings, and task artifacts.
- Code, web, video, design, research, and data projects, including folders without a standard project manifest.
- Deciding whether an inactive output should be removed, retained, or archived elsewhere.
- Explaining shared caches and external project data without claiming that the current project owns them.

The analysis recognizes clues from Node, Python, Rust, Go, Java, .NET, C/C++, mobile, browser-testing, and media workflows. Recognition does not grant permission to delete a toolchain's files. Unknown data is reported and retained while the agent investigates.

## How a task proceeds

1. Identify the project, its actual volume, available capacity, and any user-selected destination.
2. Explain the main space consumers, their producers, ownership, references, and reconstruction or retrieval requirements.
3. Recommend deletion, migration, or a combination. Explain the expected benefit, usage impact, retained data, and recovery or retrieval method.
4. Execute only the authorized, supported scope and verify the result. Stop if content, identities, membership, volume, evidence, or usage conditions change.

Analysis-only requests remain read-only. Existing authorization for a clearly defined action is respected; users do not need to choose file IDs or enter plan hashes.

## Supported execution routes

| Data | Current route |
| --- | --- |
| Strict CPython bytecode caches with retained source | Exact-file cleanup, with runtime, age, identity, and content checks |
| Deterministic, locally reconstructible media intermediates | Exact-file deletion while retaining inputs and production evidence |
| Rigorously proven project-exclusive pip caches | Native pip purge for supported versions and evidence contracts only |
| Valuable, inactive artifacts | Copy, full verification, usage acceptance, then release the source |
| Redundant inactive artifacts with a usable retained copy | Verify the retained copy and purpose before releasing the redundant files |
| Other build systems, shared caches, dependencies, and worktrees | Diagnosis and tool- or host-specific proposals; no generic directory deletion |

Native adapters accept separately qualified project-exclusive pip **25.0.1 or 26.1.1** caches and npm **10.9.2** content caches. uv, shared/default caches and unsupported versions remain advice-only. Existing caches cannot qualify by adding a marker or fabricating a production receipt after the fact. See the [npm contract](references/npm-cache.md).

Version 1.4 adds a separate [disposable test-data lifecycle](references/retired-runtime.md) for positively proven synthetic PostgreSQL test data. It retains producers, inputs, logs and results; it never clears a whole runtime directory or business database. The profile now ranks major occupancy groups for further evidence review. A small bytecode plan must not conceal large unqualified test or cache stores. Occupancy, qualified planned release, conditional potential and actual release are reported separately. See [upgrade notes](docs/RELEASE_NOTES_v1.4.0.md).

Reconstructible intermediates do not need a second retained copy of the same output. They do need retained inputs, genuine production evidence, available reconstruction dependencies, and a supported deterministic operation. Unique AI outputs, delivery files, visual baselines, acceptance evidence, and recovery material remain protected.

## Install

Requirements: Python 3.10 or newer and an agent that can load local skills and run the included tools. Runtime helpers use the Python standard library. The native pip route additionally requires an already-installed, trusted, supported pip version; the skill does not install one automatically.

Place the complete `codex-project-storage` folder in the skill directory supported by your host. `SKILL.md` must be directly inside that folder.

Common Codex discovery locations include:

| Scope | Location |
| --- | --- |
| User | `~/.agents/skills/codex-project-storage` |
| Project | `<project>/.agents/skills/codex-project-storage` |
| Hosts that explicitly use the older root | `~/.codex/skills/codex-project-storage` |

Use the location your host actually supports, keep one active copy of this skill, and do not change `CODEX_HOME` to install it. Download and inspect the release archive or source before copying it. This project does not require a remote shell installer.

## Use it in a project

Open the intended project and ask:

```text
$codex-project-storage Optimize the disk that contains this project. Investigate the main space consumers, their growth and value. Recommend deletion, migration, or a combination, explaining the benefit, impact, and retained data. Handle technical judgment yourself; let me decide which outcome to adopt. Protect source, original assets, sessions, indexes, and recovery material.
```

You can instead ask for **analysis only**, name an available archive location, or specify a free-space goal. None of those choices authorizes cleanup across an entire disk.

## Protection and measurement

Sessions, indexes, SQLite files and sidecars, credentials, source, original assets, dependencies, unique generated results, delivery and acceptance records, and recovery data are protected by default. Configured Codex state roots receive additional boundary checks. Active worktree cleanup must follow the current host's supported management route and preserve needed ignored files.

A name such as `cache`, a large size, old modification time, or Git-ignore status is not proof that something is disposable. The tools do not automatically terminate applications, elevate privileges, alter configuration, create compatibility links, or schedule background cleanup.

Moving within the same volume does not release that volume's space. A copy that retains its source is reported as a copy, not as reclaimed capacity. Logical file sizes, known allocated sizes, and observed volume-free changes are reported separately; links, compression, snapshots, shared blocks, and other writers can affect the result.

No tool can infer every private format, prove every external reference, or eliminate concurrency risks. Unknown ownership or inadequate evidence means retention. Read the mode-specific rules before invoking an executor.

## Validation status

The current 1.4 runtime source revision, `b75a54ccd85f8cb55561bc84c6db1eba89877f15`, passed the [four-job GitHub Actions run (43557649569)](https://github.com/SoberAming/codex-project-storage/actions/runs/43557649569); its evidence summary reports `qualified=true`. All four jobs used Node 22.14.0 / npm 10.9.2:

| Hosted environment | Python | Tests | Passed | Platform-specific skips |
| --- | --- | --- | --- | --- |
| Windows X64 | 3.10.11 | 258 | 256 | 2 |
| Windows X64 | 3.13.17 | 258 | 256 | 2 |
| macOS ARM64, `macos26` | 3.10.11 | 258 | 254 | 4 |
| macOS ARM64, `macos26` | 3.13.17 | 258 | 254 | 4 |

Windows skips two native Apple ACL tests. macOS skips three Windows PowerShell / CIM / process checks and one Windows mandatory sharing-denial test. Each job also completed real CLI executions for native npm 10.9.2 cleanup in an isolated cache and retirement of a synthetic PostgreSQL test-directory layout in a fictional project. No real user cache was touched, no database was connected, and no project code was executed.

The failed [initial 1.4 matrix run (43556855654)](https://github.com/SoberAming/codex-project-storage/actions/runs/43556855654) remains available. A narrow compatibility fix allows verification to continue when npm's builtin configuration file, `npm/npmrc`, is explicitly absent in the installation layout. It does not broaden the exclusive-cache contract or the CLI execution scope.

These results qualify only the named revision in the listed hosted environments and isolated fixtures. **Personal Mac devices, external drives, all APFS layouts, and actual business workflows have not been accepted; neither has a real PostgreSQL server.** Every release tag must still bind its exact revision and pass the release gate. A later final documentation commit or any other new revision needs its own four-job run and cannot inherit this CI result. Local installation, GitHub publication, remote CI, and actual business cleanup remain separate evidence states.

Historical evidence: an earlier local 1.4 candidate completed 246 checks on Windows / Python 3.13.13, with 237 passed and 9 skipped for platform or fixture-filesystem link limitations, plus 32 independent targeted review groups. Those are not the current matrix counts. The historical v1.3 core run executed 116 isolated-fixture tests, with 114 passed and 2 skipped because the fixture filesystem could not create the required links; separate checks covered an isolated pip-cache purge and a frozen-version fictional-project cleanup. See the [upgrade notes](docs/RELEASE_NOTES_v1.4.0.md) and [verification record](references/verification.json).

## Documentation and contributions

- [Installation](docs/INSTALLATION.md) and [quick start](docs/QUICKSTART.md)
- [Skill instructions](SKILL.md)
- [Architecture](docs/ARCHITECTURE.md), [safety](docs/SAFETY.md), and [compatibility](docs/COMPATIBILITY.md)
- [Project types and routing](references/project-types.md)
- [Operations](references/operations.md)
- [Generated intermediates](references/generated-artifacts.md)
- [Native cache contract](references/native-cache.md)
- [Migration and redundant-copy release](references/relocation.md)
- [Codex state and worktrees](references/codex-state.md)
- [Contributing](CONTRIBUTING.md), [support](SUPPORT.md), and [security reporting](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Release process](docs/RELEASING.md) and [roadmap](docs/ROADMAP.md)

See [LICENSE](LICENSE) for the distribution terms. Review the repository's current license before redistributing. Codex is an OpenAI product name; this is an independent community project and does not imply OpenAI endorsement.
