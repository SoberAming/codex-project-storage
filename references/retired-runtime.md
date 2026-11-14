# Retire a proven disposable synthetic PG run

Version 1.4.0 adds `scripts/retired_runtime_guard.py`. It is a separate exact
execution mode, not a relaxation of artifact relocation or database protection.
The first supported producer style is JavaScript/TypeScript using `randomUUID`,
fresh `initdb`, loopback PG, and `pg_ctl stop` in `finally`. Python/PowerShell
producers and other engines currently require a future reviewed adapter. The
ordinary-file/manifest mechanism is reusable; the current qualification rules
must not be advertised as supporting arbitrary test environments.

An old test cluster can be disposable without requiring a database backup first
when its complete data unit is positively established to contain only
rebuildable synthetic output. Business data, customer imports, active databases,
Codex state, restoration chains, and unique evidence remain protected.

## Agent review before the tool

Read the actual retained producer and synthetic generators/fixtures. Trace their
input chain, creation path, connection targets, and shutdown behavior. Establish
that the exact historical run was independently initialized and contains no
unique business or user input. Review the actual historical completion log and
preserve useful failure/success evidence. Review current project configuration
bindings, tasks, recovery instructions, and usage. Do not execute the producer,
tests, database commands, or project hooks to perform this review.

A directory name, old mtime, `NODE_ENV=test`, `PG_VERSION`, no `postmaster.pid`,
or a new JSON saying `is_test=true` is insufficient. Current producer code does
not by itself establish what an old run used. If historical source/input/run
association is missing, name the missing relationship. Keep the unit or propose
a separately reviewed retention migration; do not fabricate a completion receipt.

The tool checks real file hashes, exact quotations, producer/input references,
same-run completion location/UUID, current reference/activity facts, and complete
data membership. It cannot independently understand arbitrary program behavior
or authenticate who wrote a historical log. Agent semantic review and the user's
specific retirement decision remain necessary. Matching code words is a narrow
eligibility check, never proof that source behavior is harmless.

## Exact supported unit

The source must be exactly:

```text
.runtime/<family>-pg-<canonical-random-UUIDv4>/data
```

For example `.runtime/analytics-pg-01234567-89ab-4cde-8fab-0123456789ab/data`.
`.runtime/pgdata`, an entire `.runtime`, a business database, and a general
directory cannot be selected. Only ordinary PG 13+ initdb layouts are currently
supported. The explicit layout rejects unexpected notes, scripts, source,
credentials, recovery markers, nonempty tablespaces/replication slots/prepared
transaction directories, links, hardlinks, special files, or unsupported metadata.
Root PG configurations are checked as bounded text for credential/recovery or
external-archive settings. Binary database payload is only hashed as opaque
bytes; no SQL or database-content inspection occurs.

Unknown members block the whole unit. Never remove unknown files first merely
to make a unit qualify. Instead preserve and explain their role or choose a
smaller independently generated unit. The selected `data/` is the unit being
retired; sibling logs, results, producer, inputs, baseline scripts, and recovery
evidence remain in place.

## Assessment schema

All paths below are forward-slash project-relative paths except the CLI's
assessment/plan/receipt paths. Every SHA256 is the hash of an existing retained
file. Quotations must be actual nonempty substrings, not summaries. The illustrative
UUID, snippets, and hashes below must be replaced with actual evidence; do not
write these examples into a live project to manufacture eligibility.

```json
{
  "schema": "retired-synthetic-pg-assessment-v1",
  "source": ".runtime/analytics-pg-01234567-89ab-4cde-8fab-0123456789ab/data",
  "data_class": "synthetic-rebuildable-only",
  "review": {
    "reviewer": "Agent and review identifier",
    "synthetic_data_reason": "Explain the actual synthetic input provenance and historical association.",
    "rebuild_recipe": "Explain retained sources, input chain and available matching tool version; no remote service or unique customer input.",
    "unique_value_review": "Explain why data has no unique evidence/input value and where logs/results are retained.",
    "reference_scope_reason": "Explain current project binding review and the privacy-limited automated search gaps."
  },
  "producer": {
    "path": "tests/analytics-isolated.mjs",
    "sha256": "ACTUAL_64_LOWERCASE_HEX_CHARACTERS",
    "claims": {
      "fresh_initdb": "actual source substring containing initdb",
      "unique_generated_directory": "actual source substring containing .runtime, analytics-pg and randomUUID",
      "loopback_only": "actual source substring containing 127.0.0.1",
      "stop_in_finally": "actual source substring containing finally, pg_ctl and stop"
    }
  },
  "inputs": [
    {
      "path": "tests/analytics-postgres.mjs",
      "sha256": "ACTUAL_64_LOWERCASE_HEX_CHARACTERS",
      "kind": "synthetic-generator",
      "synthetic_quote": "actual source/fixture substring supporting synthetic provenance",
      "reason": "Explain why this input generates fictional rows and how historical use is established.",
      "referenced_by": "tests/analytics-isolated.mjs"
    }
  ],
  "completion": {
    "path": ".runtime/analytics-pg-01234567-89ab-4cde-8fab-0123456789ab/commands.log",
    "sha256": "ACTUAL_64_LOWERCASE_HEX_CHARACTERS",
    "stop_quote": "server stopped",
    "terminal_quote": "actual completed/failed test result substring or actual terminal JSON object"
  },
  "historical_references": [],
  "reference_files": []
}
```

Every input must link to a real retained producer/input file that actually
mentions its path/name, and its chain must reach the producer without cycles.
`synthetic-fixture` is the other accepted input kind. This relationship check
does not replace reviewing how the input is used. The completion log must be a
retained sibling of `data/`, or its real content must contain this exact UUID.
`passed=true` is not mandatory: a real terminal test JSON with multiple fields,
a completion/failure result, and actual shutdown evidence are accepted. Failed
run data still needs an explicit unique-value review before retirement.

Existing historical-only references outside the runtime can be declared in
`historical_references` with `{path, sha256, quote, reason}`. They must be real
retained evidence, and their historical role requires agent review. Do not
whitelist a current active configuration by calling it historical evidence.

`reference_files` optionally declares a few specifically reviewed non-sensitive
project configuration files with `{path, sha256, reason}`. Supported config names
start with package/tsconfig/jsconfig/project/runtime/test/pytest/settings/config
and use json/toml/yaml/yml/ini/cfg/conf extensions. Their bodies are inspected,
but a matching runtime reference still blocks retirement. `.env`, credential,
customer, business, backup and recovery names cannot be declared safe this way.

## Privacy-limited references and live activity

The tool discovers project entries using bounded metadata inspection. It reads
bodies only for ordinary, non-sensitive source code and the few exact declared
safe configurations. `.env`, auth/secrets/credential paths, customer documents,
arbitrary JSON/TXT/Markdown files, materials, dependencies, and Codex state are
not body-searched. Other ordinary files are metadata-only; protected/generated
scopes are disclosed as skipped. No database bodies are searched for references.
The required producer, inputs and completion evidence are separately bounded
and hashed. No empty hand-written reference report can replace the live checks.

This is not a claim of whole-project reference absence. The agent must explicitly
review remaining configuration/usage bindings within the user's authorized
scope. If a meaningful binding cannot be resolved safely, do not offer deletion.

Windows uses live CIM process facts and exclusive current-file/ancestor handles.
macOS uses visible `ps`/`lsof`, no-follow directory descriptors, and advisory
`flock`. Activity-query errors, missing tools, inaccessible candidate runtime
command lines, live project processes, or `postmaster.pid` block release. No
process is stopped. An unrelated PG process whose cluster cannot be reliably
attributed can also block this narrow implementation; keep other projects
running and report the attribution limitation, rather than requesting a global
PostgreSQL shutdown.

Windows CIM can retain a row for a just-exited process. A missing runtime command
line is ignored only when a read-only Windows process-lifetime API confirms
that PID has exited/no longer exists. Access denied or a still-running process
remains unknown and blocks release; a missing command line is not treated as idle.

Activity commands use fixed system executable paths and a minimal allowlisted
environment/cwd. Windows obtains its real system directory through the Windows
API, imports system CimCmdlets/Utility manifests explicitly, and disables module
autoload; caller `SystemRoot`, `PSModulePath`, policy/cache and startup variables
cannot substitute project/user modules. macOS receives no caller LD/DYLD/startup
environment. Project code is not used as an activity provider.

macOS advisory locks do not freeze noncooperating writers. Visibility of every
other account is not guaranteed. `--confirm-idle` is therefore mandatory on both
systems and means project writers will remain stopped through the operation.
Two stable snapshots are additional evidence, not an operating-system freeze.
Personal Mac and external-drive validation remain separate from hosted macOS
fixtures, Windows execution and mocked unit tests.

## Commands

Use an absolute installed script path; `-I -B` isolates imports and prevents
bytecode generation. Choose administrative output paths outside the selected
data unit, preferably outside the project to avoid unrelated report changes.

Known sensitive names and default/configured Codex or SQLite state roots
(including metadata-resolved identity aliases) are rejected before reading
assessment/plan bodies or writing outputs. If using an explicitly relocated
`--codex-home`, also pass it to apply so that privacy boundary is known before
the plan is read. State may not hold assessment, plan, receipt or checkpoint
outputs, and sensitive files cannot be supplied as fake administrative input.

```text
python -I -B /ABS/retired_runtime_guard.py plan --project /ABS/project --source .runtime/analytics-pg-UUID/data --assessment /ABS/report/assessment.json --output /ABS/report/plan.json --confirm-idle
python -I -B /ABS/retired_runtime_guard.py apply --plan /ABS/report/plan.json --authorize-plan EXACT_PLAN_SHA256 --receipt /ABS/report/receipt.json --confirm-idle
```

The plan prints its exact SHA256. Existing administrative files are not
overwritten. The default minimum file age is 48 hours, idle interval 2 seconds,
file limit 100000, and total content/evidence read budget 16 GiB. `--max-files`,
`--max-bytes`, `--min-age-hours` (at least 48), `--idle-seconds` (1–60), and
`--codex-home` are available at planning. Plans bind these limits and the
configured project/Codex state boundary. Plan/apply never connect a database,
execute project/test code, modify sources, or terminate processes.

Apply rechecks the assessment and all retained evidence, the exact full file
manifest and hashes, project references, activity, and a further idle snapshot.
Full directory traversals occur at stage boundaries, not once per deleted file.
Each exact file then receives an identity/content guard before unlink; only
known empty directories are removed. Unexpected new contents are never swept up.

At most 32 explicit evidence files plus the assessment are held with read guards
through the complete release. Their hashes are checked on entry and final fd
verification; identity/metadata is rechecked between batches. Windows sharing
guards prevent ordinary writes/replacement of that retained proof during release.
macOS locks remain advisory: noncooperating changes can be detected and reported
as partial/uncertain, but this does not establish an operating-system freeze.

Each source has a stable atomic single-attempt claim under the project's
`.storage-retirement-claims/`. It binds project/source identity, the exact plan
hash, manifest hash, and original receipt. Preserve this folder. Changing the
receipt path or producing another plan does not authorize an automatic retry.
The receipt's `.in-progress/events.jsonl` durably records bounded pending batches
of at most 64 exact files before releasing any of them, appends per-file results,
and flushes completed batches. A crash can leave members of that exact pending
batch uncertain; reconcile them individually. This avoids a physical flush for
each tiny file while preserving a durable list of all possibly attempted files.
After a refusal/interruption, reconcile that exact claim and receipt; do not
delete claims automatically to retry. A pending deletion can be uncertain, and
partially retired PG data is not a valid database or an intact rollback copy.

The receipt distinguishes logical bytes deleted from allocated estimates and
the observed volume-free delta. Other processes, allocation, snapshots and open
handles can affect actual free space. A project occupying 2.83 GiB cannot yield
dozens of GiB; a positively qualified 2.18 GiB historical test workload is a
material candidate even when the ordinary bytecode cleaner yields only KiB.

## Verification scope

The [qualified hosted run](https://github.com/SoberAming/codex-project-storage/actions/runs/43557649569)
binds revision `b75a54ccd85f8cb55561bc84c6db1eba89877f15`. Windows X64 and
macOS ARM64 (`macos26`) each ran Python 3.10.11 and 3.13.17. All four jobs
completed the real isolated plan/apply CLI and the native OS activity queries
against a new fictional PG layout: six files and 29,461,707 logical bytes.
No PostgreSQL server was started or connected, and no project code was executed.
The retained producer, inputs and sibling completion log remained available.

The 40-case retirement suite passed all 40 cases on each Windows job. Each Mac
job passed 37 and skipped only the three Windows-specific PowerShell/CIM/process
lifetime tests. The overall ten-suite counts and exact skip names are recorded
in [compatibility](../docs/COMPATIBILITY.md). A skipped Windows-specific check
does not establish its equivalent on macOS; advisory locking and visibility
limitations above remain in force.

These results qualify the tested hosted fixtures, not personal Macs, external
drives, complete APFS clone/snapshot or business workflows, real PostgreSQL
server operation, or retirement of arbitrary business/state databases. Each
release tag still requires its exact revision to pass the gate; the linked run
does not qualify a later documentation commit. Initial 1.4 CI failure evidence
is [retained](https://github.com/SoberAming/codex-project-storage/actions/runs/43556855654);
the npm builtin-config compatibility fix did not relax retirement rules.

## Retention migration is separate

This mode does not create physical PG archives or claim database restore
validation. If provenance, rebuildability or unique value is uncertain, preserve
the data and propose a separate stopped-directory retention migration with
complete byte/metadata checks and explicit recovery limitations. An exFAT copy
does not automatically preserve NTFS/APFS ACLs, extended attributes or privacy.
Do not use portable export to move sensitive business databases or imply a
cross-version/cross-OS logical database backup.
