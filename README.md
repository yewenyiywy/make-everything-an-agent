# make-everything-an-agent

> just try to liberate myself

A personal multi-model agent command center: OpenAI for planning, Anthropic Claude for analysis/review, and Meta Muse Code for controlled code execution.

**Status:** MVP foundation. A local dashboard, durable SQLite task queue, model adapters, approvals, retries, and tests are implemented. Job-board discovery, LinkedIn automation, scheduled cloud workers and deployment are **not** wired yet.

## Quick start

Requires Python 3.11+. No third-party packages needed for the core.

```bash
python3 -m unittest discover -s tests -v
python3 agent_company.py init
python3 agent_company.py add --role research --backend mock --prompt "Summarize three AI startup opportunities"
python3 agent_company.py run-once
python3 agent_company.py list
python3 agent_company.py serve
```

Open http://127.0.0.1:8765 for the dashboard. It runs locally only (no authentication); **do not expose this HTTP server to the public Internet**.

## Real model adapters

Use environment variables, never store keys in Git:
```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=...    # model ID available to your account
export ANTHROPIC_API_KEY=...
export ANTHROPIC_MODEL=... # model ID available to your account
```

OpenAI: `--backend openai`. Claude: `--backend claude`. Both use their HTTPS APIs and return text. Model subscriptions and API billing are separate.

Muse Code: install and authenticate Meta Muse Code separately and verify `muse --help` and `muse exec --help`. Use `--backend muse --workspace /absolute/path/to/isolated/git/worktree`. This adapter invokes `muse exec --prompt-file <file>` from that workspace without shell interpolation. **Do not run untrusted code against your main repository.** Commands and options can vary by installed Muse version.

## Example

```bash
python3 agent_company.py add --role planning --backend openai --prompt "Prioritize today's research tasks"
python3 agent_company.py add --role review --backend claude --prompt "Evaluate the plan for reliability"
python3 agent_company.py run-once
python3 agent_company.py list
python3 agent_company.py show 1
python3 agent_company.py approve 1
```

By default tasks end in `review`, not `done`. Only a human can approve. Errors are retried up to 3 attempts with a delay. This MVP uses a single local worker; move to Postgres + a durable remote worker for multi-machine or always-on production use.

## Safety and privacy

- Public repo: **never commit** .env, API tokens, résumés, contact lists, personal application data, SQLite databases, or execution logs.
- Web UI is localhost-only and read-only. All mutations use the local CLI.
- No automated external messaging, job application submission, trade execution, PR merge, or deployment.
- Muse runs in the supplied directory; prepare an isolated worktree/container with restricted credentials and run tests independently.
- `review` means awaiting verification, not verified success.
- Model output is untrusted; do not treat it as authorization to execute tools.
- Set API provider account spend caps separately before using paid backends.

## Components

```text
agent_company.py      CLI, SQLite state machine, adapters, HTTP dashboard
web/index.html         Local read-only dashboard
tests/test_core.py     Queue + approval + mock tests
.github/workflows/ci.yml
.env.example           Non-secret configuration examples
.gitignore             Secrets and artifacts excluded
```

## Next milestones

1. GitHub App / isolated worktrees / PR review workflow
2. Authorized job feed integration and ranking, contact research using permitted data
3. Scheduler + hosted database + worker leases + budgets + metrics
4. Authenticated web dashboard with user approval actions and audit trails
