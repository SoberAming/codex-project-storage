# Agent Development Artifact Cleanup · Codex Project Storage

[中文](README.md) · [Skill instructions](SKILL.en.md) · [Install and use](docs/QUICKSTART.en.md) · [1.6 release notes](docs/RELEASE_NOTES_v1.6.0.en.md)

**Reclaim storage from verified obsolete Agent development artifacts while keeping source, useful results, sessions and indexes intact.**

The task may have been initiated by Codex, WorkBuddy, Claude Code, Kimi Code or another Agent. The actual writer may be npm, a browser, test runner or renderer. Product names do not establish ownership or disposal eligibility. The selected project is the scope boundary, not a reason to archive ordinary business documents.

## 1.6 capabilities

- A [persistent metadata inventory](references/batched-inventory.md) resumes within bounded batches and retains exact paths and file identities. Completed units can proceed while other units remain pending or fail. Build-focused exclusions remain explicitly unmeasured.
- Shared files are retained individually; independent files in the same directory can still be reviewed. Overview aggregation is not treated as an executable cleanup unit.
- A separate [inactive Next build guard](references/historical-builds.md) verifies retained source, genuine build IDs, reviewed launch/configuration inputs and native/loopback runtime bindings. It selects independent compiled code and webpack cache files, including supported `.next/dev` outputs, while preserving shared files, prerendered content, manifests and unknown data. Reactivating that candidate requires a rebuild.
- Legacy builds use an explicit current-state review when historical terminal records are unavailable. No historical evidence is fabricated; other cleanup policies keep their own evidence requirements.

- A bounded metadata profiler exposes an additive `agent_residue_review` queue for scratch runs, failed-download fragments, captures/traces and testing/output clues. It reuses exclusive measurements and never converts names, age or size into deletion permission.
- The [task artifact guard](references/agent-artifacts.md) plans and precisely deletes supported disposable units of completed tasks. It binds real producer and terminal evidence, retained results, current references/activity, complete membership, identities and content.
- Recent completed tasks can qualify without a blanket 48-hour wait. Existing CPython, media and synthetic PostgreSQL routes retain their independent policies.
- State paths, sessions, indexes, source, originals, final outputs and recovery data remain protected. Custom discovered state locations can be explicitly protected without reading their bodies.
- Native pip/npm cleanup remains restricted to their separately verified exclusive caches and supported versions. Other tools and unknown layouts stay analysis-only.
- Migration is optional for valuable inactive artifacts, after full copy and use acceptance. Copying while retaining the source is not reclaimed space.

## Use

Requires Python 3.10+ and a host able to load local Skills and run the included scripts. Install the complete folder in the actual host-supported Skill location. The [English quickstart](docs/QUICKSTART.en.md) includes Windows/macOS installation, analysis and approval examples, migration choices and report interpretation.

```text
Use codex-project-storage to investigate obsolete artifacts from Agent development in this project: failed task scratch, captures and recordings, download fragments, previews, repeated test environments and caches. Verify the producer, run completion, retained results and current use. Recommend a concrete cleanup with benefits and consequences. Analyze only first; protect source, useful outputs, sessions and indexes.
```

After reviewing the exact proposal, authorize that scope. The agent manages internal plans and digests; the user does not need to choose file IDs. Codex supports `$codex-project-storage`; other hosts have different entry points.

## Delete or migrate?

| Finding | Recommended handling |
| --- | --- |
| Verified disposable artifacts supported by an executor | Propose exact deletion, with retained results and impact. |
| Valuable inactive results that the user wants to retain | Propose migration to a user-selected qualified destination; verify usability before source release. |
| Active, shared, unique or unresolved data | Retain and investigate. Shared files stay individually protected. |

Reports distinguish occupancy, potential pending evidence, qualified plan benefit and actual release. A copy that retains its source has reclaimed zero space. A free-space goal does not authorize broader deletion.

## English documentation

- [Skill instructions](SKILL.en.md): project scope, decision logic, supported routes, safeguards and recurring-growth investigation.
- [Quickstart](docs/QUICKSTART.en.md): installation and ready-to-use requests for analysis, large projects, approved cleanup and migration.
- [1.6 release notes](docs/RELEASE_NOTES_v1.6.0.en.md): executable improvements and validation boundaries.

The English documents accompany the existing `SKILL.md` entrypoint and use the same runtime implementation. Detailed route schemas remain in the linked reference files.

## Verification

CI runs Windows/macOS × Python 3.10/3.13 with isolated fixtures, real exact-cleanup CLIs, state-boundary tests and curated package builds. Verify the exact revision's [checks](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml), [compatibility notes](docs/COMPATIBILITY.md) and release evidence. Operating-system checks do not certify every Agent host, external drive or business workflow. macOS advisory locking cannot prevent noncooperating writes; verified inactivity remains required.

No project code, install, build, process termination or background cleanup is automatically performed. Unknown ownership, active references, changed members/content, unsupported state or storage errors stop the operation. A large or old file is not automatically disposable.

MIT licensed, independent of the Agent vendors. See [release notes](docs/RELEASE_NOTES_v1.6.0.en.md), [contributing](CONTRIBUTING.md) and [security](SECURITY.md).
