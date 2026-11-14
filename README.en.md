# Codex Project Storage

[![CI](https://github.com/YiMingchen111/codex-project-storage/actions/workflows/ci.yml/badge.svg)](https://github.com/YiMingchen111/codex-project-storage/actions/workflows/ci.yml)

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

The native cache adapter currently accepts only qualifying pip **25.0.1 or 26.1.1** caches. uv and npm are advice-only. Existing caches cannot qualify by adding a marker or fabricating a production receipt after the fact.

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

The v1.3.0 Windows regression run executed **116 tests: 114 passed and 2 were explicitly skipped** because the fixture filesystem could not create the required links. Independent checks included a new isolated pip-cache purge and a frozen-version fictional-project cleanup with retained-file verification.

The public version runs isolated fixtures in GitHub-hosted Windows/macOS and Python 3.10/3.13 environments. Check the CI link above for the actual result and revision. The first Mac run exposed an empty-ACL compatibility error; that failure is retained, and a narrow fix and regression tests were added. **Personal Mac devices, external drives, and actual business workflows have not been accepted.** Hosted fixture results do not establish all-filesystem support. Exact component hashes, historical evidence, and limitations are in [the verification record](references/verification.json). Release-tool and ACL tests are separate from the original 116-test record.

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
