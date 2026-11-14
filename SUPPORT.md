# Support / 使用帮助

Start with [the Chinese guide](README.md) or [the English guide](README.en.md), then the mode-specific references linked from [SKILL.md](SKILL.md). The [verification record](references/verification.json) states the tested versions, platforms, and limitations.

## Choose a route

| Need | Where to go |
| --- | --- |
| Understand why a project is large | Ask the skill for analysis only; review the largest producers, ownership, and coverage gaps |
| Decide between deleting and moving data | Ask for one recommended outcome with expected benefit, retained data, impact, and retrieval method |
| Unexpected behavior in a supported route | Use the bug-report issue form with a fictional reproduction |
| A new project type or cleanup route | Use the feature-request form; describe producer, ownership, references, retention, and expected impact |
| Usage or compatibility question | Use the usage-question form after reviewing the relevant documentation |
| Possible boundary bypass, data disclosure, or unsafe deletion | Follow [SECURITY.md](SECURITY.md); keep details private |

Open the repository's Issues page and choose the applicable form when templates are available. Community support depends on maintainer and contributor availability. There is no guaranteed response time, remote repair service, or promise that every project can be automatically cleaned.

## What is useful in a public question

Include the skill version, operating system and Python version, the requested operation, the filesystem type if relevant, the exact non-sensitive error, and a small fictional directory layout. State whether the issue occurred during analysis, planning, copying, acceptance, or release. Clearly label expected versus observed behavior.

Do not upload an entire generated report by default. Reports may include personal paths, project names, environment information, and ownership clues. Share only relevant fields after reviewing and redacting them. Do not post sessions, indexes, databases, credentials, tokens, customer content, or private source/assets.

## If an operation stopped

Keep the plan, receipt, and checkpoints locally. Do not automatically repeat the operation, force-unlock files, delete recovery evidence, or loosen a protected boundary. A partially completed or uncertain result needs reconciliation of the exact original scope. Ask for help with a redacted status and a fictional reproduction.

CRC, bad-block, EIO, permission, or device-disconnection errors are not reasons to keep hashing or copying large files. Stop the affected operation and investigate the underlying storage condition. The skill is not a disk-repair or complete-backup product.
