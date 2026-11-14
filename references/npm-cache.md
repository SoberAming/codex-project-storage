# Project-exclusive npm cache retirement

This adapter closes a practical gap: a dedicated npm package cache can be much
larger than Python bytecode, yet clearing it is different from deleting an
installation or treating every cache-like folder as disposable.

`scripts/npm_cache_guard.py` is a separate v1.4 adapter. The existing pip adapter
is unchanged. This adapter supports the reviewed **npm 10.9.2** command and native
Node major versions 18, 20, 22, and 24. This is a version admission range, not a
claim that every listed major remains in upstream support. Unsupported versions receive a specific
blocked result. Do not change a version string or use another command to bypass
that result. The selected installed Node/npm must be trusted by the operator;
this tool binds core implementation files and is not software attestation.

Official Node distribution archives may legitimately omit the installed
`npm/npmrc` builtin configuration; an MSI installation may contain it. Only this
one implementation file is optional. The plan records either its exact ordinary
file identity/content or verified absence under the unchanged ordinary npm
installation directory. Absence is checked twice, again after the Node probe,
and immediately before native cache cleaning. A file that appears later, a
replacement, links/reparse points, permission/I/O errors, missing parent or
inspection drift refuses execution. The adapter never creates or repairs an
installed `npmrc`. All other listed implementation files remain mandatory.

## What is eligible

- An explicitly selected npm cache **inside the selected independent project**.
- Its exact `_cacache` subtree has the reviewed content-v2/index-v5 layout.
- Real retained producer/configuration citations identify npm and the explicit
  dedicated cache. A real, existing npm debug log identifies that exact cache
  argument and completed process. The log is not manufactured by the guard.
- A finite, recent agent review establishes that other projects do not use it,
  all cached packages can be fetched again or filled from retained originals,
  and cache writers/consumers are idle. Current ownership cannot be inferred
  merely from a path name or from `safe=true`.
- Every member is an ordinary single-link file or directory, with complete
  bounded inventory. File hashes, content addresses, index record checksums and
  key bucket addresses are checked. Unknown entries, nonempty temporary work,
  links, mixed notes, corrupt/unsupported layouts, or missing evidence block the
  entire operation.
- Additional data streams, resource forks, xattrs and unsupported filesystem
  metadata on the root, directories **or** files also block it. Metadata is
  checked again in the second pass; an ordinary-file-only manifest would miss
  unique payload attached to a directory. Native metadata checks reuse the
  existing reviewed relocation helper. Unknown macOS ACL support is refused.

Keep source, `node_modules`, lockfiles, private offline-only packages, application
data, databases, Codex state, and every required recovery asset. Default/shared
user caches are outside this adapter. npm's `_logs`, `_npx`, and other sibling
data are not part of the deletion scope. Do not clear the entire cache parent.

For a legacy cache, inspect existing scripts and native logs. Do not fabricate
a historical producer receipt, insert a marker, run an install merely to make
old contents appear owned, or claim a new log proves earlier shared contents
were exclusive. If evidence is incomplete, identify the missing ownership or
refetchability fact and report the item as a candidate; it is not executable.

## Agent-owned review, simple user decision

The agent reads the cited source and establishes the semantic relationship.
The executor binds the cited bytes and review to one exact plan; it does **not**
prove arbitrary source code correct or independently discover every possible
outside consumer. A truthful activity/reference review and explicit idle
confirmation remain required.

The user should decide a concrete consequence: “Clear this project's package
download cache; keep the installed dependencies and sources. A later install
may need to download packages again.” The agent supplies the exact estimate,
scope, evidence, missing facts, and result. The user should not have to classify
hash buckets or review npm arguments.

The review is a small JSON file **outside the project**. Required structure:

```json
{
  "schema": "project-npm-cache-assessment-v1",
  "project": "/absolute/path/to/project",
  "cache": ".runtime/npm-cache",
  "ownership": "project-exclusive-refetchable",
  "producer": {
    "path": "scripts/start.ps1",
    "excerpts": ["an exact existing source excerpt naming npm and --cache"],
    "explanation": "Explain the real producer, the dedicated cache path, and why this retained source establishes the relationship."
  },
  "existing_log": ".runtime/npm-cache/_logs/an-existing-debug-0.log",
  "review": {
    "reviewed_at": "timezone-aware current ISO timestamp",
    "reviewed_by": "reviewer identifier",
    "checked_project_roots": ["/absolute/path/to/project"],
    "external_references": "none-found",
    "writers": "none-found",
    "reference_findings": "Describe actual finite reference checks, the roots checked, results, and limits; do not insert a generic success sentence.",
    "refetch_findings": "Explain how these particular packages can be obtained again and identify retained originals or accessible registries; protect unique offline inputs.",
    "activity_checked_at": "timezone-aware current ISO timestamp",
    "activity_findings": "Describe the actual current producer/consumer/process checks, their results and visibility limits; unknown activity must block execution."
  }
}
```

This is a schema illustration, **not qualifying evidence**. Replace every field
with actual findings. Producer/log paths use project-relative forward slashes
on both systems. Absolute paths use the host's actual convention. Evidence is
bounded to 256 KiB per file; do not dump large logs or credentials into the
assessment. Cite a suitable original bounded log rather than silently truncate
or invent history. Reference review expires after seven days; activity review
after thirty minutes. Recheck current activity before execution even within that
window.

Before opening caller-selected assessment/plan bytes, the adapter rejects known
sensitive names and default/configured `CODEX_HOME` or `CODEX_SQLITE_HOME`
locations. This is a metadata-only check, including known physical paths and
directory identity aliases; JSON schema validation happens only afterwards.
Plan outputs and receipts cannot be written into those locations either.
This guard does not inspect private file contents to decide that they are
private. A renamed, copied secret in an otherwise ordinary unknown location is
not automatically recognizable; only select real storage review files.

## CLI contract

Use the host's existing Python launcher (`python` or `python3`) and trusted,
already installed **native** Node plus its installed `bin/npm-cli.js`. Do not
pass `npm.cmd`, `npm.ps1`, a project-local npm, or a shell recipe. If installation
launchers use symlinks, inspect and explicitly select the actual ordinary target
paths; the executor refuses traversal through links/reparse points.

```text
python npm_cache_guard.py plan --project PROJECT --cache RELATIVE_CACHE \
  --assessment REVIEW_JSON --node NATIVE_NODE --npm-cli INSTALLED_NPM_CLI \
  --output NEW_PLAN_JSON

python npm_cache_guard.py apply --plan NEW_PLAN_JSON \
  --authorize-plan EXACT_PLAN_SHA256 --receipt NEW_RECEIPT_JSON --confirm-idle
```

These are argument illustrations, not one universal shell paste. Report paths
must be outside the project and must not exist. Planning does not write the
project/cache and does not run npm, install packages, verify cache contents with
npm, or invoke project hooks; it may run the selected native `node --version`.

## Why this uses npm `--force`

The reviewed official `npm cache clean` command explicitly requires `--force`
for clearing all package cache entries. That flag permits this scoped cache
operation; it is **not** permission to bypass producer locks, identity checks,
missing evidence, or approval. Prohibiting this required argument globally
would leave a known refetchable cache permanently advice-only.

`npm cache verify` also changes the cache: it checks entries and garbage
collects unnecessary data. It is not a read-only diagnosis and requires its own
authorized plan. This adapter does not invoke it.

## Execution and concurrency

1. Recompute the complete qualification and snapshot; compare all policy-bearing
   fields, evidence, selected Node/npm hashes, identities, members and contents
   to the authorized exact plan bytes.
2. Claim the plan once in a stable per-cache location. A different receipt path
   cannot bypass the claim. A cooperative guard lock prevents competing guard
   operations; it does not prove npm is idle.
3. Create a unique same-volume private directory under the cache parent, with
   two distinct empty npm config files. Move only `_cacache` into that directory
   without replacing an existing target. **Moving releases zero bytes.**
4. Recheck complete membership/content and the trusted implementation. NTFS and
   POSIX must preserve the root identity. On Windows exFAT only, a cross-parent
   rename changes the root's directory-entry FileID: record that explicit
   transition and require the same volume, every descendant identity, complete
   membership and every content hash to match. No other identity difference is
   waived.
5. Run one fixed native Node/npm command against the detached cache, in that
   guard-owned directory. No inherited `NODE_OPTIONS`, `NODE_PATH`, npm settings,
   proxies or preload environment reaches it. Separate empty user/global config,
   fixed cache/prefix, offline operation, no update notifier, zero native log
   retention and disabled lifecycle scripts avoid project configuration/hooks.
   Immediately before this step, recompute ownership/activity qualification and
   require the exact original provenance record. Hold the assessment, retained
   producer and original log under simultaneous guarded read handles through
   native return, rechecking their identities and hashes at both boundaries.
   Windows denies shared write/delete on those evidence files; macOS/POSIX
   protection is cooperative and does not stop a writer that ignores locks.
   Detected evidence drift stops the operation or marks the result for review.
6. Confirm the detached `_cacache` no longer exists. Report removed logical
   payload bytes and observed volume-free change separately. Never touch a new
   `_cacache` recreated at the original path. The tiny detached folder/config
   records may remain for review and are not counted as recovered payload.

The native manager performs recursive removal of the admitted detached cache;
this is **not an exact per-file deletion manifest**. Anchored parent directories
and an unpredictable private detached path reduce namespace races, but they do
not freeze all descendant writers. A noncooperating process with an existing
handle can still write; POSIX/macOS advisory locks are not mandatory exclusion.
Unknown activity blocks the operation. Never describe successful lock acquisition
as proof that all producers have stopped.

Timeout terminates only the native child launched by this operation, never a
user's npm process or a process tree. A failed/interrupted result retains its
exact detached location and a single-use claim. It may already be partially
removed. Reconcile the original receipt; do not retry blindly, claim recovery,
or restore over a newly recreated original path. Stage movement itself is not
counted as saved disk space.

The algorithm uses a constant number of full traversals and linear content
reading, not a full-tree rescan per deleted file. Default complete-snapshot
limits are 100,000 members, 8 GiB logical contents and 240 seconds per snapshot.
The report budget is independently bounded. Exceeding a budget retains the
cache and reports a concrete blocker.

## Verification scope

The unit suite uses only explicitly located temporary fixtures. The optional
native integration test uses a new inert local tarball, performs offline native
cache-add to its own new cache, consumes npm's actual debug log as producer
evidence, then performs the authorized native clean. Original tarball, producer
and log must survive. This does not qualify any real user's old cache.

```text
python tests/test_npm_cache_guard.py --work-root SAFE_TEST_ROOT
python tests/test_npm_cache_guard.py --work-root SAFE_TEST_ROOT \
  --integration-node TRUSTED_NATIVE_NODE --integration-npm-cli TRUSTED_NPM_CLI
```

The [qualified hosted run](https://github.com/SoberAming/codex-project-storage/actions/runs/43557649569)
binds revision `b75a54ccd85f8cb55561bc84c6db1eba89877f15`. Its Windows X64 and
macOS ARM64 (`macos26`) jobs each ran Python 3.10.11 and 3.13.17 with native
Node 22.14.0/npm 10.9.2. The 64-case npm suite passed all 64 cases on each
Windows job; each Mac job passed 63 and skipped only the Windows mandatory
sharing-denial test. Native integration was explicitly enabled and completed
on all four jobs, removing two new cache files: 878 logical bytes on Windows
and 894 on macOS. The original package, producer and original log survived;
no real user/shared cache was selected. Logical bytes are separate from observed
free-space changes, which can be negative because other disk activity continues.

The [initial failed run](https://github.com/SoberAming/codex-project-storage/actions/runs/43556855654)
is retained. It exposed an installed-layout difference: official Node archives
can omit the builtin `npm/npmrc`. Only this missing leaf under a stable ordinary
package directory is now recorded as absent; a present file remains fully
hashed. Missing parents, links, permission/I/O errors, appearance and identity
drift still refuse execution. All other bound implementation files remain
mandatory, and the optional state is checked before/after probing and again
before native clean. No installed configuration is created or repaired.

Earlier Windows/exFAT integration remains historical evidence. Other allowed
Node majors are admission ranges, not individually tested native versions.
Hosted results do not qualify personal Macs, external drives, complete APFS
clone/snapshot or business workflows, or mandatory exclusion of writers.
Each release tag still requires a passing gate for its exact revision; the run
above does not qualify a later documentation commit. Other npm versions remain
unsupported rather than silently using the nearest reviewed contract.

## Primary references

- [npm cache documentation](https://docs.npmjs.com/cli/v10/commands/npm-cache)
  describes `_cacache`, refetchable cache behavior, required `--force` for full
  cleaning, and garbage collection performed by `verify`.
- [Reviewed npm 10.9.2 cache implementation](https://raw.githubusercontent.com/npm/cli/v10.9.2/lib/commands/cache.js)
  scopes `clean` to `join(this.npm.cache, '_cacache')` and removes it through the
  native filesystem API. Its normalized command-source SHA256 is checked.
- [npm 10.9.2 configuration loader](https://raw.githubusercontent.com/npm/cli/v10.9.2/workspaces/config/lib/index.js)
  loads the builtin `npmPath/npmrc` through its file loader; a missing builtin
  configuration is a legitimate default rather than a required installed file.
- [cacache content paths](https://raw.githubusercontent.com/npm/cacache/v19.0.1/lib/content/path.js)
  and [index implementation](https://raw.githubusercontent.com/npm/cacache/v19.0.1/lib/entry-index.js)
  define the reviewed content-address and checksummed key-bucket layout.
