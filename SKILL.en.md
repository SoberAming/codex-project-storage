# Agent Development Artifact Cleanup

[Chinese instructions](SKILL.md) · [English quickstart](docs/QUICKSTART.en.md) · [English overview](README.en.md)

This is the English companion to the installed `SKILL.md` entrypoint. Install the complete folder and keep `SKILL.md` in place. Both documents describe the same tools, scope and protection rules; this translation grants no additional permissions.

Use this skill to investigate and clean up **verified obsolete or redundant artifacts produced during Agent development and task execution**. Codex, WorkBuddy, Claude Code or Kimi Code may initiate a task; npm, a browser, a test runner or a renderer may actually write the files. Identify the real producer and current consumers before choosing an operation.

The selected project or task defines the starting scope. Ordinary document organization and moving useful business assets are separate decisions. Delete supported, verified disposable artifacts; migrate valuable inactive artifacts only when that serves the user's goal. Retain anything whose origin, role or current use remains unresolved.

## Let the user decide the outcome

Recommend one concrete plan, with at most two alternatives when the tradeoff matters. Explain the evidence for disposal, exact scope, source volume, qualified benefit, retained results and consequences. For migration, identify the destination, retrieval method and disconnection impact. The Agent manages technical review, plan IDs and digests; users should not have to classify indexes or choose individual file IDs.

- Delete supported regenerable caches or intermediate artifacts after their route qualifies them.
- Release a redundant inactive copy only after verifying a complete, usable retained copy.
- Migrate valuable inactive artifacts to a user-selected, qualified destination after checking consumers.
- Protect source, original assets, unique generated results, deliverables, acceptance evidence, baselines, business/state databases, credentials, dependency environments, sessions, indexes and recovery material by default. Synthetic test data needs its own positive lifecycle evidence before retirement.

Age, size, a Git ignore rule or a name containing `temp`, `cache` or `old` does not prove that a file is disposable. Continue within an already approved scope without repeatedly requesting the same approval. Analysis-only requests remain read-only. Ask only for a missing business preference that changes the outcome; investigate technical facts yourself.

## 1. Establish the project and actual volume

Read applicable `AGENTS.md` files and project guidance. Reconcile the host project path, current directory and Git root; do not treat a parent containing multiple projects as one project. Inspect the relevant script's `--help` before use. Script paths below are relative to this skill folder.

```text
python ABS_SKILL/scripts/volume_advisor.py inspect --project ABS_PROJECT --output ABS_REPORT.json
```

Add `--target ABS_TARGET` or `--goal-free-gib NUMBER` when the user supplied a destination or free-space goal. Write reports outside the project on a healthy volume with room. Do not silently write them back to a nearly full source volume.

Drive letters and paths do not establish physical storage or volume boundaries. Moving within one volume does not free that volume. Network storage, cloud placeholders, read-only targets and unknown filesystem capabilities need a separate plan.

## 2. Explain the major occupancy before selecting cleanup

```text
python ABS_SKILL/scripts/project_profiler.py inspect --project ABS_PROJECT --output ABS_PROFILE.json
```

The profiler uses bounded metadata traversal and a small allowlist of configuration reads. It measures dependencies, Git, environments and build directories without running project scripts, installs or builds, or reading session, credential or customer-document bodies. Unknown directories still appear as unknown occupancy. See [project types and routes](references/project-types.md).

An explicitly related external directory can be inspected with `--related-root ABS_PATH`; permission to inspect metadata is not permission to delete. Shared caches are discovered rather than recursively measured by default. Keep project-local, related, shared and unknown ownership separate.

Read `agent_residue_review` and `review_priorities`. Investigate the major sources before presenting a tiny bytecode-only plan. For each major group, explain its producer, purpose, ownership, logical size, known allocation, duplicate accounting, protection and missing evidence. Follow the real producer, run relationship, completion state, retained results, current references and activity. Names and extensions are clues only.

Distinguish **current occupancy / qualified plan benefit / potential pending evidence / actual release**. Only qualified plans contribute to the promised benefit. With no execution, actual release is zero. A copy that leaves the source in place also releases zero. One snapshot explains size, not growth; growth needs comparable scope, policy and coverage across observations.

`coverage.complete=false` can describe incomplete semantic/ownership review; inspect `project_traversal_complete` separately. A complete, independently verified subtree may proceed through its dedicated executor even while the overall project remains incomplete. Do not compare a narrow cache scan with a comprehensive profile and call the difference growth.

If safe project-local benefit falls short, state the shortfall and propose a bounded related-directory or volume investigation. Do not expand deletion scope to meet a number. Databases and environments deserve investigation, but unknown historic data does not become disposable because an Agent writes a new declaration.

### Resume large scans and protect shared files precisely

When the overview reaches its traversal or attribution budget, or merges directories into category buckets, use [the persistent inventory](references/batched-inventory.md). `project_batches.py` stores exact task/artifact paths, identities and complete/pending/error progress outside the project. Resume bounded batches instead of restarting the whole scan. Build-focused scans can exclude unrelated dependencies and assets, with their sizes explicitly unknown.

A completed unit can move to qualification while other units remain pending. An overview bucket is not an executable cleanup unit. `independent_review_bytes` is a review priority, not reclaimable space. Retain shared files individually and investigate independent files beside them. Do not follow junctions or count their targets again as source-volume occupancy. Stop immediately on CRC/EIO or other fatal storage errors.

## 3. Choose an evidence-backed route

| Artifact | Executor or route | Qualification and protection |
| --- | --- | --- |
| Inactive isolated Next builds | `build_artifact_guard.py` | [Current-state build review](references/historical-builds.md); genuine producer/source/build identity, retained current/rollback apps, reviewed configuration, native activity and loopback static proof. Supports selected compiled files and webpack packs, including the corresponding `.next/dev` layout. |
| Disposable captures, recordings, traces, download fragments and supported scratch from completed tasks | `agent_artifact_guard.py` | [Task-artifact contract](references/agent-artifacts.md); genuine producer and terminal evidence, retained results, exact supported unit, no current use, complete members and hashes. No blanket 48-hour wait. |
| Strict CPython caches with source present | `storage_guard.py` | Interpreter format, age, identity and protection checks under the [operation rules](references/operations.md). |
| Locally reproducible media intermediates | `generated_artifact_guard.py` | Retained inputs and producer basis, supported deterministic recipe, no unique AI output or external-service dependency; [dedicated rules](references/generated-artifacts.md). |
| Project-exclusive pip or npm caches | `native_cache_guard.py` / `npm_cache_guard.py` | Separately supported versions, genuine producer/ownership evidence and fixed trusted tools; [pip](references/native-cache.md) and [npm](references/npm-cache.md) contracts remain independent. |
| Completed disposable synthetic PostgreSQL test data | `retired_runtime_guard.py` | [Positive lifecycle evidence](references/retired-runtime.md), retained generator/inputs/logs/results, exact inactive data scope and current activity checks. No business database or recovery-chain retirement. |
| Valuable inactive artifacts or verified redundant copies | `relocation_guard.py` | [Migration contract](references/relocation.md); complete verification, use acceptance, then source release. |
| Host-managed completed worktrees | Current host's supported management | Establish the exact object and retained scope, preserve necessary ignored files, and use the host facility. Do not substitute raw Git-directory deletion. |
| Other build systems, shared caches, models, dependencies, browser profiles or Git objects | Investigate and recommend a tool-specific plan | No generic deletion permission. A native clean command may run project code or affect other projects. |
| Sessions, indexes, state SQLite, authentication and recovery points | Protect and diagnose | Do not truncate history, delete raw state or modify databases. Supported migration/retention needs a separate plan. |

### Completed task residue

Read the task-artifact schema before planning. Captures can be acceptance evidence; recordings can be unique results; logs can support recovery. Bind real producer and completion evidence rather than creating fictional historic records. Do not empty an entire `outputs`, `.runtime`, download root or Agent home.

New tasks can record their run relationship from creation and organize artifacts at completion. Calling this skill does not itself authorize changing a producer or scheduling background cleanup.

### Historic builds without terminal records

Use the build executor's explicit `current-state-reconstruction` route only for its supported isolated Next candidates. Verify adjacent `package.json`, retained independent source/results, the genuine `BUILD_ID`, current launch/configuration inputs, retained applications, native process identity and static content served by active previews. Do not present a current review as historical completion evidence.

Only selected independent compiled code and recognized webpack cache files qualify. Preserve source, formal releases, rollback/recovery material, build identity/manifests, prerendered content, unknown data and shared files. The inactive candidate needs rebuilding before it can be served again. Unknown previews and selected active build IDs, including aliases, block the operation. This route does not relax the separate task-artifact or database contracts.

### Native caches and test environments

Never fabricate provenance to qualify an existing cache, silently install cleanup tools, or invoke project-defined clean hooks. Keep unsupported versions, shared ownership and unknown layouts. npm's fixed native `--force` argument does not override scope, locks or authorization.

Retire only the synthetic PostgreSQL `data/` scope covered by its lifecycle contract, not a whole environment or business `pgdata`. A UUID, test environment variable or missing PID file is insufficient evidence. Preserve logs, outputs, production basis and recovery data. Do not require a duplicate same-size backup of genuinely disposable data merely to remove it. A cold file copy is not database backup or restore acceptance.

### Migration and worktrees

Copy and fully verify, preserve the source, confirm usability, then release the source. Reuse the verification/release stages when a retained copy already exists. Current authorization can cover these steps; do not ask again for the same scope.

Compatibility links, changed application settings, active engineering data, sessions and dependencies require a separately justified plan. This version does not automatically create junctions or reconfigure applications. Read [state and worktree boundaries](references/codex-state.md).

## 4. Validate the result and stop safely

Changed membership, identity, content, producer evidence, consumers, activity or volume conditions stop the operation. Never force locks, kill user processes, elevate privileges or blindly replay a failed apply. Reconcile the original receipt/claim first. CRC, bad-block or EIO evidence stops cleanup and large hashing/compression.

Windows handles and macOS advisory locks provide different guarantees. Advisory locks do not prevent noncooperating writers. Verify inactivity before passing `--confirm-idle`; a missing lock file does not prove inactivity. Future process starts and future external-drive connectivity cannot be guaranteed.

Check retained data, necessary project operations and source-volume free space. Report deleted logical bytes, known allocation, migrated content, whether originals remain, measured free-space change and incomplete work separately. Hardlinks, sparse/compressed files, APFS clones/snapshots and concurrent writes can make these numbers differ. Do not count copying, same-volume relocation or a same-volume recycle bin as space reclaimed.

## 5. Trace repeated growth

Identify actual write paths and producers. Recommend bounded task outputs, separation of inputs/intermediates/deliverables/recovery material, and cleanup at genuine task completion. Summarize logs before reading large excerpts; avoid repeatedly injecting full logs or base64 into sessions. Do not truncate existing history.

When a producer repeatedly creates environments but only stops them afterward, propose a narrow prospective fix: record run ID, exact artifact root, producer/input version, retained results and terminal state from creation onward. Record no credentials or customer bodies. New records establish future facts, not old history.

Recommend configuration changes separately from execution. Do not automatically change production settings, disable history, schedule cleanup or treat `history.max_bytes` as a universal session/database limit. See [storage mechanisms](references/storage-map.md), [design references](references/mature-patterns.md), [verification identities](references/verification.json) and [compatibility limits](docs/COMPATIBILITY.md).
