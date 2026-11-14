# 1.6 — Resumable inventory and inactive build cleanup

[中文](RELEASE_NOTES_v1.6.0.md) · [English overview](../README.en.md) · [English quickstart](QUICKSTART.en.md)

Large projects can consume substantial storage while a cleanup tool produces only a tiny cache plan. An overview may hit its scan budget, a directory may mix independent files with hardlinks, or an old task may lack reliable terminal records. Version 1.6 adds executable tools for those cases, while keeping disposal qualification separate from occupancy.

## Persistent project inventory

`project_batches.py` stores a metadata inventory outside the project. Discovery, bounded scan batches and reporting are separate commands. Later batches resume a persistent queue rather than restarting the entire project. Exact paths and file identities survive beyond the overview's attribution budget.

Each selected unit has a complete, pending, scanning or error state. A complete unit can enter a dedicated cleanup review while others remain pending. Changed directory identity or membership stops the affected unit; fatal storage errors stop the operation. Build-focused exclusions remain explicitly unmeasured.

## Selective inactive Next build cleanup

`build_artifact_guard.py` provides `plan` and `apply` for supported isolated inactive Next candidates. It verifies adjacent build configuration, genuine build ID, retained source/results, reviewed launch/configuration inputs, retained current/rollback apps and native activity. Running previews must be bound to their process creation identity and the exact static build content served over loopback.

Supported files include independently generated compiled code and recognized webpack packs, including corresponding `.next/dev` development outputs. Shared files are protected individually. Source, build IDs/manifests, prerendered content, unknown data, media, databases, sessions, indexes and recovery material stay in place. A cleaned inactive candidate needs rebuilding before it can be served again.

Where old terminal records are unavailable, this separate policy uses an explicit current-state review. It does not fabricate historic completion or loosen the independent requirements for general task artifacts or database retirement. Reviewed references and visible activity do not prove the absence of every possible consumer.

## Validation and distribution

The Windows/macOS × Python 3.10/3.13 workflow runs 15 suites, including all earlier routes, persistent inventory, exact CLI cleanup, live-writer refusal, changed-membership/evidence rejection and protected-state sentinels. Verify the [exact source commit's checks](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml); an older green run does not qualify a new revision.

Real-project maintainer validation produced reviewable plans only. It did not delete business-project files or Agent state. Isolated fixture success does not certify every Agent host, personal external drive or all APFS clone/snapshot semantics. Logical deletion and measured free-space change remain separate figures.

The distribution includes the [English skill instructions](../SKILL.en.md), [quickstart](QUICKSTART.en.md) and this release note alongside the Chinese material. Both languages describe the same runtime implementation and protection rules. A source update on `main` does not itself create a version tag or GitHub Release.

## Using the new routes

Ask the Agent to resume scans in bounded batches, prioritize inactive historic builds, retain shared files individually, and provide an exact proposal with qualified benefit and consequences. The Agent manages the inventory, evidence, plans and digests; the user chooses the scope.

See [persistent inventory mechanics](../references/batched-inventory.md) and [historic build qualification](../references/historical-builds.md). Do not replay an old plan across tool revisions or changed conditions. Read the current facts, generate a fresh plan and reconcile any existing apply claim before proceeding.
