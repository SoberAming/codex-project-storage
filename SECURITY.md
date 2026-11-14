# Security policy / 安全报告

This skill can delete or relocate files within an authorized scope. Bugs that cross protected boundaries, mishandle identities or paths, allow untrusted commands, disclose private data, or falsely report successful retention are security-relevant.

## Report privately

Use this repository's **Security → Advisories → Report a vulnerability** entry when private vulnerability reporting is enabled. GitHub's [private reporting documentation](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository) explains the feature.

Private reporting must be enabled by the repository owner. Check the actual Security entry; this policy does not itself establish that the channel is active. If the private entry is unavailable, do not post exploit details, sensitive paths, payloads, or affected private data publicly. You may open a minimal public request asking the maintainer to enable a private reporting channel, without disclosing the vulnerability. Keep the detailed report local until a private channel is available.

Do not send reports to an address found in commits or personal profile data unless the maintainer explicitly designates it for security reporting. No email address, guaranteed response time, bounty, or support service is implied by this policy.

## Include a safe reproduction

Share the affected release or commit, operating system, Python/tool versions, a concise description of impact, and a minimal reproduction using newly created fictional files. Explain what the tool was authorized to do and what boundary was crossed. Include only the relevant, redacted error or receipt fields.

Do not attach Codex sessions or indexes, SQLite files or sidecars, credentials, tokens, customer content, original media, full environment dumps, full command histories, or raw disk scans. Paths and filenames can also contain private information. Replace them with fictional values while preserving the relevant path relationship.

Never reproduce a deletion flaw against real data. Stop using the affected write route, retain the current receipt and checkpoints, and reconcile that exact operation. Do not rerun an uncertain operation, remove checkpoints, disable protections, or force-unlock files to obtain more evidence.

## Scope and maintenance

Report issues against the latest available release and identify older affected versions when known. There is no published long-term-support schedule. Older releases may require an upgrade; fixes and backports depend on maintainer review and capacity.

Maintainers should confirm reports in isolated fixtures, limit any fix to the actual failure mode, and retest successful and refused paths. A fix should describe affected versions, user action, remaining limits, and recovery considerations without disclosing private reporter data. Use a coordinated GitHub advisory where appropriate, and avoid publishing exploit details before a remediation decision.

## Limits that are not claims of safety

Windows test results do not establish macOS or APFS acceptance. POSIX locks are advisory, and other writers or disconnected targets can invalidate assumptions. Ownership and reconstruction assertions must be based on real evidence; filling a JSON field is not proof. The verification record documents the current tested scope and should be consulted before relying on a particular route.
