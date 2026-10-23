# Agent Instructions

## Repository Navigation

- **Execution Root:** `ticket-api/`. Execute all git commands, test suites, and build scripts inside `ticket-api/`.
- **Production Deployment:** Render deploys exclusively from `master`. Merge changes to `dev` first, then promote through `staging` to `master` for production deployment.

## Operational Standards

- **Pre-commit Gate:** Run `powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1` before every git commit.
- **Network Probes:** Always set explicit timeout flags on shell network calls (e.g., `curl -m 10`) to prevent lingering background tasks.
- **Cloud Egress:** Cloud runtimes (Render Free Tier) block TCP ports 25, 465, and 587. Dispatch outbound email via HTTPS APIs over port 443 (`RESEND_API_KEY`, `BREVO_API_KEY`, or `EMAIL_WEBHOOK_URL`). Use `onboarding@resend.dev` as default sender for unverified domains.
- **Flat-File Storage:** Serialize enum attributes with `.value` (never `Enum.name`). Always sanitize tabular cells via `sanitize_cell()` before writing to CSV.
- **PowerShell Multi-line Commands:** On Windows PowerShell, avoid passing raw multi-line strings with quotes and ampersands directly into CLI flags (e.g., `gh pr create --body "..."`). Write the body to a scratch file and pass `--body-file <path>`.
- **Git Branch Pruning:** Run `git fetch --prune origin` before batch remote branch deletions to synchronize tracking refs and prevent `remote ref does not exist` errors.
- **Actionable Links:** All notification links and action buttons must resolve through `get_base_url()` in `app/escalation.py` to prevent hardcoded localhost fallbacks in production.

## Context Pointers

- **Issues & Specs:** See `docs/agents/issue-tracker.md` when managing GitHub Issues or milestones.
- **Triage Labels:** See `docs/agents/triage-labels.md` when labeling tickets.
- **Domain Glossary:** See `docs/agents/domain.md` for domain terminology and ADRs.
