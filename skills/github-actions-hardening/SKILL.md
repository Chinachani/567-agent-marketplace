---
name: "github-actions-hardening"
description: "专用于 GitHub Actions 工作流（.github/workflows/*.yml）的安全审查与加固。能够深入识别常规代码检查工具与模式匹配所遗漏的威胁模型，防范不可信输入引发的脚本注入、特权触发器执行 Fork 恶意代码、非固定 Action 引用以及 Token 权限过大等风险。\n\n适用于审查、审计、加固现有 CI/CD 工作流或编写安全的新工作流，可精准响应“此工作流是否安全？”、“排查 CI 安全漏洞”、“为什么 pull_request_target 存在风险？”、“锁定 Action 的 SHA 版本”或“收紧 GITHUB_TOKEN 权限”等需求。\n\n核心覆盖范围包括：${{ }} 表达式脚本注入、pull_request_target / workflow_run 提权隐患、第三方 Action 的 SHA 哈希锁定、最小权限原则配置、GITHUB_ENV / GITHUB_OUTPUT 注入、敏感凭据泄露防护、优先采用 OIDC 替代长期凭据，以及公开仓库自托管 Runner 的安全暴露风险防范。"
version: "1.0.0"
license: "MIT"
---
# GitHub Actions Hardening

A focused security reviewer for GitHub Actions workflows. It reasons about the *Actions-specific*
threat model — where trust boundaries live in trigger types, token scopes, and string
interpolation — rather than the application-code vulnerabilities a general security scanner looks
for. Most workflow risks are invisible to language linters because the dangerous code is the YAML
itself and the way GitHub expands `${{ }}` expressions into a shell before your script runs.

## When to Use This Skill

Use this skill when the request involves:

* Reviewing, auditing, or hardening any file under `.github/workflows/`
* Authoring a new workflow and wanting it secure by default
* A workflow that uses `pull_request_target`, `workflow_run`, or `issue_comment` triggers
* Questions about `GITHUB_TOKEN` permissions or the `permissions:` key
* Pinning actions to commit SHAs vs tags vs branches
* Handling untrusted input (issue titles, PR bodies, branch names, commit messages) in `run:` steps
* OIDC / cloud authentication from Actions, or secret handling in CI
* Self-hosted runners on public repositories
* Any request like "is this workflow safe?", "secure my CI", or "review this GitHub Action"

## The Core Insight

In a workflow, **`${{ <expr> }}` is expanded by the runner into the script *before* the shell
executes it.** So a step like:

```yaml
- run: echo "Title: ${{ github.event.issue.title }}"
```

is not passing a variable — it is *pasting attacker-controlled text directly into your shell
command*. An issue titled `"; <attacker-command> #` is concatenated into the script and executed.
This single mechanism is the most common real-world Actions vulnerability, and models routinely
generate it. Treat every
`${{ }}` that contains data an outside contributor can influence as a code-injection sink.

## Execution Workflow

Follow these steps **in order** for every workflow reviewed.

### Step 1 — Map the Triggers and Trust Level

Read every `on:` trigger and classify the workflow's privilege:

* `push`, `pull_request` (from same repo) → runs with the contributor's own trust
* `pull_request` from a **fork** → runs with a **read-only** token, **no secrets** (safe by design)
* `pull_request_target`, `workflow_run`, `issue_comment`, `issues` → run in the context of the
  **base repository** with a **read/write token and full access to secrets**, but can be
  **triggered by outside contributors**. These are the dangerous triggers.

Read `references/triggers-and-privilege.md` for the full trust matrix.

### Step 2 — Hunt for Script Injection

For every `run:` block, every `script:` in `actions/github-script`, and every input to a custom
action, list the `${{ }}` expressions and check whether any resolve to attacker-controllable data.
High-risk contexts include:

* `github.event.issue.title`, `github.event.issue.body`
* `github.event.pull_request.title`, `github.event.pull_request.body`, `.head.ref`, `.head.label`
* `github.event.comment.body`, `github.event.review.body`
* `github.event.pages.*.page_name`, `github.event.commits.*.message`, `github.event.head_commit.*`
* `github.head_ref` and any `github.event.*` field a fork author can set

Read `references/injection.md` for the complete sink list and the safe-pattern fixes.

### Step 3 — Check Privileged Triggers Don't Execute Untrusted Code

If a `pull_request_target` or `workflow_run` workflow checks out PR/fork code
(`ref: ${{ github.event.pull_request.head.sha }}`) **and then runs it** (build, test, install
scripts, `npm install` with lifecycle scripts, etc.), that is remote code execution against a
privileged token. Flag it as CRITICAL. The safe pattern is to split into two workflows: an
unprivileged `pull_request` workflow that runs the untrusted code, and a privileged
`workflow_run` workflow that only consumes its results.

### Step 4 — Audit `permissions:`

* If there is **no** `permissions:` block, the workflow inherits the repository default, which may
  be read/write to everything. Flag it.
* Recommend a top-level `permissions: {}` (deny-all) or `contents: read`, then grant the minimum
  per job (e.g. `pull-requests: write` only on the job that comments).
* Flag any `permissions: write-all` or broad `write` scopes that the steps don't actually need.

Read `references/permissions-and-tokens.md` for the per-scope guidance and OIDC setup.

### Step 5 — Audit Action References (Supply Chain)

For every `uses:`:

* **Third-party actions** (not `actions/*` or `github/*`) MUST be pinned to a full 40-character
  commit SHA, not a tag or branch. Tags and branches are mutable; a compromised upstream action
  can rewrite `v1` to malicious code that runs with your token and secrets.
* First-party `actions/*` are lower risk but SHA-pinning is still the hardened recommendation.
* Flag `@main`, `@master`, or any branch reference as HIGH — that is "latest" and can change under
  you at any time.
* Note the human-readable version in a trailing comment: `uses: foo/bar@<sha> # v2.1.0`.

Read `references/supply-chain.md` for pinning, Dependabot for actions, and artifact/cache risks.

### Step 6 — Check Secret and Output Handling

* No secrets echoed, printed, or written to logs; no `set -x` / `bash -x` in steps that touch
  secrets.
* Secrets must not be passed to steps that run untrusted code or to untrusted third-party actions.
* Untrusted multiline data written to `$GITHUB_ENV` or `$GITHUB_OUTPUT` can inject environment
  variables or step outputs — use the random-delimiter heredoc form and never write raw user input.
* `actions/checkout` leaves a token on disk by default; set `persist-credentials: false` when the
  job later runs untrusted code.

### Step 7 — Produce the Report

Output findings using the format in `references/report-format.md`: a severity summary table first,
then grouped findings with file, the exact offending YAML, the risk in plain English, and a
concrete before/after fix. Never auto-apply changes — present them for review.

## Severity Guide

| Severity | Meaning | Example |
| --- | --- | --- |
| 🔴 CRITICAL | Token/secret theft or RCE reachable by an outside contributor | `pull_request_target` checking out and running fork code; `${{ github.event.* }}` in a `run:` on a privileged trigger |
| 🟠 HIGH | Exploitable supply-chain or scope problem | Third-party action on a mutable tag/branch; `write-all` permissions; injection sink on `issue_comment` |
| 🟡 MEDIUM | Risk under conditions or chaining | Missing `permissions:` block; secret reachable by a non-fork PR author |
| 🔵 LOW | Hardening gap, low direct risk | First-party action not SHA-pinned; `persist-credentials` left default on a non-privileged job |
| ⚪ INFO | Observation, not a vulnerability | Version comment missing next to a pinned SHA |

## Output Rules

* **Always** show a findings summary table (counts by severity) first.
* **Group by issue type**, not by file.
* **Be exact** — quote the offending line and give the line location.
* **Always** pair every CRITICAL/HIGH with a concrete corrected YAML snippet.
* **Never** claim a fork `pull_request` is dangerous just because it runs untrusted code — it has
  no secrets and a read-only token. Reserve CRITICAL for the privileged triggers.
* If the workflow is already hardened, say so and list what was checked.

## Reference Files

Load these as needed:

* `references/triggers-and-privilege.md` — Trust matrix for every trigger, why `pull_request_target`
  and `workflow_run` are privileged, and the two-workflow safe pattern.
  + Search patterns: `pull_request_target`, `workflow_run`, `issue_comment`, `fork`, `secrets`, `read-only token`, `trust boundary`
* `references/injection.md` — Full list of attacker-controllable `${{ }}` contexts and the
  `env:`-variable safe pattern for each sink (`run`, `github-script`, action inputs).
  + Search patterns: `script injection`, `github.event`, `head_ref`, `issue title`, `env`, `intermediate variable`, `actions/github-script`
* `references/permissions-and-tokens.md` — `GITHUB_TOKEN` scopes, least-privilege `permissions:`
  recipes per job type, and OIDC for cloud auth instead of long-lived secrets.
  + Search patterns: `permissions`, `GITHUB_TOKEN`, `write-all`, `contents: read`, `id-token`, `OIDC`, `least privilege`
* `references/supply-chain.md` — SHA-pinning third-party actions, Dependabot for `github-actions`,
  artifact and cache poisoning across `workflow_run`, and self-hosted runner exposure.
  + Search patterns: `SHA pin`, `uses`, `mutable tag`, `Dependabot`, `download-artifact`, `cache`, `self-hosted runner`
* `references/report-format.md` — Output template: summary table, finding cards, and before/after
  remediation blocks.
  + Search patterns: `report`, `format`, `finding`, `summary`, `remediation`, `before`, `after`

