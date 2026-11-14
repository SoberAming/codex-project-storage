# Contributing / 参与贡献

欢迎提供可复现问题、项目类型线索、文档改进和经过验证的处理路线。中文或英文均可。先阅读[行为规范](CODE_OF_CONDUCT.md)；漏洞或可能导致越界删除的问题走[安全报告](SECURITY.md)，不要直接公开利用细节。

## Start with a concrete case

Describe the user's task, the data producer, the actual project boundary, ownership and references, and what should remain available after optimization. Prefer a small fictional project that reproduces the behavior. Do not submit real sessions, indexes, databases, credentials, customer files, production configuration, or a full disk inventory.

Project-type recognition and executable deletion are different changes. A classifier may explain occupancy without authorizing cleanup. Adding a familiar directory name to a delete list is not an acceptable substitute for proving provenance, scope, retention, and current usage.

## Development setup

Runtime helpers use Python's standard library. Use Python 3.10 or newer; the published verification record identifies the versions that have actually been run. Development checks may have separate dependencies listed in `requirements-dev.txt`.

For the repository checks, install the development dependencies and require the YAML checks:

```text
python -m pip install -r requirements-dev.txt
python -I -B tools/validate_repository.py --repo ABS_REPOSITORY --require-yaml
```

This development setup is separate from running the installed skill. See [the release process](docs/RELEASING.md) for artifact generation and verification.

Work in a local checkout and use a healthy, project-external test directory. Every cleanup test must operate on newly created fictional data. Do not use a real user's project, Codex state, shared cache, or a production volume root as a fixture.

The core regression suites are:

```text
python -I -B tests/test_storage_guard.py --work-root ABS_TEST_PARENT
python -I -B tests/test_storage_modes.py --work-root ABS_TEST_PARENT
python -I -B tests/test_project_profiler.py --work-root ABS_TEST_PARENT
python -I -B tests/test_generated_artifacts.py --work-root ABS_TEST_PARENT
python -I -B tests/test_native_cache.py --work-root ABS_TEST_PARENT
python -I -B tests/test_state_boundaries.py --work-root ABS_TEST_PARENT
python -I -B tests/test_release_tools.py --work-root ABS_TEST_PARENT
```

`ABS_TEST_PARENT` is a placeholder for your explicitly selected, project-external test parent. These commands create isolated fixtures under it. Tests may retain evidence; inspect their output before removing only your own test directories. Use each test's `--help` where applicable. Never change a user's file timestamps to make cleanup qualify.

The optional cross-volume suite requires two explicitly selected fixture parents. Do not run it against existing data. Native-cache regressions use controlled fixtures; do not replace them with a purge of your real default pip cache. A new real integration must define its exact disposable scope first and must not install packages or modify shared environments merely to pass a test.

## Requirements for changes

- Keep analysis, user choice, planning, execution, and acceptance distinct. Respect the existing task scope and authorization.
- Protect source, original inputs, credentials, sessions/indexes/databases, dependencies, delivery/acceptance/baseline records, unique outputs, and recovery material.
- Treat shared and external data separately. An explicit metadata scan does not authorize deletion. A missing reference in one project does not prove global non-use.
- Bind plans to exact paths, identities, content and applicable evidence. Recheck before mutation; stop on drift, I/O errors, locks, disconnection, or uncertain results. Do not introduce silent retries or broaden a partially completed batch.
- Keep file-deletion plans distinct from native-tool range operations. A native `clean` command can run project code or affect other environments; review its actual semantics and version.
- Retain needed reconstruction inputs and genuine production evidence. Do not fabricate cache ownership, audit records, or historical receipts. Do not equate rerunning an AI service with reproducible local reconstruction.
- Report logical sizes, known allocation estimates, and volume-free observations separately. Do not count a plan, a same-volume move, or a source-retaining copy as released space.
- Preserve Windows/macOS differences. A simulated identity, a skipped test, or Windows success must not be described as real Mac, NTFS, or APFS acceptance.
- Keep the runtime instructions concise. Put conditional detail in relevant references, and keep UI metadata consistent with the behavior.

## What to validate

Run the targeted suite for the changed behavior, then the required regression suites. Include meaningful refusal tests as well as successful paths. For deletion or migration changes, verify protected-file hashes or identities, exact affected members, receipt status, and incomplete/uncertain outcomes. Do not write tests that only mirror wording or implementation details.

Test new or changed executable maintenance tools. For a substantial or risky workflow change, use an independent forward-use test with a realistic request and raw fictional artifacts; do not give the evaluator the intended answer or a proposed fix. Preserve failed evidence and clearly distinguish corrected assertions from implementation repairs.

Update applicable documentation and the verification record. Record platform, Python/tool versions, component hashes, skips, simulations, historical evidence, and untested boundaries. Do not overwrite the old record to imply that a broader platform or version was tested.

## Pull requests

Use the [pull-request template in the source repository](https://github.com/SoberAming/codex-project-storage/blob/main/.github/PULL_REQUEST_TEMPLATE.md). Lead with the user-visible problem and resulting behavior. Keep changes focused and explain any effect on protected boundaries or mutation scope. List the tests you ran, failures or skips, and material limitations. If a change modifies only documentation, say so.

Do not include raw local reports, absolute personal paths, screenshots containing private information, fixture downloads, `.git` data, `__pycache__`, or credentials. Review the diff and generated archive before proposing publication.

Contribute only material you have permission to share. Preserve third-party notices and identify any borrowed implementation, asset, or text with its source and license. Design references are not permission to copy code. Contributions are subject to the repository's [LICENSE](LICENSE); this project does not require a separate contributor agreement in these instructions.
