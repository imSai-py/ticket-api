# Agent Instructions

## Repository Navigation

- **Execution Root:** `ticket-api/`. Execute all git commands, test suites, and build scripts inside `ticket-api/`.
- **Production Deployment:** Render deploys exclusively from `master`. Merge changes to `dev` first, then promote through `staging` to `master` for production deployment.

## Operational Standards

- **Pre-commit Gate:** Run `powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1` before every git commit.
- **Network Probes:** Always set explicit timeout flags on shell network calls (e.g., `curl -m 10`) to prevent lingering background tasks.
- **Cloud Egress:** Cloud runtimes (Render Free Tier) block TCP ports 25, 465, and 587. Dispatch outbound email via HTTPS APIs over port 443 (`RESEND_API_KEY`, `BREVO_API_KEY`, or `EMAIL_WEBHOOK_URL`). Use `onboarding@resend.dev` as default sender for unverified domains.
- **Flat-File Storage:** Serialize enum attributes with `.value` (never `Enum.name`). Always sanitize tabular cells via `sanitize_cell()` before writing to CSV.

## Context Pointers

- **Issues & Specs:** See `docs/agents/issue-tracker.md` when managing GitHub Issues or milestones.
- **Triage Labels:** See `docs/agents/triage-labels.md` when labeling tickets.
- **Domain Glossary:** See `docs/agents/domain.md` for domain terminology and ADRs.
