# Architecture

Task lifecycle: queued -> running -> review -> done; failures: running -> retry -> failed.

## Actors
- Chief/planner: OpenAI task interpretation
- Builder: Meta Muse Code in isolated Git worktree
- Reviewer: Anthropic Claude
- Human: grants final approval by CLI

## MVP limits
- Single worker; no external task leasing or distributed scheduling
- Static local read-only dashboard, not a hosted multi-user website
- No automatic job applications, outreach, Git pushes, merges, trades or deployments
- Claude adapter currently uses Messages API, not the Claude Code Agent SDK
- Muse invocation requires an installed CLI; the exact flags should be verified against installed Muse version
- Restart recovery for orphaned `running` tasks is not yet implemented
- Spend and rate limits must be set with API providers; no built-in per-task metering

## Production roadmap
1. Persist jobs in managed Postgres; implement leases, heartbeats, retries, idempotency.
2. Separate untrusted execution into sandboxed containers with restricted secrets and scoped repository tokens.
3. Connect source-approved job search feeds and consent-based outreach.
4. Add authenticated Dashboard, safe review screens, RBAC, immutable logs, spend limits.
5. Use a worker/scheduler platform for reliable cloud execution and failure recovery.
