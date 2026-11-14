# English quickstart

[Overview](../README.en.md) · [Skill instructions](../SKILL.en.md) · [1.6 changes](RELEASE_NOTES_v1.6.0.en.md) · [中文](QUICKSTART.md)

## Requirements and installation

Use Python 3.10+ on Windows or macOS, with an Agent host that can load local skills and run local scripts. Runtime tools use the Python standard library. PyYAML is a development-only dependency. Specialized native cache routes require their own already installed, trusted and supported tool; do not install or upgrade a tool just to clean up.

Choose one directory that your host actually discovers. Current Codex user skills use `~/.agents/skills`; repository skills use `.agents/skills`. See the [official skill-discovery documentation](https://learn.chatgpt.com/docs/build-skills). Existing installations explicitly discovered from a legacy location can stay there. Avoid duplicate installations with the same skill name.

The commands below install the current `main` source into a new directory. A `main` checkout does not establish a released tag or a published ZIP. Check the exact commit's CI before relying on an update. These commands do not overwrite an existing nonempty installation.

Windows PowerShell:

```powershell
$skillParent = Join-Path $env:USERPROFILE '.agents\skills'
$skillTarget = Join-Path $skillParent 'codex-project-storage'
if (Test-Path -LiteralPath $skillTarget) { throw 'An installation already exists. Review and back it up before upgrading.' }
New-Item -ItemType Directory -Path $skillParent -Force | Out-Null
git clone --depth 1 --branch main https://github.com/SoberAming/codex-project-storage.git $skillTarget
```

macOS:

```sh
mkdir -p "$HOME/.agents/skills"
git clone --depth 1 --branch main https://github.com/SoberAming/codex-project-storage.git "$HOME/.agents/skills/codex-project-storage"
```

Alternatively, use a curated ZIP when the selected release actually provides one, verify it against its published `SHA256SUMS`, and place the complete `codex-project-storage` folder in the chosen location. The installed folder must contain `SKILL.md`, `scripts`, `references` and `agents`. Keep `SKILL.en.md` as the English companion; do not install it as a second skill.

For an upgrade, inspect the existing installation and custom changes first, and keep its backup outside the skill-discovery root. No session migration, index changes or history deletion is needed. Other Agent hosts have their own locations and permissions; operating-system CI does not establish end-to-end integration in every host.

## Start with analysis

Open the actual project and ask:

```text
Use codex-project-storage to investigate files left by Agent development in this project. Focus on obsolete task scratch, failed downloads, screenshots and recordings, previews, repeated test environments and caches. Identify the real producer, retained results, current consumers and activity. Recommend one concrete plan with qualified space benefit and consequences. Analyze only first; protect source, useful results, sessions, indexes, databases and recovery data.
```

Codex supports explicit invocation as `$codex-project-storage`. Other hosts may use different entry points. Let the Agent investigate technical facts and manage exact plans; users decide the outcome.

## Large projects and old previews

```text
If the overview reaches its scan or attribution budget, create a persistent inventory outside the project and resume in bounded batches. Prioritize inactive historic builds, including supported .next/dev outputs. Retain shared files individually and continue reviewing independent generated files beside them. Qualify complete units without waiting for the entire project. Report unfinished coverage and give an exact cleanup proposal; do not delete yet.
```

Completed units can produce plans while other units remain pending. The build route can use an explicit present-state review when historic completion logs are missing; it still needs genuine source/build identity, reviewed references, retained current/rollback applications and current runtime checks. It does not apply that exception to databases or arbitrary task outputs.

## Approve a reviewed scope

After a concrete plan exists, an approval can be as simple as:

```text
Execute the exact cleanup plan we just reviewed. Keep all listed protected material. Recheck current conditions before each operation, stop on any changed membership, identity, content, shared relationship or active consumer, and report completed and untouched items. Manage internal hashes and receipts yourself; do not stop applications or broaden the scope.
```

This example is not authorization for unrelated files or new users. The Agent must respect the actual scope approved in the conversation. Do not remove an apply claim or change receipts to force a retry.

## Preserve valuable inactive results elsewhere

```text
I have an external storage location and want to retain useful old results. Inspect the actual volumes, capacity and filesystem capabilities. Recommend which inactive artifacts can move, with disconnection and retrieval consequences. Keep active projects and Agent state in place. Analyze first; I will choose the destination and scope.
```

Migration is optional. Verify the complete copy and its usability before releasing the source. A copy that leaves the original in place has reclaimed zero source space. Compatibility links and changed project references require a separate plan.

## Understand the report

| Reported figure | Meaning |
| --- | --- |
| Current occupancy | Observed size within the stated scan scope, including material that must stay. |
| Review priority / potential | A clue requiring evidence; no disposal qualification yet. |
| Qualified plan benefit | Exact supported files that passed the route's review and current checks. |
| Deleted logical bytes | Content removed by execution, with a receipt. |
| Source-volume free-space change | A measured difference that may also reflect concurrent writes and filesystem behavior. |

With no execution, actual release is zero. A large or old folder is not automatically waste. If qualified benefit falls short, the Agent should explain the gap and propose a bounded next investigation, rather than deleting more to meet a target.

See the [English instructions](../SKILL.en.md) for route selection and safeguards, and the [exact-commit checks](https://github.com/SoberAming/codex-project-storage/actions/workflows/ci.yml) for validation. Windows/macOS fixture tests do not certify every Agent host, external disk, business workflow or APFS sharing/snapshot behavior.
